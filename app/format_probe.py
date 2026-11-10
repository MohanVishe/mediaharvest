"""Probe one video's real formats for the format picker (#1032).

Read-only, like the playlist Browse dialog: nothing is downloaded, queued or
persisted. The picker shows every stream the site offers (resolution, codec,
frame rate, bitrate, size) and submits the chosen yt-dlp ``format_id``s with
the download, where ``dl_formats.get_format`` puts them in front of the
form's usual selector as a fallback chain.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import re
from functools import partial
from typing import Any, Optional

import yt_dlp

from dl_formats import merge_ytdl_option_layers
from subscriptions import _impersonate_opt, unexpected_ytdl_error
from url_guard import download_proxies, validate_url

log = logging.getLogger('format_probe')

# One format id, or a video id and an audio id joined by "+". Restricted to
# the characters real format ids use, so a submitted value can never carry
# yt-dlp selector syntax ("/", "[...]", ",", "(...)") into the format string.
_FORMAT_ID_PART = r'[A-Za-z0-9_.=-]{1,64}'
FORMAT_ID_RE = re.compile(rf'{_FORMAT_ID_PART}(\+{_FORMAT_ID_PART})?')

# Longest list the picker is sent. YouTube offers ~30 streams; a site that
# returns thousands (some HLS masters) would only make the dialog unusable.
_MAX_FORMATS = 300

NOT_A_VIDEO_MSG = 'This URL is a playlist or channel; use Browse… to pick its videos first.'


def is_valid_format_id(value: str) -> bool:
    return bool(FORMAT_ID_RE.fullmatch(value or ''))


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value >= 0 else None


def _codec(value: Any) -> Optional[str]:
    """yt-dlp reports 'none' for an absent stream and None for an unknown one."""
    if value is None:
        return None
    value = str(value)
    return '' if value == 'none' else value


def _short_codec(value: Optional[str]) -> str:
    if not value:
        return ''
    # avc1.640028 -> avc1, mp4a.40.2 -> mp4a, vp09.00.40.08 -> vp09
    return value.split('.', 1)[0]


def format_row(fmt: dict, duration: Optional[float]) -> Optional[dict]:
    """One picker row from a yt-dlp format dict, or None for formats nobody
    downloads on purpose (storyboards, image tracks)."""
    format_id = str(fmt.get('format_id') or '')
    if not is_valid_format_id(format_id):
        return None
    ext = str(fmt.get('ext') or '')
    note = str(fmt.get('format_note') or '')
    if ext == 'mhtml' or 'storyboard' in note.lower():
        return None

    vcodec = _codec(fmt.get('vcodec'))
    acodec = _codec(fmt.get('acodec'))
    height = _num(fmt.get('height'))
    if vcodec is None and acodec is None:
        # Nothing known about the streams (a direct file link): one muxed file.
        has_video = has_audio = True
    else:
        has_video = bool(vcodec) or (vcodec is None and height is not None)
        # An unknown audio codec next to a known stream is assumed present.
        has_audio = bool(acodec) or acodec is None
    if has_video and has_audio:
        kind = 'muxed'
    elif has_video:
        kind = 'video'
    elif has_audio:
        kind = 'audio'
    else:
        return None

    size = _num(fmt.get('filesize'))
    size_kind = 'exact'
    if size is None:
        size = _num(fmt.get('filesize_approx'))
        size_kind = 'approx'
    tbr = _num(fmt.get('tbr'))
    if size is None and tbr and duration:
        # kbit/s * seconds -> bytes
        size = tbr * duration * 125
        size_kind = 'estimate'
    if size is None:
        size_kind = None

    return {
        'format_id': format_id,
        'kind': kind,
        'ext': ext,
        'width': _num(fmt.get('width')),
        'height': height,
        'fps': _num(fmt.get('fps')),
        'vcodec': _short_codec(vcodec) if has_video else '',
        'acodec': _short_codec(acodec) if has_audio else '',
        'dynamic_range': str(fmt.get('dynamic_range') or '') if has_video else '',
        'tbr': tbr,
        'vbr': _num(fmt.get('vbr')),
        'abr': _num(fmt.get('abr')),
        'asr': _num(fmt.get('asr')),
        'audio_channels': _num(fmt.get('audio_channels')),
        'language': str(fmt.get('language') or ''),
        'note': note,
        'protocol': str(fmt.get('protocol') or ''),
        'size': size,
        'size_kind': size_kind,
    }


def summarize(info: dict) -> dict:
    """The picker's view of an extracted video: metadata plus format rows."""
    duration = _num(info.get('duration'))
    rows = []
    for fmt in info.get('formats') or []:
        if not isinstance(fmt, dict):
            continue
        row = format_row(fmt, duration)
        if row is not None:
            rows.append(row)
        if len(rows) >= _MAX_FORMATS:
            break
    thumbnail = info.get('thumbnail')
    return {
        'status': 'ok',
        'title': info.get('title') or '',
        'uploader': info.get('artist') or info.get('uploader') or info.get('channel') or '',
        'duration': duration,
        'thumbnail': thumbnail if isinstance(thumbnail, str) and thumbnail.startswith('https://') else '',
        'is_live': bool(info.get('is_live')),
        'formats': rows,
    }


