"""The Settings page's store, the Windows helper bridge, and their routes."""

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web

import app_settings
import main
from ytdl import thumbnail_url


def _config(**changes):
    return SimpleNamespace(**{'DELETE_FILE_ON_TRASHCAN': 'false', 'CLEAR_COMPLETED_AFTER': 0, **changes})


def _beat(state, folders=None, age=0):
    (state / app_settings.HELPER_FILE).write_text(json.dumps({
        'heartbeat': time.time() - age,
        'folders': folders or {'downloads': 'C:\\Users\\me\\Downloads\\MediaHarvest', 'music': '', 'temp': ''},
    }))


# --- AppSettings ------------------------------------------------------------

def test_defaults_come_from_the_environment(tmp_path):
    store = app_settings.AppSettings(_config(DELETE_FILE_ON_TRASHCAN='ask', CLEAR_COMPLETED_AFTER=7 * 86400), tmp_path)
    assert store.values() == {'delete_files': 'ask', 'keep_original': False,
                              'clear_completed_days': 7, 'keep_partial_files': False}


def test_seconds_that_are_not_whole_days_show_as_none(tmp_path):
    store = app_settings.AppSettings(_config(CLEAR_COMPLETED_AFTER=3600), tmp_path)
    assert store.values()['clear_completed_days'] is None


def test_a_change_is_applied_saved_and_read_back(tmp_path):
    config = _config()
    store = app_settings.AppSettings(config, tmp_path)
    values = store.update({'delete_files': 'always', 'keep_original': True,
                           'clear_completed_days': 30, 'keep_partial_files': True})
    assert values == {'delete_files': 'always', 'keep_original': True,
                      'clear_completed_days': 30, 'keep_partial_files': True}
    assert config.DELETE_FILE_ON_TRASHCAN == 'true'
    assert config.CLEAR_COMPLETED_AFTER == 30 * 86400
    assert config.KEEP_ORIGINAL_AFTER_COMPRESS is True
    assert config.KEEP_PARTIAL_FILES is True
    # A restart reads the saved file and wins over the environment.
    again = _config(DELETE_FILE_ON_TRASHCAN='ask')
    app_settings.AppSettings(again, tmp_path)
    assert again.DELETE_FILE_ON_TRASHCAN == 'true'
    assert again.CLEAR_COMPLETED_AFTER == 30 * 86400


@pytest.mark.parametrize('changes', [
    {},
    {'delete_files': 'sometimes'},
    {'keep_original': 'yes'},
    {'clear_completed_days': -1},
    {'clear_completed_days': 4000},
    {'clear_completed_days': True},
    {'clear_completed_days': 1.5},
    {'colour': 'teal'},
])
def test_bad_changes_are_refused_and_nothing_is_saved(tmp_path, changes):
    store = app_settings.AppSettings(_config(), tmp_path)
    with pytest.raises(app_settings.SettingsError):
        store.update(changes)
    assert not (tmp_path / app_settings.SETTINGS_FILE).exists()


def test_a_damaged_saved_value_is_ignored(tmp_path):
    (tmp_path / app_settings.SETTINGS_FILE).write_text(json.dumps({'delete_files': 'whenever', 'keep_original': True}))
    config = _config()
    app_settings.AppSettings(config, tmp_path)
    assert config.DELETE_FILE_ON_TRASHCAN == 'false'
    assert config.KEEP_ORIGINAL_AFTER_COMPRESS is True


def test_an_unreadable_settings_file_means_defaults(tmp_path):
    (tmp_path / app_settings.SETTINGS_FILE).write_text('{not json')
    store = app_settings.AppSettings(_config(), tmp_path)
    assert store.values()['delete_files'] == 'never'


# --- folders ----------------------------------------------------------------

def test_folders_are_checked_and_tidied():
    assert app_settings.check_folders({'downloads': ' "D:\\Videos" ', 'music': 'E:/Music'}) == {
        'downloads': 'D:\\Videos', 'music': 'E:/Music', 'temp': ''}


@pytest.mark.parametrize('folders', [
    {'music': 'D:\\Music'},
    {'downloads': 'Videos'},
    {'downloads': 'D:\\Videos\\..\\Windows'},
    {'downloads': 'D:\\' + 'x' * 300},
    {'downloads': 5},
    {'downloads': 'D:\\Videos', 'photos': 'D:\\Photos'},
    'D:\\Videos',
])
def test_bad_folders_are_refused(folders):
    with pytest.raises(app_settings.SettingsError):
        app_settings.check_folders(folders)


# --- the Windows helper -----------------------------------------------------

def test_no_helper_file_means_no_helper(tmp_path):
    assert app_settings.HostHelper(tmp_path).status() is None


