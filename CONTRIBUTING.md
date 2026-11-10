# Contributing to MediaHarvest

Bug reports, ideas and pull requests are welcome. For a change that isn't
obvious, open an issue about the approach first. [AGENTS.md](AGENTS.md) has the
scope, the project layout and the conventions.

Site support and site-specific fixes belong in
[yt-dlp](https://github.com/yt-dlp/yt-dlp/issues); MediaHarvest picks them up
automatically.

## Develop

Everything runs in the dev container, so nothing is installed on your machine:
open the folder in VS Code and choose **Reopen in Container** (Docker needed).
Then:

```bash
# backend
uv sync --frozen --group dev
uv run pytest app/tests/

# frontend
cd ui
pnpm install --frozen-lockfile
pnpm run lint
pnpm exec ng test --watch=false
pnpm run build

# run it (serves the built UI on http://localhost:8081)
cd ..
uv run python app/main.py
```

Build the production image from source with `docker compose up -d --build`.

Icons: edit and run `uv run scripts/make_icons.py`.

## Pull requests

- One change per pull request, with tests, and a sensible default rather than a
  new setting where possible.
- `main` publishes a new image on every push, so a pull request must be ready to
  ship as merged. CI runs the tests, the linter, the builds and a vulnerability scan.
