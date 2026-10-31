# 树莓派网页 kiosk 实测记录（2026-10-31）

> 环境：Raspberry Pi 4B / 1GB / Debian 13 / Python 3.13 / IMX219 CSI / DSI 800×480 / Chromium 155
> 代码：`feature/web-earnotch`（网页 kiosk + 剪耳判定），对应提交 `c2019a3` 及之前若干修复
> 目标：双击桌面图标，全屏看摄像头画面 + 猫/非猫 + 剪耳（绝育）判定；手机/电脑也能看

## 1. 部署结果

| 项 | 值 |
|---|---|
| 摄像头服务 | `catvision-camera.service`（systemd **用户**服务，`:8000`） |
| 服务自启 | `systemctl --user enable` + `loginctl enable-linger lyx` → 开机即起，不用登录桌面 |
| 桌面图标 | `~/Desktop/CatTrace.desktop` → `scripts/pi_kiosk.sh` |
| kiosk | Chromium `--kiosk --start-fullscreen --ozone-platform=wayland`，打开 `/kiosk` |
| 页面 | `/` 带 30 帧记录表；`/kiosk` 只留全屏画面 |
| 判定 | `cat_vs_notcat` 门控 → 有猫才跑 `EarNotchModel` → 已剪耳/未剪耳/看不清 |

## 2. 验证结果

- `/stats` 已包含：`verdict`、`p_notch`、`notched`、`ear_enabled`、`history[].verdict`；
- 用 Pi 上的 `tests/fixtures/classifier/chelsea_cat.png` 跑两级：
  - `p_cat = 0.9999` → `cat`
  - `p_notch = 0.503` → 落在 `0.58 ± 0.12` 不确定带 → `uncertain`（链路通，模型保守）
- kiosk 全屏截图确认：800×480、中文 HUD、无翻译气泡、无键盘遮挡；
- HUD 中文字体用 Pi OS 自带的 `DroidSansFallbackFull.ttf`，数字/英文用 DejaVu。

## 3. 已修复的问题

| # | 现象 | 原因 | 处理 |
|---|---|---|---|
| 1 | 页面一直旧版、`frames` 卡住 | 8000 被 07:24 手动启动的旧 `pi_phone_demo` 占着（采集线程已死），systemd 服务绑不上端口 | `kill` 旧进程后重启服务 |
| 2 | 剪耳模型不加载 | `models/earnotch_resnet18224_v0.onnx.json` 被本地 `scp a b` 覆盖成 43MB 的 onnx 二进制 | 从 git 恢复 400B JSON 并重传 |
| 3 | Chromium 启动即退出 | Pi OS 是 Wayland，Chromium 默认连 X11，报 `Missing X server or $DISPLAY` | `--ozone-platform=wayland` |
| 4 | 只开 560×420 小窗 | labwc 下仅 `--kiosk` 不强制全屏 | 追加 `--start-fullscreen` |
| 5 | 右上角弹翻译气泡 | Chromium 界面语言英文、页面中文 | `/etc/chromium/policies/managed/cattrace.json` → `{"TranslateEnabled": false}` |
| 6 | HUD 数字/英文显示成方框 | `DroidSansFallbackFull` 只有中文字形，ASCII 用它会变方框 | 中文/英文分开选字体；分隔符 `·` 改中文逗号 `，` |
| 7 | 推理时摄像头超时 | 取帧和推理在同一个循环，推理 1s+ 期间没人 dequeue，libcamera 报超时并永久阻塞 | 取帧独立线程（~10fps），推理线程只读最新帧；加 `--stall-timeout 60` 看门狗 |
| 8 | 反复 `pkill` 后 Chromium 黑屏 | 默认 profile 留下崩溃恢复状态 | kiosk 用独立 `--user-data-dir=/tmp/cattrace-chrome` |

## 4. 未解决：CSI 摄像头连续出流超时

**这是硬件/供电问题，不是网页。** 证据：