def test_a_recent_heartbeat_means_the_helper_runs(tmp_path):
    _beat(tmp_path, {'downloads': 'D:\\Videos', 'music': 'D:\\Music'})
    assert app_settings.HostHelper(tmp_path).status() == {
        'folders': {'downloads': 'D:\\Videos', 'music': 'D:\\Music', 'temp': ''}}


def test_an_old_heartbeat_means_it_stopped(tmp_path):
    _beat(tmp_path, age=app_settings.HELPER_STALE_SECONDS + 5)
    assert not app_settings.HostHelper(tmp_path).connected()


async def test_ask_waits_for_the_matching_answer(tmp_path):
    helper = app_settings.HostHelper(tmp_path)

    async def answer():
        request_file = tmp_path / app_settings.REQUEST_FILE
        while not request_file.exists():
            await asyncio.sleep(0.05)
        request = json.loads(request_file.read_text())
        (tmp_path / app_settings.RESPONSE_FILE).write_text(json.dumps({'id': 'someone else', 'path': 'X:\\'}))
        await asyncio.sleep(0.6)
        (tmp_path / app_settings.RESPONSE_FILE).write_text(json.dumps({'id': request['id'], 'path': 'D:\\Videos'}))

    task = asyncio.ensure_future(answer())
    response = await helper.ask('browse', timeout=5, kind='downloads')
    await task
    assert response['path'] == 'D:\\Videos'
    assert not (tmp_path / app_settings.RESPONSE_FILE).exists()


async def test_ask_gives_up_after_the_timeout(tmp_path):
    assert await app_settings.HostHelper(tmp_path).ask('browse', timeout=0.6) is None


# --- routes -----------------------------------------------------------------

@pytest.fixture
def routes(tmp_path, monkeypatch):
    # The store changes main.config, as it does in the app; monkeypatch puts
    # every value back afterwards.
    for key, value in (('DELETE_FILE_ON_TRASHCAN', 'false'), ('CLEAR_COMPLETED_AFTER', 0),
                       ('KEEP_ORIGINAL_AFTER_COMPRESS', False), ('KEEP_PARTIAL_FILES', False)):
        monkeypatch.setattr(main.config, key, value)
    monkeypatch.setattr(main, 'settings_store', app_settings.AppSettings(main.config, tmp_path))
    monkeypatch.setattr(main, 'host_helper', app_settings.HostHelper(tmp_path))
    monkeypatch.setattr(main.sio, 'emit', AsyncMock())
    dqueue = MagicMock()
    dqueue.clear_expired = AsyncMock()
    monkeypatch.setattr(main, 'dqueue', dqueue)
    return tmp_path


def _request(body=None):
    request = MagicMock(spec=web.Request)
    request.json = AsyncMock(return_value={} if body is None else body)
    return request


def _body(response):
    return json.loads(response.text)


async def test_settings_without_the_helper(routes):
    data = _body(await main.get_settings(_request()))
    assert data == {'settings': {'delete_files': 'never', 'keep_original': False,
                                 'clear_completed_days': 0, 'keep_partial_files': False},
                    'helper': False, 'folders': None}


async def test_settings_with_the_helper_show_its_folders(routes):
    _beat(routes)
    data = _body(await main.get_settings(_request()))
    assert data['helper'] is True
    assert data['folders']['downloads'] == 'C:\\Users\\me\\Downloads\\MediaHarvest'


async def test_saving_settings_tells_every_browser(routes):
    data = _body(await main.update_settings(_request({'delete_files': 'ask'})))
    assert data['settings']['delete_files'] == 'ask'
    main.dqueue.clear_expired.assert_awaited_once()
    event, payload = main.sio.emit.await_args.args
    assert event == 'configuration'
    assert json.loads(payload)['DELETE_FILE_ON_TRASHCAN'] == 'ask'


async def test_a_bad_setting_is_a_bad_request(routes):
    with pytest.raises(web.HTTPBadRequest):
        await main.update_settings(_request({'delete_files': 'sometimes'}))


async def test_folders_and_close_need_the_helper(routes):
    with pytest.raises(web.HTTPConflict):
        await main.change_folders(_request({'downloads': 'D:\\Videos'}))
    with pytest.raises(web.HTTPConflict):
        await main.close_app(_request())
    with pytest.raises(web.HTTPConflict):
        await main.browse_folder(_request({'kind': 'downloads'}))
    assert not (routes / app_settings.REQUEST_FILE).exists()


async def test_bad_folders_are_refused_before_anything_restarts(routes):
    _beat(routes)
    with pytest.raises(web.HTTPBadRequest):
        await main.change_folders(_request({'downloads': 'Videos'}))
    assert not (routes / app_settings.REQUEST_FILE).exists()


