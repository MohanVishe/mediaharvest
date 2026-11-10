"""Extra yt-dlp postprocessors for this fork: smaller audio on request,
lyrics, a disk-space check before long downloads, and video compression.

Every one of them is best-effort: they warn and continue, so a lookup or a
probe that goes wrong never fails a download that otherwise succeeded. The
disk-space check is the exception by design — it stops a download that
cannot fit before it fills the disk.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import compress
import urllib.parse
from typing import Any, Optional

from yt_dlp.networking import Request
from yt_dlp.postprocessor.common import PostProcessor
from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor
from yt_dlp.utils import PostProcessingError, format_bytes, prepend_extension

# ---------------------------------------------------------------------------
# Audio bitrate
# ---------------------------------------------------------------------------

# Audio formats whose bitrate choice needs a real re-encode. yt-dlp's
# FFmpegExtractAudio stream-copies when the source already has the target
# codec (YouTube's Opus -> .opus, its AAC -> .m4a) and then ignores the
# bitrate, so "OPUS 96 kbps" came out as large as "OPUS Best".
_REENCODE = {
    'opus': ('opus', 'libopus'),
    'm4a': ('aac', 'aac'),
}


class AudioBitratePP(FFmpegPostProcessor):
    """Re-encode the extracted audio down to the bitrate the user picked,
    when FFmpegExtractAudio copied the stream instead. Runs right after it,
    before the tags and cover are written."""

    def __init__(self, downloader, audio_format: str, kbps: int):
        super().__init__(downloader)
        self._audio_format = audio_format
        self._kbps = kbps

    @classmethod
    def pp_key(cls):
        return 'AudioBitrate'

    def run(self, info):
        target = _REENCODE.get(self._audio_format)
        path = info.get('filepath')
        if not target or not path or not os.path.exists(path):
            return [], info
        codec, encoder = target
        try:
            if self.get_audio_codec(path) != codec:
                # A different codec was re-encoded by FFmpegExtractAudio with
                # the requested bitrate already.
                return [], info
            source_kbps = info.get('abr') or info.get('tbr')
            if isinstance(source_kbps, (int, float)) and source_kbps <= self._kbps * 1.05:
                self.to_screen(f'Source audio is {source_kbps:.0f} kbps; keeping it as is')
                return [], info
            tmp = prepend_extension(path, 'temp')
            self.to_screen(f'Re-encoding audio to {self._kbps} kbps {codec}')
            opts = ['-vn', '-map', '0:a:0', '-c:a', encoder, '-b:a', f'{self._kbps}k']
            if codec == 'aac':
                opts += ['-movflags', '+faststart']
            self.run_ffmpeg(path, tmp, opts)
            os.replace(tmp, path)
            info['abr'] = self._kbps
        except Exception as exc:  # best-effort: keep the original file
            self.report_warning(f'Could not reduce the audio bitrate, keeping the original: {exc}')
            try:
                tmp = prepend_extension(path, 'temp')
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
        return [], info


def attach_audio_bitrate_pp(ydl, audio_format: str, quality: str) -> None:
    """Insert AudioBitratePP right after FFmpegExtractAudio, when the picked
    format and bitrate need it."""
    if audio_format not in _REENCODE or not str(quality).isdigit():
        return
    pps = ydl._pps['post_process']
    pp = AudioBitratePP(ydl, audio_format, int(quality))
    for index, existing in enumerate(pps):
        if existing.pp_key() == 'ExtractAudio':
            pps.insert(index + 1, pp)
            return
    pps.insert(0, pp)


# ---------------------------------------------------------------------------
# Disk space
# ---------------------------------------------------------------------------

# A video+audio pair is downloaded as two files and then merged into a third,
# so the peak use is about twice the streams' size. Single files get a margin.
_MERGE_FACTOR = 2.1
_SINGLE_FACTOR = 1.1


def _format_size(fmt: dict, duration: Optional[float]) -> Optional[float]:
    for key in ('filesize', 'filesize_approx'):
        value = fmt.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    tbr = fmt.get('tbr')
    if isinstance(tbr, (int, float)) and tbr > 0 and duration:
        return tbr * duration * 125
    return None


def estimated_download_bytes(info: dict) -> Optional[float]:
    duration = info.get('duration') if isinstance(info.get('duration'), (int, float)) else None
    formats = info.get('requested_formats') or [info]
    sizes = [_format_size(f, duration) for f in formats]
    if not sizes or any(s is None for s in sizes):
        return None
    factor = _MERGE_FACTOR if len(formats) > 1 else _SINGLE_FACTOR
    return sum(sizes) * factor


class DiskSpaceCheckPP(PostProcessor):
    """Before the download starts (formats chosen, nothing fetched yet),
    refuse it if the estimated size will not fit on the disk."""

    def __init__(self, downloader, directories: tuple[str, ...]):
        super().__init__(downloader)
        self._directories = tuple(d for d in directories if d)

    @classmethod
    def pp_key(cls):
        return 'DiskSpaceCheck'

    def run(self, info):
        if info.get('is_live'):
            return [], info  # no size to know in advance
        needed = estimated_download_bytes(info)
        if not needed:
            return [], info
        for directory in self._directories:
            try:
                free = shutil.disk_usage(directory).free
            except OSError:
                continue
            if needed > free:
                raise PostProcessingError(
                    f'Not enough disk space: this download needs about {format_bytes(needed)} '
                    f'(including room to merge), but only {format_bytes(free)} is free '
                    f'in {directory}.')
        return [], info


# ---------------------------------------------------------------------------
# Compression
# ---------------------------------------------------------------------------

class CompressPP(PostProcessor):
    """Make the finished video smaller (compress.py), after every other
    postprocessor has written into it (subtitles, chapters, metadata). A
    failure only warns: the download itself worked, and the original stays.

    *report* gets ('progress', compress.Progress) while it runs and
    ('result', dict) once at the end; the dict is DownloadInfo.compression.
    """

    def __init__(self, downloader, preset: str, report=None, max_height=None):
        super().__init__(downloader)
        self._preset = preset
        self._max_height = max_height
        self._report = report or (lambda kind, value: None)

    @classmethod
    def pp_key(cls):
        return 'Compress'

    def run(self, info):
        path = info.get('filepath')
        if not path or not os.path.isfile(path):
            return [], info
        try:
            result = compress.compress_file(
                path, self._preset, on_progress=lambda p: self._report('progress', p),
                max_height=self._max_height)
        except compress.CompressError as exc:
            self.report_warning(f'Not compressed: {exc}')
            self._report('result', {'state': 'error', 'preset': self._preset,
                                    'height': self._max_height, 'msg': str(exc)})
            return [], info
        self._report('result', {
            'state': 'kept' if result.kept_original else 'done',
            'preset': self._preset,
            'height': self._max_height,
            'original_size': result.original_size,
            'size': result.size,
        })
        if result.path and result.path != path:
            # Any device writes an .mp4 in place of an .mkv or .webm: point
            # MoveFiles, and so the Completed row, at the new file.
            moves = info.get('__files_to_move')
            if isinstance(moves, dict):
                moves.pop(path, None)
            info['filepath'] = result.path
            info['ext'] = os.path.splitext(result.path)[1].lstrip('.')
        return [], info


# ---------------------------------------------------------------------------
# Lyrics
# ---------------------------------------------------------------------------

LRCLIB_URL = 'https://lrclib.net/api'
# LRCLIB asks clients to identify themselves; no personal details here.
_USER_AGENT = 'MediaHarvest lyrics lookup'
_DURATION_TOLERANCE = 4  # seconds

_NOISE = re.compile(
    r'\s*[\(\[][^)\]]*\b(official|video|audio|lyrics?|visuali[sz]er|hd|4k|hq|remaster(ed)?|mv|m/v)\b[^)\]]*[\)\]]',
    re.IGNORECASE,
)
_TOPIC_SUFFIX = re.compile(r'\s*(- Topic|VEVO|Official)$', re.IGNORECASE)
_LRC_TIME = re.compile(r'^\s*\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?\]\s?', re.MULTILINE)


def clean_title(title: str) -> str:
    return re.sub(r'\s{2,}', ' ', _NOISE.sub('', title or '')).strip(' -|')


def guess_artist_track(info: dict) -> tuple[str, str]:
    """Artist and track for the lookup, from the extractor's music fields
    when it has them (YouTube Music, Bandcamp), else from "Artist - Title"."""
    artists = info.get('artists') if isinstance(info.get('artists'), list) else []
    artist = info.get('artist') or (artists[0] if artists else '') or info.get('creator') or ''
    track = info.get('track') or ''
    title = clean_title(str(info.get('title') or ''))
    if not track and ' - ' in title:
        left, right = title.split(' - ', 1)
        artist = artist or left
        track = right
    if not track:
        track = title
    if not artist:
        artist = _TOPIC_SUFFIX.sub('', str(info.get('uploader') or info.get('channel') or '')).strip()
    return str(artist).split(',')[0].strip(), clean_title(str(track))


def plain_from_synced(synced: str) -> str:
    return _LRC_TIME.sub('', synced).strip()


def pick_result(results: list, duration: Optional[float]) -> Optional[dict]:
    """The closest-length result with lyrics, preferring synced ones."""
    best = None
    best_key = None
    for item in results or []:
        if not isinstance(item, dict) or item.get('instrumental'):
            continue
        if not (item.get('syncedLyrics') or item.get('plainLyrics')):
            continue
        item_duration = item.get('duration')
        if duration and isinstance(item_duration, (int, float)):
            gap = abs(item_duration - duration)
            if gap > _DURATION_TOLERANCE:
                continue
        else:
            gap = _DURATION_TOLERANCE
        key = (0 if item.get('syncedLyrics') else 1, gap)
        if best_key is None or key < best_key:
            best, best_key = item, key
    return best


def write_lyrics_tag(path: str, text: str) -> bool:
    """Write plain lyrics into the file's own lyrics tag. True if written."""
    import mutagen
    from mutagen.flac import FLAC
    from mutagen.id3 import ID3, USLT, ID3NoHeaderError
    from mutagen.mp4 import MP4

    ext = os.path.splitext(path)[1].lower()
    if ext == '.mp3':
        try:
            tags = ID3(path)
        except ID3NoHeaderError:
            tags = ID3()
        tags.setall('USLT', [USLT(encoding=3, lang='eng', desc='', text=text)])
        tags.save(path)
        return True
    if ext in ('.m4a', '.mp4', '.m4b', '.aac'):
        audio = MP4(path)
        audio['\xa9lyr'] = [text]
        audio.save()
        return True
    if ext == '.flac':
        audio = FLAC(path)
        audio['LYRICS'] = text
        audio.save()
        return True
    if ext in ('.opus', '.ogg', '.oga'):
        audio = mutagen.File(path)
        if audio is None:
            return False
        audio['LYRICS'] = [text]
        audio.save()
        return True
    return False


