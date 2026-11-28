#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${XGIF_APP_DIR:-/opt/apps/twittergifdownloader}"
BIN_PATH="/usr/local/bin/xgif-deploy"
SERVICE_PATH="/etc/systemd/system/xgif-deploy.service"
TIMER_PATH="/etc/systemd/system/xgif-deploy.timer"
RC_MARKER="# >>> xgif-deploy auto-run >>>"

usage() {
  cat <<'EOF'
Usage: xgif-deploy [options]

Pulls the latest code and rebuilds/restarts the Docker services.

Options:
  -b, --bot            Build and restart the bot service too
  -c, --changed        Rebuild only when origin/main has new commits
      --install        Install to /usr/local/bin and enable the login hook
      --install-timer  Install a systemd timer that deploys new pushes
  -h, --help           Show this help

Environment:
  XGIF_APP_DIR        Repository path (default: /opt/apps/twittergifdownloader)
  XGIF_POLL_SECONDS   systemd timer interval in seconds (default: 120)
  XGIF_SKIP_DEPLOY    Set to 1 to skip the automatic login run
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

  sed -i '/# >>> xgif-deploy auto-run >>>/,/# <<< xgif-deploy auto-run <</d' "$rc"

  {
    echo ""
    echo "$RC_MARKER"
    echo 'if [ -t 1 ] && [ -z "${TMUX:-}" ] && [ -z "${XGIF_DEPLOY_DONE:-}" ] && [ -z "${XGIF_SKIP_DEPLOY:-}" ]; then'
    echo '  export XGIF_DEPLOY_DONE=1'
    echo '  bash /usr/local/bin/xgif-deploy --bot --changed || echo "xgif-deploy failed; continuing to shell." >&2'
    echo 'fi'
    echo '# <<< xgif-deploy auto-run <<<'
  } >> "$rc"

  echo "Installed $BIN_PATH -> $src"
  echo "Login hook enabled in $rc"
}

install_timer() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo: sudo bash $0 --install-timer" >&2
    exit 1
  fi

  local poll="${XGIF_POLL_SECONDS:-120}"

  cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=Deploy Twitter GIF downloader updates
After=network-online.target docker.service
Wants=network-online.target docker.service

[Service]
Type=oneshot
WorkingDirectory=$APP_DIR
Environment=HOME=/root
Environment=GIT_TERMINAL_PROMPT=0
Environment=XGIF_APP_DIR=$APP_DIR
ExecStart=/bin/bash $APP_DIR/scripts/xgif-deploy.sh --bot --changed
TimeoutStartSec=0
EOF

  cat > "$TIMER_PATH" <<EOF
[Unit]
Description=Poll for Twitter GIF downloader updates

[Timer]
OnActiveSec=30s
OnBootSec=2min
OnUnitActiveSec=${poll}s
AccuracySec=30s
Unit=xgif-deploy.service

[Install]
WantedBy=timers.target
EOF

  systemctl daemon-reload
  systemctl enable --now xgif-deploy.timer

  echo "Installed and enabled xgif-deploy.timer (every ${poll}s)."
  echo "Logs: journalctl -u xgif-deploy.service -f"
}

BUILD_BOT=0
ONLY_CHANGED=0
DO_INSTALL=0
DO_INSTALL_TIMER=0
for arg in "$@"; do
  case "$arg" in
    -b|--bot) BUILD_BOT=1 ;;
    -c|--changed|--only-changed) ONLY_CHANGED=1 ;;
    --install) DO_INSTALL=1 ;;
    --install-timer) DO_INSTALL_TIMER=1 ;;
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

if [ "$DO_INSTALL_TIMER" -eq 1 ]; then
  install_timer
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

services=(web)
if [ "$BUILD_BOT" -eq 1 ]; then
  services+=(bot)
fi

before="$(git rev-parse HEAD)"

echo "==> git pull in $APP_DIR"
git pull --ff-only

after="$(git rev-parse HEAD)"

if [ "$ONLY_CHANGED" -eq 1 ] && [ "$before" = "$after" ]; then
  echo "==> No new commits; ensuring ${services[*]} is running"
  docker_cmd compose up -d "${services[@]}"
  docker_cmd compose ps
  exit 0
fi

echo "==> docker compose up -d --build ${services[*]}"
docker_cmd compose up -d --build "${services[@]}"

echo "==> docker compose ps"
docker_cmd compose ps
