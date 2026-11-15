"""MCP endpoint at /mcp: lets AI agents use MediaHarvest as a tool.

An agent (Claude Code, Claude Desktop, Cursor, any MCP client) can preview a
link, read a video's transcript, queue a download and follow it. The tools
call the same code as the web UI, so the same checks apply: the SSRF guard,
the format catalog, and no per-download yt-dlp options.

The official MCP SDK serves an ASGI (Starlette) app and aiohttp is not ASGI,
so Endpoint.handle passes each request through to it. It runs stateless with
JSON replies: every request stands alone and nothing is kept between calls.
"""

from __future__ import annotations

import asyncio
import html
import math
import re
from functools import partial
from typing import Any, Literal
from urllib.parse import quote, urljoin

import yt_dlp
from aiohttp import web
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import ToolAnnotations

import format_catalog
import format_probe
from url_guard import download_proxies, socket_guard_scope, validate_url

INSTRUCTIONS = (
    'MediaHarvest downloads video and audio from YouTube and the other sites '
    'yt-dlp supports, on the machine it runs on. Use get_transcript to read '
    'what a video says without saving anything. Use preview to check a link, '
    'download to save a file, and list_downloads to follow it until it is '
    'finished; its file_url fetches the file from this server.'
)

# Most recent finished downloads that list_downloads returns.
_FINISHED_LIMIT = 50
# Transcript characters per reply: about 8,000 tokens of English, well under
# the tool-output limits of MCP clients (Claude Code stops at 25,000 tokens).
_PART_CHARS = 30_000

_READ = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
_TAG = re.compile(r'<[^>]+>')


def vtt_to_text(vtt: str) -> str:
    """The spoken text of a WebVTT file, one line per caption line.

    Drops the header, cue ids, timings and inline tags. Automatic captions
    repeat each line in the next cue as they scroll, so a line equal to the
    one before it is dropped.
    """
    lines: list[str] = []
    for block in vtt.replace('\r\n', '\n').split('\n\n'):
        rows = block.split('\n')
        timing = next((i for i, row in enumerate(rows) if '-->' in row), None)
        if timing is None:  # the WEBVTT header, NOTE or STYLE
            continue
        for row in rows[timing + 1:]:
            text = html.unescape(_TAG.sub('', row)).strip()
            if text and (not lines or lines[-1] != text):
                lines.append(text)
    return '\n'.join(lines)


def pick_track(info: dict, language: str):
    """(automatic, language code, track) for the best WebVTT track, or None.

    Subtitles written by people win over automatic captions; an exact code
    ('en') wins over a regional one ('en-US').
    """
    want = language.strip().lower()
    for automatic, key in ((False, 'subtitles'), (True, 'automatic_captions')):
        tracks = info.get(key) or {}
        exact = [code for code in tracks if code.lower() == want]
        regional = [code for code in tracks if code.lower().split('-')[0] == want and code not in exact]
        for code in exact + regional:
            vtt = next((t for t in tracks[code] if t.get('ext') == 'vtt' and t.get('url')), None)
            if vtt:
                return automatic, code, vtt
    return None


def _read(ydl, url: str) -> str:
    with ydl.urlopen(url) as response:
        return response.read().decode('utf-8', 'replace')


def _transcript(config, url: str, language: str) -> dict[str, Any]:
    with yt_dlp.YoutubeDL(params=format_probe.probe_params(config)) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            raise ToolError('Could not read that link.')
        found = pick_track(info, language)
        if found is None:
            manual = ', '.join(sorted(info.get('subtitles') or {})) or 'none'
            auto = ', '.join(sorted(info.get('automatic_captions') or {})[:40]) or 'none'
            raise ToolError(
                f"This video has no '{language}' subtitles or captions. "
                f'Subtitles: {manual}. Automatic captions: {auto}.')
        automatic, code, track = found
        # The caption links come from the site, not from the user, so they
        # can point anywhere: refuse internal hosts as the downloads do.
        with socket_guard_scope(config.ALLOW_PRIVATE_ADDRESSES,
                                proxy_urls=(config.YTDL_OPTIONS.get('proxy'),)):
            vtt = _read(ydl, track['url'])
            if vtt.startswith('#EXTM3U'):
                # YouTube's automatic captions: an HLS playlist of WebVTT parts.
                parts = [urljoin(track['url'], line) for line in vtt.splitlines()
                         if line.strip() and not line.startswith('#')]
                vtt = '\n\n'.join(_read(ydl, part) for part in parts)
    return {
        'title': info.get('title') or '',
        'language': code,
        'automatic_captions': automatic,
        'text': vtt_to_text(vtt),
    }


