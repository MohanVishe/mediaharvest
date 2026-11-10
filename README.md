<p align="center">
  <img src="docs/logo.png" alt="" width="96" height="96">
</p>

<h1 align="center">MediaHarvest</h1>

<p align="center">
  Paste a link, see every format the video offers, and save the video or music
  in the quality and size you choose. It runs on your own computer, in Docker.
</p>

![A pasted YouTube link: the preview shows the video, its 13 video and 12 audio formats, and a Choose format button](docs/screenshot-preview.jpg)

## What it does

**Any link, every option.** Paste a link and MediaHarvest shows what it is and how
many formats it has. **All formats** lists every stream: resolution, frame rate,
HDR, codec, bitrate and file size, with the best and the smallest marked. Or just
press **Download** with your usual settings. YouTube and
[more than a thousand other sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)
work, through [yt-dlp](https://github.com/yt-dlp/yt-dlp).

**Music that sounds right and stays small.**
- *Original* keeps the audio exactly as the site serves it: the best quality and
  usually the smallest file.
- Need it smaller? Opus 128/96/64 kbps, M4A 192/128/96 kbps or MP3 320/192/128 kbps
  really re-encode to that size. A source already below the size you pick is kept as is.
- The thumbnail is embedded as cover art, with title and artist tags.
- Optional lyrics from [LRCLIB](https://lrclib.net), written into the file, plus a
  timed `.lrc` file when available.

**Video, including very long ones.**
- Subtitles: English by default (written ones, or YouTube's automatic ones when
  there are none), English plus other languages, or none. They're embedded as
  switchable tracks and saved beside the video as `.srt`.
- Long downloads retry, fetch 4 pieces at a time, and resume after a failure. Disk
  space is checked before a download starts.

**And more:** whole playlists and channels, subscriptions that fetch new uploads,
clips by start and end time, sponsor-segment removal, splitting by chapters,
captions or thumbnails on their own.

![The format picker: every stream of the video with its quality, codec, bitrate and size](docs/screenshot-picker.jpg)

## Install

You need [Docker](https://docs.docker.com/get-docker/) (on Windows and Mac:
Docker Desktop, started). MediaHarvest then opens at **http://localhost:8081**.

**Windows** (PowerShell):

```powershell
irm https://raw.githubusercontent.com/MohanVishe/mediaharvest/main/install.ps1 | iex
```

**Linux, macOS, WSL:**

```bash
curl -fsSL https://raw.githubusercontent.com/MohanVishe/mediaharvest/main/install.sh | sh
```

The installer makes one folder (`MediaHarvest` in your user folder) with the
settings, starts MediaHarvest and saves files to `Downloads/MediaHarvest`. Run it
again any time to update. You can read both scripts before running them:
[install.ps1](install.ps1), [install.sh](install.sh).

**Docker Compose**, from a clone of this repository:

```bash
cp .env.example .env     # optional: download folder, port
docker compose up -d     # add --build to build from source
```

**docker run:**

```bash
docker run -d --name mediaharvest --restart unless-stopped \
  -p 127.0.0.1:8081:8081 -v "$HOME/Downloads/MediaHarvest:/downloads" \
  ghcr.io/mohanvishe/mediaharvest:latest
```

Images are built for amd64 and arm64. `latest` follows `main`, and every build
also gets a dated tag to pin.

### Update, stop, remove

In the install folder (or the repository):

| | |
|---|---|
| Update | `docker compose pull && docker compose up -d` |
| Stop | `docker compose down` |
| Remove | `docker compose down --rmi all`, then delete the folder |

A new image is published after every yt-dlp release, so updating also keeps
sites working.

## Use it

1. Paste a link. A card shows the video and how many formats it has.
2. Pick **Video**, **Audio**, **Captions** or **Thumbnail**, and the format below.
   Then press **Download**, or open **All formats** to choose the exact stream.
3. Finished files appear under **Completed**. Click one to save it to the device
   you're using; they're also in the download folder.

**Which audio format?** Keep *Original* unless a player can't open it. For an
older car stereo or iPod, pick MP3. For Apple devices, M4A. To save space, pick Opus
at 96 kbps: a smaller file that still sounds clean for music. The picker shows the
size each choice will have before you download.

**As an app:** in Chrome or Edge, use *Install MediaHarvest* in the address bar.
It then opens in its own window, like a desktop app.

**From your phone or another computer:** MediaHarvest has no login, so it only
answers on the computer it runs on. To reach it from other devices, put a
reverse proxy with a login and HTTPS in front of it (for example Caddy or
Nginx; [examples](https://github.com/alexta69/metube/wiki/Reverse-proxy-configurations)),
then publish the port on your network address instead of `127.0.0.1`. On Android,
once it's installed as an app over HTTPS, you can share a link straight to it from
the YouTube app.

Every setting (download folders, file names, yt-dlp options, HTTPS) is in
[docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Security and privacy

- **This computer only** by default, as above.
- **No tracking, no accounts.** The only outside connections are to the site you
  download from, and to LRCLIB when you turn lyrics on (it receives the artist,
  title and length).
- **Verified image.** Every binary the image downloads is pinned to one version
  and checked against its SHA-256, and CI scans for known vulnerabilities.
- **Cookies** are a signed-in session. Upload them only when a video needs them,
  and use a separate account.
- Keep **per-download yt-dlp options** off (the default): they can run commands.

Details and how to report a problem: [SECURITY.md](SECURITY.md).

## Develop

Everything builds and runs in Docker, through the dev container. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## Legal

Download only what you have the right to. Some sites' terms forbid downloading
except through their own apps; downloaded music is for personal use.

## License

[AGPL-3.0](LICENSE). MediaHarvest is based on
[MeTube](https://github.com/alexta69/metube) (AGPL-3.0); see [NOTICE](NOTICE).
