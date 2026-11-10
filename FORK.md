# MeTube fork: format picker, music and subtitles

A fork of [MeTube](https://github.com/alexta69/metube) (self-hosted web UI for
[yt-dlp](https://github.com/yt-dlp/yt-dlp)). Upstream's README covers everything
else; this page lists what the fork adds and how to run it.

## What the fork adds

| Area | Feature |
|---|---|
| Any link | **Choose format…** (in the menu next to Download): probes the video and lists every stream the site offers: resolution, frame rate, HDR, codec, bitrate and size. *Best* and *Smallest* are marked. Pick a video stream and an audio track, or an audio-only stream. Implements upstream issue [#1032](https://github.com/alexta69/metube/issues/1032). |
| Music | **Original (no re-encode)** is the default audio format: the stream is kept exactly as served (YouTube: Opus), which is both the best quality and the smallest file. |
| Music | Smaller files on request: OPUS 128/96/64 kbps and M4A 192/128/96 kbps really re-encode. Before, yt-dlp copied a same-codec stream and silently ignored the bitrate. A source already at or under the target is left as is. |
| Music | Cover art and tags as upstream (*With cover* by default). |
| Music | **Lyrics** (optional, off by default): looked up on [LRCLIB](https://lrclib.net) and written into the file's lyrics tag (MP3, M4A, Opus, FLAC). Synced lyrics are also saved as a `.lrc` file beside the song. A failed lookup never fails the download. |
| Video | **Subtitles**: *English* (default), *English + other languages*, or *None*. Embedded as switchable tracks and kept as `.srt` beside the video. English uses written subtitles, or YouTube's automatic ones when there are none. Other languages are the written ones only, not 150 machine translations. A subtitle that cannot be fetched only gives a warning. |
| Video | Long videos: more retries (30) and 4 parallel fragments for HLS/DASH. A **disk-space check** runs before the download starts and refuses one that will not fit, merge space included. A failed download resumes from its `.part` file on Retry. |
| Build | Every binary the image downloads (ffmpeg, the PO-token helper, uv) is pinned to one version and checked against its SHA-256. |

## Run locally

Needs Docker. On Windows, run these in a WSL terminal:

```bash
git clone https://github.com/MohanVishe/metube-plus.git && cd metube-plus
cp .env.example .env        # set METUBE_DOWNLOADS to where files should go
docker compose up -d --build
```

Open http://localhost:8081. Stop it with `docker compose down`.

Development (tests, UI build) runs in the dev container: VS Code → **Reopen in
Container**, then:

```bash
uv sync --frozen --group dev && uv run pytest app/tests
cd ui && pnpm install --frozen-lockfile && pnpm run lint && pnpm exec ng test --watch=false && pnpm run build
cd .. && uv run python app/main.py      # serves the built UI on :8081
```

## Security and privacy

- **This PC only.** `docker-compose.yml` publishes the port on `127.0.0.1`. MeTube has no login, so
  never publish it on `0.0.0.0` or the internet without an authenticating reverse proxy.
- **No telemetry.** The only outside connections are yt-dlp to the site you paste, and LRCLIB
  when you turn lyrics on (it receives the artist, title and length).
- **Cookies** are a signed-in session. Upload them only if a video needs them, and use a
  throwaway account.
- **Keep per-download yt-dlp options off** (`ALLOW_YTDL_OPTIONS_OVERRIDES=false`), and don't add
  `exec`, `netrc_cmd` or aria2c options: each was behind a past remote-code-execution bug in
  yt-dlp.
- **Update monthly.** yt-dlp breaks as YouTube changes. Bump `yt-dlp` in `uv.lock`, then the
  ffmpeg and PO-token pins in `Dockerfile` (the comments there explain how).

Downloading from YouTube is against its terms except through its own offline feature, and
downloaded music is for personal use only.