def _file_url(config, info) -> str:
    """Where the web UI links a finished file; same rule as buildDownloadLink."""
    if not getattr(info, 'filename', None):
        return ''
    base = config.PUBLIC_HOST_AUDIO_URL if info.download_type == 'audio' else config.PUBLIC_HOST_URL
    if info.folder:
        base += quote(info.folder.strip('/')) + '/'
    prefix = config.URL_PREFIX.strip('/')
    return urljoin(f'/{prefix}/' if prefix else '/', base + quote(info.filename))


def _row(config, info) -> dict[str, Any]:
    return {
        'id': info.url,
        'title': info.title,
        'kind': info.download_type,
        'status': info.status,
        'percent': info.percent,
        'speed': info.speed,
        'eta': info.eta,
        'size': info.size,
        'error': info.error or (info.msg if info.status == 'error' else None),
        'file_url': _file_url(config, info),
    }


def build_server(config, dqueue, parse_options, version: str) -> MCPServer:
    """The MCP tools. parse_options is main.parse_download_options."""
    server = MCPServer(name='mediaharvest', title='MediaHarvest', version=version,
                       instructions=INSTRUCTIONS)

    @server.tool(annotations=_READ)
    async def preview(url: str) -> dict[str, Any]:
        """Look up a video link without downloading it. Returns the title,
        uploader, length in seconds, whether it is live, and the formats on
        offer (resolution, codec, size)."""
        result = await format_probe.probe_formats(config, url.strip())
        if result.get('status') != 'ok':
            raise ToolError(result.get('msg') or 'Could not read that link.')
        result.pop('status')
        return result

    @server.tool(annotations=_READ)
    async def get_transcript(url: str, language: str = 'en', part: int = 1) -> dict[str, Any]:
        """Get what a video says as plain text, from its subtitles or the
        site's automatic captions. Saves nothing. language is a code such as
        en, hi or de. A long transcript comes in parts of 30,000 characters:
        when parts is more than 1, call again with part=2 and so on."""
        url = url.strip()
        loop = asyncio.get_running_loop()
        error = await loop.run_in_executor(None, partial(
            validate_url, url, allow_private=config.ALLOW_PRIVATE_ADDRESSES,
            proxies=download_proxies(config.YTDL_OPTIONS)))
        if error:
            raise ToolError(error)
        try:
            result = await loop.run_in_executor(None, partial(_transcript, config, url, language))
        except yt_dlp.utils.YoutubeDLError as exc:
            raise ToolError(str(exc)) from exc
        parts = max(1, math.ceil(len(result['text']) / _PART_CHARS))
        if not 1 <= part <= parts:
            raise ToolError(f'This transcript has {parts} part(s). Ask for part 1 to {parts}.')
        start = (part - 1) * _PART_CHARS
        result.update(text=result['text'][start:start + _PART_CHARS], part=part, parts=parts)
        return result

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    async def download(
        url: str,
        kind: Literal['video', 'audio', 'captions', 'thumbnail'] = 'video',
        quality: str = 'best',
        format: str = '',
        folder: str = '',
    ) -> dict[str, Any]:
        """Save a video, its audio, its subtitles or its thumbnail into the
        MediaHarvest download folder. Returns once queued; follow it with
        list_downloads. A playlist or channel link queues every video in it.

        quality: for video best, worst or a height (2160, 1440, 1080, 720,
        480, 360, 240); for audio best or a bitrate in kbps (320, 192, 128).
        format: video any, mp4 or ios; audio auto, m4a, mp3, opus, wav or
        flac; captions srt, txt or vtt. Empty picks the default.
        folder: a subfolder of the download folder; empty for the top."""
        try:
            url, options = parse_options({
                'url': url, 'download_type': kind, 'quality': quality,
                'format': format or format_catalog.choice_default(kind, 'format'),
                'folder': folder or None,
            })
        except web.HTTPBadRequest as exc:
            raise ToolError(exc.reason) from exc
        status = await dqueue.add(url, options)
        if status.get('status') != 'ok':
            raise ToolError(status.get('msg') or 'Could not add the download.')
        return {'queued': url, 'note': status.get('msg') or 'Added. Check list_downloads for progress.'}

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    async def list_downloads() -> dict[str, Any]:
        """Downloads that are queued or running, and the most recent finished
        ones (newest first, at most 50). status is queued, scheduled (a live
        stream not started yet), pending (waiting for Start in the web UI),
        preparing, downloading, postprocessing, finished or error. file_url is the path of
        the finished file on this server."""
        active = [d.info for _, d in list(dqueue.queue.items()) + list(dqueue.pending.items())]
        finished = sorted((d.info for _, d in dqueue.done.items()), key=lambda i: i.timestamp, reverse=True)
        return {
            'active': [_row(config, i) for i in active],
            'finished': [_row(config, i) for i in finished[:_FINISHED_LIMIT]],
        }

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                                             idempotentHint=True, openWorldHint=False))
    async def cancel_download(id: str) -> dict[str, Any]:
        """Stop a queued or running download. id comes from list_downloads.
        Finished files are not touched."""
        if not (dqueue.queue.exists(id) or dqueue.pending.exists(id)):
            raise ToolError('No queued or running download has that id.')
        await dqueue.cancel([id])
        return {'cancelled': id}

    return server


