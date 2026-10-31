# 树莓派桌面 Kiosk：网页方案

> 目标：树莓派桌面上双击一个图标，全屏看到摄像头实时画面和「CAT / NOT CAT」判定；
> 手机、电脑打开同一个地址也能看。适合 **1GB Pi4 + DSI/HDMI 屏**，不需要装 pygame。

## 1. 怎么实现

```
CSI 摄像头 (picamera2)
   │
   ▼
scripts/pi_phone_demo.py  ──  http://127.0.0.1:8000/        普通页面（带 30 帧记录表）
   │                            http://127.0.0.1:8000/kiosk  全屏页面（只留画面）
   ▼
Chromium --kiosk  （树莓派桌面图标启动）
```

- `/kiosk` 复用同一个页面，只加了一个 `kiosk` class：隐藏页头、记录表和提示，
  画面按 `100vw × 100vh` 铺满（`object-fit: contain`，不变形），断流时底部显示「断线重连中…」。
- 判定文字和 `p_cat` 已经烧在视频帧里（PIL 画的），所以全屏时不需要额外 HUD。
- 页面用 250ms 轮询 `/frame.jpg` 而不是 MJPEG 长连接，断线能自己恢复。

| | 网页 kiosk（本方案） | pygame（`pi_screen_earnotch.py`） |
|---|---|---|
| 手机 / 电脑远程看 | ✅ 浏览器打开 | ❌ |
| Pi 屏幕全屏 | ✅ Chromium kiosk | ✅ 直接渲染 |
| 桌面图标 | ✅ `.desktop` | ✅ `.desktop` |
| 内存 | 较高（Chromium 约 350MB+） | 低（约 100MB） |
| 1GB Pi4 | 能跑，但和推理抢内存 | 更稳 |
| 剪耳判定 | ❌ 只有猫/非猫 | ✅ |

## 2. 前置条件

1. **图形桌面**：`systemctl get-default` 应该是 `graphical.target`。
   如果之前按 [`部署.md`](./部署.md) 关过桌面：

   ```bash
   sudo systemctl set-default graphical.target
   sudo reboot
   ```

   > 桌面约占 270MB，Chromium 再占 350MB+，1GB 的 Pi4 会比较紧。
   > 装完先用 `free -m` 看剩余内存；吃紧就退回 pygame 方案（见第 8 节）。

2. **Chromium**：

   ```bash
   sudo apt install -y chromium        # Bookworm / Trixie
   # 老系统包名是 chromium-browser
   ```

3. **venv 和模型**（`~/catvision` 已部署过的话一般都有了）：

   ```bash
   source ~/venvs/catvision/bin/activate
   python -c "import onnxruntime, picamera2; print('deps OK')"
   ls models/cat_vs_notcat.onnx
   ```

4. **摄像头可用**：

   ```bash
   rpicam-still -o /tmp/t.jpg --timeout 2000 && echo camera OK
   ```

## 3. 安装（一条命令）

```bash
ssh lyx@10.1.41.171
cd ~/catvision
git pull
bash scripts/install_pi_kiosk.sh
```

脚本是幂等的，做四件事：

| 步骤 | 结果 |
|---|---|
| 写 systemd 用户服务 | `~/.config/systemd/user/catvision-camera.service`，开机/登录后常驻 `:8000` |
| 写桌面图标 | `~/Desktop/CatTrace.desktop`（`Exec` 指向 `scripts/pi_kiosk.sh`） |
| 写应用菜单项 | `~/.local/share/applications/CatTrace.desktop` |
| 等 20 秒自检 | 打 `http://127.0.0.1:8000/stats`，服务没起来会提示看哪份日志 |

可选参数：

```bash
bash scripts/install_pi_kiosk.sh --autostart      # 登录桌面后自动全屏打开
bash scripts/install_pi_kiosk.sh --port 8080      # 换端口
bash scripts/install_pi_kiosk.sh --venv ~/venvs/catvision --repo ~/catvision
bash scripts/install_pi_kiosk.sh --no-service     # 只放图标，服务自己起
```

## 4. 日常使用

- **双击桌面图标「CatTrace 摄像头」**：Chromium kiosk 全屏打开 `http://127.0.0.1:8000/kiosk`。
  图标本身不启动模型，`scripts/pi_kiosk.sh` 会先确认服务在跑（没跑就拉起来），再开浏览器。
