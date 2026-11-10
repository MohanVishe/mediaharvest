"""Make a downloaded video smaller by re-encoding it with ffmpeg.

Everything here is open source: ffmpeg runs the job, SVT-AV1 encodes the
picture (AV1 plays in current browsers, VLC, Windows 11 and Android), and
Opus encodes the sound (AAC inside MP4 files). The 'compatible' level writes
H.264 and AAC in an MP4 instead, which plays on every device, including older
TVs, iPhones and Macs that have no AV1 decoder; it uses an NVIDIA GPU (NVENC)
when one is present, and the CPU (x264) otherwise.

Measured on clips spread across a 138-hour 720p YouTube video (VP9 + Opus,
about 1 Mbit/s) with VMAF, a 0-100 score of how close the picture stays to the
original (above about 93 people can't tell them apart):

    light       AV1, same resolution, sound kept    24% smaller   VMAF 93.5
    medium      AV1, same resolution, Opus 64k      51% smaller   VMAF 91.8
    strong      AV1, at most 480p, Opus 48k         64% smaller   VMAF 82.8
    compatible  H.264 + AAC 96k in MP4              20% smaller   VMAF 90-92

The AV1 levels ran at 14-17 times real time on 12 CPU cores, so an hour of
video takes about four minutes. Any level can also be limited to a lower
resolution (max_height); a video is never scaled up.

How much a video shrinks depends on the video: one the site already
compressed hard may barely change. When the result is not clearly smaller
(KEEP_RATIO), the original is kept and nothing changes.

The AV1 levels keep the file's name and container. 'compatible' writes an MP4
with the same name (the original is removed once the MP4 is complete).
Subtitle tracks, extra audio tracks, chapters and tags are carried over; text
subtitles become MP4 subtitles when the container changes, and only what an
MP4 cannot hold (picture-based subtitles, MKV attachments) is left out.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Callable, Optional

log = logging.getLogger('compress')

PRESETS = {
    'light': {'codec': 'av1', 'crf': 38, 'speed': 10, 'max_height': None, 'audio_kbps': None},
    'medium': {'codec': 'av1', 'crf': 46, 'speed': 10, 'max_height': None, 'audio_kbps': 64},
    'strong': {'codec': 'av1', 'crf': 44, 'speed': 10, 'max_height': 480, 'audio_kbps': 48},
    # Plays everywhere. x264 CRF 28 and NVENC CQ 32 gave the same size (20-21%
    # smaller) at VMAF 92 and 90; the GPU is about twice as fast.
    'compatible': {'codec': 'h264', 'crf': 28, 'gpu_cq': 32, 'max_height': None, 'audio_kbps': 64},
}

# Resolutions a video can be limited to, on top of its level.
HEIGHTS = (1080, 720, 480, 360)

# The result has to be at least 5% smaller, or the original is kept.
KEEP_RATIO = 0.95

# Containers that take AAC rather than Opus for re-encoded sound.
_AAC_CONTAINERS = ('.mp4', '.m4v', '.mov')
# Containers AV1 is written in as they are; anything else becomes .mkv.
_AV1_CONTAINERS = ('.mp4', '.m4v', '.mkv', '.webm')
# Subtitle formats that can be turned into MP4 (mov_text) subtitles.
_TEXT_SUBTITLES = ('subrip', 'srt', 'ass', 'ssa', 'webvtt', 'mov_text', 'text')
# Cover pictures an MP4 can hold.
_MP4_COVERS = ('mjpeg', 'png')
# yt-dlp and ffmpeg pick the muxer from the extension; a temporary name has
# to end in the real one.
_TEMP_MARK = '.compressing'


class CompressError(Exception):
    """The video could not be compressed; the original is untouched."""


@dataclass
class CompressResult:
    original_size: int
    size: int
    kept_original: bool
    # Where the video is now: the original path, or a new one when the
    # container changed (an .mkv that became .mp4). Empty means unchanged.
    path: str = ''

    @property
    def saved(self) -> int:
        return self.original_size - self.size


@dataclass
class Progress:
    percent: float
    eta: Optional[float]
    speed: Optional[float]  # times real time


def _ffmpeg() -> str:
    return shutil.which('ffmpeg') or 'ffmpeg'


def _ffprobe() -> str:
    return shutil.which('ffprobe') or 'ffprobe'


_gpu_checked: Optional[bool] = None


def gpu_available() -> bool:
    """Whether ffmpeg can encode H.264 on an NVIDIA GPU here. Checked once
    with a tiny test encode. COMPRESS_GPU=off turns the GPU off."""
    global _gpu_checked
    if os.environ.get('COMPRESS_GPU', 'auto').strip().lower() in ('off', 'false', '0', 'no'):
        return False
    if _gpu_checked is None:
        try:
            subprocess.run(
                [_ffmpeg(), '-hide_banner', '-v', 'error', '-f', 'lavfi', '-i', 'color=size=256x256:duration=0.1',
                 '-c:v', 'h264_nvenc', '-f', 'null', '-'],
                capture_output=True, check=True, timeout=60)
            _gpu_checked = True
        except (OSError, subprocess.SubprocessError):
            _gpu_checked = False
        log.info('Compression uses %s for H.264', 'the NVIDIA GPU' if _gpu_checked else 'the CPU')
    return _gpu_checked


def output_extension(path: str, preset: str) -> str:
    """The extension the *preset* version of *path* is written with."""
    ext = os.path.splitext(path)[1].lower()
    if PRESETS[preset]['codec'] == 'h264':
        return '.mp4'
    return ext if ext in _AV1_CONTAINERS else '.mkv'


def probe(path: str) -> dict:
    """Duration and streams of *path*, from ffprobe."""
    try:
        out = subprocess.run(
            [_ffprobe(), '-v', 'error', '-show_entries',
             'format=duration:stream=index,codec_type,codec_name,height,pix_fmt:stream_disposition=attached_pic',
             '-of', 'json', path],
            capture_output=True, text=True, check=True, timeout=120,
        ).stdout
        data = json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise CompressError(f'Could not read the video: {exc}') from exc
    streams = data.get('streams') or []
    video = [s for s in streams if s.get('codec_type') == 'video'
             and not (s.get('disposition') or {}).get('attached_pic')]
    if not video:
        raise CompressError('The file has no video to compress.')
    try:
        duration = float((data.get('format') or {}).get('duration') or 0)
    except ValueError:
        duration = 0.0
    return {
        'duration': duration,
        'height': video[0].get('height') or 0,
        'ten_bit': '10' in str(video[0].get('pix_fmt') or ''),
        'has_audio': any(s.get('codec_type') == 'audio' for s in streams),
        'streams': [{
            'index': s.get('index', i),
            'type': s.get('codec_type') or '',
            'codec': s.get('codec_name') or '',
            'cover': bool((s.get('disposition') or {}).get('attached_pic')),
        } for i, s in enumerate(streams)],
    }


def _target_height(preset: str, max_height: Optional[int]) -> Optional[int]:
    limits = [h for h in (PRESETS[preset]['max_height'], max_height) if h]
    return min(limits) if limits else None


def _default_streams(media: dict) -> list[dict]:
    """Streams for a probe result made by hand: one video and, when there is
    sound, one audio track."""
    streams = [{'index': 0, 'type': 'video', 'codec': '', 'cover': False}]
    if media.get('has_audio'):
        streams.append({'index': 1, 'type': 'audio', 'codec': '', 'cover': False})
    return streams


def build_command(src: str, dst: str, preset: str, media: dict,
                  max_height: Optional[int] = None, gpu: bool = False) -> list[str]:
    """The ffmpeg command that writes the *preset* version of *src* to *dst*,
    no taller than *max_height*. Each stream of *src* is mapped on its own, so
    it is re-encoded, copied, converted or left out as the output container
    needs."""
    settings = PRESETS[preset]
    src_ext = os.path.splitext(src)[1].lower()
    dst_ext = os.path.splitext(dst)[1].lower()
    mp4 = dst_ext in _AAC_CONTAINERS
    same_container = src_ext == dst_ext or (mp4 and src_ext in _AAC_CONTAINERS)
    height = _target_height(preset, max_height)
    kbps = settings['audio_kbps']

    cmd = [_ffmpeg(), '-hide_banner', '-nostdin', '-y', '-v', 'error',
           '-progress', 'pipe:1', '-nostats', '-i', src]
    out = 0
    for stream in media.get('streams') or _default_streams(media):
        kind, index = stream['type'], stream['index']
        args: list[str] = []
        if kind == 'video' and not stream['cover']:
            args = _video_args(out, settings, media, height, gpu)
        elif kind == 'video':
            if same_container or dst_ext == '.mkv' or (mp4 and stream['codec'] in _MP4_COVERS):
                args = [f'-c:{out}', 'copy']
                if mp4:
                    args += [f'-disposition:{out}', 'attached_pic']
        elif kind == 'audio':
            if kbps:
                args = ([f'-c:{out}', 'aac', f'-b:{out}', f'{kbps + 32}k'] if mp4
                        else [f'-c:{out}', 'libopus', f'-b:{out}', f'{kbps}k'])
            elif same_container:
                args = [f'-c:{out}', 'copy']
            else:
                args = ([f'-c:{out}', 'aac', f'-b:{out}', '160k'] if mp4
                        else [f'-c:{out}', 'libopus', f'-b:{out}', '128k'])
        elif kind == 'subtitle':
            if same_container or dst_ext == '.mkv':
                args = [f'-c:{out}', 'copy']
            elif mp4 and stream['codec'] in _TEXT_SUBTITLES:
                args = [f'-c:{out}', 'mov_text']
            elif dst_ext == '.webm' and stream['codec'] in _TEXT_SUBTITLES:
                args = [f'-c:{out}', 'webvtt']
        elif kind == 'attachment':
            if dst_ext == '.mkv':
                args = [f'-c:{out}', 'copy']
        # Data streams, and anything the output cannot hold, are left out.
        if args:
            cmd += ['-map', f'0:{index}'] + args
            out += 1
    if mp4:
        cmd += ['-movflags', '+faststart']
    cmd += ['-max_muxing_queue_size', '4096', dst]
    return cmd


def _video_args(out: int, settings: dict, media: dict, height: Optional[int], gpu: bool) -> list[str]:
    if settings['codec'] == 'h264':
        if gpu:
            args = [f'-c:{out}', 'h264_nvenc', '-preset', 'p7', '-tune', 'hq', '-rc', 'vbr',
                    '-cq', str(settings['gpu_cq']), f'-b:{out}', '0', '-spatial-aq', '1',
                    '-temporal-aq', '1', '-rc-lookahead', '32']
        else:
            args = [f'-c:{out}', 'libx264', '-preset', 'medium', '-crf', str(settings['crf'])]
        # 8-bit High profile: what every H.264 player decodes.
        args += [f'-profile:{out}', 'high', f'-pix_fmt:{out}', 'yuv420p']
    else:
        args = [f'-c:{out}', 'libsvtav1', '-preset', str(settings['speed']), '-crf', str(settings['crf']),
                f'-pix_fmt:{out}', 'yuv420p10le' if media.get('ten_bit') else 'yuv420p']
    if height and media.get('height', 0) > height:
        args += [f'-filter:{out}', f'scale=-2:{height}']
    return args


def temp_path(path: str) -> str:
    stem, ext = os.path.splitext(path)
    return f'{stem}{_TEMP_MARK}{ext}'


def compress_file(
    path: str,
    preset: str,
    on_progress: Optional[Callable[[Progress], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    output: Optional[str] = None,
    max_height: Optional[int] = None,
) -> CompressResult:
    """Re-encode *path* with *preset*, no taller than *max_height*, and
    replace it when the result is clearly smaller, or write the result to
    *output* and leave *path* as it is. The result's path is where the video
    is afterwards. Raises CompressError and leaves *path* untouched when it
    cannot be done."""
    if preset not in PRESETS:
        raise CompressError(f'Unknown compression preset {preset!r}.')
    if max_height is not None and max_height not in HEIGHTS:
        raise CompressError(f'Unknown resolution {max_height!r}.')
    original_size = os.path.getsize(path)
    media = probe(path)
    target = os.path.splitext(output or path)[0] + output_extension(output or path, preset)
    if target != path and os.path.exists(target) and not output:
        raise CompressError(f'A file named {os.path.basename(target)} is already beside the video.')
    directory = os.path.dirname(os.path.abspath(target))
    # The new file is written beside the old one before it replaces it. It is
    # nearly always smaller; asking for the original's size is the safe bound.
    free = shutil.disk_usage(directory).free
    if free < original_size:
        raise CompressError(
            f'Not enough disk space to compress: needs up to {original_size / 1e9:.1f} GB '
            f'free beside the video, {free / 1e9:.1f} GB is free.')
    dst = temp_path(target)
    gpu = PRESETS[preset]['codec'] == 'h264' and gpu_available()
    log.info('Compressing %s (%s%s%s)', path, preset,
             f', at most {max_height}p' if max_height else '', ', GPU' if gpu else '')
    try:
        _encode(build_command(path, dst, preset, media, max_height, gpu), media, on_progress, should_stop)
    except CompressError:
        if not gpu or (should_stop and should_stop()):
            raise
        # The GPU can refuse a job (too many encodes at once, a driver
        # update); the CPU always can.
        log.warning('The GPU could not compress %s; using the CPU', path)
        _encode(build_command(path, dst, preset, media, max_height, False), media, on_progress, should_stop)
    finally:
        if not os.path.isfile(dst) or os.path.getsize(dst) == 0:
            _remove(dst)
    if not os.path.isfile(dst):
        raise CompressError('ffmpeg could not compress the video: it wrote no file.')
    size = os.path.getsize(dst)
    if size >= original_size * KEEP_RATIO:
        _remove(dst)
        log.info('Kept %s: the %s version was not smaller (%d vs %d bytes)', path, preset, size, original_size)
        return CompressResult(original_size, original_size, kept_original=True, path=path)
    os.replace(dst, target)
    if not output and target != path:
        _remove(path)
    log.info('Compressed %s: %d -> %d bytes', target, original_size, size)
    return CompressResult(original_size, size, kept_original=False, path=target)


def _encode(cmd, media, on_progress, should_stop):
    """Run one ffmpeg *cmd*, reporting progress. Raises CompressError, with
    the temporary output removed, when it fails or is stopped."""
    dst = cmd[-1]
    with tempfile.TemporaryFile(mode='w+') as errors:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errors, text=True)
        try:
            _follow(proc, media['duration'], on_progress, should_stop)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            if proc.stdout:
                proc.stdout.close()
        if proc.returncode != 0:
            _remove(dst)
            if should_stop and should_stop():
                raise CompressError('Compression was stopped.')
            errors.seek(0)
            tail = [line.strip() for line in errors.read().splitlines() if line.strip()][-3:]
            raise CompressError('ffmpeg could not compress the video: ' + (' '.join(tail) or
                                f'exit code {proc.returncode}'))


def remove_leftovers(path: str) -> None:
    """Delete half-written compressed copies of *path*, left when the server
    stopped in the middle of compressing it."""
    stem = os.path.splitext(path)[0]
    for ext in {os.path.splitext(path)[1], '.mp4', '.mkv'}:
        leftover = temp_path(stem + ext)
        if os.path.isfile(leftover):
            log.info('Removing unfinished %s', leftover)
            _remove(leftover)


def _follow(proc, duration, on_progress, should_stop):
    """Read ffmpeg's -progress output until it exits, reporting progress at
    most every two seconds."""
    started = time.monotonic()
    last_report = 0.0
    for line in proc.stdout:
        if should_stop and should_stop():
            proc.terminate()
            break
        key, _, value = line.strip().partition('=')
        if key != 'out_time_us' or not on_progress or duration <= 0:
            continue
        now = time.monotonic()
        if now - last_report < 2:
            continue
        last_report = now
        try:
            done = max(int(value), 0) / 1e6
        except ValueError:
            continue
        percent = min(done / duration * 100, 99.9)
        elapsed = now - started
        speed = done / elapsed if elapsed > 0 else None
        eta = (duration - done) / speed if speed else None
        on_progress(Progress(percent=percent, eta=eta, speed=speed))


def _remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError as exc:
        log.warning('Could not remove %s: %s', path, exc)


def main(argv=None):
    """Compress a file from the command line:
    ``python3 compress.py LEVEL VIDEO [--output NEW] [--max-height 720]``. Without
    --output it replaces VIDEO; with it, VIDEO is left as it is."""
    import argparse
    parser = argparse.ArgumentParser(description='Make a video smaller with ffmpeg.')
    parser.add_argument('preset', choices=sorted(PRESETS))
    parser.add_argument('video')
    parser.add_argument('--output', help='write the smaller video here and keep the original')
    parser.add_argument('--max-height', type=int, choices=HEIGHTS, help='also limit the resolution')
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    def show(p: Progress):
        eta = f', {p.eta / 60:.0f} min left' if p.eta else ''
        speed = f', {p.speed:.1f}x real time' if p.speed else ''
        print(f'{p.percent:5.1f}%{speed}{eta}', flush=True)

    try:
        result = compress_file(args.video, args.preset, on_progress=show, output=args.output,
                               max_height=args.max_height)
    except CompressError as exc:
        print(exc)
        return 1
    if result.kept_original:
        print('Kept the original: the compressed version was not smaller.')
    else:
        print(f'{result.original_size / 1e9:.2f} GB -> {result.size / 1e9:.2f} GB '
              f'({result.saved / result.original_size:.0%} smaller): {result.path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
