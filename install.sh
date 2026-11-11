#!/bin/sh
# MediaHarvest installer for Linux, macOS and WSL. Needs Docker with Compose v2.
#
#   curl -fsSL https://raw.githubusercontent.com/MohanVishe/mediaharvest/main/install.sh | sh
#
# Or download it, read it, then run:  sh install.sh
#
# It makes one folder (default ~/mediaharvest) holding compose.yaml and .env,
# pulls the published image, starts it on http://localhost:8081 (this
# computer only), and saves downloads to ~/mediaharvest/downloads.
# Run it again at any time to update. Change the defaults with:
#   MEDIAHARVEST_DIR, MEDIAHARVEST_PORT, MEDIAHARVEST_DOWNLOADS
# MEDIAHARVEST_PULL=0 skips the download and uses an image already on this
# computer (offline machines, or one built from source).
set -eu

IMAGE="ghcr.io/mohanvishe/mediaharvest"
DIR="${MEDIAHARVEST_DIR:-$HOME/mediaharvest}"
PORT="${MEDIAHARVEST_PORT:-8081}"
DOWNLOADS="${MEDIAHARVEST_DOWNLOADS:-$DIR/downloads}"

fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 \
  || fail "Docker is not installed. Install it from https://docs.docker.com/get-docker/ and run this again."
docker compose version >/dev/null 2>&1 \
  || fail "Docker Compose v2 (the 'docker compose' command) is missing. Update Docker and run this again."
docker info >/dev/null 2>&1 \
  || fail "Docker is not running, or your user may not use it. Start Docker (or add yourself to the 'docker' group) and run this again."

mkdir -p "$DIR" "$DOWNLOADS"
cd "$DIR"

# Settings are written once; later runs keep your edits.
if [ ! -f .env ]; then
  cat > .env <<EOF
MEDIAHARVEST_DOWNLOADS=$DOWNLOADS
MEDIAHARVEST_PORT=$PORT
MEDIAHARVEST_TAG=latest
MEDIAHARVEST_UID=$(id -u)
MEDIAHARVEST_GID=$(id -g)
EOF
fi
PORT="$(sed -n 's/^MEDIAHARVEST_PORT=//p' .env)"
PORT="${PORT:-8081}"

# Same service as the repo's docker-compose.yml, without the source build.
cat > compose.yaml <<EOF
services:
  mediaharvest:
    image: $IMAGE:\${MEDIAHARVEST_TAG:-latest}
    container_name: mediaharvest
    restart: unless-stopped
    ports:
      - "127.0.0.1:\${MEDIAHARVEST_PORT:-8081}:8081"
    volumes:
      - "\${MEDIAHARVEST_DOWNLOADS:-./downloads}:/downloads"
    environment:
      PUID: \${MEDIAHARVEST_UID:-1000}
      PGID: \${MEDIAHARVEST_GID:-1000}
      ALLOW_YTDL_OPTIONS_OVERRIDES: "false"
      DEFAULT_THEME: "mono"
EOF

if [ "${MEDIAHARVEST_PULL:-1}" != "0" ]; then
  echo "Downloading MediaHarvest..."
  docker compose pull
fi

# An NVIDIA GPU makes the "Any device" compression faster. Use it only when
# Docker can really reach it; otherwise the CPU does the work.
if [ "${MEDIAHARVEST_GPU:-1}" != "0" ] && command -v nvidia-smi >/dev/null 2>&1 \
  && docker run --rm --gpus all --entrypoint true "$IMAGE" >/dev/null 2>&1; then
  cat >> compose.yaml <<'EOF'
      NVIDIA_DRIVER_CAPABILITIES: "compute,utility,video"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
EOF
  echo "NVIDIA graphics card found: MediaHarvest will use it to compress videos."
fi
docker compose up -d

printf 'Starting'
i=0
while [ "$i" -lt 45 ]; do
  state="$(docker inspect -f '{{.State.Health.Status}}' mediaharvest 2>/dev/null || true)"
  [ "$state" = "healthy" ] && break
  printf '.'
  i=$((i + 1))
  sleep 2
done
echo

cat <<EOF

MediaHarvest is running: http://localhost:$PORT
Downloads are saved in:  $(sed -n 's/^MEDIAHARVEST_DOWNLOADS=//p' .env)

In $DIR:
  Update:     docker compose pull && docker compose up -d
  Stop:       docker compose down
  Settings:   edit .env, then docker compose up -d
  Uninstall:  docker compose down --rmi all, then delete $DIR
EOF
