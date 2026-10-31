#!/usr/bin/env bash
# 树莓派桌面「CatTrace 摄像头」快捷方式的实际入口。
#
# 做两件事：
#   1. 保证摄像头网页服务（scripts/pi_phone_demo.py）在 127.0.0.1:8000 可用；
#   2. 用 Chromium kiosk 全屏打开 http://127.0.0.1:8000/kiosk。
#
# 手动运行：bash scripts/pi_kiosk.sh
# 退出 kiosk：Alt+F4，或另开终端 pkill chromium
# 安装桌面图标：bash scripts/install_pi_kiosk.sh
set -euo pipefail

REPO_DIR="${CATVISION_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
VENV_PY="${CATVISION_PY:-$HOME/venvs/catvision/bin/python}"
PORT="${CATVISION_PORT:-8000}"
URL="http://127.0.0.1:${PORT}/kiosk"
STATS="http://127.0.0.1:${PORT}/stats"
LOG="${CATVISION_LOG:-/tmp/catvision-camera.log}"
WAIT_S="${CATVISION_WAIT:-60}"

log() { printf '[cattrace-kiosk] %s\n' "$*"; }

find_chromium() {
  local b
  for b in chromium chromium-browser; do
    if command -v "$b" >/dev/null 2>&1; then
      printf '%s' "$b"
      return 0
    fi
  done
  return 1
}

service_up() {
  curl -fsS --max-time 1 "$STATS" >/dev/null 2>&1
}

CHROME="$(find_chromium)" || {
  log "没找到 chromium。先装：sudo apt install -y chromium"
  exit 1
}

if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  log "当前没有图形会话（DISPLAY / WAYLAND_DISPLAY 都为空）。"
  log "请在树莓派桌面上双击图标，或 ssh -X 后再运行。"
  exit 1
fi

if ! service_up; then
  STARTED=0
  if systemctl --user cat catvision-camera.service >/dev/null 2>&1; then
    log "启动 systemd 用户服务 catvision-camera.service"
    systemctl --user start catvision-camera.service && STARTED=1 || true
  fi

  if (( ! STARTED )); then
    log "后台启动摄像头服务：$VENV_PY scripts/pi_phone_demo.py --port $PORT"
    mkdir -p "$(dirname "$LOG")"
    nohup "$VENV_PY" "$REPO_DIR/scripts/pi_phone_demo.py" \
      --rotate 180 --port "$PORT" --threads 2 --fps 2 --earnotch auto \
      >>"$LOG" 2>&1 &
  fi

  for _ in $(seq 1 "$WAIT_S"); do
    service_up && break
    sleep 1
  done
fi

if ! service_up; then
  log "摄像头服务 ${WAIT_S}s 内没有就绪。"
  log "查日志：tail -n 50 $LOG"
  log "或：journalctl --user -u catvision-camera.service -n 50"
  command -v zenity >/dev/null 2>&1 && \
    zenity --error --text="摄像头服务没起来，日志在 $LOG" || true
  exit 1
fi

# kiosk 常驻时别让屏幕休眠/黑屏
command -v xset >/dev/null 2>&1 && xset s off -dpms 2>/dev/null || true

CHROME_ARGS=()
if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
  # Raspberry Pi OS Bookworm/Trixie 默认 Wayland；不加这个 Chromium 会去连 X11，
  # 报 "Missing X server or $DISPLAY" 后直接退出。
  CHROME_ARGS+=(--ozone-platform=wayland)
fi

log "打开 $URL"
exec "$CHROME" \
  "${CHROME_ARGS[@]}" \
  --kiosk \
  --start-fullscreen \
  --incognito \
  --no-first-run \
  --password-store=basic \
  --disable-translate \
  --disable-features=Translate,TranslateUI \
  "$URL"
