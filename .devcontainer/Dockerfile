# Dev container for this MeTube fork: Python 3.14 + uv for the backend,
# Node 22 + pnpm (corepack) for the Angular UI, ffmpeg for yt-dlp's
# postprocessors (audio extraction, cover art, metadata, merging).
# The production image is the root Dockerfile, not this one.
FROM node:22.22-bookworm-slim AS node

FROM mcr.microsoft.com/devcontainers/python:3.14-trixie
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /bin/
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && ln -s ../lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack \
    && corepack enable
ENV UV_LINK_MODE=copy \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