async def test_changing_folders_asks_the_helper_to_restart(routes, monkeypatch):
    _beat(routes)
    monkeypatch.setattr(main.host_helper, 'ask', AsyncMock(return_value={'id': '1', 'ok': True}))
    data = _body(await main.change_folders(_request({'downloads': 'D:\\Videos', 'music': 'D:\\Music'})))
    assert data == {'status': 'restarting'}
    assert main.host_helper.ask.await_args.args == ('restart',)
    assert main.host_helper.ask.await_args.kwargs['folders'] == {
        'downloads': 'D:\\Videos', 'music': 'D:\\Music', 'temp': ''}


async def test_folders_the_helper_cannot_make_are_reported(routes, monkeypatch):
    _beat(routes)
    monkeypatch.setattr(main.host_helper, 'ask', AsyncMock(
        return_value={'id': '1', 'ok': False, 'error': 'Drive Q: is not on this computer.'}))
    with pytest.raises(web.HTTPBadRequest, match='Drive Q:'):
        await main.change_folders(_request({'downloads': 'Q:\\Videos'}))


async def test_a_silent_helper_is_a_timeout(routes, monkeypatch):
    _beat(routes)
    monkeypatch.setattr(main.host_helper, 'ask', AsyncMock(return_value=None))
    with pytest.raises(web.HTTPGatewayTimeout):
        await main.change_folders(_request({'downloads': 'D:\\Videos'}))


def test_a_drifted_clock_still_sees_a_running_helper(tmp_path):
    helper = app_settings.HostHelper(tmp_path)
    _beat(tmp_path, age=3600)      # Windows clock an hour behind
    assert not helper.connected()  # first sight: not trusted
    _beat(tmp_path, age=3597)      # but the heartbeat keeps changing
    assert helper.connected()


async def test_close_asks_the_helper(routes):
    _beat(routes)
    assert _body(await main.close_app(_request())) == {'status': 'closing'}
    assert json.loads((routes / app_settings.REQUEST_FILE).read_text())['action'] == 'close'


async def test_browse_returns_the_folder_picked(routes, monkeypatch):
    _beat(routes)
    monkeypatch.setattr(main.host_helper, 'ask', AsyncMock(return_value={'id': '1', 'path': 'D:\\Videos'}))
    assert _body(await main.browse_folder(_request({'kind': 'music', 'current': 'C:\\'}))) == {'path': 'D:\\Videos'}
    assert main.host_helper.ask.await_args.kwargs == {'timeout': 300, 'kind': 'music', 'current': 'C:\\'}


async def test_browse_cancelled_returns_no_folder(routes, monkeypatch):
    _beat(routes)
    monkeypatch.setattr(main.host_helper, 'ask', AsyncMock(return_value={'id': '1', 'path': None}))
    assert _body(await main.browse_folder(_request({'kind': 'temp'}))) == {'path': None}


async def test_browse_needs_a_known_folder_kind(routes):
    _beat(routes)
    with pytest.raises(web.HTTPBadRequest):
        await main.browse_folder(_request({'kind': 'photos'}))


def test_the_browser_is_told_whether_the_helper_runs(routes):
    assert main._frontend_configuration()['HOST_HELPER'] is False
    _beat(routes)
    assert main._frontend_configuration()['HOST_HELPER'] is True


async def test_open_pages_hear_when_the_helper_appears(routes, monkeypatch):
    # The page may connect before the helper is seen, as after a restart.
    ticks = 0

    async def tick(_seconds):
        nonlocal ticks
        ticks += 1
        if ticks == 2:
            _beat(routes)
        if ticks == 4:
            raise asyncio.CancelledError

    monkeypatch.setattr(main.asyncio, 'sleep', tick)
    with pytest.raises(asyncio.CancelledError):
        await main._watch_host_helper()
    event, payload = main.sio.emit.await_args.args
    assert event == 'configuration'
    assert json.loads(payload)['HOST_HELPER'] is True
    assert main.sio.emit.await_count == 1


# --- thumbnails -------------------------------------------------------------

@pytest.mark.parametrize('entry, url, expected', [
    ({}, 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'https://i.ytimg.com/vi/dQw4w9WgXcQ/mqdefault.jpg'),
    (None, 'https://youtu.be/dQw4w9WgXcQ?t=3', 'https://i.ytimg.com/vi/dQw4w9WgXcQ/mqdefault.jpg'),
    ({'thumbnail': 'https://cdn.example.com/a.jpg'}, 'https://example.com/v/1', 'https://cdn.example.com/a.jpg'),
    ({'thumbnails': [{'url': 'https://e.com/s.jpg'}, {'url': 'https://e.com/l.jpg'}]}, 'https://e.com/1', 'https://e.com/l.jpg'),
    ({'thumbnail': 'javascript:alert(1)'}, 'https://example.com/v/1', None),
    (None, 'https://example.com/v/1', None),
])
def test_thumbnail_url(entry, url, expected):
    assert thumbnail_url(entry, url) == expected
