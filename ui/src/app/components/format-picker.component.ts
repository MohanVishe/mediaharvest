import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  DestroyRef,
  OnInit,
  inject,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NgbActiveModal } from '@ng-bootstrap/ng-bootstrap';
import { DownloadsService, ProbeFormat, ProbePayload } from '../services/downloads.service';
import { FormatCatalog, FormatOption, Option } from '../interfaces';

/** What the picker closes with: the streams picked plus how to save them. */
export interface FormatPickerResult {
  downloadType: 'video' | 'audio';
  // yt-dlp format ids: "137+251" for a video stream with an audio stream.
  formatId: string;
  // Catalog ids: the container (video) or the conversion (audio).
  format: string;
  quality: string;
  audioTags?: string;
  lyrics?: boolean;
  videoSubtitles?: string;
}

const VIDEO_CODECS: Record<string, string> = {
  avc1: 'H.264', avc3: 'H.264', h264: 'H.264',
  hev1: 'H.265', hvc1: 'H.265', hevc: 'H.265', h265: 'H.265',
  vp09: 'VP9', vp9: 'VP9', vp8: 'VP8',
  av01: 'AV1', av1: 'AV1',
};
const AUDIO_CODECS: Record<string, string> = {
  opus: 'Opus', mp4a: 'AAC', aac: 'AAC', mp3: 'MP3', vorbis: 'Vorbis',
  'ac-3': 'AC-3', 'ec-3': 'E-AC-3', flac: 'FLAC',
};