```text
V4L2 ... Dequeue timer of 1000000.00us has expired!
ERROR RPI pipeline_base.cpp:1387 Camera frontend has timed out!
ERROR RPI pipeline_base.cpp:1388 Please check that your camera sensor connector is attached securely.
ERROR RPISTREAM rpi_stream.cpp:267 Failed to queue buffer for Unicam Image
```

- 两次间隔 4 秒抓 `/frame.jpg`，字节完全一致，`frames` 停在 349；
- 停掉我们的服务，单独跑官方命令也失败：
  - `rpicam-vid -t 6000 --width 640 --height 480 --framerate 10` → 失败
  - `rpicam-vid ... --framerate 5` → 失败
  - `rpicam-vid --width 320 --height 240 --framerate 5` → 失败
- 但 `rpicam-still` 连拍 3 张全部成功（约 2.5MB/张）；
- `vcgencmd get_throttled` = **`0x50005`**（欠压已发生、正在限频），从开机起一直存在。

结论：单帧拍照正常，持续视频流几秒后 Unicam 收不到 buffer。优先怀疑**供电不足**和**CSI 排线接触**。

处理顺序：

1. 换官方 **5V/3A（5.1V/3A）** 电源；
2. 断电重插 CSI 排线（Pi CAM0 与摄像头两端），换一根排线再试；
3. 不启服务，先验证：

   ```bash
   rpicam-still -o /tmp/t.jpg --timeout 2000   # 应成功
   rpicam-vid -t 5000 -o /tmp/t.h264           # 修好后应正常结束
   ```

4. 两者正常后再启动服务：

   ```bash
   systemctl --user start catvision-camera
   ```

软件兜底：取帧/推理已拆线程；`--stall-timeout 60` 会在 60 秒没有新帧时退出，让 `Restart=always` 重新初始化摄像头。硬件没修好前，服务会反复重启（实测 NRestarts 28 次）。

## 5. 判定质量（别当生产判断）

- 现场这只已绝育的猫被判成「未剪耳，未绝育」，原因：
  - 猫脸贴镜头太近，画面只剩鼻子/眼睛，**耳朵不在取景框里**，剪耳模型没有可看的耳标；
  - 同一只猫 `p_notch` 在 `0.30 / 0.37 / 0.63 / 0.80` 之间跳，画面模糊/角度变化时结论不稳定；
  - Pi 默认 resnet18 的 test acc 只有 **0.75**、漏绝育 **33%**。
- 使用建议：猫离镜头 **30–50cm**，让**整个头和两只耳朵**在画面里，保持不动、光线充足；
- 仍判错再考虑换 convnext（Pi 上 3.2s/帧）或用数据集重训：
  `D:\cathouse\cathouse_tnr\cathouse_tnr\datasets\TNR\main-74d34db8\dataset_v1\splits`。
- 当前模型没有左右耳结论，只回答"这张图里的猫有没有剪耳"。

## 6. 常用命令

```bash
# 服务
systemctl --user status catvision-camera
systemctl --user restart catvision-camera
systemctl --user stop catvision-camera
journalctl --user -u catvision-camera -n 50

# 页面
curl -s http://127.0.0.1:8000/stats
curl -s http://127.0.0.1:8000/frame.jpg -o /tmp/f.jpg

# 摄像头自检（先停服务再跑，避免抢摄像头）
rpicam-still -o /tmp/t.jpg --timeout 2000
rpicam-vid -t 5000 -o /tmp/t.h264
vcgencmd get_throttled
```

## 7. 下次怎么开

- **不用手动开服务**：`catvision-camera.service` 已 `enabled`，且 `Linger=yes`，开机自动启动；
- **双击桌面「CatTrace 摄像头」**即可：`pi_kiosk.sh` 会确认服务在跑（没跑就拉起来，最多等 60 秒），再打开 Chromium；
- **不会自动全屏**（默认没有 autostart）。要开机/登录后自动全屏：

  ```bash
  bash ~/catvision/scripts/install_pi_kiosk.sh --autostart
  ```

- 改了代码或刚修完摄像头：`systemctl --user restart catvision-camera`；
- 当前（2026-10-31）摄像头硬件未修复，服务已被手动 `stop`，避免每 60 秒重启刷日志；修好后 `start` 或双击图标即可。
