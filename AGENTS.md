# Agent Guidelines

MediaHarvest: a self-hosted web app that downloads video and music with
yt-dlp. Paste a link, see every format it offers, pick one, get the file.

## Scope

- In scope: anything that makes choosing and getting the right file easier
  (formats, quality, size, subtitles, covers, lyrics, tags) and anything that
  makes running it easier and safer (Docker image, installers, defaults).
- Out of scope: a media library or player, accounts, cloud features, and
  anything that needs a server outside the user's own machine, except the
  site being downloaded from and optional lookups the user turns on (LRCLIB).
- Keep the default install safe: port on 127.0.0.1, per-download yt-dlp
  options off, pinned and checksummed binaries in the image.

## Documentation: where content goes

- `README.md`: what it does, install, everyday use, security. Short.
- `docs/FEATURES.md`: every option on the page, for people who don't read code.
- `docs/HOW-IT-WORKS.md`: the flow from link to file, compression, and which
  file does what, in plain words.
- `docs/CONFIGURATION.md`: every environment variable and yt-dlp option.
- Code comments: the why, next to the code.

## Tech stack

- **Backend:** Python 3.13+, aiohttp, python-socketio 5.x, yt-dlp
- **Frontend:** Angular 22, TypeScript, Bootstrap 5, SASS, ngx-socket-io
- **Package managers:** uv (Python), pnpm (frontend)
- **Container:** Multi-stage Docker (Node builder + Python runtime), multi-arch (amd64/arm64)

## Build & test commands

```bash
# Frontend (run from ui/)
pnpm install --frozen-lockfile
pnpm run lint
pnpm run build
pnpm exec ng test --watch=false

# Backend (run from repo root)
uv sync --frozen --group dev
uv run python -m compileall -q app
uv run pytest app/tests/
```

All of these run in CI (`.github/workflows/ci.yml`) on every push and pull
request, and must pass. Run them in the dev container (`.devcontainer/`).

The backend tests need no frontend build and can run from the repo root or
from `app/`: `app/tests/conftest.py` points `BASE_DIR` at a stand-in UI
directory before `main` is imported.

Every non-markdown push to `main` publishes a new image to
`ghcr.io/mohanvishe/mediaharvest:latest`, so `main` must always be releasable.
A `v*` tag publishes that version and a GitHub Release.

## Code style

Follow `.editorconfig`:
- Python: 4-space indent
- Everything else (TypeScript, YAML, JSON, HTML): 2-space indent
- UTF-8, LF line endings, trim trailing whitespace, final newline

Frontend additionally uses ESLint (`ui/eslint.config.js`) and Prettier (config in `ui/package.json`: `printWidth=100`, `singleQuote=true`).

## Project structure

```
app/main.py          — HTTP server, Socket.IO events, REST API routes, Config class
app/ytdl.py          — Download queue logic, yt-dlp integration
app/download_options.py — DownloadOptions: one request's options, passed whole through the queue
app/subscriptions.py — Channel/playlist subscription manager
app/state_store.py   — JSON-based persistent storage with atomic writes
app/format_catalog.py — The download options (types, codecs, formats, qualities, labels, defaults)
app/dl_formats.py    — Maps those options onto yt-dlp format selectors and options
app/format_probe.py  — The link preview and the All formats picker (read-only)
app/media_extras.py  — Extra yt-dlp postprocessors: disk check, smaller audio, lyrics, compression
app/compress.py      — Makes videos smaller with ffmpeg (levels, per-stream command, GPU)
app/app_settings.py  — The Settings page's choices (settings.json) and the Windows helper's files
windows/MediaHarvest.ps1 — Windows helper: desktop shortcut, start/close, folder picker, restart with folders
app/tests/           — pytest tests (asyncio_mode=auto)
ui/src/app/          — Angular standalone components (no NgModules)
ui/src/_mh-theme.sass — The page's look: colour tokens for light and dark, top bar, tabs, settings
```

## Key conventions

- Backend configuration lives in the `Config` class in `app/main.py` with env-var defaults in `_DEFAULTS`. New env vars go there.
- Download options are defined only in `app/format_catalog.py`. Request validation, `dl_formats`, the UI's form (sent over Socket.IO on connect) and `GET /formats` all read it; never hardcode an option list or id elsewhere. A new codec, format or quality also needs its yt-dlp mapping in `dl_formats`, which `test_format_catalog.py` enforces.
- Real-time communication uses Socket.IO events, not REST polling.
- Frontend uses standalone Angular components with `inject()` for DI, RxJS Subjects for state, and `takeUntilDestroyed()` for cleanup.
- Frontend components use OnPush change detection: subscribe callbacks must call `cdr.markForCheck()`.
- State is persisted as JSON files via `AtomicJsonStore` in `app/state_store.py`.
- Persisted state stays compact: the completed queue deliberately drops bulky entry data (see `_compact_persisted_entry` in `app/ytdl.py`). Don't expand what gets persisted without discussion.
- Custom yt-dlp postprocessors added to `ytdl_params['postprocessors']` run in **list order** within a stage. When combining postprocessors, mirror the ordering the yt-dlp CLI would produce (e.g. sponsor-segment removal before chapter splitting).
- No pre-commit hooks — linting and tests are enforced in CI only.

## Checklist: adding a per-download option

New options on the download form (the `split_by_chapters` pattern) need **all** of
these pieces — the last three are the ones commonly missed:

1. A field on `DownloadOptions` in `app/download_options.py`, set by
   `parse_download_options` in `app/main.py`. The queue's add, playlist,
   failed-add and retry paths all carry that one value, so nothing else in
   them needs touching.
2. A field on `DownloadInfo` in `app/ytdl.py`.
3. A default in `_DOWNLOAD_INFO_DEFAULTS` in `app/ytdl.py`, which old persisted
   records take (a test fails if a `DownloadInfo` field has none).
4. The safe-deserialization field list in `app/ytdl.py`.
5. UI form control + `SettingsStore` persistence in `ui/src/app/app.ts` / `app.html`, and
   the payload in `downloads.service.ts` (plus its spec).
6. The redownload path in `app.ts`, so retries carry the option.
7. If the option makes sense for unattended downloads: threading through
   `app/subscriptions.py` (`SubscriptionInfo` field, serializer, add/update
   routes, `SubscriptionInfo.download_options()`) — or a note in the PR that it's deliberately
   direct-downloads-only.

## Security invariants

User input and extractor-provided metadata (titles, playlist names, URLs) are
untrusted. Use the existing guards instead of hand-rolling:

- User-submitted URLs go through the SSRF guard (see `test_url_guard.py` for the
  expected behavior).
- Anything that becomes a filesystem path goes through `_is_within_directory` and
  `_sanitize_path_component` in `app/ytdl.py` — including values that arrive via
  yt-dlp metadata, which sites can influence.
