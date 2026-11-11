"""The Settings page: what people change there, kept in the state folder, and
the link to the Windows helper (windows/MediaHarvest.ps1) that can restart
MediaHarvest with other folders or close it together with Docker.

The helper and the server talk through small JSON files in the state folder,
the one folder both can always reach:

- helper.json           the helper writes it every few seconds while it runs:
                        a heartbeat plus the folders on this computer.
- helper-request.json   the server writes one request: close, restart with new
                        folders, or show a folder picker.
- helper-response.json  the helper's answer to a request, matched by id.
"""

import asyncio
import json
import logging
import os
import re
import time
import uuid

log = logging.getLogger('app_settings')

SETTINGS_FILE = 'settings.json'
HELPER_FILE = 'helper.json'
REQUEST_FILE = 'helper-request.json'
RESPONSE_FILE = 'helper-response.json'

# The helper writes its heartbeat every 3 seconds; three missed ones mean it is gone.
HELPER_STALE_SECONDS = 10

FOLDER_KINDS = ('downloads', 'music', 'temp')

# DELETE_FILE_ON_TRASHCAN spelled the way the Settings page says it.
_DELETE_CHOICES = {'never': 'false', 'ask': 'ask', 'always': 'true'}
_MAX_DAYS = 3650
_MAX_PATH = 260
# A Windows folder (C:\... or C:/...), or a Linux one for the helper's WSL mode.
_FOLDER_RE = re.compile(r'^(?:[A-Za-z]:[\\/]|/)')


class SettingsError(ValueError):
    """A value the Settings page sent that cannot be used."""


def _write_json(path, data):
    """Write *data* so a reader never sees half a file."""
    tmp = f'{path}.{os.getpid()}.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


def _read_json(path):
    try:
        with open(path, encoding='utf-8-sig') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


class AppSettings:
    """Settings saved from the Settings page. They win over the matching
    environment variables, which stay the defaults until something is saved."""

    def __init__(self, config, state_dir):
        self.config = config
        self.path = os.path.join(state_dir, SETTINGS_FILE)
        self.saved = {}
        loaded = _read_json(self.path) or {}
        for key, value in loaded.items():
            try:
                self.saved[key] = self._check(key, value)
            except SettingsError as exc:
                log.warning('Ignoring the saved setting %s: %s', key, exc)
        self.apply()

    def values(self) -> dict:
        """Every setting as the Settings page shows it."""
        inverse = {v: k for k, v in _DELETE_CHOICES.items()}
        clear_after = self.config.CLEAR_COMPLETED_AFTER
        return {
            'delete_files': inverse[self.config.DELETE_FILE_ON_TRASHCAN],
            'keep_original': bool(getattr(self.config, 'KEEP_ORIGINAL_AFTER_COMPRESS', False)),
            # None: CLEAR_COMPLETED_AFTER is set in seconds that are not whole days.
            'clear_completed_days': clear_after // 86400 if clear_after % 86400 == 0 else None,
            'keep_partial_files': bool(getattr(self.config, 'KEEP_PARTIAL_FILES', False)),
        }

    def update(self, changes) -> dict:
        if not isinstance(changes, dict) or not changes:
            raise SettingsError('Nothing to change.')
        checked = {key: self._check(key, value) for key, value in changes.items()}
        self.saved.update(checked)
        _write_json(self.path, self.saved)
        self.apply()
        log.info('Settings changed: %s', checked)
        return self.values()

    def apply(self):
        """Put the saved settings into the running configuration."""
        config = self.config
        if 'delete_files' in self.saved:
            config.DELETE_FILE_ON_TRASHCAN = _DELETE_CHOICES[self.saved['delete_files']]
        if 'clear_completed_days' in self.saved:
            config.CLEAR_COMPLETED_AFTER = self.saved['clear_completed_days'] * 86400
        config.KEEP_ORIGINAL_AFTER_COMPRESS = self.saved.get('keep_original', False)
        config.KEEP_PARTIAL_FILES = self.saved.get('keep_partial_files', False)

    @staticmethod
    def _check(key, value):
        if key == 'delete_files':
            if value not in _DELETE_CHOICES:
                raise SettingsError('Delete files must be never, ask or always.')
            return value
        if key in ('keep_original', 'keep_partial_files'):
            if not isinstance(value, bool):
                raise SettingsError(f'{key} must be true or false.')
            return value
        if key == 'clear_completed_days':
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _MAX_DAYS:
                raise SettingsError(f'Days must be a whole number from 0 to {_MAX_DAYS}.')
            return value
        raise SettingsError(f'Unknown setting {key!r}.')


