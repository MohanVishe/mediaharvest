# Configuration

MediaHarvest is configured with environment variables: `-e NAME=value` with `docker run`, or the `environment:` section of `docker-compose.yml`. Defaults are the Docker image's; outside Docker, the directories default to the working directory.

MediaHarvest is built on [MeTube](https://github.com/alexta69/metube), so the guides in [its wiki](https://github.com/alexta69/metube/wiki) apply here as well; they are linked below where they help.
## Runtime and permissions

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PUID` / `PGID` | `1000` | User and group MediaHarvest runs as and writes files with. Legacy `UID`/`GID` also work. |
| `UMASK` | `022` | Umask for the files MediaHarvest creates. |
| `CHOWN_DIRS` | `true` | Make `PUID:PGID` the owner of the download, state and temp directories at startup. With `false`, MediaHarvest's user must already have access. |
| `LOGLEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` or `NONE`. |
| `ENABLE_ACCESSLOG` | `false` | Log every HTTP request. |
| `DEFAULT_THEME` | `auto` | UI theme: `light`, `dark`, `auto` to follow the system, or `terminal` (dark, styled like a command-line tool). |

## Downloads

| Variable | Default | Description |
| :--- | :--- | :--- |
| `MAX_CONCURRENT_DOWNLOADS` | `3` | Downloads that run at once; the rest wait their turn. |
| `DEFAULT_OPTION_PLAYLIST_ITEM_LIMIT` | `0` | Default for the **Items Limit** field: how many entries of a playlist or channel to download (`0` = all). |
| `CLEAR_COMPLETED_AFTER` | `0` | Seconds before finished and failed downloads leave the Completed list (`0` = never). |
| `DELETE_FILE_ON_TRASHCAN` | `false` | Also delete the file from disk when its entry is removed from Completed. `ask` prompts each time. |
| `SUBSCRIPTION_DEFAULT_CHECK_INTERVAL` | `60` | Default minutes between checks of a [subscription](https://github.com/alexta69/metube/wiki/Subscriptions). |
| `SUBSCRIPTION_SCAN_PLAYLIST_END` | `50` | Newest entries fetched each time a subscription is checked. |
| `SUBSCRIPTION_MAX_SEEN_IDS` | `50000` | Video IDs remembered per subscription, to bound the state file's size. |

## Directories

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DOWNLOAD_DIR` | `/downloads` | Where downloads are saved. |
| `AUDIO_DOWNLOAD_DIR` | same as `DOWNLOAD_DIR` | Where audio-only downloads are saved, to keep them apart from video. |
| `TEMP_DIR` | `/downloads` | Where files are written while downloading. An SSD or `tmpfs` is faster, but on a RAM disk interrupted downloads can't resume. |
| `STATE_DIR` | `/downloads/.metube` | Where MediaHarvest keeps its queue, history, subscriptions, uploaded cookies and the Settings page's choices (`settings.json`). |
| `CUSTOM_DIRS` | `true` | Show a **Download Folder** field under Advanced Options, to save into a subfolder of the download directory. |
| `CREATE_CUSTOM_DIRS` | `true` | Let that field create folders that don't exist yet. |
| `CUSTOM_DIRS_EXCLUDE_REGEX` | `(^\|/)[.@].*$` | Folders left out of the field's suggestions; the default hides names starting with `.` or `@`. Empty hides none. |
| `DEFAULT_FOLDER` | | Folder the field starts with, relative to the download directory. Requires `CUSTOM_DIRS`. |
| `DOWNLOAD_DIRS_INDEXABLE` | `false` | Serve browsable listings of the download directories. |

### Folders with Docker Compose

`docker-compose.yml` mounts four folders from this computer. Set them in `.env`;
each one left out falls back to the download folder.

| `.env` variable | Mounted at | For |
|---|---|---|
| `MEDIAHARVEST_DOWNLOADS` | `/downloads` | Finished files |
| `MEDIAHARVEST_MUSIC` | `/music` | Audio downloads. Also set `MEDIAHARVEST_MUSIC_DIR=/music` |
| `MEDIAHARVEST_TEMP` | `/temp` | Downloads in progress. Also set `MEDIAHARVEST_TEMP_DIR=/temp` |
| `MEDIAHARVEST_STATE` | `/state` | Lists and settings (default: `.metube` in the download folder) |

On Windows, the desktop shortcut's helper sets all of these from the Settings
page and restarts MediaHarvest with them; there is nothing to edit by hand.

### The Settings page

**Files** on the Settings page change four things while MediaHarvest runs, and
are saved in `settings.json` in `STATE_DIR`. A saved choice wins over the
environment variable: `DELETE_FILE_ON_TRASHCAN` (removing an item),
`CLEAR_COMPLETED_AFTER` (whole days only; a value in seconds that is not whole
days shows as *As set in .env* until changed), keeping the original after
compressing, and keeping partial files of cancelled or failed downloads (both
off by default).

### Very large downloads

A 138-hour video at 720p is about 51 GB, and merging needs about as much again
while it runs. Keep the download folder on a drive with that much room.

On **Windows with Docker Desktop**, put the download folder on a Windows drive
(`C:\Users\you\Downloads\MediaHarvest`, which is what `install.ps1` does, or
`/mnt/c/...` from WSL). A folder inside WSL lives in a virtual disk that reports
far more free space than the drive under it has, so the disk check before a
download can't warn you in time.

Downloads that stop part-way resume by themselves; there is nothing to set. See
"Video, including very long ones" in the [README](../README.md).

### Compressing videos

Compression is chosen per download (**Compress** and **Resolution**) or from a
video's row in Completed. While it runs it needs up to the video's own size free
on the same drive. How it works and what the levels do:
[HOW-IT-WORKS.md](HOW-IT-WORKS.md#making-videos-smaller).

| Variable | Default | Description |
| :--- | :--- | :--- |
| `COMPRESS_GPU` | `auto` | `auto` uses an NVIDIA graphics card for the **Any device** level when the container can reach one; `off` always uses the processor. |

**Using an NVIDIA graphics card.** The container needs access to it. The
installers add this by themselves when they find a card Docker can use. With
Docker Compose, start with [docker-compose.gpu.yml](../docker-compose.gpu.yml)
as well:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

or add `COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml` to `.env`
(on Windows separate the two with `;`). With `docker run`, add
`--gpus all -e NVIDIA_DRIVER_CAPABILITIES=compute,utility,video`. Docker
Desktop on Windows passes the card through by itself; on Linux install the
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
The log says which one compression uses (`Compression uses the NVIDIA GPU for
H.264`).

**From the command line**, to compress a file in the download folder and keep
the original:

```bash
docker exec mediaharvest python3 /app/app/compress.py medium "/downloads/video.mkv" --output "/downloads/video.small.mkv"
```

Leave out `--output` to replace the file in place. The level is `light`,
`medium`, `strong` or `compatible` (Any device, which always writes an `.mp4`);
add `--max-height 720` (or 1080, 480, 360) to limit the resolution.

## File naming

Templates use [yt-dlp's output template syntax](https://github.com/yt-dlp/yt-dlp/blob/master/README.md#output-template). How MediaHarvest applies them is explained in [Output templates](https://github.com/alexta69/metube/wiki/Output-templates).

| Variable | Default | Description |
| :--- | :--- | :--- |
| `OUTPUT_TEMPLATE` | `%(title)s.%(ext)s` | Filename for downloads. |
| `OUTPUT_TEMPLATE_PLAYLIST` | `%(playlist_title)s/%(title)s.%(ext)s` | Filename for items added from a playlist. Empty means `OUTPUT_TEMPLATE`. |
| `OUTPUT_TEMPLATE_CHANNEL` | `%(channel)s/%(title)s.%(ext)s` | Filename for items added from a channel. Empty means `OUTPUT_TEMPLATE`. |
| `OUTPUT_TEMPLATE_CHAPTER` | `%(title)s - %(section_number)02d - %(section_title)s.%(ext)s` | Default filename for each chapter when **Split by chapters** is on. |

## yt-dlp

| Variable | Default | Description |
| :--- | :--- | :--- |
| `YTDL_OPTIONS` | `{}` | Options for every download, as a JSON object — see [yt-dlp options](#yt-dlp-options). |
| `YTDL_OPTIONS_FILE` | | Path to a JSON file of such options. Reloaded when it changes; wins over `YTDL_OPTIONS` for the same key. |
| `YTDL_OPTIONS_PRESETS` | `{}` | Named option bundles, picked per download in the UI. |
| `YTDL_OPTIONS_PRESETS_FILE` | | Path to a JSON file of presets. Reloaded when it changes; wins over `YTDL_OPTIONS_PRESETS` for the same name. |
| `ALLOW_YTDL_OPTIONS_OVERRIDES` | `false` | Show a field for per-download yt-dlp options in the UI. Trusted users only: it allows running commands in the container. |
| `YTDL_NIGHTLY_UPDATE_TIME` | | Use [nightly yt-dlp builds](https://github.com/yt-dlp/yt-dlp-nightly-builds), upgrading and restarting daily at this time (`HH:MM`, 24-hour). |

## Web server and network

| Variable | Default | Description |
| :--- | :--- | :--- |
| `HOST` | `0.0.0.0` | Address to listen on. The default is every IPv4 interface; `*` (or empty) adds IPv6; `::` is IPv6 only. |
| `PORT` | `8081` | Port to listen on. |
| `URL_PREFIX` | `/` | Base path, for serving MediaHarvest under a subpath of a [reverse proxy](https://github.com/alexta69/metube/wiki/Reverse-proxy-configurations). |
| `HTTPS` | `false` | Serve HTTPS directly, using `CERTFILE` and `KEYFILE`. |
| `CERTFILE` / `KEYFILE` | | Paths to the HTTPS certificate and key. |
| `PUBLIC_HOST_URL` | `download/` | Base URL for the links to completed files. The default is relative to MediaHarvest itself; set a full URL if the files are served from elsewhere. |
| `PUBLIC_HOST_AUDIO_URL` | `audio_download/` | The same, for audio downloads. |
| `CORS_ALLOWED_ORIGINS` | | Comma-separated origins allowed to call MediaHarvest from other sites, as [browser extensions and bookmarklets](https://github.com/alexta69/metube/wiki/Sending-links-to-MeTube) do. `*` allows any site, so prefer naming them. |
| `ALLOW_PRIVATE_ADDRESSES` | `false` | Allow URLs on private and internal addresses, turning off SSRF protection. Needed for Fake-IP proxy clients, not for ordinary proxies — [details](https://github.com/alexta69/metube/wiki/Troubleshooting-FAQ#refusing-to-fetch-internal-host-proxies-and-vpns). |
| `ROBOTS_TXT` | | Path to a `robots.txt` file to serve, mounted into the container. |

## yt-dlp options

yt-dlp options are JSON objects keyed by yt-dlp's [API option names](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py#L224), which differ from its command-line flags ([converter](https://github.com/yt-dlp/yt-dlp/blob/master/devscripts/cli_to_api.py)). They apply at three levels, and for an option set at more than one, the more specific level wins:

1. **Global** — `YTDL_OPTIONS` and `YTDL_OPTIONS_FILE`, for every download.
2. **Presets** — `YTDL_OPTIONS_PRESETS` and `YTDL_OPTIONS_PRESETS_FILE`, picked per download under **Advanced Options**.
3. **Overrides** — typed into the UI for a single download, when `ALLOW_YTDL_OPTIONS_OVERRIDES` is on.

```yaml
environment:
  - 'YTDL_OPTIONS={"writesubtitles": true, "subtitleslangs": ["en", "de"], "updatetime": false}'
```

The [yt-dlp options guide](https://github.com/alexta69/metube/wiki/yt-dlp-options) covers presets, overrides and option files in detail, and the [YTDL_OPTIONS Cookbook](https://github.com/alexta69/metube/wiki/YTDL_OPTIONS-Cookbook) has ready-made recipes.

## Keeping yt-dlp up to date

Sites change constantly, and yt-dlp keeps up with frequent releases. A new MediaHarvest image is published automatically after every yt-dlp stable release, so keep yours updated (`docker compose pull && docker compose up -d`) — [watchtower](https://github.com/nicholas-fedor/watchtower) can do it for you. To follow yt-dlp's nightly builds instead, set `YTDL_NIGHTLY_UPDATE_TIME`.

## Troubleshooting and support

MediaHarvest is only a UI for yt-dlp, so most download failures are yt-dlp's. Reproduce them with yt-dlp inside the container, and once a set of options works there, carry it over to `YTDL_OPTIONS`:

```bash
docker exec -ti mediaharvest sh
cd /downloads
yt-dlp <url>
```

The [Troubleshooting FAQ](https://github.com/alexta69/metube/wiki/Troubleshooting-FAQ) covers common problems. Bugs in MediaHarvest itself go to [its issues](https://github.com/MohanVishe/mediaharvest/issues).
