# Pinned to a major version rather than the lts-alpine floating tag: that tag
# has lagged behind and resolved to a Node patch older than the Angular CLI's
# minimum supported version, breaking the build. node:22-alpine currently
# satisfies @angular/cli's >=22.22.3 requirement.
#
# Pinned further, to a digest: Docker Hub rebuilt node:22-alpine on 2026-09-17
# with the same Node (22.23.2) but refreshed Alpine layers, and that rebuild
# dies under QEMU while cross-building the arm64 leg — `qemu: uncaught target
# signal 4 (Illegal instruction)`, exit 132, during `pnpm install`. Three
# consecutive release builds failed identically on it while every other input
# (runner image, binfmt digest, pnpm version, lockfile) was unchanged.
#
# This digest is the last image known to cross-build cleanly (built 2026-07-29).
# It ships nothing: this stage is thrown away and only ui/dist is copied out.
# Unpin once the arm64 leg builds natively instead of under emulation, or once
# a later node:22-alpine is confirmed to survive QEMU.
FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS builder

WORKDIR /metube
COPY ui ./
RUN corepack enable && corepack prepare pnpm --activate
RUN CI=true pnpm install && pnpm run build


FROM python:3.14-slim

WORKDIR /app

# Fork: uv comes from its pinned image instead of `curl | sh` of whatever the
# install script serves that day. Removed again after the sync below.
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock docker-entrypoint.sh ./

# Use sed to strip carriage-return characters from the entrypoint script (in case building on Windows)
# Install dependencies
RUN sed -i 's/\r$//g' docker-entrypoint.sh && \
    chmod +x docker-entrypoint.sh && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      xz-utils \
      unzip \
      aria2 \
      coreutils \
      gosu \
      curl \
      tini \
      build-essential && \
    UV_PROJECT_ENVIRONMENT=/usr/local uv sync --frozen --no-dev --compile-bytecode && \
    uv cache clean && \
    rm -f /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/uvw && \
    apt-get purge -y --auto-remove build-essential && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir /.cache && chmod 777 /.cache

ARG TARGETARCH

# ffmpeg is a static build of upstream's 8.1 release branch rather than
# Debian's package: Debian stable stays a major version behind, and its 7.1
# cannot seek into YouTube's HLS formats, so clip downloads came out with no
# video (#1092). BtbN's builds are the ones yt-dlp's own FFmpeg-Builds fork;
# the release-branch build takes 8.1 point releases only.
#
# Fork: pinned to one dated build and checked against its SHA-256, instead of
# the rolling "latest" with no check. A swapped or tampered file now fails the
# build rather than landing in the image. To update: pick a newer
# autobuild-* release, copy the two lines for the 8.1 linux64/linuxarm64 gpl
# tarballs from its checksums.sha256, and test clips and audio extraction.
# BtbN prunes old autobuilds, so an old pin fails closed with a 404.
ARG FFMPEG_RELEASE=autobuild-2026-11-09-12-42
ARG FFMPEG_VERSION=n8.1.3-34-ga35157abb9
ARG FFMPEG_BRANCH=8.1
ARG FFMPEG_SHA256_AMD64=23c6279d9f10afbcc273082256ae2073495595ab53fbcd729a5a93913b3fdd75
ARG FFMPEG_SHA256_ARM64=28a4fdb4ac17ffb3b41dac009ceedb844de9988111d94d61f42521ff5aba6ee4
RUN case "$TARGETARCH" in \
      amd64) FFMPEG_ARCH="linux64"; FFMPEG_SHA256="$FFMPEG_SHA256_AMD64" ;; \
      arm64) FFMPEG_ARCH="linuxarm64"; FFMPEG_SHA256="$FFMPEG_SHA256_ARM64" ;; \
      *) echo "Unsupported TARGETARCH: $TARGETARCH" >&2; exit 1 ;; \
    esac && \
    curl -fsSL -o /tmp/ffmpeg.tar.xz \
      "https://github.com/BtbN/FFmpeg-Builds/releases/download/${FFMPEG_RELEASE}/ffmpeg-${FFMPEG_VERSION}-${FFMPEG_ARCH}-gpl-${FFMPEG_BRANCH}.tar.xz" && \
    echo "${FFMPEG_SHA256}  /tmp/ffmpeg.tar.xz" | sha256sum -c - && \
    tar -xJf /tmp/ffmpeg.tar.xz -C /usr/local/bin --strip-components=2 --wildcards '*/bin/ffmpeg' '*/bin/ffprobe' && \
    rm /tmp/ffmpeg.tar.xz && \
    ffmpeg -version | head -n 1

