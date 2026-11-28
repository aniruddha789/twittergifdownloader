#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${XGIF_APP_DIR:-/opt/apps/twittergifdownloader}"
BIN_PATH="/usr/local/bin/xgif-deploy"
RC_MARKER="# >>> xgif-deploy auto-run >>>"

usage() {
  cat <<'EOF'
Usage: xgif-deploy [options]

Pulls the latest code and rebuilds/restarts the Docker services.

Options:
  -b, --bot       Build and restart the bot service too
      --install   Install to /usr/local/bin and enable the login hook
  -h, --help      Show this help

Environment:
  XGIF_APP_DIR       Repository path (default: /opt/apps/twittergifdownloader)
  XGIF_SKIP_DEPLOY   Set to 1 to skip the automatic login run
EOF
}

docker_cmd() {
  if [ "$(id -u)" -eq 0 ]; then
    docker "$@"
  else
    sudo docker "$@"
  fi
}

install_self() {
  local src owner home rc
  src="$(readlink -f "${BASH_SOURCE[0]}")"

  if [ "$(id -u)" -eq 0 ]; then
    chmod +x "$src"
    ln -sfn "$src" "$BIN_PATH"
  else
    sudo chmod +x "$src"
    sudo ln -sfn "$src" "$BIN_PATH"
  fi

  owner="${SUDO_USER:-$(id -un)}"
  home="$(getent passwd "$owner" 2>/dev/null | cut -d: -f6 || true)"
  if [ -z "$home" ]; then
    home="$HOME"
  fi
  rc="$home/.bashrc"
  touch "$rc"

  if ! grep -qF "$RC_MARKER" "$rc"; then
    {
      echo ""
      echo "$RC_MARKER"
      echo 'if [ -t 1 ] && [ -z "${TMUX:-}" ] && [ -z "${XGIF_DEPLOY_DONE:-}" ] && [ -z "${XGIF_SKIP_DEPLOY:-}" ]; then'
      echo '  export XGIF_DEPLOY_DONE=1'
      echo '  bash /usr/local/bin/xgif-deploy || echo "xgif-deploy failed; continuing to shell." >&2'
      echo 'fi'
      echo '# <<< xgif-deploy auto-run <<<'
    } >> "$rc"
  fi

  echo "Installed $BIN_PATH -> $src"
  echo "Login hook enabled in $rc"
  echo "Use 'xgif-deploy --bot' after login when you also want to rebuild the bot."
}

BUILD_BOT=0
DO_INSTALL=0
for arg in "$@"; do
  case "$arg" in
    -b|--bot) BUILD_BOT=1 ;;
    --install) DO_INSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown option: $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ "$DO_INSTALL" -eq 1 ]; then
  install_self
  exit 0
fi

if [ ! -d "$APP_DIR/.git" ]; then
  echo "Repository not found at $APP_DIR (set XGIF_APP_DIR)." >&2
  exit 1
fi

cd "$APP_DIR"

if command -v flock >/dev/null 2>&1; then
  exec 9>"${TMPDIR:-/tmp}/xgif-deploy.lock"
  if ! flock -n 9; then
    echo "Another deploy is already running; skipping."
    exit 0
  fi
fi

echo "==> git pull in $APP_DIR"
git pull --ff-only

services=(web)
if [ "$BUILD_BOT" -eq 1 ]; then
  services+=(bot)
fi

echo "==> docker compose up -d --build ${services[*]}"
docker_cmd compose up -d --build "${services[@]}"

echo "==> docker compose ps"
docker_cmd compose ps