def _extract(config, url: str, extra_opts: dict, video_password: Optional[str]) -> Optional[dict]:
    params: dict[str, Any] = {
        'quiet': not logging.getLogger().isEnabledFor(logging.DEBUG),
        'verbose': logging.getLogger().isEnabledFor(logging.DEBUG),
        'no_color': True,
        'noplaylist': True,
        'ignore_no_formats_error': True,
        'paths': {'home': config.DOWNLOAD_DIR, 'temp': config.TEMP_DIR},
        **copy.deepcopy(config.YTDL_OPTIONS),
        **copy.deepcopy(extra_opts or {}),
        # A probe never writes anything, whatever YTDL_OPTIONS asks for.
        'skip_download': True,
        'allow_playlist_files': False,
        'writethumbnail': False,
        'writeinfojson': False,
        'writedescription': False,
        'writesubtitles': False,
        'writeautomaticsub': False,
        # Format selection would fail on a "format" the video lacks; the
        # picker wants the full list, not a choice.
        'format': 'all',
    }
    if video_password:
        params['videopassword'] = video_password
    params = _impersonate_opt(params)
    with yt_dlp.YoutubeDL(params=params) as ydl:
        return ydl.extract_info(url, download=False)


async def probe_formats(
    config,
    url: str,
    ytdl_options_presets: Optional[list[str]] = None,
    ytdl_options_overrides: Optional[dict[str, Any]] = None,
    video_password: Optional[str] = None,
) -> dict:
    extra = merge_ytdl_option_layers(
        ytdl_options_presets, ytdl_options_overrides, config.YTDL_OPTIONS_PRESETS
    )
    loop = asyncio.get_running_loop()
    # SSRF guard, same as /add and /browse.
    proxies = download_proxies({**config.YTDL_OPTIONS, **extra})
    url_error = await loop.run_in_executor(
        None,
        partial(
            validate_url,
            url,
            allow_private=getattr(config, 'ALLOW_PRIVATE_ADDRESSES', False),
            proxies=proxies,
        ),
    )
    if url_error is not None:
        log.warning('Rejected probe URL "%s": %s', url, url_error)
        return {'status': 'error', 'msg': url_error}
    try:
        info = await loop.run_in_executor(
            None, partial(_extract, config, url, extra, video_password)
        )
    except yt_dlp.utils.YoutubeDLError as exc:
        return {'status': 'error', 'msg': str(exc)}
    except Exception as exc:
        log.exception('yt-dlp crashed probing %s', url)
        return {'status': 'error', 'msg': unexpected_ytdl_error(exc)}
    if not info:
        return {'status': 'error', 'msg': 'Could not resolve URL'}
    if (info.get('_type') or 'video') != 'video':
        return {'status': 'error', 'msg': NOT_A_VIDEO_MSG}
    return summarize(info)