class Endpoint:
    """Serves an MCPServer from an aiohttp route."""

    def __init__(self, server: MCPServer, origin_allowed):
        self._server = server
        self._origin_allowed = origin_allowed
        # cross_origin_guard and handle() check the Origin; the SDK's own
        # Host allow-list would refuse every address but localhost.
        self._asgi = server.streamable_http_app(
            streamable_http_path='/mcp', stateless_http=True, json_response=True,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))

    async def lifespan(self, app):
        """For app.cleanup_ctx: the SDK's task group lives as long as the app.

        It runs in a task of its own: an anyio task group must close in the
        task that opened it, and aiohttp may run startup and cleanup in two.
        """
        started, stop = asyncio.Event(), asyncio.Event()

        async def serve():
            async with self._server.session_manager.run():
                started.set()
                await stop.wait()

        task = asyncio.create_task(serve())
        waiter = asyncio.create_task(started.wait())
        await asyncio.wait((task, waiter), return_when=asyncio.FIRST_COMPLETED)
        if task.done():
            waiter.cancel()
            task.result()  # raises why it could not start
        yield
        stop.set()
        await task

    async def handle(self, request: web.Request) -> web.StreamResponse:
        # MCP clients are not web pages and send no Origin. One that does is
        # a page in a browser, perhaps one that rebound its own domain to
        # this machine, so only origins the operator listed get through.
        origin = request.headers.get('Origin')
        if origin and not self._origin_allowed(origin):
            raise web.HTTPForbidden(text='MediaHarvest accepts MCP requests from web pages '
                                         'only if their origin is in CORS_ALLOWED_ORIGINS.')
        body = await request.read()
        scope = {
            'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
            'method': request.method, 'scheme': request.scheme,
            'path': '/mcp', 'raw_path': b'/mcp', 'root_path': '',
            'query_string': request.query_string.encode(),
            'headers': [(k.lower(), v) for k, v in request.raw_headers],
            'client': (request.remote or '', 0),
            'server': (request.url.host or '', request.url.port or 0),
        }
        finished = asyncio.Event()
        body_sent = False

        async def receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {'type': 'http.request', 'body': body, 'more_body': False}
            await finished.wait()
            return {'type': 'http.disconnect'}

        response: web.StreamResponse | None = None

        async def send(message):
            nonlocal response
            if message['type'] == 'http.response.start':
                response = web.StreamResponse(status=message['status'])
                for k, v in message.get('headers', []):
                    response.headers.add(k.decode('latin-1'), v.decode('latin-1'))
                await response.prepare(request)
            elif message['type'] == 'http.response.body':
                await response.write(message.get('body', b''))

        try:
            await self._asgi(scope, receive, send)
        finally:
            finished.set()
        if response is None:
            raise web.HTTPInternalServerError(text='The MCP server sent no reply.')
        await response.write_eof()
        return response


def create(config, dqueue, parse_options, version: str, origin_allowed) -> Endpoint:
    return Endpoint(build_server(config, dqueue, parse_options, version), origin_allowed)
