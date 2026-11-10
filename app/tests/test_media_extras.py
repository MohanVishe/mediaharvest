"""Tests for the fork's extra postprocessors (audio bitrate, disk space, lyrics)."""

import os
from collections import namedtuple
from unittest.mock import MagicMock

import pytest
from yt_dlp.utils import PostProcessingError

import media_extras
from media_extras import (
    AudioBitratePP,
    DiskSpaceCheckPP,
    LyricsPP,
    attach_audio_bitrate_pp,
    clean_title,
    estimated_download_bytes,
    guess_artist_track,
    pick_result,
    plain_from_synced,
)


def _fake_ydl():
    ydl = MagicMock()
    ydl.params = {}
    return ydl


class _PP:
    def __init__(self, key):
        self._key = key

    def pp_key(self):
        return self._key


class TestAttachAudioBitrate:
    def test_inserted_right_after_extract_audio(self):
        ydl = _fake_ydl()
        ydl._pps = {'post_process': [_PP('ExtractAudio'), _PP('FFmpegMetadata'), _PP('EmbedThumbnail')]}
        attach_audio_bitrate_pp(ydl, 'opus', '96')
        keys = [p.pp_key() for p in ydl._pps['post_process']]
        assert keys == ['ExtractAudio', 'AudioBitrate', 'FFmpegMetadata', 'EmbedThumbnail']

    @pytest.mark.parametrize('fmt,quality', [('opus', 'best'), ('mp3', '192'), ('auto', 'best'), ('flac', 'best')])
    def test_not_needed(self, fmt, quality):
        ydl = _fake_ydl()
        ydl._pps = {'post_process': [_PP('ExtractAudio')]}
        attach_audio_bitrate_pp(ydl, fmt, quality)
        assert len(ydl._pps['post_process']) == 1


class TestAudioBitratePP:
    def test_skips_when_source_is_already_small(self, tmp_path, monkeypatch):
        path = tmp_path / 'a.opus'
        path.write_bytes(b'x')
        pp = AudioBitratePP(_fake_ydl(), 'opus', 128)
        monkeypatch.setattr(pp, 'get_audio_codec', lambda p: 'opus')
        run_ffmpeg = MagicMock()
        monkeypatch.setattr(pp, 'run_ffmpeg', run_ffmpeg)
        pp.run({'filepath': str(path), 'abr': 120})
        run_ffmpeg.assert_not_called()

    def test_reencodes_copied_stream(self, tmp_path, monkeypatch):
        path = tmp_path / 'a.opus'
        path.write_bytes(b'big')
        pp = AudioBitratePP(_fake_ydl(), 'opus', 64)
        monkeypatch.setattr(pp, 'get_audio_codec', lambda p: 'opus')

        def fake_ffmpeg(src, dst, opts):
            assert opts[-2:] == ['-b:a', '64k'] and 'libopus' in opts
            with open(dst, 'wb') as fh:
                fh.write(b's')

        monkeypatch.setattr(pp, 'run_ffmpeg', fake_ffmpeg)
        _, info = pp.run({'filepath': str(path), 'abr': 160})
        assert path.read_bytes() == b's'
        assert info['abr'] == 64

    def test_failure_keeps_original(self, tmp_path, monkeypatch):
        path = tmp_path / 'a.m4a'
        path.write_bytes(b'orig')
        pp = AudioBitratePP(_fake_ydl(), 'm4a', 96)
        monkeypatch.setattr(pp, 'get_audio_codec', lambda p: 'aac')
        monkeypatch.setattr(pp, 'run_ffmpeg', MagicMock(side_effect=RuntimeError('boom')))
        monkeypatch.setattr(pp, 'report_warning', MagicMock())
        pp.run({'filepath': str(path), 'abr': 128})
        assert path.read_bytes() == b'orig'


Usage = namedtuple('Usage', 'total used free')


