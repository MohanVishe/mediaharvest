# Features

Everything MediaHarvest can do, in plain words, in the order you meet it on
the page. For what happens behind the page, see
[HOW-IT-WORKS.md](HOW-IT-WORKS.md). For settings an administrator changes, see
[CONFIGURATION.md](CONFIGURATION.md).

## Contents

- [Paste a link](#paste-a-link)
- [Video](#video)
- [Making videos smaller (Compress)](#making-videos-smaller-compress)
- [Audio](#audio)
- [Captions and Thumbnail](#captions-and-thumbnail)
- [All formats](#all-formats)
- [Advanced Options](#advanced-options)
- [Playlists, channels and subscriptions](#playlists-channels-and-subscriptions)
- [Downloading](#downloading)
- [Completed](#completed)
- [On your phone or as an app](#on-your-phone-or-as-an-app)

## Paste a link

Paste a link to a video, a playlist or a channel into the box at the top. A
card appears with the title, the picture, the length and how many video and
audio formats the site offers. Nothing is downloaded yet.

YouTube and [more than a thousand other sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)
work. Then choose what you want with the four buttons below the box:
**Video**, **Audio**, **Captions** or **Thumbnail**, and press **Download**.

MediaHarvest remembers your last choices in this browser, so next time you
can paste and press Download straight away.

## Video

| Option | What it does |
|---|---|
| **Format** | *Auto* picks the best the site offers. *MP4* always gives an .mp4 file. *iOS Compatible* gives a file iPhones and iPads play without an app. |
| **Quality** | The picture size: *Best*, or a fixed height such as 1080p or 720p. If the video doesn't come in that size, the nearest smaller one is used. |
| **Subtitles** | *English* (the default) adds English subtitles: the written ones, or YouTube's automatic ones when there are none. *English + other languages* adds every written language too. They are added as tracks you switch on in the player, and saved beside the video as `.srt` files. *None* skips them. |
| **Compress** | Makes the video smaller after it downloads. See the next section. |
| **Resolution** | Shown when Compress is on: makes the compressed video no taller than this. |

**Very long videos** are fine. There is no limit on length or size. Before a
download starts, MediaHarvest checks the drive has room. If the download
stops part-way, it carries on by itself (see [Downloading](#downloading)).

## Making videos smaller (Compress)

Pick a level before you press Download, or compress a video later from
[Completed](#completed). It runs on your own computer with open-source tools
(ffmpeg), with no limits and no upload anywhere.

| Level | What you get | Plays on | Smaller by (tested) |
|---|---|---|---|
| **Off** | The file as downloaded | | |
| **Light** | Looks the same | Current phones, computers, browsers | about 24% |
| **Medium** | Very close; fine detail a little softer | Current phones, computers, browsers | about 51% |
| **Strong** | Lowered to 480p | Current phones, computers, browsers | about 64% |
| **Any device** | An MP4 that plays everywhere | Every TV, phone and computer, old ones too | about 20% |

The figures come from a 138-hour 720p YouTube video. Every video is
different: one the site already squeezed hard may shrink less.

**Which one?**
- To save space and keep the picture, pick **Medium**.
- For talks, lectures and audiobooks, where the picture matters less, pick
  **Strong**.
- If a TV, an older phone or a car screen won't play your videos, pick
  **Any device**.

**Resolution** adds a size limit to any level: *Original* (no change), 1080p, 720p,
480p or 360p. A smaller picture means a smaller file. A video is never made
bigger than it already is.

**What is kept:** the subtitle tracks, every sound track (for example a
second language), the chapters and the title and artist tags. With Any device,
the file becomes an `.mp4` (an `.mkv` is converted, and the old file removed
once the new one is complete).

**Safe:** the smaller copy is written next to the original and only replaces
it when it's finished. If it wouldn't save at least 5%, or anything goes
wrong, the original stays exactly as it was and the row tells you why.

**How long it takes:** the first three levels take about 4 minutes per hour of
video on a 12-core computer. Any device uses the computer's NVIDIA graphics
card when there is one (about twice as fast as without). Very long videos take
hours: for a 100-hour recording, downloading a lower **Quality** in the first
place (for example 480p) is often quicker than compressing.

## Audio

| Option | What it does |
|---|---|
| **Format** | *Original* keeps the sound exactly as the site sends it: the best quality, and usually the smallest file. *OPUS*, *M4A (AAC)* and *MP3* convert it, at the size you pick (for example MP3 320, 192 or 128 kbps). *WAV* and *FLAC* are uncompressed, for editing. |
| **Tags** | *With cover* writes the title, the artist and the thumbnail as cover art into the file. *No cover* skips the picture; *None* writes nothing. |
| **Lyrics** | Looks the song up on [LRCLIB](https://lrclib.net) and writes the lyrics into the file. When timed lyrics exist, they're also saved as a `.lrc` file for players that scroll them. Only the artist, title and length are sent to LRCLIB. |

**Which format?** Keep *Original* unless a player can't open it. For an older
car stereo, MP3. For Apple devices, M4A. To save space, Opus at 96 kbps still
sounds clean for music. The size of each choice is shown before you download.

## Captions and Thumbnail

**Captions** saves only the subtitles, as a file. Pick the **Format** (SRT
works almost everywhere; TXT is the plain text, handy for reading or
searching), the **Language**, and the **Subtitle Source**: written by people
(*Manual*), made by YouTube (*Auto*), or one of them first.

**Thumbnail** saves the video's picture as a JPG.

## All formats

**All formats**, next to Download, lists every stream the site offers: size,
frame rate, HDR, codec, bitrate and file size, with the best and the smallest
marked. Pick a video and a sound stream and download exactly those.

## Advanced Options

Click **Advanced Options** under the buttons.

| Option | What it does |
|---|---|
| **Video Codec** | Prefer one picture format. H.264 plays everywhere; AV1 and VP9 are smaller at the same quality. |
| **Download Folder** | Save into a sub-folder of the download folder. Type a new name to make one. |
| **Custom Name Prefix** | Text added to the front of the file names. |
| **Remove sponsor segments** | Cuts out sponsor parts marked by [SponsorBlock](https://sponsor.ajay.app) viewers (YouTube only). |
| **Split by chapters** | Saves each chapter of the video as its own file. **Template** sets their names. |
| **Clip start / Clip end** | Download only part of a video, for example from 2:26 to 3:24. |
| **Auto Start** | Off means downloads wait in the list until you start them. |
| **Items Limit** | For playlists and channels: download only the first N items (0 means all). |
| **Option Presets** | Ready-made yt-dlp settings an administrator added (see CONFIGURATION.md). |
| **Video Password** | For password-protected videos, for example on Vimeo. Not saved. |
| **Cookies** | Upload a `cookies.txt` exported from your browser, for videos that need you signed in. Use a separate account: cookies are a signed-in session. |
| **Import / Export / Copy URLs** | Add many links at once from a list, or save the links in your lists. |

## Playlists, channels and subscriptions

Paste a playlist or channel link and every item is added. The arrow next to
Download has more actions:
- **Pick from playlist** shows the items first, so you can choose some.
- **Subscribe to channel or playlist** checks it regularly and downloads new
  uploads by itself. The **Subscriptions** list at the bottom shows each one,
  when it was last checked, and lets you check now or remove it. Under
  Advanced Options you can set how often it checks, only take titles that
  match a pattern, and skip members-only videos.

## Downloading

Each download shows a progress bar, the speed and the time left. Up to three
run at once; the rest wait their turn. Cancel one, or several at once with the
boxes on the left.

**When a download stops, it carries on.** YouTube's download links run out
after about 6 hours, and networks drop. MediaHarvest then shows *Reconnecting*,
waits a little, gets a fresh link and continues from where it stopped, so
nothing is downloaded twice. The waits grow from 15 seconds to 5 minutes. After
10 failed tries in a row it marks the download as failed; **Retry** still
continues from the part already saved. A restart of the computer works the
same way.

While a video is being compressed, its bar says **Compressing** with a
percentage.

## Completed

Finished downloads move here.

- **Click the title** (or the download arrow) to save the file to the device
  you're using. Files are also in the download folder on the computer.
- **Share** sends the file to another app (on phones and some browsers).
- **Compress** (the arrows-pointing-in button) makes a finished video
  smaller: choose a **Resolution** at the top of the menu if you like, then a
  level. The row shows the progress, then for example *"Compressed (Medium):
  97.50 MB → 58.82 MB, 40% smaller"*.
- A failed download shows a red cross. Click it for the reason, copy the
  details, or press **Retry**.
- **Clear completed**, **Clear failed**, **Retry failed** and **Download
  Selected** work on many rows at once; the sort button switches between
  newest and oldest first. Removing a row keeps the file unless your
  administrator set it otherwise.

## On your phone or as an app

- **As an app:** in Chrome or Edge, choose *Install MediaHarvest* in the
  address bar. It then opens in its own window.
- **Light or dark:** the button at the top right switches the theme, or
  follows your system.
- **From a phone:** MediaHarvest answers only on the computer it runs on,
  because it has no login. To use it from other devices, put a reverse proxy
  with a login in front of it; the README explains how.
