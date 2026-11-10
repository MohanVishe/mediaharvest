import { describe, expect, it } from 'vitest';
import { App } from './app';
import { ProbeResult } from './services/downloads.service';

describe('link preview', () => {
  it('looks up single video links only', () => {
    for (const url of [
      'https://www.youtube.com/watch?v=jNQXAC9IVRw',
      'https://youtu.be/jNQXAC9IVRw',
      'https://www.youtube.com/watch?v=jNQXAC9IVRw&list=PL123',
      'https://vimeo.com/76979871',
      'https://www.youtube.com/shorts/abc123',
    ]) {
      expect(App.looksLikeOneVideo(url), url).toBe(true);
    }
    for (const url of [
      '',
      'not a link',
      'ftp://example.com/file',
      'https://www.youtube.com/playlist?list=PL123',
      'https://www.youtube.com/@SomeChannel',
      'https://www.youtube.com/@SomeChannel/videos',
      'https://www.youtube.com/channel/UC123',
      'https://www.youtube.com/c/Name',
      'https://www.youtube.com/user/Name',
      'https://www.youtube.com/results?search_query=x',
      'https://www.youtube.com/watch?list=PL123',
      'https://a.com/one https://b.com/two',
    ]) {
      expect(App.looksLikeOneVideo(url), url).toBe(false);
    }
  });

  it('formats durations like a player', () => {
    expect(App.durationLabel(19)).toBe('0:19');
    expect(App.durationLabel(212)).toBe('3:32');
    expect(App.durationLabel(3 * 3600 + 5 * 60 + 7)).toBe('3:05:07');
  });

  it('summarises the formats a video offers', () => {
    const result: ProbeResult = {
      status: 'ok', title: 'Me at the zoo', uploader: 'jawed', duration: 19, thumbnail: 'https://i.ytimg.com/x.jpg', is_live: false,
      formats: [
        { kind: 'video', height: 240 }, { kind: 'video', height: 144 }, { kind: 'muxed', height: 360 },
        { kind: 'audio', height: null },
      ] as ProbeResult['formats'],
    };
    expect(App.summarize(result)).toEqual({
      title: 'Me at the zoo',
      thumbnail: 'https://i.ytimg.com/x.jpg',
      meta: 'jawed · 0:19',
      counts: '3 video formats and 1 audio format available · up to 360p',
    });
  });

  it('says when a stream is live and leaves out what it does not know', () => {
    const live = App.summarize({ status: 'ok', title: 'T', is_live: true, formats: [] } as ProbeResult);
    expect(live.meta).toBe('Live now');
    expect(live.counts).toBe('0 video formats and 0 audio formats available');
  });
});