class TestDiskSpace:
    def test_estimate_merges_pairs(self):
        info = {'duration': 10, 'requested_formats': [{'filesize': 100}, {'filesize_approx': 50}]}
        assert estimated_download_bytes(info) == pytest.approx(150 * 2.1)

    def test_unknown_size_gives_none(self):
        assert estimated_download_bytes({'requested_formats': [{'filesize': 1}, {}]}) is None

    def test_refuses_when_it_will_not_fit(self, monkeypatch):
        monkeypatch.setattr(media_extras.shutil, 'disk_usage', lambda d: Usage(0, 0, 1000))
        pp = DiskSpaceCheckPP(_fake_ydl(), ('/downloads',))
        with pytest.raises(PostProcessingError, match='Not enough disk space'):
            pp.run({'filesize': 5000})

    def test_passes_when_it_fits_or_is_live(self, monkeypatch):
        monkeypatch.setattr(media_extras.shutil, 'disk_usage', lambda d: Usage(0, 0, 10**12))
        pp = DiskSpaceCheckPP(_fake_ydl(), ('/downloads',))
        pp.run({'filesize': 5000})
        pp.run({'filesize': 10**15, 'is_live': True})


class TestLyricsHelpers:
    def test_clean_title(self):
        assert clean_title('Artist - Song (Official Music Video) [HD]') == 'Artist - Song'
        assert clean_title('Song (feat. X)') == 'Song (feat. X)'

    def test_guess_from_music_fields(self):
        assert guess_artist_track({'artist': 'A, B', 'track': 'T', 'title': 'x'}) == ('A', 'T')

    def test_guess_from_title_and_topic_channel(self):
        assert guess_artist_track({'title': 'Artist - Song (Lyrics)'}) == ('Artist', 'Song')
        assert guess_artist_track({'title': 'Song', 'uploader': 'Artist - Topic'}) == ('Artist', 'Song')

    def test_pick_prefers_synced_and_close_duration(self):
        results = [
            {'plainLyrics': 'p', 'duration': 200},
            {'syncedLyrics': '[00:01.00] s', 'duration': 202},
            {'syncedLyrics': '[00:01.00] far', 'duration': 260},
            {'instrumental': True, 'plainLyrics': 'x', 'duration': 200},
        ]
        assert pick_result(results, 200)['syncedLyrics'] == '[00:01.00] s'
        assert pick_result([{'plainLyrics': 'p', 'duration': 300}], 200) is None

    def test_plain_from_synced(self):
        assert plain_from_synced('[00:01.00] one\n[00:02.50]two') == 'one\ntwo'


class TestLyricsPP:
    def test_writes_tag_and_lrc_and_registers_move(self, tmp_path, monkeypatch):
        path = tmp_path / 'song.opus'
        path.write_bytes(b'x')
        pp = LyricsPP(_fake_ydl())
        monkeypatch.setattr(pp, 'find', lambda info: {'syncedLyrics': '[00:01.00] hi', 'plainLyrics': 'hi'})
        written = {}
        monkeypatch.setattr(media_extras, 'write_lyrics_tag', lambda p, t: written.setdefault(p, t) or True)
        _, info = pp.run({'filepath': str(path)})
        assert written == {str(path): 'hi'}
        lrc = tmp_path / 'song.lrc'
        assert lrc.read_text(encoding='utf-8') == '[00:01.00] hi\n'
        assert str(lrc) in info['__files_to_move']

    def test_lookup_failure_never_fails_the_download(self, tmp_path, monkeypatch):
        path = tmp_path / 'song.mp3'
        path.write_bytes(b'x')
        pp = LyricsPP(_fake_ydl())
        monkeypatch.setattr(pp, 'find', MagicMock(side_effect=OSError('offline')))
        monkeypatch.setattr(pp, 'report_warning', MagicMock())
        pp.run({'filepath': str(path)})
        pp.report_warning.assert_called_once()
        assert not os.path.exists(tmp_path / 'song.lrc')
