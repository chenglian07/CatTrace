#!/usr/bin/env bash
# 在树莓派上安装「桌面双击打开摄像头页面」所需的一切（幂等，可反复跑）：
#   1. systemd 用户服务：摄像头网页常驻在 127.0.0.1:8000
#   2. 桌面图标 + 应用菜单项：Chromium kiosk 全屏打开 /kiosk
#   3. 可选 --autostart：登录桌面后自动打开
#
# 用法：
#   bash scripts/install_pi_kiosk.sh
#   bash scripts/install_pi_kiosk.sh --autostart
#   bash scripts/install_pi_kiosk.sh --repo ~/catvision --venv ~/venvs/catvision --port 8000
#
# 前置：图形桌面（graphical.target）、chromium、venv 里装好 onnxruntime 和模型。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="${CATVISION_VENV:-$HOME/venvs/catvision}"
PORT="${CATVISION_PORT:-8000}"
AUTOSTART=0
INSTALL_SERVICE=1

log()  { printf '\033[32m[cattrace]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[cattrace]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m[cattrace]\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)      REPO_DIR="$(cd "$2" && pwd)" || die "无效的 --repo：$2"; shift 2 ;;
    --venv)      VENV_DIR="$(cd "$2" && pwd)" || die "无效的 --venv：$2"; shift 2 ;;
    --port)      PORT="$2"; shift 2 ;;
    --autostart) AUTOSTART=1; shift ;;
    --no-service) INSTALL_SERVICE=0; shift ;;
    -h|--help)   usage; exit 0 ;;
    *)           die "未知参数：$1（--help 看用法）" ;;
  esac
done

VENV_PY="$VENV_DIR/bin/python"
REPO_ESC="${REPO_DIR//&/\\&}"
VENV_ESC="${VENV_PY//&/\\&}"

[[ -x "$VENV_PY" ]] || die "找不到虚拟环境 Python：$VENV_PY
先建环境：python3 -m venv --system-site-packages ~/venvs/catvision && pip install -e ~/catvision onnxruntime"
[[ -f "$REPO_DIR/scripts/pi_phone_demo.py" ]] || die "$REPO_DIR 不像 catvision 仓库根目录（缺 scripts/pi_phone_demo.py）"

CHROME="$(command -v chromium || command -v chromium-browser || true)"
[[ -n "$CHROME" ]] || die "没装 chromium。先执行：
  sudo apt install -y chromium
装完再跑一次本脚本。"

command -v curl >/dev/null 2>&1 || die "缺 curl：sudo apt install -y curl"

TARGET="$(systemctl get-default 2>/dev/null || echo unknown)"
if [[ "$TARGET" != "graphical.target" ]]; then
  warn "当前默认启动级别是 ${TARGET}，桌面图标需要图形界面。"
  warn "要开机进桌面：sudo systemctl set-default graphical.target && sudo reboot"
  warn "（1GB 的 Pi4 上桌面约占 270MB，和 Chromium 一起比较吃紧）"
fi

chmod +x "$REPO_DIR/scripts/pi_kiosk.sh"

# --- 1. systemd 用户服务 -----------------------------------------------------
if (( INSTALL_SERVICE )); then
  UNIT_DIR="$HOME/.config/systemd/user"
  mkdir -p "$UNIT_DIR"

  sed -e "s|%h/venvs/catvision/bin/python|$VENV_ESC|g" \
      -e "s|%h/catvision|$REPO_ESC|g" \
      -e "s|--port 8000|--port $PORT|g" \
      "$REPO_DIR/deploy/catvision-camera.service" > "$UNIT_DIR/catvision-camera.service"

  if systemctl --user daemon-reload 2>/dev/null; then
    if systemctl --user enable catvision-camera.service >/dev/null 2>&1; then
      log "已设置开机常驻（systemctl --user enable）"
    fi

    if systemctl --user restart catvision-camera.service; then
      log "摄像头服务已启动（catvision-camera.service，端口 $PORT）"
    else
      warn "服务启动失败，查：journalctl --user -u catvision-camera -n 50"
      warn "桌面图标仍可用：scripts/pi_kiosk.sh 会自己把进程拉起来"
    fi
  else
    warn "当前会话没有 systemd 用户实例，跳过服务启动（桌面图标会自己拉起进程）"
  fi

  loginctl enable-linger "$USER" >/dev/null 2>&1 \
    || warn "enable-linger 失败：开机自启可能要在图形登录后才生效（sudo loginctl enable-linger $USER）"
else
  warn "跳过 systemd 服务安装（--no-service）"
fi

# --- 2. 桌面图标 + 应用菜单 --------------------------------------------------
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
[[ -n "$DESKTOP_DIR" ]] || DESKTOP_DIR="$HOME/Desktop"
mkdir -p "$DESKTOP_DIR" "$HOME/.local/share/applications"

install_desktop() {
  local dest="$1"
  sed "s|/home/lyx/catvision|$REPO_ESC|g" "$REPO_DIR/deploy/cattrace-kiosk.desktop" > "$dest"
  if [[ "$PORT" != "8000" ]]; then
    # 非默认端口时，把端口通过环境变量传给 pi_kiosk.sh
    sed -i "s|^Exec=.*|Exec=/usr/bin/env CATVISION_PORT=$PORT $REPO_DIR/scripts/pi_kiosk.sh|" "$dest"
  fi
  chmod +x "$dest"
  # 让文件管理器认为它可信；无图形会话时 gio 会失败，首次双击手动选「允许启动」即可
  command -v gio >/dev/null 2>&1 && gio set "$dest" metadata::trusted true 2>/dev/null || true
}

install_desktop "$DESKTOP_DIR/CatTrace.desktop"
install_desktop "$HOME/.local/share/applications/CatTrace.desktop"
log "桌面图标：$DESKTOP_DIR/CatTrace.desktop"

# --- 3. 可选：登录桌面后自动打开 ---------------------------------------------
if (( AUTOSTART )); then
  mkdir -p "$HOME/.config/autostart"
  install_desktop "$HOME/.config/autostart/CatTrace.desktop"
  log "已加入自启动：~/.config/autostart/CatTrace.desktop"
fi

# --- 4. 等服务就绪（失败只警告，不挡安装） -----------------------------------
READY=0
for _ in $(seq 1 20); do
  if curl -fsS --max-time 1 "http://127.0.0.1:${PORT}/stats" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 1
done

echo
if (( READY )); then
  log "服务已就绪。"
else
  warn "服务 20s 内还没就绪，通常是摄像头/模型的问题："
  warn "  journalctl --user -u catvision-camera.service -n 50"
  warn "  tail -n 50 /tmp/catvision-camera.log（非 systemd 启动时）"
fi

cat <<EOF

  双击桌面图标「CatTrace 摄像头」：Chromium kiosk 全屏打开
  本机直接访问：http://127.0.0.1:${PORT}/kiosk
  手机 / 电脑：http://<树莓派IP>:${PORT}/      （普通页面，带记录表）

  退出 kiosk：Alt+F4；看服务状态：systemctl --user status catvision-camera
  首次双击若提示「不受信任」：右键图标 →「允许启动 / Allow Launching」

EOF
