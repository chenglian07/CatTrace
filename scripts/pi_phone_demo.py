#!/usr/bin/env python3
"""摄像头 → 猫/非猫分类 → 网页实时预览。

用途：拿手机屏幕显示一张猫的照片，凑到树莓派摄像头前，看网页上的判定翻转，
用来验证「摄像头拍到的是手机上的图片」时模型是否还判得对。

    # 树莓派上（CSI 摄像头）
    ssh pi-cat
    cd ~/catvision && source ~/venvs/catvision/bin/activate
    python scripts/pi_phone_demo.py --rotate 180 --port 8000 --stream-fps 8 --fps 2 --threads 1

    # 然后在这台电脑浏览器打开
    http://192.168.31.252:8000/

页面里：左边是实时视频，右边是最近 30 次推理结果；两项互不阻塞。
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
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.catface.cat_classifier import CatClassifier  # noqa: E402

STATE_LOCK = threading.Lock()
STATE = {
    "label": "starting",
    "p_cat": 0.0,
    "fps": 0.0,
    "luma": 0.0,
    "frames": 0,
    "stream_fps": 0.0,
    "stream_frames": 0,
    "history": deque(maxlen=30),
    "jpeg": b"",
    "raw": None,
    "started": time.time(),
}
# 采集线程发布新帧，每个直播连接只在该帧真正到达时写出，避免固定轮询拖慢直播。
FRAME_READY = threading.Condition(STATE_LOCK)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


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


def capture_loop(args, frame_fn, close_fn):
    """持续采集并推流；采集频率与 AI 推理频率解耦。"""
    frame_interval = 1.0 / args.stream_fps if args.stream_fps > 0 else 0.0
    fps_smooth = 0.0
    last = time.perf_counter()
    try:
        while True:
            started = time.perf_counter()
            rgb = frame_fn()

            if args.rotate == 180:
                rgb = rgb[::-1, ::-1]
            elif args.rotate == 90:
                rgb = np.rot90(rgb, k=-1)
            elif args.rotate == 270:
                rgb = np.rot90(rgb, k=1)

            # 网页直播间始终拿原始画面，不把调试标注烧进视频。
            jpg = encode(Image.fromarray(rgb), quality=args.jpeg_quality)

            now = time.perf_counter()
            dt = now - last
            last = now
            if dt > 0:
                fps_smooth = 0.9 * fps_smooth + 0.1 * (1.0 / dt) if fps_smooth else 1.0 / dt

            with FRAME_READY:
                STATE["raw"] = rgb
                STATE["jpeg"] = jpg
                STATE["stream_frames"] += 1
                STATE["stream_fps"] = fps_smooth
                FRAME_READY.notify_all()

            time.sleep(max(0.0, frame_interval - (time.perf_counter() - started)))
    except KeyboardInterrupt:
        log("采集中断")
    except Exception as exc:
        log(f"采集线程退出：{exc}")
    finally:
        close_fn()


def inference_loop(args, clf):
    """按推理帧率读取最新画面，分类结果不会阻塞直播。"""
    fps_smooth = 0.0
    last = time.perf_counter()
    while True:
        started = time.perf_counter()
        with STATE_LOCK:
            rgb = STATE["raw"]
        if rgb is None:
            time.sleep(0.1)
            continue

        try:
            probs = clf.predict_proba(rgb)
        except Exception as exc:
            log(f"推理失败：{exc}")
            time.sleep(1.0)
            continue

        p_cat = float(probs[0])
        label = "cat" if p_cat >= args.threshold else "notcat"
        luma = float(rgb.mean())

        now = time.perf_counter()
        dt = now - last
        last = now
        if dt > 0:
            fps_smooth = 0.9 * fps_smooth + 0.1 * (1.0 / dt) if fps_smooth else 1.0 / dt

        with STATE_LOCK:
            STATE["label"] = label
            STATE["p_cat"] = p_cat
            STATE["fps"] = fps_smooth
            STATE["luma"] = luma
            STATE["frames"] += 1
            STATE["history"].appendleft(
                {
                    "t": round(time.time() - STATE["started"], 2),
                    "label": label,
                    "p_cat": round(p_cat, 4),
                }
            )
            frame_no = STATE["frames"]

        if frame_no % 10 == 0:
            log(f"#{frame_no:4d} {label:6s} p_cat={p_cat:.4f} {fps_smooth:.1f} FPS")

        time.sleep(max(0.0, args.interval - (time.perf_counter() - started)))


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
</style></head><body>
<header>
  <h1>猫识别 · 摄像头实时验证</h1>
  <span class="pill">判定：<span id="lab">--</span></span>
  <span class="pill">p_cat：<span id="p">--</span></span>
  <span class="pill">视频 <span id="stream-fps">--</span> FPS</span>
  <span class="pill">识别 <span id="fps">--</span> FPS</span>
  <span class="pill">识别帧数 <span id="n">0</span></span>
  <button onclick="snap()">保存快照</button>
</header>
<div class="wrap">
  <div class="left"><img id="s" src="/stream"></div>
  <div class="right"><table id="hist"></table></div>
</div>
<div class="hint">
 把手机屏幕上的猫图凑到摄像头前，判定应该在 CAT / NOT CAT 之间翻转。
 若画面上下颠倒，用 <code>--rotate 180</code> 启动。快照存在树莓派的 /dev/shm/shots。
</div>
<script>
async function tick(){
  try{
    const r = await fetch('/stats'); const d = await r.json();
    const lab = document.getElementById('lab');
    lab.textContent = d.label === 'cat' ? 'CAT（是猫）' : 'NOT CAT（不是猫）';
    lab.className = d.label === 'cat' ? 'cat' : 'notcat';
    document.getElementById('p').textContent = d.p_cat.toFixed(4);
    document.getElementById('stream-fps').textContent = d.stream_fps.toFixed(1);
    document.getElementById('fps').textContent = d.fps.toFixed(1);
    document.getElementById('n').textContent = d.frames;
    document.getElementById('hist').innerHTML = d.history.map(h =>
      `<tr><td>${h.t.toFixed(1)}s</td><td class="${h.label}">${h.label.toUpperCase()}</td><td>${h.p_cat.toFixed(4)}</td></tr>`
    ).join('');
  }catch(e){}
}
async function snap(){ await fetch('/snapshot', {method:'POST'}); alert('已保存到 /dev/shm/shots'); }
setInterval(tick, 1000); tick();
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
                    "luma": round(STATE["luma"], 1),
                    "frames": STATE["frames"],
                    "stream_fps": round(STATE["stream_fps"], 2),
                    "stream_frames": STATE["stream_frames"],
                    "history": list(STATE["history"]),
                }
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                last_frame = -1
                while True:
                    with FRAME_READY:
                        if STATE["stream_frames"] == last_frame:
                            FRAME_READY.wait(timeout=2.0)
                        jpg = STATE["jpeg"]
                        frame_no = STATE["stream_frames"]
                    if not jpg or frame_no == last_frame:
                        continue
                    last_frame = frame_no
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(jpg)}\r\n\r\n".encode())
                    self.wfile.write(jpg)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass

        elif self.path == "/snapshot.jpg":
            with STATE_LOCK:
                jpg = STATE["jpeg"]
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpg)))
            self.end_headers()
            self.wfile.write(jpg)

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
    ap.add_argument("--fps", type=float, default=2.0, help="AI 推理帧率上限")
    ap.add_argument("--stream-fps", type=float, default=8.0, help="实时视频帧率上限")
    ap.add_argument("--threads", type=int, default=1, help="AI 推理线程数")
    ap.add_argument("--jpeg-quality", type=int, default=75, help="推流 JPEG 质量")
    ap.add_argument("--rotate", type=int, default=0, choices=(0, 90, 180, 270))
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()
    args.interval = 1.0 / args.fps if args.fps > 0 else 0.0

    clf = CatClassifier(args.model, intra_op_threads=args.threads)
    log(f"模型已加载 {args.model}")

    frame_fn, close_fn = open_camera(args)
    capture_worker = threading.Thread(
        target=capture_loop, args=(args, frame_fn, close_fn), name="camera-stream", daemon=True
    )
    inference_worker = threading.Thread(
        target=inference_loop, args=(args, clf), name="cat-inference", daemon=True
    )
    capture_worker.start()
    inference_worker.start()

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