/** Lexicographic comparison of two rank tuples (higher is better). */
function compareRanks(a: number[], b: number[]): number {
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const diff = (a[i] ?? 0) - (b[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

/**
 * Modal that probes one video and lists every stream the site offers, so the
 * exact resolution, codec and audio track can be picked, with sizes. The
 * opener sets the public fields on the component instance before the first
 * change detection, as for PlaylistBrowserComponent.
 */
@Component({
  selector: 'app-format-picker',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule],
  styles: [`
    .fp-thumb { width: 7.5rem; aspect-ratio: 16 / 9; object-fit: cover; border-radius: .375rem; }
    .fp-table tbody tr { cursor: pointer; }
    .fp-table td, .fp-table th { white-space: nowrap; }
    .fp-total { font-variant-numeric: tabular-nums; }
  `],
  template: `
    <div class="modal-header">
      <h5 class="modal-title">Choose format</h5>
      <button type="button" class="btn-close" aria-label="Close" (click)="activeModal.dismiss()"></button>
    </div>
    <div class="modal-body">
      @if (loading) {
        <div class="d-flex align-items-center gap-2">
          <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
          <span>Reading the available formats…</span>
        </div>
      } @else if (errorMsg) {
        <div class="alert alert-danger mb-0" role="alert">{{ errorMsg }}</div>
      } @else {
        <div class="d-flex gap-3 mb-3 align-items-start">
          @if (thumbnail) {
            <img class="fp-thumb flex-shrink-0" [src]="thumbnail" alt="" referrerpolicy="no-referrer" />
          }
          <div class="min-w-0">
            <div class="fw-semibold text-break">{{ title }}</div>
            <div class="text-body-secondary small">
              {{ uploader }}@if (uploader && duration) { · }{{ formatDuration(duration) }}
              @if (isLive) { <span class="badge bg-danger ms-1">Live</span> }
            </div>
          </div>
        </div>

        <ul class="nav nav-tabs mb-3" role="tablist">
          <li class="nav-item" role="presentation">
            <button type="button" class="nav-link" role="tab" [class.active]="tab === 'video'"
              [disabled]="videos.length === 0" (click)="setTab('video')">
              Video ({{ videos.length }})
            </button>
          </li>
          <li class="nav-item" role="presentation">
            <button type="button" class="nav-link" role="tab" [class.active]="tab === 'audio'"
              [disabled]="audios.length === 0" (click)="setTab('audio')">
              Audio only ({{ audios.length }})
            </button>
          </li>
        </ul>

        @if (tab === 'video') {
          <div class="table-responsive">
            <table class="table table-sm table-hover align-middle fp-table mb-2">
              <thead>
                <tr>
                  <th scope="col" style="width: 1rem;"></th>
                  <th scope="col">Quality</th>
                  <th scope="col">Codec</th>
                  <th scope="col">Type</th>
                  <th scope="col" class="text-end">Bitrate</th>
                  <th scope="col" class="text-end">Size with audio</th>
                </tr>
              </thead>
              <tbody>
                @for (f of videos; track f.format_id) {
                  <tr (click)="selectVideo(f)" [class.table-active]="f.format_id === videoId">
                    <td>
                      <input class="form-check-input" type="radio" name="fpVideo"
                        [id]="'fp-v-' + f.format_id" [checked]="f.format_id === videoId"
                        (change)="selectVideo(f)" [attr.aria-label]="resolution(f)" />
                    </td>
                    <td>
                      {{ resolution(f) }}
                      @if (f.dynamic_range && f.dynamic_range !== 'SDR') {
                        <span class="badge text-bg-warning ms-1">{{ f.dynamic_range }}</span>
                      }
                      @if (f.format_id === bestVideoId) {
                        <span class="badge text-bg-primary ms-1">Best</span>
                      }
                      @if (smallestIds.has(f.format_id)) {
                        <span class="badge text-bg-success ms-1">Smallest</span>
                      }
                    </td>
                    <td>{{ videoCodec(f) }}@if (f.kind === 'muxed') { + {{ audioCodec(f) }} }</td>
                    <td>{{ f.ext }}@if (f.kind === 'muxed') { <span class="text-body-secondary"> (has audio)</span> }</td>
                    <td class="text-end">{{ kbps(f.vbr || f.tbr) }}</td>
                    <td class="text-end fp-total">{{ sizeText(videoTotal(f), f.size_kind) }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
          <div class="row g-2">
            <div class="col-md-7">
              <div class="input-group">
                <span class="input-group-text">Audio track</span>
                <select class="form-select" name="fpVideoAudio" [ngModel]="audioId"
                  (ngModelChange)="selectAudioId($event)" [disabled]="selectedVideo?.kind === 'muxed'">
                  @for (a of audios; track a.format_id) {
                    <option [ngValue]="a.format_id">{{ audioLabel(a) }}</option>
                  }
                </select>
              </div>
            </div>
            <div class="col-md-5">
              <div class="input-group">
                <span class="input-group-text">Save as</span>
                <select class="form-select" name="fpContainer" [(ngModel)]="container">
                  @for (c of containers; track c.id) {
                    <option [ngValue]="c.id">{{ c.text }}</option>
                  }
                </select>
              </div>
            </div>
            <p class="col-12 small text-body-secondary mb-0">
              Best is what yt-dlp picks: highest resolution, then the most efficient codec
              (AV1 &gt; VP9 &gt; H.264). For old TVs and phones, pick H.264.
            </p>
            @if (subtitleOptions.length) {
              <div class="col-md-7">
                <div class="input-group">
                  <span class="input-group-text">Subtitles</span>
                  <select class="form-select" name="fpSubtitles" [(ngModel)]="videoSubtitles">
                    @for (s of subtitleOptions; track s.id) {
                      <option [ngValue]="s.id">{{ s.text }}</option>
                    }
                  </select>
                </div>
              </div>
            }
          </div>
        } @else {
          <div class="table-responsive">
            <table class="table table-sm table-hover align-middle fp-table mb-2">
              <thead>
                <tr>
                  <th scope="col" style="width: 1rem;"></th>
                  <th scope="col">Codec</th>
                  <th scope="col" class="text-end">Bitrate</th>
                  <th scope="col">Language</th>
                  <th scope="col">Note</th>
                  <th scope="col" class="text-end">Size</th>
                </tr>
              </thead>
              <tbody>
                @for (a of audios; track a.format_id) {
                  <tr (click)="selectAudio(a)" [class.table-active]="a.format_id === audioId">
                    <td>
                      <input class="form-check-input" type="radio" name="fpAudio"
                        [id]="'fp-a-' + a.format_id" [checked]="a.format_id === audioId"
                        (change)="selectAudio(a)" [attr.aria-label]="audioLabel(a)" />
                    </td>
                    <td>
                      {{ audioCodec(a) }} <span class="text-body-secondary">({{ a.ext }})</span>
                      @if (a.format_id === bestAudioId) {
                        <span class="badge text-bg-primary ms-1">Best</span>
                      }
                    </td>
                    <td class="text-end">{{ kbps(a.abr || a.tbr) }}</td>
                    <td>{{ a.language }}</td>
                    <td class="text-body-secondary small">{{ a.note }}</td>
                    <td class="text-end fp-total">{{ sizeText(a.size, a.size_kind) }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
          <div class="row g-2">
            <div class="col-md-6">
              <div class="input-group">
                <span class="input-group-text">Save as</span>
                <select class="form-select" name="fpAudioFormat" [ngModel]="audioFormat"
                  (ngModelChange)="setAudioFormat($event)">
                  @for (o of audioFormats; track o.id) {
                    <option [ngValue]="o.id">{{ o.text }}</option>
                  }
                </select>
              </div>
            </div>
            <div class="col-md-6">
              <div class="input-group">
                <span class="input-group-text">Bitrate</span>
                <select class="form-select" name="fpAudioQuality" [(ngModel)]="audioQuality"
                  [disabled]="audioQualities.length <= 1">
                  @for (q of audioQualities; track q.id) {
                    <option [ngValue]="q.id">{{ q.text }}</option>
                  }
                </select>
              </div>
            </div>
            <div class="col-md-6">
              <div class="input-group">
                <span class="input-group-text">Tags</span>
                <select class="form-select" name="fpAudioTags" [(ngModel)]="audioTags"
                  [disabled]="!tagsSupported()">
                  @for (t of audioTagsOptions; track t.id) {
                    <option [ngValue]="t.id">{{ t.text }}</option>
                  }
                </select>
              </div>
            </div>
            <div class="col-md-6 d-flex align-items-center">
              <div class="form-check form-switch mb-0">
                <input class="form-check-input" type="checkbox" role="switch" id="fp-lyrics"
                  name="fpLyrics" [(ngModel)]="lyrics" [disabled]="!tagsSupported()" />
                <label class="form-check-label" for="fp-lyrics">Add lyrics (LRCLIB)</label>
              </div>
            </div>
          </div>
          <p class="small text-body-secondary mt-2 mb-0">{{ audioAdvice() }}</p>
        }
      }
    </div>
    <div class="modal-footer justify-content-between">
      <span class="text-body-secondary fp-total">
        @if (!loading && !errorMsg) { Estimated file: <strong>{{ estimateText() }}</strong> }
      </span>
      <div class="d-flex gap-2">
        <button type="button" class="btn btn-outline-secondary" (click)="activeModal.dismiss()">Cancel</button>
        <button type="button" class="btn btn-primary" [disabled]="!canDownload()" (click)="download()">
          Download
        </button>
      </div>
    </div>
  `,
})
export class FormatPickerComponent implements OnInit {
  readonly activeModal = inject(NgbActiveModal);
  private downloads = inject(DownloadsService);
  private cdr = inject(ChangeDetectorRef);
  private destroyRef = inject(DestroyRef);

  // Set by the opener through NgbModalRef.componentInstance.
  payload!: ProbePayload;
  catalog: FormatCatalog | null = null;
  initialTab: 'video' | 'audio' = 'video';
  audioTags = 'with_cover';
  lyrics = false;
  container = 'any';
  videoSubtitles = 'en';
  subtitleOptions: Option[] = [];

  loading = true;
  errorMsg = '';
  title = '';
  uploader = '';
  thumbnail = '';
  duration: number | null = null;
  isLive = false;
  tab: 'video' | 'audio' = 'video';

  videos: ProbeFormat[] = [];
  audios: ProbeFormat[] = [];
  videoId = '';
  audioId = '';
  bestVideoId = '';
  bestAudioId = '';
  smallestIds = new Set<string>();

  containers: Option[] = [];
  audioFormats: FormatOption[] = [];
  audioFormat = 'auto';
  audioQualities: Option[] = [];
  audioQuality = 'best';
  audioTagsOptions: Option[] = [];

  ngOnInit(): void {
    this.readCatalog();
    this.downloads
      .probe(this.payload)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((result) => {
        this.loading = false;
        if (result.status === 'error') {
          this.errorMsg = result.msg || 'Could not read the formats';
        } else {
          this.title = result.title ?? '';
          this.uploader = result.uploader ?? '';
          this.thumbnail = result.thumbnail ?? '';
          this.duration = result.duration ?? null;
          this.isLive = !!result.is_live;
          this.load(result.formats ?? []);
        }
        this.cdr.markForCheck();
      });
  }

  private readCatalog(): void {
    const types = this.catalog?.download_type.options ?? [];
    const video = types.find((t) => t.id === 'video');
    const audio = types.find((t) => t.id === 'audio');
    // The iOS profile is a selector, not a container: it does not apply to
    // streams picked by hand.
    this.containers = (video?.format.options ?? []).filter((o) => o.id !== 'ios');
    if (!this.containers.some((c) => c.id === this.container)) {
      this.container = this.containers[0]?.id ?? 'any';
    }
    this.subtitleOptions = video?.subtitles?.options ?? [];
    if (this.subtitleOptions.length && !this.subtitleOptions.some((s) => s.id === this.videoSubtitles)) {
      this.videoSubtitles = video?.subtitles?.default ?? 'none';
    }
    this.audioFormats = audio?.format.options ?? [];
    this.audioTagsOptions = audio?.audio_tags?.options ?? [];
    this.setAudioFormat(audio?.format.default ?? 'auto');
  }

  private load(formats: ProbeFormat[]): void {
    const height = (f: ProbeFormat) => f.height ?? 0;
    const size = (f: ProbeFormat) => f.size ?? Number.MAX_VALUE;
    this.videos = formats
      .filter((f) => f.kind !== 'audio')
      .sort((a, b) => height(b) - height(a) || (b.fps ?? 0) - (a.fps ?? 0) || size(a) - size(b));
    this.audios = formats
      .filter((f) => f.kind === 'audio')
      .sort((a, b) => compareRanks(this.audioRank(b), this.audioRank(a)));

    // Best video, as yt-dlp ranks it: resolution, frame rate, HDR, then the
    // more efficient codec (AV1 > VP9 > H.265 > H.264), then bitrate.
    // Smallest: the lightest stream at each resolution.
    const best = [...this.videos].sort(
      (a, b) => compareRanks(this.videoRank(b), this.videoRank(a)),
    )[0];
    this.bestVideoId = best?.format_id ?? '';
    const smallest = new Map<number, ProbeFormat>();
    for (const f of this.videos) {
      if (f.size === null) continue;
      const current = smallest.get(height(f));
      if (!current || (current.size ?? Infinity) > f.size) smallest.set(height(f), f);
    }
    this.smallestIds = new Set(
      [...smallest.values()].filter((f) => f.format_id !== this.bestVideoId).map((f) => f.format_id),
    );
    this.bestAudioId = this.audios[0]?.format_id ?? '';
    this.videoId = this.bestVideoId;
    this.audioId = this.bestAudioId;
    this.tab = this.initialTab;
    if (this.tab === 'video' && this.videos.length === 0) this.tab = 'audio';
    if (this.tab === 'audio' && this.audios.length === 0) this.tab = 'video';
  }

  // As yt-dlp ranks audio: known streams first, full dynamic range before
  // YouTube's "DRC" tracks (compressed peaks, not better), the original
  // language before dubs, then codec (Opus > AAC > others), then bitrate.
  private audioRank(f: ProbeFormat): number[] {
    const note = f.note.toLowerCase();
    const bitrate = f.abr ?? f.tbr ?? 0;
    const drc = f.format_id.endsWith('-drc') || note.includes('drc');
    const original = note.includes('original') || note.includes('default');
    const codec = { opus: 3, mp4a: 2, aac: 2 }[f.acodec.toLowerCase()] ?? (f.acodec ? 1 : 0);
    return [bitrate > 0 ? 1 : 0, drc ? 0 : 1, original ? 1 : 0, codec, bitrate];
  }

  private videoRank(f: ProbeFormat): number[] {
    const codec: Record<string, number> = { av01: 4, vp09: 3, vp9: 3, hev1: 2, hvc1: 2, avc1: 1 };
    const hdr = f.dynamic_range && f.dynamic_range !== 'SDR' ? 1 : 0;
    return [f.height ?? 0, f.fps ?? 0, hdr, codec[f.vcodec.toLowerCase()] ?? 0, f.vbr ?? f.tbr ?? 0];
  }

  get selectedVideo(): ProbeFormat | undefined {
    return this.videos.find((f) => f.format_id === this.videoId);
  }

  get selectedAudio(): ProbeFormat | undefined {
    return this.audios.find((f) => f.format_id === this.audioId);
  }

  setTab(tab: 'video' | 'audio'): void {
    this.tab = tab;
    this.cdr.markForCheck();
  }

  selectVideo(f: ProbeFormat): void {
    this.videoId = f.format_id;
    this.cdr.markForCheck();
  }

  selectAudio(f: ProbeFormat): void {
    this.audioId = f.format_id;
    this.cdr.markForCheck();
  }

  selectAudioId(id: string): void {
    this.audioId = id;
    this.cdr.markForCheck();
  }

  setAudioFormat(id: string): void {
    this.audioFormat = id;
    const fmt = this.audioFormats.find((o) => o.id === id);
    this.audioQualities = fmt?.quality?.options ?? [{ id: 'best', text: 'Best' }];
    if (!this.audioQualities.some((q) => q.id === this.audioQuality)) {
      this.audioQuality = fmt?.quality?.default ?? 'best';
    }
    this.cdr.markForCheck();
  }

  tagsSupported(): boolean {
    return this.audioFormats.find((o) => o.id === this.audioFormat)?.tags !== false;
  }

  canDownload(): boolean {
    if (this.loading || this.errorMsg) return false;
    return this.tab === 'video' ? !!this.selectedVideo : !!this.selectedAudio;
  }

  videoTotal(f: ProbeFormat): number | null {
    if (f.size === null) return null;
    if (f.kind === 'muxed') return f.size;
    const audio = this.selectedAudio;
    return audio?.size != null ? f.size + audio.size : f.size;
  }

  /** Expected size of the saved audio file for the chosen conversion. */
  audioOutputBytes(): number | null {
    const source = this.selectedAudio;
    const seconds = this.duration;
    if (!source) return null;
    const sourceKbps = source.abr ?? source.tbr ?? null;
    const atKbps = (k: number) => (seconds ? k * seconds * 125 : null);
    switch (this.audioFormat) {
      case 'auto':
        return source.size;
      case 'wav':
        return atKbps(1411);
      case 'flac':
        return atKbps(900);
    }
    const target = /^\d+$/.test(this.audioQuality) ? Number(this.audioQuality) : null;
    if (target === null) {
      // "Best": copied when the codec matches, otherwise high-quality VBR.
      const sameCodec = (this.audioFormat === 'opus' && source.acodec === 'opus')
        || (this.audioFormat === 'm4a' && source.acodec === 'mp4a');
      return sameCodec ? source.size : atKbps(this.audioFormat === 'mp3' ? 245 : 192);
    }
    if (sourceKbps !== null && this.audioFormat !== 'mp3' && sourceKbps <= target * 1.05) {
      return source.size; // already at or below the target: kept as is
    }
    return atKbps(target);
  }

  estimateText(): string {
    if (this.tab === 'video') {
      const v = this.selectedVideo;
      return v ? this.sizeText(this.videoTotal(v), v.size_kind) : '—';
    }
    return this.sizeText(this.audioOutputBytes(), 'estimate');
  }

  audioAdvice(): string {
    switch (this.audioFormat) {
      case 'auto':
        return 'Best quality and smallest file: the stream is saved exactly as the site serves it.';
      case 'flac':
      case 'wav':
        return 'Lossless containers: much bigger files, but no better than the original, which is already compressed.';
      case 'mp3':
        return 'Re-encoded for old players. 192 kbps sounds like the original for most people.';
      default:
        return 'Lower bitrates make smaller files. Opus at 96 kbps is hard to tell from the original; 64 kbps suits speech.';
    }
  }

  download(): void {
    if (this.tab === 'video') {
      const video = this.selectedVideo;
      if (!video) return;
      const audio = this.selectedAudio;
      const formatId = video.kind === 'muxed' || !audio
        ? video.format_id
        : `${video.format_id}+${audio.format_id}`;
      this.activeModal.close({
        downloadType: 'video',
        formatId,
        format: this.container,
        quality: 'best',
        videoSubtitles: this.subtitleOptions.length ? this.videoSubtitles : undefined,
      } satisfies FormatPickerResult);
      return;
    }
    const audio = this.selectedAudio;
    if (!audio) return;
    this.activeModal.close({
      downloadType: 'audio',
      formatId: audio.format_id,
      format: this.audioFormat,
      quality: this.audioQuality,
      audioTags: this.tagsSupported() ? this.audioTags : 'none',
      lyrics: this.tagsSupported() && this.lyrics,
    } satisfies FormatPickerResult);
  }

  resolution(f: ProbeFormat): string {
    if (!f.height) return f.note || f.format_id;
    const fps = f.fps && f.fps > 30 ? String(Math.round(f.fps)) : '';
    return `${f.height}p${fps}`;
  }

  videoCodec(f: ProbeFormat): string {
    return VIDEO_CODECS[f.vcodec.toLowerCase()] ?? (f.vcodec || '?');
  }

  audioCodec(f: ProbeFormat): string {
    return AUDIO_CODECS[f.acodec.toLowerCase()] ?? (f.acodec || 'Unknown');
  }

  audioLabel(a: ProbeFormat): string {
    const parts = [this.audioCodec(a), this.kbps(a.abr || a.tbr)];
    if (a.language) parts.push(a.language);
    if (a.note) parts.push(a.note);
    return parts.filter(Boolean).join(' · ');
  }

  kbps(value: number | null): string {
    return value ? `${Math.round(value)} kbps` : '';
  }

  sizeText(bytes: number | null, kind: ProbeFormat['size_kind']): string {
    if (bytes === null || bytes === undefined || !Number.isFinite(bytes)) return 'unknown';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let value = bytes;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024;
      unit++;
    }
    const text = `${value >= 100 || unit === 0 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
    return kind === 'exact' ? text : `~${text}`;
  }

  formatDuration(seconds: number | null): string {
    if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return '';
    const total = Math.round(seconds);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = String(total % 60).padStart(2, '0');
    return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`;
  }
}
