"""Tests for compress.py, CompressPP and compressing a completed download.

The encode tests run the real ffmpeg on a two-second generated video; they
are skipped where ffmpeg or its SVT-AV1 encoder is missing.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import compress
from media_extras import CompressPP
from ytdl import Download, DownloadInfo, DownloadQueue, _download_info_from_record, _download_info_to_record


def _has_svtav1():
    if not shutil.which('ffmpeg'):
        return False
    out = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True).stdout
    return 'libsvtav1' in out


needs_ffmpeg = pytest.mark.skipif(not _has_svtav1(), reason='needs ffmpeg with libsvtav1')


def _make_video(path, height=720, audio=True):
    """A two-second clip encoded close to lossless, so any preset shrinks it."""
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi',
           '-i', f'testsrc2=size={height * 16 // 9 // 2 * 2}x{height}:rate=20:duration=2']
    if audio:
        cmd += ['-f', 'lavfi', '-i', 'sine=frequency=440:duration=2']
    cmd += ['-c:v', 'mpeg4', '-q:v', '1']
    if audio:
        cmd += ['-c:a', 'libopus', '-b:a', '256k'] if path.endswith('.mkv') else ['-c:a', 'aac']
    cmd.append(path)
    subprocess.run(cmd, check=True)
    return path


def _streams(path):
    out = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,codec_name,height', '-of', 'json', path],
        capture_output=True, text=True, check=True).stdout
    return json.loads(out)['streams']


# --- the ffmpeg command ---------------------------------------------------

MEDIA_720 = {'duration': 10.0, 'height': 720, 'ten_bit': False, 'has_audio': True}


def _after(cmd, flag):
    return cmd[cmd.index(flag) + 1]


def test_light_keeps_size_and_sound():
    cmd = compress.build_command('in.mkv', 'out.mkv', 'light', MEDIA_720)
    assert _after(cmd, '-c:0') == 'libsvtav1'
    assert _after(cmd, '-crf') == '38'
    assert '-filter:0' not in cmd
    assert _after(cmd, '-c:1') == 'copy'  # the sound is kept as it is


def test_medium_reencodes_sound_as_opus():
    cmd = compress.build_command('in.mkv', 'out.mkv', 'medium', MEDIA_720)
    assert _after(cmd, '-c:1') == 'libopus'
    assert _after(cmd, '-b:1') == '64k'


def test_strong_scales_down_only_taller_videos():
    tall = compress.build_command('in.mkv', 'out.mkv', 'strong', MEDIA_720)
    assert _after(tall, '-filter:0') == 'scale=-2:480'
    short = compress.build_command('in.mkv', 'out.mkv', 'strong', {**MEDIA_720, 'height': 360})
    assert '-filter:0' not in short


def test_mp4_gets_aac_and_faststart():
    cmd = compress.build_command('in.mp4', 'out.mp4', 'medium', MEDIA_720)
    assert _after(cmd, '-c:1') == 'aac'
    assert _after(cmd, '-b:1') == '96k'
    assert _after(cmd, '-movflags') == '+faststart'


def test_ten_bit_video_stays_ten_bit():
    cmd = compress.build_command('in.mkv', 'out.mkv', 'light', {**MEDIA_720, 'ten_bit': True})
    assert _after(cmd, '-pix_fmt:0') == 'yuv420p10le'


def test_temp_path_keeps_the_extension():
    assert compress.temp_path('/d/My video.mp4') == '/d/My video.compressing.mp4'


# --- progress -------------------------------------------------------------

def test_progress_is_read_from_ffmpeg_output():
    proc = MagicMock()
    proc.stdout = io.StringIO('frame=1\nout_time_us=2500000\nprogress=continue\nout_time_us=bad\n')
    seen = []
    with patch('compress.time.monotonic', side_effect=[0.0, 5.0, 10.0]):
        compress._follow(proc, 10.0, seen.append, None)
    assert len(seen) == 1
    assert seen[0].percent == pytest.approx(25.0)
    assert seen[0].speed == pytest.approx(0.5)   # 2.5 s of video in 5 s
    assert seen[0].eta == pytest.approx(15.0)    # 7.5 s left at 0.5x


def test_stop_request_ends_ffmpeg():
    proc = MagicMock()
    proc.stdout = io.StringIO('out_time_us=1\n')
    compress._follow(proc, 10.0, None, lambda: True)
    proc.terminate.assert_called_once()


# --- real encodes ---------------------------------------------------------

@needs_ffmpeg
@pytest.mark.parametrize('preset', ['light', 'medium', 'strong'])
def test_compress_replaces_the_file_with_a_smaller_av1_one(tmp_path, preset):
    path = _make_video(str(tmp_path / 'clip.mkv'))
    before = os.path.getsize(path)

    result = compress.compress_file(path, preset)

    assert not result.kept_original
    assert result.original_size == before
    assert result.size == os.path.getsize(path) < before
    assert not os.path.exists(compress.temp_path(path))
    streams = _streams(path)
    video = [s for s in streams if s['codec_type'] == 'video']
    assert video[0]['codec_name'] == 'av1'
    assert video[0]['height'] == (480 if preset == 'strong' else 720)
    assert any(s['codec_type'] == 'audio' for s in streams)


@needs_ffmpeg
def test_output_leaves_the_original_alone(tmp_path):
    path = _make_video(str(tmp_path / 'clip.mkv'))
    with open(path, 'rb') as f:
        original = f.read()
    out = str(tmp_path / 'small.mkv')

    result = compress.compress_file(path, 'medium', output=out)

    with open(path, 'rb') as f:
        assert f.read() == original
    assert os.path.getsize(out) == result.size < len(original)
    assert not os.path.exists(compress.temp_path(out))


@needs_ffmpeg
def test_mp4_stays_a_playable_mp4(tmp_path):
    path = _make_video(str(tmp_path / 'clip.mp4'))
    compress.compress_file(path, 'medium')
    codecs = {s['codec_type']: s['codec_name'] for s in _streams(path)}
    assert codecs == {'video': 'av1', 'audio': 'aac'}


@needs_ffmpeg
def test_original_is_kept_when_the_result_is_not_smaller(tmp_path):
    path = _make_video(str(tmp_path / 'clip.mkv'))
    with open(path, 'rb') as f:
        original = f.read()

    with patch.object(compress, 'KEEP_RATIO', 0.0):
        result = compress.compress_file(path, 'light')

    assert result.kept_original
    assert result.saved == 0
    with open(path, 'rb') as f:
        assert f.read() == original
    assert not os.path.exists(compress.temp_path(path))


@needs_ffmpeg
def test_a_file_without_video_is_refused(tmp_path):
    path = str(tmp_path / 'sound.mka')
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=1', '-c:a', 'libopus', path],
                   check=True)
    with pytest.raises(compress.CompressError, match='no video'):
        compress.compress_file(path, 'light')


@needs_ffmpeg
def test_too_little_disk_space_leaves_the_file_alone(tmp_path):
    path = _make_video(str(tmp_path / 'clip.mkv'))
    before = os.path.getsize(path)
    with patch('compress.shutil.disk_usage', return_value=MagicMock(free=10)):
        with pytest.raises(compress.CompressError, match='Not enough disk space'):
            compress.compress_file(path, 'light')
    assert os.path.getsize(path) == before


@needs_ffmpeg
def test_an_ffmpeg_failure_cleans_up_and_explains(tmp_path):
    path = _make_video(str(tmp_path / 'clip.mkv'))
    before = os.path.getsize(path)
    bad = lambda src, dst, *rest: ['ffmpeg', '-v', 'error', '-i', src, '-c:v', 'no_such_encoder', dst]
    with patch('compress.build_command', side_effect=bad):
        with pytest.raises(compress.CompressError, match='ffmpeg could not compress'):
            compress.compress_file(path, 'light')
    assert os.path.getsize(path) == before
    assert not os.path.exists(compress.temp_path(path))


def test_unknown_preset_is_refused(tmp_path):
    with pytest.raises(compress.CompressError, match='Unknown'):
        compress.compress_file(str(tmp_path / 'x.mkv'), 'tiny')


# --- during a download ----------------------------------------------------

def _info(**changes):
    info = DownloadInfo(
        id='id1', title='t', url='http://example.com/v', quality='best', download_type='video',
        codec='auto', format='any', folder='', custom_name_prefix='', error=None, entry=None,
        playlist_item_limit=0, split_by_chapters=False, chapter_template='',
    )
    for key, value in changes.items():
        setattr(info, key, value)
    return info


def test_compress_pp_reports_the_saving(tmp_path):
    path = tmp_path / 'v.mkv'
    path.write_bytes(b'x')
    reports = []
    pp = CompressPP(None, 'medium', report=lambda kind, value: reports.append((kind, value)))
    with patch('compress.compress_file', return_value=compress.CompressResult(100, 40, False)) as run:
        assert pp.run({'filepath': str(path)}) == ([], {'filepath': str(path)})
    assert run.call_args.args[:2] == (str(path), 'medium')
    assert reports == [('result', {'state': 'done', 'preset': 'medium', 'height': None,
                                   'original_size': 100, 'size': 40})]


def test_compress_pp_failure_only_warns(tmp_path):
    path = tmp_path / 'v.mkv'
    path.write_bytes(b'x')
    reports = []
    pp = CompressPP(None, 'light', report=lambda kind, value: reports.append((kind, value)))
    with patch('compress.compress_file', side_effect=compress.CompressError('boom')), \
         patch.object(pp, 'report_warning') as warn:
        pp.run({'filepath': str(path)})
    warn.assert_called_once()
    assert reports == [('result', {'state': 'error', 'preset': 'light', 'height': None, 'msg': 'boom'})]


def _pps(download):
    ydl = download._make_youtube_dl({})
    return [pp for pps in ydl._pps.values() for pp in pps]


def test_download_adds_compress_pp_only_when_asked(tmp_path):
    off = Download(str(tmp_path), str(tmp_path), '%(title)s.%(ext)s', '%(title)s.%(ext)s',
                   'best', 'any', {}, _info())
    assert not any(isinstance(pp, CompressPP) for pp in _pps(off))
    on = Download(str(tmp_path), str(tmp_path), '%(title)s.%(ext)s', '%(title)s.%(ext)s',
                  'best', 'any', {}, _info(compress='strong'))
    assert [pp._preset for pp in _pps(on) if isinstance(pp, CompressPP)] == ['strong']


def test_compression_status_reaches_the_row(tmp_path):
    download = Download(str(tmp_path), str(tmp_path), '%(title)s.%(ext)s', '%(title)s.%(ext)s',
                        'best', 'any', {}, _info(compress='medium'))
    sent = []
    download.status_queue = MagicMock(put=sent.append)
    download._report_compression('progress', compress.Progress(percent=40.0, eta=60.0, speed=12.0))
    download._report_compression('result', {'state': 'done'})
    assert sent[0] == {'status': 'compressing', 'percent': 40.0, 'eta': 60.0,
                       'msg': 'Compressing (Medium), 12x real time'}
    assert sent[1] == {'compression': {'state': 'done'}}


def test_a_compression_cut_off_by_a_restart_loads_as_stopped():
    info = _info(compression={'state': 'running', 'preset': 'light', 'percent': 30})
    restored = _download_info_from_record(_download_info_to_record(info, include_entry=False))
    assert restored.compression == {'state': 'error', 'preset': 'light', 'height': None,
                                    'msg': 'Stopped by a restart before it finished.'}


# --- compressing a completed download ---------------------------------------

@pytest.fixture
def queue(tmp_path):
    downloads = tmp_path / 'downloads'
    state = tmp_path / 'state'
    downloads.mkdir()
    state.mkdir()
    cfg = MagicMock()
    cfg.STATE_DIR = str(state)
    cfg.DOWNLOAD_DIR = cfg.AUDIO_DOWNLOAD_DIR = cfg.TEMP_DIR = str(downloads)
    cfg.MAX_CONCURRENT_DOWNLOADS = 3
    cfg.ALLOW_PRIVATE_ADDRESSES = False
    cfg.YTDL_OPTIONS = {}
    cfg.YTDL_OPTIONS_PRESETS = {}
    cfg.CUSTOM_DIRS = True
    cfg.CREATE_CUSTOM_DIRS = True
    cfg.CLEAR_COMPLETED_AFTER = 0
    cfg.DELETE_FILE_ON_TRASHCAN = 'false'
    notifier = MagicMock()
    notifier.completed = AsyncMock()
    return DownloadQueue(cfg, notifier), downloads


async def _finished(dq, downloads, **changes):
    (downloads / 'v.mkv').write_bytes(b'x' * 100)
    info = _info(**{'status': 'finished', 'filename': 'v.mkv', 'size': 100, **changes})
    download = Download.record(info)
    await dq.done.put(download)
    return info


async def _settle(dq):
    for _ in range(50):
        if not dq._compressing:
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0)


async def test_compressing_a_completed_video_records_the_saving(queue):
    dq, downloads = queue
    info = await _finished(dq, downloads)
    with patch('compress.compress_file', return_value=compress.CompressResult(100, 30, False)) as run:
        assert await dq.compress(info.url, 'medium') == {'status': 'ok'}
        await _settle(dq)
    assert run.call_args.args[0] == os.path.realpath(downloads / 'v.mkv')
    assert run.call_args.args[1] == 'medium'
    assert info.compression == {'state': 'done', 'preset': 'medium', 'height': None,
                                'original_size': 100, 'size': 30}
    assert info.size == 30
    # Saved with the completed list, so the saving survives a restart.
    reloaded = DownloadQueue(dq.config, dq.notifier)
    reloaded.done.load()
    assert reloaded.done.get(info.url).info.compression['state'] == 'done'


async def test_a_failed_compression_is_shown_on_the_row(queue):
    dq, downloads = queue
    info = await _finished(dq, downloads)
    with patch('compress.compress_file', side_effect=compress.CompressError('no room')):
        await dq.compress(info.url, 'light')
        await _settle(dq)
    assert info.compression == {'state': 'error', 'preset': 'light', 'height': None, 'msg': 'no room'}
    assert info.size == 100


@pytest.mark.parametrize('changes, message', [
    ({'status': 'error'}, 'Only finished video'),
    ({'download_type': 'audio'}, 'Only finished video'),
    ({'filename': 'missing.mkv'}, 'no longer in the download folder'),
    ({'filename': '../escape.mkv'}, 'no longer in the download folder'),
])
async def test_only_finished_videos_in_the_folder_can_be_compressed(queue, changes, message):
    dq, downloads = queue
    info = await _finished(dq, downloads, **changes)
    result = await dq.compress(info.url, 'light')
    assert result['status'] == 'error'
    assert message in result['msg']


async def test_compress_refuses_an_unknown_download(queue):
    dq, _ = queue
    assert (await dq.compress('http://example.com/none', 'light'))['status'] == 'error'


# --- Every device, resolution, streams -------------------------------------

def _stream(index, kind, codec='', cover=False):
    return {'index': index, 'type': kind, 'codec': codec, 'cover': cover}


MKV_WITH_EXTRAS = {**MEDIA_720, 'streams': [
    _stream(0, 'video', 'vp9'),
    _stream(1, 'audio', 'opus'),
    _stream(2, 'audio', 'opus'),
    _stream(3, 'subtitle', 'subrip'),
    _stream(4, 'subtitle', 'hdmv_pgs_subtitle'),
    _stream(5, 'attachment', 'ttf'),
    _stream(6, 'data', 'bin_data'),
]}


def _mapped(cmd):
    return [cmd[i + 1] for i, part in enumerate(cmd) if part == '-map']


def test_every_device_writes_h264_and_aac_in_an_mp4():
    cmd = compress.build_command('in.mkv', 'out.mp4', 'compatible', MKV_WITH_EXTRAS)
    assert _after(cmd, '-c:0') == 'libx264'
    assert _after(cmd, '-crf') == '28'
    assert _after(cmd, '-profile:0') == 'high'
    assert _after(cmd, '-pix_fmt:0') == 'yuv420p'
    # Both sound tracks, as AAC.
    assert _after(cmd, '-c:1') == _after(cmd, '-c:2') == 'aac'
    assert _after(cmd, '-b:1') == '96k'
    # Text subtitles become MP4 subtitles; what an MP4 can't hold is left out.
    assert _after(cmd, '-c:3') == 'mov_text'
    assert _mapped(cmd) == ['0:0', '0:1', '0:2', '0:3']
    assert _after(cmd, '-movflags') == '+faststart'


def test_every_device_uses_the_gpu_when_there_is_one():
    cmd = compress.build_command('in.mkv', 'out.mp4', 'compatible', MEDIA_720, gpu=True)
    assert _after(cmd, '-c:0') == 'h264_nvenc'
    assert _after(cmd, '-cq') == '32'


def test_av1_levels_copy_every_extra_track_in_the_same_container():
    cmd = compress.build_command('in.mkv', 'out.mkv', 'medium', MKV_WITH_EXTRAS)
    assert _mapped(cmd) == ['0:0', '0:1', '0:2', '0:3', '0:4', '0:5']
    assert _after(cmd, '-c:1') == _after(cmd, '-c:2') == 'libopus'
    assert _after(cmd, '-c:3') == _after(cmd, '-c:4') == _after(cmd, '-c:5') == 'copy'


def test_an_mp4_cover_picture_is_kept():
    media = {**MEDIA_720, 'streams': [_stream(0, 'video', 'h264'), _stream(1, 'audio', 'aac'),
                                      _stream(2, 'video', 'mjpeg', cover=True)]}
    cmd = compress.build_command('in.mp4', 'out.mp4', 'light', media)
    assert _after(cmd, '-c:2') == 'copy'
    assert _after(cmd, '-disposition:2') == 'attached_pic'
    assert _after(cmd, '-c:1') == 'copy'


@pytest.mark.parametrize('preset, max_height, expected', [
    ('light', 480, 'scale=-2:480'),
    ('medium', 1080, None),        # never scaled up
    ('strong', 720, 'scale=-2:480'),  # the level's own limit is lower
    ('strong', 360, 'scale=-2:360'),
    ('compatible', 720, None),     # already 720p
])
def test_resolution_limit(preset, max_height, expected):
    cmd = compress.build_command('in.mkv', 'out.mkv', preset, MEDIA_720, max_height=max_height)
    assert (_after(cmd, '-filter:0') if '-filter:0' in cmd else None) == expected


def test_output_extension():
    assert compress.output_extension('/d/a.webm', 'medium') == '.webm'
    assert compress.output_extension('/d/a.mkv', 'compatible') == '.mp4'
    assert compress.output_extension('/d/a.flv', 'light') == '.mkv'


def test_an_unknown_resolution_is_refused(tmp_path):
    with pytest.raises(compress.CompressError, match='resolution'):
        compress.compress_file(str(tmp_path / 'x.mkv'), 'light', max_height=777)


def test_gpu_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(compress, '_gpu_checked', True)
    assert compress.gpu_available()
    monkeypatch.setenv('COMPRESS_GPU', 'off')
    assert not compress.gpu_available()


def test_leftovers_of_a_cut_off_compression_are_removed(tmp_path):
    video = tmp_path / 'v.mkv'
    video.write_bytes(b'x')
    for name in ('v.compressing.mkv', 'v.compressing.mp4'):
        (tmp_path / name).write_bytes(b'half')
    compress.remove_leftovers(str(video))
    assert sorted(p.name for p in tmp_path.iterdir()) == ['v.mkv']


def _make_rich_mkv(path):
    """Two seconds with two sound tracks and an English subtitle track."""
    srt = path + '.srt'
    with open(srt, 'w') as f:
        f.write('1\n00:00:00,000 --> 00:00:01,500\nHello\n')
    subprocess.run([
        'ffmpeg', '-v', 'error', '-y',
        '-f', 'lavfi', '-i', 'testsrc2=size=1280x720:rate=20:duration=2',
        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2',
        '-f', 'lavfi', '-i', 'sine=frequency=660:duration=2',
        '-i', srt,
        '-map', '0', '-map', '1', '-map', '2', '-map', '3',
        '-c:v', 'mpeg4', '-q:v', '1', '-c:a', 'libopus', '-b:a', '256k', '-c:s', 'srt',
        '-metadata:s:s:0', 'language=eng', path], check=True)
    os.remove(srt)
    return path


@needs_ffmpeg
def test_every_device_turns_an_mkv_into_a_playable_mp4(tmp_path, monkeypatch):
    monkeypatch.setattr(compress, '_gpu_checked', False)
    path = _make_rich_mkv(str(tmp_path / 'clip.mkv'))

    result = compress.compress_file(path, 'compatible', max_height=480)

    assert result.path == str(tmp_path / 'clip.mp4')
    assert not os.path.exists(path)
    streams = _streams(result.path)
    assert [(s['codec_type'], s['codec_name']) for s in streams] == [
        ('video', 'h264'), ('audio', 'aac'), ('audio', 'aac'), ('subtitle', 'mov_text')]
    assert streams[0]['height'] == 480


@needs_ffmpeg
def test_av1_keeps_subtitles_and_every_sound_track(tmp_path):
    path = _make_rich_mkv(str(tmp_path / 'clip.mkv'))
    result = compress.compress_file(path, 'light')
    assert result.path == path
    assert [(s['codec_type'], s['codec_name']) for s in _streams(path)] == [
        ('video', 'av1'), ('audio', 'opus'), ('audio', 'opus'), ('subtitle', 'subrip')]


@needs_ffmpeg
def test_a_gpu_that_fails_falls_back_to_the_cpu(tmp_path, monkeypatch):
    monkeypatch.setattr(compress, 'gpu_available', lambda: True)
    path = _make_video(str(tmp_path / 'clip.mp4'))
    real = compress.build_command

    def no_gpu(src, dst, preset, media, max_height=None, gpu=False):
        cmd = real(src, dst, preset, media, max_height, gpu)
        return [('no_such_gpu_encoder' if part == 'h264_nvenc' else part) for part in cmd]

    monkeypatch.setattr(compress, 'build_command', no_gpu)
    result = compress.compress_file(path, 'compatible')
    assert not result.kept_original
    assert _streams(result.path)[0]['codec_name'] == 'h264'


def test_every_device_does_not_overwrite_another_file(tmp_path):
    video = tmp_path / 'v.mkv'
    video.write_bytes(b'x')
    (tmp_path / 'v.mp4').write_bytes(b'someone else')
    with patch('compress.probe', return_value=MEDIA_720):
        with pytest.raises(compress.CompressError, match='already beside'):
            compress.compress_file(str(video), 'compatible')


def test_compress_pp_points_the_download_at_the_new_mp4(tmp_path):
    path = str(tmp_path / 'v.mkv')
    open(path, 'wb').close()
    new = str(tmp_path / 'v.mp4')
    pp = CompressPP(None, 'compatible', max_height=720)
    info = {'filepath': path, 'ext': 'mkv', '__files_to_move': {path: '/final/v.mkv', 'x.srt': '/final/x.srt'}}
    with patch('compress.compress_file', return_value=compress.CompressResult(100, 40, False, new)) as run:
        _, info = pp.run(info)
    assert run.call_args.kwargs['max_height'] == 720
    assert info['filepath'] == new and info['ext'] == 'mp4'
    assert info['__files_to_move'] == {'x.srt': '/final/x.srt'}


def test_download_passes_the_resolution_to_compress_pp(tmp_path):
    on = Download(str(tmp_path), str(tmp_path), '%(title)s.%(ext)s', '%(title)s.%(ext)s',
                  'best', 'any', {}, _info(compress='light', compress_height='480'))
    assert [pp._max_height for pp in _pps(on) if isinstance(pp, CompressPP)] == [480]


async def test_every_device_on_a_completed_video_renames_the_row(queue):
    dq, downloads = queue
    info = await _finished(dq, downloads)
    new = os.path.realpath(downloads / 'v.mp4')
    with patch('compress.compress_file', return_value=compress.CompressResult(100, 60, False, new)) as run:
        assert await dq.compress(info.url, 'compatible', 720) == {'status': 'ok'}
        await _settle(dq)
    assert run.call_args.kwargs['max_height'] == 720
    assert info.filename == 'v.mp4'
    assert info.compression['height'] == 720


async def test_a_restart_removes_a_half_written_copy(queue):
    dq, downloads = queue
    await _finished(dq, downloads, compression={'state': 'running', 'preset': 'light'})
    (downloads / 'v.compressing.mkv').write_bytes(b'half')
    reloaded = DownloadQueue(dq.config, dq.notifier)
    assert not (downloads / 'v.compressing.mkv').exists()
    assert (downloads / 'v.mkv').exists()
    assert reloaded.done.exists('http://example.com/v')
