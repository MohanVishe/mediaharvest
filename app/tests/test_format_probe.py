"""Tests for the format picker's probe and the format_id selector chain."""

import re
import types

import pytest

import format_probe
from dl_formats import get_format, get_opts


class TestFormatIdValidation:
    @pytest.mark.parametrize('value', ['137', '137+251', 'hls-1080p', 'dash-video=1200000', '251-drc'])
    def test_accepts_real_format_ids(self, value):
        assert format_probe.is_valid_format_id(value)

    @pytest.mark.parametrize('value', [
        '', 'best/worst', '137+251+140', 'bestvideo[height<=720]', '137,251', '(137)', 'a' * 65,
        '137 +251', '../x',
    ])
    def test_refuses_selector_syntax(self, value):
        assert not format_probe.is_valid_format_id(value)


class TestFormatRow:
    def test_video_only_stream(self):
        row = format_probe.format_row({
            'format_id': '137', 'ext': 'mp4', 'vcodec': 'avc1.640028', 'acodec': 'none',
            'height': 1080, 'width': 1920, 'fps': 30, 'filesize': 1000, 'tbr': 4000,
        }, 60)
        assert row['kind'] == 'video'
        assert row['vcodec'] == 'avc1'
        assert row['acodec'] == ''
        assert row['size'] == 1000 and row['size_kind'] == 'exact'

    def test_audio_only_stream_size_estimated_from_bitrate(self):
        row = format_probe.format_row({
            'format_id': '251', 'ext': 'webm', 'vcodec': 'none', 'acodec': 'opus', 'abr': 130, 'tbr': 130,
        }, 100)
        assert row['kind'] == 'audio'
        assert row['size'] == 130 * 100 * 125
        assert row['size_kind'] == 'estimate'

    def test_muxed_and_unknown_codecs(self):
        muxed = format_probe.format_row({'format_id': '18', 'ext': 'mp4', 'vcodec': 'avc1', 'acodec': 'mp4a.40.2'}, None)
        unknown = format_probe.format_row({'format_id': '0', 'ext': 'mp4'}, None)
        assert muxed['kind'] == 'muxed'
        assert unknown['kind'] == 'muxed'

    def test_storyboards_and_bad_ids_are_dropped(self):
        assert format_probe.format_row({'format_id': 'sb0', 'ext': 'mhtml', 'vcodec': 'none', 'acodec': 'none'}, 1) is None
        assert format_probe.format_row({'format_id': 'a/b', 'ext': 'mp4', 'vcodec': 'avc1', 'acodec': 'none'}, 1) is None


class TestSummarize:
    def test_only_https_thumbnails_and_counts(self):
        summary = format_probe.summarize({
            'title': 'T', 'uploader': 'U', 'duration': 10, 'thumbnail': 'http://insecure/x.jpg',
            'formats': [
                {'format_id': '140', 'ext': 'm4a', 'vcodec': 'none', 'acodec': 'mp4a.40.2', 'filesize_approx': 5},
                'junk',
            ],
        })
        assert summary['status'] == 'ok'
        assert summary['thumbnail'] == ''
        assert [f['format_id'] for f in summary['formats']] == ['140']
        assert summary['formats'][0]['size_kind'] == 'approx'


class TestGetFormatWithFormatId:
    def test_picked_streams_go_first_with_form_selector_fallback(self):
        selector = get_format('video', 'auto', 'any', 'best', format_id='137+251')
        assert selector == '137+251/' + get_format('video', 'auto', 'any', 'best')

    def test_audio_pick(self):
        assert get_format('audio', 'auto', 'auto', 'best', format_id='251').startswith('251/')

    def test_ignored_for_captions_and_thumbnails(self):
        assert get_format('thumbnail', 'auto', 'jpg', 'best', format_id='251') == 'bestaudio/best'

    def test_empty_format_id_keeps_selector(self):
        assert get_format('video', 'auto', 'any', '720') == get_format('video', 'auto', 'any', '720', format_id='')


async def test_probe_rejects_internal_urls():
    config = types.SimpleNamespace(
        YTDL_OPTIONS={}, YTDL_OPTIONS_PRESETS={}, DOWNLOAD_DIR='/tmp', TEMP_DIR='/tmp',
        ALLOW_PRIVATE_ADDRESSES=False,
    )
    result = await format_probe.probe_formats(config, 'http://127.0.0.1:8081/')
    assert result['status'] == 'error'


async def test_probe_refuses_playlists(monkeypatch):
    config = types.SimpleNamespace(
        YTDL_OPTIONS={}, YTDL_OPTIONS_PRESETS={}, DOWNLOAD_DIR='/tmp', TEMP_DIR='/tmp',
        ALLOW_PRIVATE_ADDRESSES=False,
    )
    monkeypatch.setattr(format_probe, 'validate_url', lambda *a, **k: None)
    monkeypatch.setattr(format_probe, '_extract', lambda *a, **k: {'_type': 'playlist', 'entries': []})
    result = await format_probe.probe_formats(config, 'https://example.com/list')
    assert result == {'status': 'error', 'msg': format_probe.NOT_A_VIDEO_MSG}


class TestVideoSubtitleOpts:
    def test_english_subtitles_embedded_and_kept(self):
        opts = get_opts('video', 'auto', 'any', 'best', {}, video_subtitles='en')
        assert opts['subtitleslangs'] == ['en.*']
        assert opts['writesubtitles'] and opts['writeautomaticsub']
        assert opts['merge_output_format'] == 'mp4/mkv'
        keys = [p['key'] for p in opts['postprocessors']]
        assert keys == ['FFmpegSubtitlesConvertor', 'FFmpegEmbedSubtitle']
        assert opts['postprocessors'][1]['already_have_subtitle'] is True

    def test_all_languages(self):
        opts = get_opts('video', 'auto', 'mp4', 'best', {}, video_subtitles='en_all')
        assert opts['subtitleslangs'] == ['all', '-live_chat']
        assert 'merge_output_format' not in opts

    def test_none_adds_nothing(self):
        opts = get_opts('video', 'auto', 'any', 'best', {}, video_subtitles='none')
        assert 'writesubtitles' not in opts and opts['postprocessors'] == []

    def test_picked_streams_into_mp4_are_remuxed(self):
        opts = get_opts('video', 'auto', 'mp4', 'best', {}, format_id='313+251')
        assert opts['merge_output_format'] == 'mp4'


def test_machine_captions_cut_to_english(monkeypatch):
    import yt_dlp
    from ytdl import _ConfinedYoutubeDL

    seen = {}

    def fake(self, video_id, normal, automatic):
        seen['auto'] = sorted(automatic)
        seen['normal'] = sorted(normal)

    monkeypatch.setattr(yt_dlp.YoutubeDL, 'process_subtitles', fake)
    ydl = _ConfinedYoutubeDL({'quiet': True})
    ydl.auto_caption_filter = re.compile(r'en')
    ydl.process_subtitles('x', {'fr': [], 'en-GB': []}, {'en': [], 'en-orig': [], 'de': [], 'hi': []})
    assert seen == {'auto': ['en'], 'normal': ['en-GB', 'fr']}

