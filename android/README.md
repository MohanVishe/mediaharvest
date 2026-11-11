# MediaHarvest for Android

A small app with one screen: paste or share a link, pick Video (Best, 1080p,
720p, 480p) or Audio (M4A, MP3), tap Download. Files are saved to
`Download/MediaHarvest`. Installing it is covered in the main [README](../README.md#android-phone).

## How it works

| File | Does |
|---|---|
| `MainActivity.kt` | Takes shared links, reads the clipboard when Paste is tapped, queues downloads, opens files |
| `Screen.kt` | The screen, in Jetpack Compose. Content is capped at 720dp wide, for tablets and phones held sideways |
| `Theme.kt` | The web app's Mono theme: JetBrains Mono, the same greys and teal, light or dark as the phone is |
| `DownloadService.kt` | Runs downloads one at a time in a foreground service, with a progress notification |
| `Engine.kt` | yt-dlp through [youtubedl-android](https://github.com/JunkFood02/youtubedl-android), which bundles Python, FFmpeg and QuickJS. Also saves files through MediaStore |
| `Downloads.kt` | The download list, kept as JSON in the app's private files |

Video uses the server's "mp4" choice: an mp4 video stream with m4a audio,
preferring H.264 at equal height so every phone plays it. Audio is converted
with FFmpeg and gets the thumbnail as cover art.

On first use the engine unpacks Python and FFmpeg into the app's private
storage, which takes a few seconds once. *Update download engine* replaces
yt-dlp with its newest GitHub release. The app never updates on its own.

## Privacy and security

- Permissions: `INTERNET`, `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_DATA_SYNC`
  and `POST_NOTIFICATIONS`. Nothing else, and no storage permission: MediaStore
  lets an app add files to Downloads without one.
- No analytics, ads, crash reporting or Google Play services.
- `allowBackup="false"`, and the data-extraction rules exclude everything, so
  nothing goes to cloud backup or to a new phone.
- The app's own connections use HTTPS and trust only the system's certificates.
- A link reaches yt-dlp only if it is one `http(s)://` word, so it can never be
  read as a yt-dlp option. `EngineTest.kt` covers this.
- Only the launcher screen is exported. The download service is not.
- The engine pulls in Jackson 2.11.1. The build raises it to 2.18.2, as the
  updater parses GitHub's replies with it.

## Build

Everything builds in Docker. The image has JDK 21 and the Android SDK, and Gradle
comes from the checksum-pinned wrapper. From this folder:

```bash
docker build -t mediaharvest-android-dev .devcontainer
docker run --rm -u ubuntu -v "$PWD/..":/workspace -w /workspace/android \
  -v mediaharvest-gradle:/home/ubuntu/.gradle mediaharvest-android-dev \
  ./gradlew :app:testDebugUnitTest :app:assembleRelease
```

The APKs land in `app/build/outputs/apk/release/`, one per processor type.
Without a signing key they are unsigned and will not install.

### Signing

The release key and its passwords stay outside the repository, in a properties
file passed in as `MH_SIGNING`:

```properties
storeFile=/keys/release.jks
storePassword=…
keyAlias=mediaharvest
keyPassword=…
```

```bash
docker run --rm -u ubuntu -e MH_SIGNING=/keys/keystore.properties \
  -v ~/.config/mediaharvest-android:/keys:ro \
  -v "$PWD/..":/workspace -w /workspace/android \
  -v mediaharvest-gradle:/home/ubuntu/.gradle mediaharvest-android-dev \
  ./gradlew :app:assembleRelease
```

Every update must be signed with the same key, or phones refuse to install it
over the old version. Keep a copy of the key and its passwords somewhere safe.

### Test on an emulator

`.devcontainer/emulator.Dockerfile` adds a headless emulator with the plain
Android image (no Google apps). It needs KVM:

```bash
docker build -t mediaharvest-android-emu -f .devcontainer/emulator.Dockerfile .devcontainer
docker run -d --name mh-emu --device /dev/kvm --group-add "$(getent group kvm | cut -d: -f3)" \
  -v "$PWD/app/build/outputs/apk":/apk:ro mediaharvest-android-emu \
  emulator -avd test -no-window
docker exec mh-emu adb install /apk/release/MediaHarvest-1.0.0-x86_64-release.apk
```