# Fork: the PO token helper is a third-party binary that runs inside the
# container (loopback only, never published). Pinned to one release and its
# SHA-256 instead of resolving "latest" at build time. The project publishes
# no checksum file; these hashes were taken from the v0.8.1 assets on
# 2026-11-10. Bump deliberately, re-hashing the three files.
ARG BGUTIL_TAG=v0.8.1
ARG BGUTIL_SHA256_AMD64=e7c264a574fa2705b6e5dc62283a8a4e80130f27b9d7e9df44e6b09aa6151a87
ARG BGUTIL_SHA256_ARM64=4f4a1f681dba45e695e1c14d314517da180a1fd374afd09d634fd80ef6d0284b
ARG BGUTIL_PLUGIN_SHA256=99fd83b98fa93b193d6a3b69dc74410d76e7a2b889868c54d16121cac9060344
RUN case "$TARGETARCH" in \
      amd64) BGUTIL_ARCH="x86_64"; BGUTIL_SHA256="$BGUTIL_SHA256_AMD64" ;; \
      arm64) BGUTIL_ARCH="aarch64"; BGUTIL_SHA256="$BGUTIL_SHA256_ARM64" ;; \
      *) echo "Unsupported TARGETARCH: $TARGETARCH" >&2; exit 1 ;; \
    esac && \
    curl -fsSL -o /usr/local/bin/bgutil-pot \
      "https://github.com/jim60105/bgutil-ytdlp-pot-provider-rs/releases/download/${BGUTIL_TAG}/bgutil-pot-linux-${BGUTIL_ARCH}" && \
    echo "${BGUTIL_SHA256}  /usr/local/bin/bgutil-pot" | sha256sum -c - && \
    chmod +x /usr/local/bin/bgutil-pot && \
    PLUGIN_DIR="$(python3 -c 'import site; print(site.getsitepackages()[0])')" && \
    curl -fsSL -o /tmp/bgutil-ytdlp-pot-provider-rs.zip \
      "https://github.com/jim60105/bgutil-ytdlp-pot-provider-rs/releases/download/${BGUTIL_TAG}/bgutil-ytdlp-pot-provider-rs.zip" && \
    echo "${BGUTIL_PLUGIN_SHA256}  /tmp/bgutil-ytdlp-pot-provider-rs.zip" | sha256sum -c - && \
    unzip -q /tmp/bgutil-ytdlp-pot-provider-rs.zip -d "${PLUGIN_DIR}" && \
    rm /tmp/bgutil-ytdlp-pot-provider-rs.zip

COPY app ./app
COPY --from=builder /metube/dist/metube ./ui/dist/metube

ENV PUID=1000
ENV PGID=1000
ENV UMASK=022

ENV DOWNLOAD_DIR=/downloads
ENV STATE_DIR=/downloads/.metube
ENV TEMP_DIR=/downloads
ENV PORT=8081
VOLUME /downloads
EXPOSE 8081
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD case "$HTTPS" in true|True|on|1) curl -fsSk "https://localhost:${PORT}/";; *) curl -fsS "http://localhost:${PORT}/";; esac || exit 1

# Add build-time argument for version
ARG VERSION=dev
ENV METUBE_VERSION=$VERSION

ENTRYPOINT ["/usr/bin/tini", "-g", "--", "./docker-entrypoint.sh"]
