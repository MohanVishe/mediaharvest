import { TestBed } from '@angular/core/testing';
import { NgbActiveModal } from '@ng-bootstrap/ng-bootstrap';
import { of } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';
import { FormatPickerComponent } from './format-picker.component';
import { DownloadsService, ProbeFormat, ProbeResult } from '../services/downloads.service';
import { FormatCatalog } from '../interfaces';

function fmt(partial: Partial<ProbeFormat>): ProbeFormat {
  return {
    format_id: '0', kind: 'video', ext: 'mp4', width: null, height: null, fps: null,
    vcodec: '', acodec: '', dynamic_range: '', tbr: null, vbr: null, abr: null, asr: null,
    audio_channels: null, language: '', note: '', protocol: 'https', size: null, size_kind: null,
    ...partial,
  };
}

const CATALOG: FormatCatalog = {
  download_type: {
    default: 'video',
    options: [
      {
        id: 'video', text: 'Video',
        format: { default: 'any', options: [
          { id: 'any', text: 'Auto' }, { id: 'mp4', text: 'MP4' }, { id: 'ios', text: 'iOS' },
        ] },
        subtitles: { default: 'en', options: [
          { id: 'none', text: 'None' }, { id: 'en', text: 'English' }, { id: 'en_all', text: 'English + other languages' },
        ] },
      },
      {
        id: 'audio', text: 'Audio',
        format: { default: 'auto', options: [
          { id: 'auto', text: 'Original', quality: { default: 'best', options: [{ id: 'best', text: 'Best' }] }, tags: true },
          { id: 'opus', text: 'OPUS', quality: { default: 'best', options: [
            { id: 'best', text: 'Best' }, { id: '96', text: '96 kbps' },
          ] }, tags: true },
          { id: 'wav', text: 'WAV', tags: false },
        ] },
        audio_tags: { default: 'with_cover', options: [{ id: 'with_cover', text: 'With cover' }, { id: 'none', text: 'None' }] },
      },
    ],
  },
};

const PROBE: ProbeResult = {
  status: 'ok', title: 'T', uploader: 'U', duration: 100, thumbnail: '', is_live: false,
  formats: [
    fmt({ format_id: '137', height: 1080, fps: 30, vcodec: 'avc1', tbr: 4000, size: 50_000_000, size_kind: 'exact' }),
    fmt({ format_id: '399', height: 1080, fps: 30, vcodec: 'av01', tbr: 2000, size: 25_000_000, size_kind: 'exact' }),
    fmt({ format_id: '22', kind: 'muxed', height: 720, vcodec: 'avc1', acodec: 'mp4a', tbr: 1500, size: 18_000_000, size_kind: 'approx' }),
    fmt({ format_id: '233', kind: 'audio', acodec: '', note: 'Default, low' }),
    fmt({ format_id: '140', kind: 'audio', acodec: 'mp4a', abr: 129, size: 1_600_000, size_kind: 'exact' }),
    fmt({ format_id: '251', kind: 'audio', acodec: 'opus', abr: 120, size: 1_500_000, size_kind: 'exact' }),
    fmt({ format_id: '251-drc', kind: 'audio', acodec: 'opus', abr: 125, note: 'DRC', size: 1_500_000, size_kind: 'exact' }),
  ],
};

function create(probe: ProbeResult = PROBE) {
  const close = vi.fn();
  TestBed.configureTestingModule({
    imports: [FormatPickerComponent],
    providers: [
      { provide: DownloadsService, useValue: { probe: () => of(probe) } },
      { provide: NgbActiveModal, useValue: { close, dismiss: vi.fn() } },
    ],
  });
  const fixture = TestBed.createComponent(FormatPickerComponent);
  const picker = fixture.componentInstance;
  picker.payload = { url: 'https://example.com/v', ytdlOptionsPresets: [], ytdlOptionsOverrides: '' };
  picker.catalog = CATALOG;
  fixture.detectChanges();
  return { picker, close, fixture };
}

describe('FormatPickerComponent', () => {
  it('ranks like yt-dlp: AV1 over H.264 at the same resolution, Opus over AAC, DRC and unknown last', () => {
    const { picker } = create();
    expect(picker.bestVideoId).toBe('399');
    expect(picker.bestAudioId).toBe('251');
    expect(picker.audios.map((a) => a.format_id)).toEqual(['251', '140', '251-drc', '233']);
    expect(picker.videoId).toBe('399');
  });

  it('closes with the video and audio stream pair and the subtitles choice', () => {
    const { picker, close } = create();
    picker.videoSubtitles = 'en_all';
    picker.download();
    expect(close).toHaveBeenCalledWith({
      downloadType: 'video', formatId: '399+251', format: 'any', quality: 'best', videoSubtitles: 'en_all',
    });
  });

  it('a stream with its own audio is downloaded alone', () => {
    const { picker, close } = create();
    picker.selectVideo(picker.videos.find((v) => v.format_id === '22')!);
    picker.download();
    expect(close.mock.calls[0][0].formatId).toBe('22');
  });

  it('closes with the audio stream, conversion and lyrics', () => {
    const { picker, close } = create();
    picker.setTab('audio');
    picker.setAudioFormat('opus');
    picker.audioQuality = '96';
    picker.lyrics = true;
    picker.download();
    expect(close).toHaveBeenCalledWith({
      downloadType: 'audio', formatId: '251', format: 'opus', quality: '96', audioTags: 'with_cover', lyrics: true,
    });
  });

  it('estimates the smaller re-encoded size, and keeps a source already below the bitrate', () => {
    const { picker } = create();
    picker.setTab('audio');
    picker.setAudioFormat('opus');
    picker.audioQuality = '96';
    expect(picker.audioOutputBytes()).toBe(96 * 100 * 125);
    picker.audioQuality = 'best';
    expect(picker.audioOutputBytes()).toBe(1_500_000);
  });

  it('formats without tags turn tags and lyrics off', () => {
    const { picker, close } = create();
    picker.setTab('audio');
    picker.setAudioFormat('wav');
    picker.lyrics = true;
    picker.download();
    expect(close.mock.calls[0][0]).toEqual(expect.objectContaining({ audioTags: 'none', lyrics: false }));
  });

  it('shows the probe error', () => {
    const { picker } = create({ status: 'error', msg: 'nope' });
    expect(picker.errorMsg).toBe('nope');
    expect(picker.canDownload()).toBe(false);
  });
});
