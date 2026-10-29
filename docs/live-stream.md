# 实时直播接入（树莓派摄像头 → 网页直播间）

首页「实时直播间」原来是一个占位表情（🐱）。接入真实摄像头后，浏览器看到的是树莓派
摄像头的实时画面，断流时自动回退到占位动画，不会白屏。

## 1. 数据怎么走

```
树莓派摄像头 (CSI)
   │  picamera2
   ▼
树莓派 MJPEG 服务 :8000/stream        ← scripts/pi_phone_demo.py
   │  HTTP multipart/x-mixed-replace
   ▼
Flask /api/live/stream（同源代理，app.py + live_proxy.py）
   │
   ▼
浏览器 <img id="liveStream">
```

**为什么不让浏览器直连树莓派？**

| 直连 Pi | 走 Flask 代理（当前做法） |
|---|---|
| 手机换了网络就打不开 | 只要能打开网页，就能看到画面 |
| 页面以后上 HTTPS 会被判混合内容，直接拦掉 | 同源，没有混合内容问题 |
| 需要给 Pi 开 CORS | 不需要 |
| 少一跳，延迟低一丢丢 | 多一次转发（局域网内 < 30ms） |

## 2. 怎么跑

### 第一步：树莓派上启动摄像头服务

```bash
cd ~/catvision
python scripts/pi_phone_demo.py --rotate 180 --port 8000 \
  --stream-fps 8 --fps 2 --threads 1
```

确认能出画面：手机或电脑浏览器打开 `http://<树莓派IP>:8000/`。
网页直播间显示的是持续 MJPEG 视频流，不使用 `/snapshot.jpg` 轮询取帧。
`/snapshot.jpg` 只用于断线诊断和首帧预览。

> Pi 4（1GB）实测：`--threads 4` 会占满约 312% CPU，首帧可能等十几秒；
> 改成 `--threads 1` 后占用约 100%，首屏稳定在 1 秒左右。`--stream-fps 8`
> 是持续视频流目标帧率，`--fps 2` 是 AI 分类目标帧率。采集和推理由两个线程
> 解耦，推理变慢不会卡住直播。首页分别显示“视频 fps”和“识别 fps”。
>
> 电源必须是稳定的 5V/3A。若 `vcgencmd get_throttled` 不是 `0x0`，先处理欠压，
> 否则会出现花屏、掉线、USB/CSI 设备重启等难排查的问题。

### 推荐：用 systemd 用户服务保持树莓派直播常驻

SSH 断开后不能依赖 `nohup`，否则 logind 可能随会话结束清理摄像头进程。把仓库里的
`deploy/catvision-camera.service` 安装到用户级 systemd：

```bash
mkdir -p ~/.config/systemd/user
cp deploy/catvision-camera.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now catvision-camera.service
systemctl --user status catvision-camera.service
journalctl --user -u catvision-camera.service -f
```

服务使用 Pi 上的路径 `/home/lyx/catvision` 和虚拟环境 `/home/lyx/venvs/catvision`。
若成员机器路径不同，先修改 unit 里的 `WorkingDirectory` 和 `ExecStart`。`systemctl --user
enable` 需要用户 linger 已开启（`loginctl show-user <用户> -p Linger` 应为 `Linger=yes`）。

### 第二步：电脑上带着地址启动网页

Linux / macOS：

```bash
export CATTRACE_LIVE_URL=http://192.168.1.50:8000/stream
export CATTRACE_LIVE_STATS=http://192.168.1.50:8000/stats   # 可选，显示识别状态
export CATTRACE_LIVE_SNAPSHOT=http://192.168.1.50:8000/snapshot.jpg  # 可选，首屏单帧
python app.py
```

Windows PowerShell：

```powershell
$env:CATTRACE_LIVE_URL   = "http://192.168.1.50:8000/stream"
$env:CATTRACE_LIVE_STATS = "http://192.168.1.50:8000/stats"
$env:CATTRACE_LIVE_SNAPSHOT = "http://192.168.1.50:8000/snapshot.jpg"
python app.py
```

`CATTRACE_LIVE_STATS` 不填也能看画面，只是右上角徽标不会再更新「识别到猫 xx%」。

> 不配 `CATTRACE_LIVE_URL` 时，直播功能整体关闭，页面行为和之前完全一样（显示表情占位）。

### 第三步：让手机也能看

```powershell
$env:PROJECTCAT_HOST = "0.0.0.0"
python app.py
```

手机访问 `http://<电脑IP>:5000/`，画面会跟着一起出来——因为 Pi 的流是 Flask 去拉的，
手机不需要能连到树莓派。

## 3. 后端接口

| 接口 | 作用 | 说明 |
|---|---|---|
| `GET /api/live/info` | 是否可用 + 各端点地址 | 前端启动时调一次 |
| `GET /api/live/stream` | MJPEG 视频流 | 原样转发，`Cache-Control: no-store` |
| `GET /api/live/snapshot` | 截当前一帧 JPEG | 配了单帧接口时直接取图；否则从 MJPEG 流里抠帧 |
| `GET /api/live/stats` | 识别状态 JSON | 需要配 `CATTRACE_LIVE_STATS` |

环境变量：

| 变量 | 必填 | 例子 |
|---|---|---|
| `CATTRACE_LIVE_URL` | 是（否则关闭） | `http://192.168.1.50:8000/stream` |
| `CATTRACE_LIVE_STATS` | 否 | `http://192.168.1.50:8000/stats` |
| `CATTRACE_LIVE_SNAPSHOT` | 否；建议配置 | `http://192.168.1.50:8000/snapshot.jpg` |
| `CATTRACE_LIVE_TIMEOUT` | 否，默认 8 秒 | `5` |

## 4. 前端行为

- 连上：显示真实画面，隐藏表情，右上角 AI 徽标变绿点。
- 断流：显示「📡 摄像头断流」+ 重试按钮，表情回来，按 2s → 4s → 8s → 16s → 30s 退避重连。
- 画面冻结：轮询 `/stats` 时若 `stream_frames` 连续 5 秒不增长，判定「画面已冻结」并自动重连，避免一直停在最后一帧。
- 6 秒还没出第一帧：判定「摄像头无响应」。
- 没配地址：完全不打扰，保持原来的占位动画。

## 5. 已知限制

| 限制 | 原因 | 后续方案 |
|---|---|---|
| 延迟约 0.2~0.5s | MJPEG 逐帧推流 | 要 <200ms 且多人观看 → WebRTC（go2rtc / MediaMTX） |
| 每个观众占一个 Flask 线程 | 同步转发 | 观众变多 → Nginx `proxy_pass` 直接转发，绕开 Flask |
| AI 识别约 2 FPS | 1GB 机器上 ONNX 分类算力有限 | 采集/推流与推理双线程解耦；画面按 `--stream-fps` 连续推送，识别按 `--fps` 消费最新帧 |
| Pi 4 只有 1GB 内存 | 硬件 | 关掉不用的分类线程（`--threads 1`），并换 5V/3A 电源 |

## 6. 与 AI 链路的关系

直播画面和识别链路**可以共用一路摄像头**，但要注意 picamera2 一个进程独占摄像头：

- 现在：`pi_phone_demo.py` 自己开摄像头，做分类 + 推流。
- 接正式识别时：让 `pipeline.runner` 成为唯一的摄像头持有者，把抽出来的帧同时
  (a) 写 `/dev/shm` 给识别用，(b) 推给 MJPEG 服务。这样画面就是「模型看到的那一帧」，
  演示时可信度最高，也不会两个进程抢摄像头。