- **退出 kiosk**：`Alt+F4`；或另开终端 `pkill chromium`。
- **手机 / 电脑看**：`http://10.1.41.171:8000/`（普通页面，右侧有 30 帧记录表）。
- **只看全屏**：`http://10.1.41.171:8000/kiosk`。
- **服务管理**：

  ```bash
  systemctl --user status catvision-camera
  systemctl --user restart catvision-camera
  journalctl --user -u catvision-camera -f
  ```

## 5. 开机自启

两层，按需选：

1. **服务常驻**（安装脚本默认做了）：`systemctl --user enable` + `loginctl enable-linger $USER`，
   这样不登录桌面摄像头服务也在跑，手机/电脑随时能打开页面。
2. **桌面自动全屏**（可选）：`bash scripts/install_pi_kiosk.sh --autostart`，
   会在 `~/.config/autostart/` 放一份图标，登录桌面后自动打开。

> 想让机器像 Appliance 一样开机直接进画面：先设置自动登录（`raspi-config` → System Options →
> Boot / Auto Login → Desktop Autologin），再开 `--autostart`。

## 6. 从 Windows 远程部署

如果树莓派上的代码还是旧的、又不想等 PR 合入，可以只传这几个文件：

```powershell
cd "D:\cathouse\cathouse_tnr\cathouse_tnr\datasets\TNR\CatTrace"

scp scripts\pi_kiosk.sh scripts\install_pi_kiosk.sh lyx@10.1.41.171:~/catvision/scripts/
scp deploy\catvision-camera.service deploy\cattrace-kiosk.desktop lyx@10.1.41.171:~/catvision/deploy/
scp scripts\pi_phone_demo.py lyx@10.1.41.171:~/catvision/scripts/

ssh lyx@10.1.41.171 "bash ~/catvision/scripts/install_pi_kiosk.sh"
```

`install_pi_kiosk.sh` 会把 `.desktop` 里的 `Exec` 路径改成实际仓库路径，所以不用手动改。

## 7. 排障

| 现象 | 原因 / 处理 |
|---|---|
| 双击图标提示「不受信任」 | 右键图标 →「允许启动 / Allow Launching」；或 `gio set ~/Desktop/CatTrace.desktop metadata::trusted true` |
| 双击没反应 | 终端里跑 `bash ~/catvision/scripts/pi_kiosk.sh`，看它打印到哪一步 |
| `没找到 chromium` | `sudo apt install -y chromium` |
| `当前没有图形会话` | 在桌面里双击，或 `ssh -X`；纯 SSH 终端开不了 kiosk |
| 页面 404 / 打不开 | `curl http://127.0.0.1:8000/stats`；不行看 `journalctl --user -u catvision-camera -n 50` |
| 画面全黑 | 摄像头没出流：`rpicam-still -o /tmp/t.jpg --timeout 2000`；或镜头被挡（页面亮度 <25 会提示） |
| 服务反复重启 | 多半是 `onnxruntime` 或模型路径：`journalctl --user -u catvision-camera -n 100` |
| 画面卡顿 / 内存不足 | `free -m`；把 `--threads 1 --fps 3` 再降，或退回 pygame 方案 |
| 开机没自启 | `loginctl show-user lyx -p Linger` 应为 `Linger=yes`；不是就 `sudo loginctl enable-linger lyx` |
| 端口被占 | `ss -ltnp \| grep 8000`；换端口重装：`bash scripts/install_pi_kiosk.sh --port 8080` |

> ⚠️ 页面没有登录鉴权，只适合局域网。不要把 8000 端口映射到公网。

## 8. 卸载 / 退回 pygame

```bash
systemctl --user disable --now catvision-camera.service
rm -f ~/.config/systemd/user/catvision-camera.service \
      ~/Desktop/CatTrace.desktop \
      ~/.local/share/applications/CatTrace.desktop
rm -f ~/.config/autostart/CatTrace.desktop      # 用过 --autostart 才需要
systemctl --user daemon-reload
```

内存实在吃紧、或者不想要桌面，就回到 pygame 直出（剪耳判定也在里面）：

```bash
python scripts/pi_screen_earnotch.py --rotate 180
```

两套方案可以共存：网页服务常驻，需要时再手动跑 pygame，不冲突。
