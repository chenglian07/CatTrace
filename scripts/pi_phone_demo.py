#!/usr/bin/env python3
"""摄像头 → 猫/非猫分类 → 网页实时预览。

用途：拿手机屏幕显示一张猫的照片，凑到树莓派摄像头前，看网页上的判定翻转，
用来验证「摄像头拍到的是手机上的图片」时模型是否还判得对。

    # 树莓派上（CSI 摄像头）
    ssh pi-cat
    cd ~/catvision && source ~/venvs/catvision/bin/activate
    python scripts/pi_phone_demo.py --rotate 180 --port 8000

    # 然后在这台电脑浏览器打开
    http://192.168.31.252:8000/

页面里：左边是实时画面（带判定和置信度），右边是最近 30 帧的记录。
点「保存快照」会把当前帧存到 /dev/shm（内存盘，不写 SD 卡）。

没有摄像头时也能验证链路本身（拿图片当视频源）：
    python scripts/pi_phone_demo.py --source file:tests/fixtures/classifier/chelsea_cat.png
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.catface.cat_classifier import CatClassifier  # noqa: E402

STATE_LOCK = threading.Lock()
STATE = {
    "label": "starting",
    "p_cat": 0.0,
    "fps": 0.0,
    "frames": 0,
    "luma": 0.0,
    "history": deque(maxlen=30),
    "jpeg": b"",
    "raw": None,
    "started": time.time(),
}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def get_font(size: int):
    """找一个能显示中文的字体，找不到就退回默认字体。"""
    for p in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/arialbd.ttf",
    ):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def annotate(rgb: np.ndarray, label: str, p_cat: float, fps: float) -> Image.Image:
    """在画面上画判定条：顶部大字 + 置信度条。"""
    img = Image.fromarray(rgb)
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    font = get_font(max(18, h // 12))
    small = get_font(max(12, h // 26))

    is_cat = label == "cat"
    color = (46, 204, 113) if is_cat else (231, 76, 60)
    text = "CAT" if is_cat else "NOT CAT"

    # 顶部条
    draw.rectangle([0, 0, w, int(h * 0.16)], fill=(0, 0, 0, 170))
    draw.text((12, int(h * 0.02)), text, font=font, fill=color + (255,))
    draw.text((12, int(h * 0.115)), f"p_cat={p_cat:.3f}  {fps:.1f} FPS", font=small,
              fill=(220, 220, 220, 255))

    # 右侧置信度条
    bar_w = max(10, w // 28)
    bx = w - bar_w - 10
    top, bottom = int(h * 0.20), int(h * 0.94)
    draw.rectangle([bx, top, bx + bar_w, bottom], fill=(0, 0, 0, 120))
    frac = max(0.0, min(1.0, p_cat))
    fill_h = int((bottom - top) * frac)
    draw.rectangle([bx, bottom - fill_h, bx + bar_w, bottom], fill=color + (255,))
    # 0.5 阈值刻度线
    mid = bottom - int((bottom - top) * 0.5)
    draw.line([bx - 6, mid, bx + bar_w + 2, mid], fill=(255, 255, 255, 200), width=2)
    return img


def encode(img: Image.Image, quality: int = 80) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def open_camera(args):
    """返回一个 frame() -> RGB ndarray 的函数。"""
    if args.source.startswith("file:"):
        path = Path(args.source[5:])
        log(f"用图片当视频源（测试模式）：{path}")

        def frame():
            with Image.open(path) as im:
                return np.asarray(im.convert("RGB").resize((args.width, args.height)))

        return frame, (lambda: None)

    from picamera2 import Picamera2

    picam2 = Picamera2()
    cfg = picam2.create_preview_configuration(
        main={"size": (args.width, args.height), "format": "RGB888"}
    )
    picam2.configure(cfg)
    picam2.start()
    time.sleep(1.0)
    log(f"摄像头已启动 {args.width}x{args.height}")

    def frame():
        return picam2.capture_array()

    def close():
        picam2.stop()
        picam2.close()

    return frame, close


def capture_loop(args, clf, frame_fn, close_fn):
    fps_smooth = 0.0
    last = time.perf_counter()
    try:
        while True:
            rgb = frame_fn()

            if args.rotate == 180:
                rgb = rgb[::-1, ::-1]
            elif args.rotate == 90:
                rgb = np.rot90(rgb, k=-1)
            elif args.rotate == 270:
                rgb = np.rot90(rgb, k=1)

            probs = clf.predict_proba(rgb)
            label = "cat" if probs[0] >= args.threshold else "notcat"
            luma = float(rgb.mean())

            now = time.perf_counter()
            dt = now - last
            last = now
            if dt > 0:
                fps_smooth = 0.9 * fps_smooth + 0.1 * (1.0 / dt) if fps_smooth else 1.0 / dt

            img = annotate(rgb, label, float(probs[0]), fps_smooth)
            jpg = encode(img)

            with STATE_LOCK:
                STATE["label"] = label
                STATE["p_cat"] = float(probs[0])
                STATE["fps"] = fps_smooth
                STATE["frames"] += 1
                STATE["luma"] = luma
                STATE["jpeg"] = jpg
                STATE["raw"] = rgb
                STATE["history"].appendleft(
                    {
                        "t": round(time.time() - STATE["started"], 2),
                        "label": label,
                        "p_cat": round(float(probs[0]), 4),
                    }
                )

            if STATE["frames"] % 10 == 0:
                log(f"#{STATE['frames']:4d} {label:6s} p_cat={probs[0]:.4f} {fps_smooth:.1f} FPS")

            time.sleep(max(0.0, args.interval - (time.perf_counter() - now)))
    except KeyboardInterrupt:
        log("中断")
    finally:
        close_fn()


PAGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>猫识别 · 摄像头实时验证</title>
<style>
 body{margin:0;background:#12141a;color:#e8e8e8;font-family:system-ui,Segoe UI,sans-serif}
 header{padding:12px 16px;background:#1b1e27;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
 h1{font-size:16px;margin:0;font-weight:600}
 .pill{padding:4px 10px;border-radius:999px;background:#2a2f3d;font-size:13px}
 #lab{font-weight:700;font-size:15px}
 .wrap{display:flex;gap:16px;padding:16px;flex-wrap:wrap}
 .left{flex:1 1 640px;min-width:320px}
 .right{flex:0 1 320px;min-width:280px}
 img{width:100%;border-radius:10px;background:#000;display:block}
 table{width:100%;border-collapse:collapse;font-size:13px}
 td{padding:3px 6px;border-bottom:1px solid #262b36}
 .cat{color:#2ecc71;font-weight:600}.notcat{color:#e74c3c;font-weight:600}
 button{background:#2f6fed;color:#fff;border:0;padding:8px 14px;border-radius:8px;cursor:pointer}
 .hint{font-size:12px;color:#8b93a7;padding:0 16px 16px;line-height:1.6}
 .warn{display:none}
 .warn.on{display:block;margin:0 16px 12px;padding:10px 14px;border-radius:8px;
          background:#4a1d1d;border:1px solid #a33;color:#ffd9d9;font-size:13px}
</style></head><body>
<header>
  <h1>猫识别 · 摄像头实时验证</h1>
  <span class="pill">判定：<span id="lab">--</span></span>
  <span class="pill">p_cat：<span id="p">--</span></span>
  <span class="pill"><span id="fps">--</span> FPS</span>
  <span class="pill">帧数 <span id="n">0</span></span>
  <span class="pill">画面亮度 <span id="lum">--</span></span>
  <span class="pill" id="link">●</span>
  <button onclick="snap()">保存快照</button>
</header>
<div id="warn"></div>
<div class="wrap">
  <div class="left"><img id="s" alt="等待画面…"></div>
  <div class="right"><table id="hist"></table></div>
</div>
<div class="hint">
 把手机屏幕上的猫图凑到摄像头前，判定应该在 CAT / NOT CAT 之间翻转。
 若画面上下颠倒，用 <code>--rotate 180</code> 启动。快照存在树莓派的 /dev/shm/shots。
</div>
<script>
let lastFrameTs = 0, lastOk = Date.now();
const img = document.getElementById('s');

// 用轮询单帧代替 MJPEG 长连接：连接断了能自己恢复，不会永远卡在旧帧上
function pull(){
  const t = Date.now();
  const url = '/frame.jpg?t=' + t;
  const probe = new Image();
  probe.onload = () => {
    img.src = url;
    lastOk = Date.now();
    document.getElementById('link').textContent = '● 在线';
    document.getElementById('link').style.color = '#2ecc71';
  };
  probe.onerror = () => {
    document.getElementById('link').textContent = '● 断线重连中';
    document.getElementById('link').style.color = '#e74c3c';
  };
  probe.src = url;
}

async function tick(){
  try{
    const r = await fetch('/stats'); const d = await r.json();
    const lab = document.getElementById('lab');
    lab.textContent = d.label === 'cat' ? 'CAT（是猫）' : 'NOT CAT（不是猫）';
    lab.className = d.label === 'cat' ? 'cat' : 'notcat';
    document.getElementById('p').textContent = d.p_cat.toFixed(4);
    document.getElementById('fps').textContent = d.fps.toFixed(1);
    document.getElementById('n').textContent = d.frames;
    document.getElementById('lum').textContent = d.luma.toFixed(0);

    const w = document.getElementById('warn');
    if (d.luma < 25) {
      w.textContent = '⚠️ 画面几乎全黑（亮度 ' + d.luma.toFixed(0) + '/255）：镜头可能被挡住了，或者手机贴太近把镜头盖住了。';
      w.className = 'warn on';
    } else if (d.luma > 235) {
      w.textContent = '⚠️ 画面过曝（亮度 ' + d.luma.toFixed(0) + '/255）：手机屏幕太近/太亮，往后退一点。';
      w.className = 'warn on';
    } else {
      w.className = 'warn';
    }

    document.getElementById('hist').innerHTML = d.history.map(h =>
      `<tr><td>${h.t.toFixed(1)}s</td><td class="${h.label}">${h.label.toUpperCase()}</td><td>${h.p_cat.toFixed(4)}</td></tr>`
    ).join('');
  }catch(e){}
}
async function snap(){ await fetch('/snapshot', {method:'POST'}); alert('已保存到 /dev/shm/shots'); }

setInterval(pull, 250);      // 画面 4 次/秒
setInterval(tick, 1000);     // 数字 1 次/秒
pull(); tick();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):  # 静音默认访问日志
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/stats":
            with STATE_LOCK:
                data = {
                    "label": STATE["label"],
                    "p_cat": STATE["p_cat"],
                    "fps": round(STATE["fps"], 2),
                    "frames": STATE["frames"],
                    "luma": round(STATE["luma"], 1),
                    "history": list(STATE["history"]),
                }
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path.startswith(("/frame.jpg", "/snapshot.jpg")):
            with STATE_LOCK:
                jpg = STATE["jpeg"]
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpg)))
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.end_headers()
            self.wfile.write(jpg)

        elif self.path.startswith("/stream"):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                while True:
                    with STATE_LOCK:
                        jpg = STATE["jpeg"]
                    if jpg:
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(jpg)}\r\n\r\n".encode())
                        self.wfile.write(jpg)
                        self.wfile.write(b"\r\n")
                    time.sleep(0.15)
            except (BrokenPipeError, ConnectionResetError):
                pass

        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/snapshot":
            self.send_error(404)
            return
        out_dir = Path("/dev/shm/shots") if Path("/dev/shm").exists() else Path("shots")
        out_dir.mkdir(parents=True, exist_ok=True)
        with STATE_LOCK:
            raw, label, p_cat = STATE["raw"], STATE["label"], STATE["p_cat"]
        if raw is not None:
            name = out_dir / f"shot_{time.strftime('%H%M%S')}_{label}_{p_cat:.2f}.jpg"
            Image.fromarray(raw).save(name, quality=90)
            log(f"快照已保存 {name}")
        self.send_response(204)
        self.end_headers()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/cat_vs_notcat.onnx")
    ap.add_argument("--source", default="csi", help="csi 或 file:<图片路径>（测试用）")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=float, default=5.0, help="推理帧率上限")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--rotate", type=int, default=0, choices=(0, 90, 180, 270))
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()
    args.interval = 1.0 / args.fps if args.fps > 0 else 0.0

    clf = CatClassifier(args.model, intra_op_threads=args.threads)
    log(f"模型已加载 {args.model}")

    frame_fn, close_fn = open_camera(args)
    worker = threading.Thread(
        target=capture_loop, args=(args, clf, frame_fn, close_fn), daemon=True
    )
    worker.start()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    log(f"打开 http://<树莓派IP>:{args.port}/ 看实时画面")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("关闭")
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
