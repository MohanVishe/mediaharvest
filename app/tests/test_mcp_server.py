"""The MCP endpoint: helpers, and the tools through a real MCP client."""

from __future__ import annotations

import socket
from types import SimpleNamespace
from urllib.parse import urlparse
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web
from mcp import Client

import main
import mcp_server

ROLLING_VTT = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.000 align:start position:0%
hello<00:00:00.500><c> there</c>

00:00:02.000 --> 00:00:02.010
hello there

00:00:02.010 --> 00:00:04.000
hello there
general &amp; friends

3
00:00:04.000 --> 00:00:05.000
general &amp; friends
"""


def test_vtt_to_text_drops_timings_tags_and_rolling_repeats():
    assert mcp_server.vtt_to_text(ROLLING_VTT) == 'hello there\ngeneral & friends'


def _track(ext='vtt'):
    return {'ext': ext, 'url': f'https://example.com/{ext}'}


def test_pick_track_prefers_written_subtitles_then_exact_code():
    info = {
        'subtitles': {'en-US': [_track('srv3'), _track()]},
        'automatic_captions': {'en': [_track()]},
    }
    assert mcp_server.pick_track(info, 'EN')[:2] == (False, 'en-US')
    assert mcp_server.pick_track({'automatic_captions': {'de': [_track()]}}, 'de')[:2] == (True, 'de')
    assert mcp_server.pick_track({'subtitles': {'en': [_track('json3')]}}, 'en') is None
    assert mcp_server.pick_track({}, 'en') is None


class _FakeYDL:
    """yt-dlp stand-in: automatic captions served as an HLS playlist."""
    pages = {
        'https://caps.example/en.m3u8': '#EXTM3U\n#EXTINF:18,\npart1.vtt\n#EXT-X-ENDLIST\n',
        'https://caps.example/part1.vtt': ROLLING_VTT,
    }

    def __init__(self, params):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download):
        return {'title': 'Zoo', 'automatic_captions': {
            'en': [{'ext': 'vtt', 'url': 'https://caps.example/en.m3u8'}]}}

    def urlopen(self, url):
        page = MagicMock()
        page.__enter__.return_value.read.return_value = self.pages[url].encode()
        return page


def test_transcript_follows_an_hls_caption_playlist(monkeypatch):
    monkeypatch.setattr(mcp_server.yt_dlp, 'YoutubeDL', _FakeYDL)
    result = mcp_server._transcript(main.config, 'https://example.com/v', 'en')
    assert result == {'title': 'Zoo', 'language': 'en', 'automatic_captions': True,
                      'text': 'hello there\ngeneral & friends'}


class _InternalCaptionsYDL(_FakeYDL):
    """A page whose caption track points into the local network."""

    def extract_info(self, url, download):
        return {'title': 'Trap', 'subtitles': {
            'en': [{'ext': 'vtt', 'url': 'http://192.168.1.1/admin.vtt'}]}}

    def urlopen(self, url):
        socket.getaddrinfo(urlparse(url).hostname, 80)  # what a real fetch does first
        return super().urlopen(url)


def test_transcript_refuses_caption_links_to_internal_hosts(monkeypatch):
    monkeypatch.setattr(mcp_server.yt_dlp, 'YoutubeDL', _InternalCaptionsYDL)
    monkeypatch.setattr(main.config, 'ALLOW_PRIVATE_ADDRESSES', False)
    with pytest.raises(socket.gaierror, match='non-global'):
        mcp_server._transcript(main.config, 'https://example.com/v', 'en')


@pytest.mark.parametrize('prefix, kind, folder, expected', [
    ('/', 'video', None, '/download/a%20b.mp4'),
    ('/mh/', 'audio', 'music/rock', '/mh/audio_download/music/rock/a%20b.mp4'),
])
def test_file_url_matches_the_web_ui_link(prefix, kind, folder, expected):
    config = SimpleNamespace(URL_PREFIX=prefix, PUBLIC_HOST_URL='download/',
                             PUBLIC_HOST_AUDIO_URL='audio_download/')
    info = SimpleNamespace(filename='a b.mp4', download_type=kind, folder=folder)
    assert mcp_server._file_url(config, info) == expected
    assert mcp_server._file_url(config, SimpleNamespace(filename=None)) == ''


def test_main_serves_mcp_before_the_static_catch_all():
    match = [r for r in main.app.router.routes() if r.handler == main.mcp_endpoint.handle]
    assert match and match[0].resource.canonical == main.config.URL_PREFIX + 'mcp'


def _info(url, status, **kw):
    fields = dict(url=url, title='T', download_type='video', status=status, percent=None,
                  speed=None, eta=None, size=None, error=None, msg=None, filename=None,
                  folder=None, timestamp=0)
    fields.update(kw)
    return SimpleNamespace(**fields)


@pytest.fixture
def dqueue():
    d = MagicMock()
    d.add = AsyncMock(return_value={'status': 'ok'})
    d.cancel = AsyncMock(return_value={'status': 'ok'})
    running = _info('https://example.com/run', 'downloading', percent=40.0)
    d.queue.items = MagicMock(return_value=[('https://example.com/run', SimpleNamespace(info=running))])
    d.pending.items = MagicMock(return_value=[])
    d.done.items = MagicMock(return_value=[
        (f'u{i}', SimpleNamespace(info=_info(f'u{i}', 'finished', timestamp=i, filename=f'{i}.mp4')))
        for i in range(60)])
    d.queue.exists = MagicMock(side_effect=lambda key: key == 'https://example.com/run')
    d.pending.exists = MagicMock(return_value=False)
    return d


@pytest.fixture
async def mcp_url(dqueue, aiohttp_server):
    endpoint = mcp_server.create(main.config, dqueue, main.parse_download_options, 'test',
                                 origin_allowed=lambda origin: origin == 'https://trusted.example')
    app = web.Application(middlewares=[main.cross_origin_guard])
    app.router.add_route('*', '/mcp', endpoint.handle)
    app.cleanup_ctx.append(endpoint.lifespan)
    server = await aiohttp_server(app)
    return str(server.make_url('/mcp'))


async def _call(url, tool, args=None):
    async with Client(url) as client:
        return await client.call_tool(tool, args or {})


def _text(result) -> str:
    return ' '.join(getattr(c, 'text', '') for c in result.content)


async def test_lists_the_five_tools_with_hints(mcp_url):
    async with Client(mcp_url) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {'preview', 'get_transcript', 'download', 'list_downloads', 'cancel_download'}
    assert tools['get_transcript'].annotations.read_only_hint is True
    assert tools['download'].annotations.read_only_hint is False
    assert tools['download'].input_schema['properties']['kind']['enum'] == ['video', 'audio', 'captions', 'thumbnail']


async def test_download_queues_through_the_same_validation(mcp_url, dqueue):
    result = await _call(mcp_url, 'download', {'url': 'https://example.com/v', 'kind': 'audio', 'format': 'mp3'})
    assert not result.is_error, _text(result)
    url, options = dqueue.add.await_args.args
    assert (url, options.download_type, options.format) == ('https://example.com/v', 'audio', 'mp3')

    for kind in ('video', 'captions', 'thumbnail'):  # empty format takes the default
        result = await _call(mcp_url, 'download', {'url': 'https://example.com/v', 'kind': kind})
        assert not result.is_error, (kind, _text(result))
    assert dqueue.add.await_count == 4

    bad = await _call(mcp_url, 'download', {'url': 'https://example.com/v', 'quality': '9999'})
    assert bad.is_error and dqueue.add.await_count == 4


async def test_download_reports_a_queue_error(mcp_url, dqueue):
    dqueue.add.return_value = {'status': 'error', 'msg': 'Folder not allowed'}
    result = await _call(mcp_url, 'download', {'url': 'https://example.com/v'})
    assert result.is_error and 'Folder not allowed' in _text(result)


async def test_preview_and_transcript_refuse_private_addresses(mcp_url):
    for tool in ('preview', 'get_transcript'):
        result = await _call(mcp_url, tool, {'url': 'http://127.0.0.1/secret'})
        assert result.is_error, tool


async def test_long_transcripts_come_in_parts(mcp_url, monkeypatch):
    monkeypatch.setattr(mcp_server, 'validate_url', lambda *a, **kw: None)
    monkeypatch.setattr(mcp_server, '_PART_CHARS', 4)
    monkeypatch.setattr(mcp_server, '_transcript', lambda config, url, language: {
        'title': 'Long', 'language': 'en', 'automatic_captions': False, 'text': 'abcdefghij'})
    texts = []
    for part in (1, 2, 3):
        result = await _call(mcp_url, 'get_transcript', {'url': 'https://example.com/v', 'part': part})
        assert result.structured_content['parts'] == 3
        texts.append(result.structured_content['text'])
    assert texts == ['abcd', 'efgh', 'ij']
    beyond = await _call(mcp_url, 'get_transcript', {'url': 'https://example.com/v', 'part': 4})
    assert beyond.is_error and 'part 1 to 3' in _text(beyond)


async def test_list_downloads_shows_active_and_newest_50_finished(mcp_url):
    result = await _call(mcp_url, 'list_downloads')
    data = result.structured_content
    assert [d['percent'] for d in data['active']] == [40.0]
    assert len(data['finished']) == 50
    assert data['finished'][0]['id'] == 'u59'
    assert data['finished'][0]['file_url'].endswith('/download/59.mp4')


async def test_cancel_download_only_touches_active_ones(mcp_url, dqueue):
    missing = await _call(mcp_url, 'cancel_download', {'id': 'u3'})
    assert missing.is_error
    dqueue.cancel.assert_not_awaited()
    ok = await _call(mcp_url, 'cancel_download', {'id': 'https://example.com/run'})
    assert not ok.is_error
    dqueue.cancel.assert_awaited_once_with(['https://example.com/run'])


async def test_web_pages_need_a_listed_origin(mcp_url):
    import aiohttp
    body = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}}
    async with aiohttp.ClientSession() as session:
        async with session.post(mcp_url, json=body, headers={'Origin': 'https://evil.example'}) as resp:
            assert resp.status == 403
        async with session.get(mcp_url, headers={'Origin': 'https://evil.example'}) as resp:
            assert resp.status == 403


async def test_a_2025_client_with_the_initialize_handshake_works(mcp_url):
    import aiohttp
    headers = {'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json'}
    init = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
        'protocolVersion': '2025-06-18', 'capabilities': {},
        'clientInfo': {'name': 'old-client', 'version': '1'}}}
    async with aiohttp.ClientSession() as session:
        async with session.post(mcp_url, json=init, headers=headers) as resp:
            assert resp.status == 200, await resp.text()
            reply = await resp.json()
        assert reply['result']['protocolVersion'] == '2025-06-18'
        assert reply['result']['serverInfo']['name'] == 'mediaharvest'
        call = {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                'params': {'name': 'list_downloads', 'arguments': {}}}
        async with session.post(mcp_url, json=call,
                                headers={**headers, 'MCP-Protocol-Version': '2025-06-18'}) as resp:
            assert resp.status == 200, await resp.text()
            reply = await resp.json()
        assert reply['result']['isError'] is False
