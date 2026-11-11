import { KeyValuePipe } from '@angular/common';
import {
  AfterViewInit,
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  DestroyRef,
  OnDestroy,
  inject,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FontAwesomeModule } from '@fortawesome/angular-fontawesome';
import {
  faClock,
  faDownload,
  faExternalLinkAlt,
  faTrashAlt,
} from '@fortawesome/free-solid-svg-icons';
import { NgbTooltip } from '@ng-bootstrap/ng-bootstrap';
import { merge } from 'rxjs';
import { actionError } from '../action-result';
import { catalogTypes, formatLabel, typeIcon } from '../catalog-labels';
import { Download } from '../interfaces';
import { EtaPipe, SpeedPipe } from '../pipes';
import { DownloadsService } from '../services/downloads.service';
import { ToastService } from '../services/toast.service';
import { SelectAllCheckboxComponent } from './master-checkbox.component';
import { ItemCheckboxComponent } from './slave-checkbox.component';

/** The Downloading section: queued, pending, scheduled and running downloads. */
@Component({
  selector: 'app-downloading-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    KeyValuePipe,
    FontAwesomeModule,
    NgbTooltip,
    EtaPipe,
    SpeedPipe,
    SelectAllCheckboxComponent,
    ItemCheckboxComponent,
  ],
  templateUrl: './downloading-section.component.html',
  styleUrl: './downloading-section.component.sass',
})
export class DownloadingSectionComponent implements AfterViewInit, OnDestroy {
  readonly downloads = inject(DownloadsService);
  private toasts = inject(ToastService);
  private cdr = inject(ChangeDetectorRef);
  private destroyRef = inject(DestroyRef);

  selectedCount = 0;
  readonly masterCheckbox = viewChild<SelectAllCheckboxComponent>('queueMasterCheckboxRef');
  private viewReady = false;
  private liveCountdownTimer?: ReturnType<typeof setInterval>;

  readonly faClock = faClock;
  readonly faDownload = faDownload;
  readonly faExternalLinkAlt = faExternalLinkAlt;
  readonly faTrashAlt = faTrashAlt;

  constructor() {
    this.downloads.queueChanged.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      // The box exists before its inputs are set; the first render reads the
      // list itself.
      if (this.viewReady) this.masterCheckbox()?.selectionChanged();
    });
    merge(this.downloads.queueChanged, this.downloads.updated, this.downloads.formatsChanged)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.syncLiveCountdownTimer();
        this.cdr.markForCheck();
      });
    this.syncLiveCountdownTimer();
  }

  ngAfterViewInit() {
    this.viewReady = true;
  }

  ngOnDestroy() {
    if (this.liveCountdownTimer) {
      clearInterval(this.liveCountdownTimer);
    }
  }

  // keyvalue comparator that preserves insertion order (Angular's keyvalue
  // pipe sorts by key by default): https://github.com/angular/angular/issues/31420
  asIsOrder() {
    return 0;
  }

  formatLabel(download: Download): string {
    return formatLabel(download, catalogTypes(this.downloads.formats));
  }

  selectionChanged(checked: number) {
    this.selectedCount = checked;
  }

  downloadItemByKey(id: string) {
    this.downloads.startById([id]).subscribe((res) => this.report(res, 'Start download failed'));
  }

  startSelectedDownloads() {
    this.downloads
      .startByFilter('queue', (dl) => !!dl.checked)
      .subscribe((res) => this.report(res, 'Start download failed'));
  }

  delDownload(id: string) {
    this.cancel([id]);
  }

  delSelectedDownloads() {
    const ids: string[] = [];
    this.downloads.queue.forEach((dl, key) => {
      if (dl.checked) ids.push(key);
    });
    this.cancel(ids);
  }

  // Removing a queued download cancels it; there is no file to ask about.
  private cancel(ids: string[]) {
    this.downloads.delById('queue', ids).subscribe((res) => this.report(res, 'Delete failed'));
    this.cdr.markForCheck();
  }

  // 'preparing' (yt-dlp starting up) and 'postprocessing' (ffmpeg merging,
  // re-encoding or splitting once the bytes have landed) both have real work in
  // flight with no percentage to report, so the bar runs animated at full width
  // instead of showing a number that cannot move.
  isIndeterminate(download: Download): boolean {
    return download.status === 'preparing' || download.status === 'postprocessing';
  }

  readonly typeIcon = typeIcon;

  // How far along the thumbnail's bottom edge the bar runs, or null for none
  // (not started yet). Work with no percentage runs a moving bar instead.
  progress(download: Download): number | null {
    if (this.isIndeterminate(download)) return 100;
    if (['downloading', 'compressing', 'resuming'].includes(download.status)) {
      return Math.max(0, Math.min(100, download.percent ?? 0));
    }
    return null;
  }

  stateText(download: Download): string {
    const percent = `${Math.round(download.percent ?? 0)}%`;
    switch (download.status) {
      case 'queued': return 'Queued';
      case 'pending': return 'Not started';
      case 'preparing': return 'Starting';
      case 'downloading': return percent;
      case 'postprocessing': return 'Finishing';
      case 'compressing': return `Compressing ${percent}`;
      case 'resuming': return 'Reconnecting';
      default: return download.status;
    }
  }

  liveCountdownSeconds(download: Download): number | null {
    const ts = download.live_release_timestamp;
    if (ts == null || download.status !== 'scheduled') {
      return null;
    }
    return Math.max(0, ts - Date.now() / 1000);
  }

  private syncLiveCountdownTimer() {
    const hasScheduled = Array.from(this.downloads.queue.values()).some(
      (download) => download.status === 'scheduled',
    );
    if (hasScheduled && !this.liveCountdownTimer) {
      this.liveCountdownTimer = setInterval(() => this.cdr.markForCheck(), 1000);
    } else if (!hasScheduled && this.liveCountdownTimer) {
      clearInterval(this.liveCountdownTimer);
      this.liveCountdownTimer = undefined;
    }
  }

  private report(res: unknown, fallbackMsg: string) {
    const error = actionError(res);
    if (error) {
      this.toasts.error(error || fallbackMsg);
    }
    this.cdr.markForCheck();
  }
}