class LyricsPP(PostProcessor):
    """Look the song up on LRCLIB (free, no key) and write the lyrics into
    the file's lyrics tag; synced lyrics also go to a .lrc file beside it,
    which players with synced-lyrics support pick up. Opt-in per download:
    it sends the artist, title and length to lrclib.net."""

    def __init__(self, downloader, base_url: str = LRCLIB_URL):
        super().__init__(downloader)
        self._base_url = base_url.rstrip('/')

    @classmethod
    def pp_key(cls):
        return 'Lyrics'

    def _get_json(self, endpoint: str, query: dict[str, Any]) -> Any:
        url = f'{self._base_url}/{endpoint}?{urllib.parse.urlencode(query)}'
        request = Request(url, headers={'User-Agent': _USER_AGENT, 'Accept': 'application/json'})
        try:
            with self._downloader.urlopen(request) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as exc:
            status = getattr(exc, 'status', None) or getattr(getattr(exc, 'response', None), 'status', None)
            if status == 404:
                return None
            raise

    def find(self, info: dict) -> Optional[dict]:
        artist, track = guess_artist_track(info)
        if not track:
            return None
        duration = info.get('duration') if isinstance(info.get('duration'), (int, float)) else None
        if artist:
            query = {'artist_name': artist, 'track_name': track}
            if info.get('album'):
                query['album_name'] = info['album']
            if duration:
                query['duration'] = int(round(duration))
            exact = self._get_json('get', query)
            if isinstance(exact, dict) and pick_result([exact], duration):
                return exact
            found = pick_result(self._get_json('search', {'artist_name': artist, 'track_name': track}), duration)
            if found:
                return found
        return pick_result(self._get_json('search', {'q': f'{artist} {track}'.strip()}), duration)

    def run(self, info):
        path = info.get('filepath')
        if not path or not os.path.exists(path):
            return [], info
        try:
            result = self.find(info)
            if not result:
                self.to_screen('No lyrics found')
                return [], info
            synced = result.get('syncedLyrics') or ''
            plain = result.get('plainLyrics') or plain_from_synced(synced)
            if plain and write_lyrics_tag(path, plain):
                self.to_screen('Lyrics written into the file')
            if synced:
                lrc_path = os.path.splitext(path)[0] + '.lrc'
                with open(lrc_path, 'w', encoding='utf-8') as fh:
                    fh.write(synced.strip() + '\n')
                # Moved next to the audio with it, when a temp dir is in use.
                info.setdefault('__files_to_move', {})[lrc_path] = None
                self.to_screen('Synced lyrics saved as .lrc')
        except Exception as exc:
            self.report_warning(f'Lyrics lookup failed, continuing without lyrics: {exc}')
        return [], info
