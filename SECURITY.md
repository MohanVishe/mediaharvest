# Security Policy

## Reporting a vulnerability

Report it privately through GitHub: the repository's **Security** tab →
**Report a vulnerability**. Please don't open a public issue for a security
problem. Include how to reproduce it and the version shown in the page footer.

Only the latest image is supported; update before reporting
(`docker compose pull && docker compose up -d`).

## What is and isn't a vulnerability

MediaHarvest has no login by design. The default setup publishes it on
`127.0.0.1`, so only the computer it runs on can reach it. Opening it to a
network without an authenticating reverse proxy is a configuration choice, so
"the page is reachable without a login" is not a vulnerability.

## Built-in protections

- Links to private and internal addresses are refused (SSRF guard), unless
  `ALLOW_PRIVATE_ADDRESSES` is set.
- Requests from other websites are refused (cross-site request guard), unless
  listed in `CORS_ALLOWED_ORIGINS`.
- Per-download yt-dlp options are off by default (`ALLOW_YTDL_OPTIONS_OVERRIDES`):
  they can run commands inside the container.
- File paths built from site metadata are kept inside the download folder.
- Every binary the image downloads (ffmpeg, the PO-token helper, uv) is pinned
  to one version and checked against its SHA-256 at build time.
- CI scans the repository for known vulnerabilities on every push.