def check_folders(folders) -> dict:
    """The folders the Settings page asks for, checked: a download folder is
    required, music and temp may be empty (meaning the download folder)."""
    if not isinstance(folders, dict):
        raise SettingsError('Folders must be an object.')
    unknown = set(folders) - set(FOLDER_KINDS)
    if unknown:
        raise SettingsError(f'Unknown folder {sorted(unknown)[0]!r}.')
    checked = {}
    for kind in FOLDER_KINDS:
        value = folders.get(kind) or ''
        if not isinstance(value, str):
            raise SettingsError(f'The {kind} folder must be text.')
        value = value.strip().strip('"')
        if not value:
            if kind == 'downloads':
                raise SettingsError('Choose a download folder.')
            checked[kind] = ''
            continue
        if len(value) > _MAX_PATH or not _FOLDER_RE.match(value) or '\0' in value:
            raise SettingsError(f'"{value}" is not a full folder path, like D:\\Videos.')
        if any(part == '..' for part in re.split(r'[\\/]', value)):
            raise SettingsError(f'"{value}" must not contain "..".')
        checked[kind] = value
    return checked


class HostHelper:
    """The Windows helper, seen from the server."""

    def __init__(self, state_dir):
        self.state_dir = state_dir
        self._data = None
        self._last_beat = None
        self._seen_at = None

    def _path(self, name):
        return os.path.join(self.state_dir, name)

    def observe(self):
        """Read the heartbeat. The helper counts as running while its value
        keeps changing, timed on this server's own clock: the clocks of
        Windows and of the Linux machine Docker runs in can drift apart
        after the computer sleeps. The very first value read is trusted only
        when it is recent by the shared clock."""
        data = _read_json(self._path(HELPER_FILE))
        beat = data.get('heartbeat') if data else None
        if isinstance(beat, bool) or not isinstance(beat, (int, float)):
            self._data = None
            return
        if beat != self._last_beat:
            if self._last_beat is not None or abs(time.time() - beat) <= HELPER_STALE_SECONDS:
                self._seen_at = time.monotonic()
            self._last_beat = beat
        self._data = data

    def status(self):
        """What the running helper reports, or None when no helper is running."""
        self.observe()
        data = self._data
        if data is None or self._seen_at is None or time.monotonic() - self._seen_at > HELPER_STALE_SECONDS:
            return None
        folders = data.get('folders') if isinstance(data.get('folders'), dict) else {}
        return {'folders': {kind: str(folders.get(kind) or '') for kind in FOLDER_KINDS}}

    def connected(self) -> bool:
        return self.status() is not None

    def send(self, action, **data) -> str:
        """Leave a request for the helper; returns its id."""
        request_id = uuid.uuid4().hex
        _write_json(self._path(REQUEST_FILE), {'id': request_id, 'action': action, 'time': time.time(), **data})
        log.info('Asked the Windows helper to %s', action)
        return request_id

    async def ask(self, action, timeout, **data):
        """Send a request and wait for the helper's answer (None on timeout)."""
        request_id = self.send(action, **data)
        response_path = self._path(RESPONSE_FILE)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            await asyncio.sleep(0.5)
            response = _read_json(response_path)
            if response and response.get('id') == request_id:
                try:
                    os.remove(response_path)
                except OSError:
                    pass
                return response
        return None
