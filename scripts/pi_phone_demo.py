#!/usr/bin/env python3
"""摄像头 → 猫/非猫 + 剪耳（绝育）判定 → 网页实时预览。

两级串联，和原来的屏幕演示同一套模型：
  1. cat_vs_notcat：画面里有没有猫（没有猫就不给绝育结论，避免对墙报"已绝育"）；
  2. earnotch：这只猫剪没剪耳 → 已绝育 / 未绝育 / 看不清。

用途：树莓派网页（含桌面 kiosk）实时显示摄像头画面和判定，手机/电脑也能看。

    # 树莓派上（CSI 摄像头）
    ssh pi-cat
    cd ~/catvision && source ~/venvs/catvision/bin/activate
    python scripts/pi_phone_demo.py --rotate 180 --port 8000

    # 然后在这台电脑浏览器打开
    http://192.168.31.252:8000/

页面里：左边是实时画面（带判定和置信度），右边是最近 30 帧的记录。
点「保存快照」会把当前帧存到 /dev/shm（内存盘，不写 SD 卡）。

树莓派桌面全屏（Chromium kiosk）用 /kiosk：只留画面，隐藏页头和记录表，
适合双击桌面图标直接看。安装脚本见 scripts/install_pi_kiosk.sh。
    http://127.0.0.1:8000/kiosk

没有剪耳权重 / 不想跑第二级时加 --earnotch off，退回只看猫/非猫；
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

# 模型依赖 onnxruntime，放到 main() 里再 import：
# 这样只跑网页（或单测页面路由）时不需要装推理运行时。

STATE_LOCK = threading.Lock()
STATE = {
    "label": "starting",
    "p_cat": 0.0,
    "fps": 0.0,
    "frames": 0,
    "luma": 0.0,
    "verdict": "starting",
    "p_notch": None,
    "notched": None,
    "ear_enabled": False,
    "history": deque(maxlen=30),
    "jpeg": b"",
    "raw": None,
    "started": time.time(),
}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


CJK_FONTS = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "C:/Windows/Fonts/msyh.ttc",
)
FALLBACK_FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)


def get_font(size: int):
    """优先中文字体（HUD 用中文），没有就退回西文字体。"""
    for p in CJK_FONTS + FALLBACK_FONTS:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def has_cjk_font() -> bool:
    return any(Path(p).is_file() for p in CJK_FONTS)


VERDICT_COLOR = {
    "notched": (46, 204, 113),
    "intact": (243, 156, 18),
    "uncertain": (149, 165, 166),
    "nocat": (231, 76, 60),
    "cat": (46, 204, 113),
}
VERDICT_TEXT = {
    "zh": {
        "notched": "已剪耳 · 已绝育",
        "intact": "未剪耳 · 未绝育",
        "uncertain": "看不清 · 不下结论",
        "nocat": "没有猫",
        "cat": "是猫",
    },
    "en": {
        "notched": "NOTCHED · NEUTERED",
        "intact": "INTACT · NOT NEUTERED",
        "uncertain": "UNCERTAIN",
        "nocat": "NOT CAT",
        "cat": "CAT",
    },
}


def crop_box(w: int, h: int, frac: float) -> tuple[int, int, int, int]:
    """取景框：只对画面中央的正方形做推理，猫离得远时用 0.5~0.7。"""
    if frac >= 1.0:
        return 0, 0, w, h
    s = int(min(w, h) * frac)
    cx, cy = w // 2, h // 2
    return cx - s // 2, cy - s // 2, cx + s // 2, cy + s // 2


def classify_notch(prob: float, threshold: float, band: float) -> str:
    """三档判定，比较方向与 modules.earnotch 的 `_one()` 保持一致。"""
    if prob > threshold + band:
        return "notched"
    if prob < threshold - band:
        return "intact"
    return "uncertain"


def annotate(
    rgb: np.ndarray,
    *,
    label: str,
    p_cat: float,
    fps: float,
    verdict: str | None = None,
    p_notch: float | None = None,
    notch_threshold: float = 0.5,
    notch_band: float = 0.0,
) -> Image.Image:
    """顶部大字判定 + 右侧概率条；剪耳可用时显示绝育结论和 p_notch。"""
    img = Image.fromarray(rgb)
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    font = get_font(max(18, h // 12))
    small = get_font(max(12, h // 26))
    texts = VERDICT_TEXT["zh" if has_cjk_font() else "en"]

    key = verdict or ("cat" if label == "cat" else "nocat")
    color = VERDICT_COLOR.get(key, (231, 76, 60))
    text = texts.get(key, texts["nocat"])

    # 顶部条
    draw.rectangle([0, 0, w, int(h * 0.16)], fill=(0, 0, 0, 170))
    draw.text((12, int(h * 0.02)), text, font=font, fill=color + (255,))
    second = []
    if p_notch is not None:
        second.append(f"p_notch={p_notch:.3f}")
    second.append(f"p_cat={p_cat:.3f}")
    second.append(f"{fps:.1f} FPS")
    draw.text((12, int(h * 0.115)), "  ".join(second), font=small,
              fill=(220, 220, 220, 255))

    # 右侧概率条：有剪耳结论时画 p_notch，否则画 p_cat
    bar_w = max(10, w // 28)
    bx = w - bar_w - 10
    top, bottom = int(h * 0.20), int(h * 0.94)
    draw.rectangle([bx, top, bx + bar_w, bottom], fill=(0, 0, 0, 120))
    value = p_notch if p_notch is not None else p_cat
    fill_h = int((bottom - top) * max(0.0, min(1.0, value)))
    draw.rectangle([bx, bottom - fill_h, bx + bar_w, bottom], fill=color + (255,))

    if p_notch is not None:
        thr_line, band = notch_threshold, notch_band
    else:
        thr_line, band = 0.5, 0.0
    if band > 0:
        band_top = bottom - int((bottom - top) * min(1.0, thr_line + band))
        band_bottom = bottom - int((bottom - top) * max(0.0, thr_line - band))
        draw.rectangle([bx, band_top, bx + bar_w, band_bottom], fill=(255, 255, 255, 40))
    mid = bottom - int((bottom - top) * max(0.0, min(1.0, thr_line)))
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


def capture_loop(args, clf, notch, frame_fn, close_fn):
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

            h, w = rgb.shape[:2]
            x0, y0, x1, y1 = crop_box(w, h, args.crop)
            roi = Image.fromarray(rgb[y0:y1, x0:x1])

            p_cat = float(clf.predict_proba(roi)[0])
            label = "cat" if p_cat >= args.threshold else "notcat"
            p_notch = None
            verdict = None
            if label == "cat" and notch is not None:
                try:
                    p_notch = float(notch.predict_image(roi))
                    verdict = classify_notch(p_notch, notch.threshold, notch.band)
                except Exception as exc:  # 单帧失败不该拖垮整条流
                    log(f"剪耳推理失败，跳过本帧：{exc}")
            luma = float(rgb.mean())

            now = time.perf_counter()
            dt = now - last
            last = now
            if dt > 0:
                fps_smooth = 0.9 * fps_smooth + 0.1 * (1.0 / dt) if fps_smooth else 1.0 / dt

            img = annotate(
                rgb,
                label=label,
                p_cat=p_cat,
                fps=fps_smooth,
                verdict=verdict,
                p_notch=p_notch,
                notch_threshold=notch.threshold if notch else 0.5,
                notch_band=notch.band if notch else 0.0,
            )
            jpg = encode(img)

            with STATE_LOCK:
                STATE["label"] = label
                STATE["p_cat"] = p_cat
                STATE["fps"] = fps_smooth
                STATE["frames"] += 1
                STATE["luma"] = luma
                STATE["jpeg"] = jpg
                STATE["raw"] = rgb
                STATE["p_notch"] = p_notch
                STATE["notched"] = None if verdict in (None, "uncertain") else verdict == "notched"
                STATE["verdict"] = verdict or ("nocat" if label != "cat" else "cat")
                STATE["history"].appendleft(
                    {
                        "t": round(time.time() - STATE["started"], 2),
                        "label": label,
                        "p_cat": round(p_cat, 4),
                        "verdict": STATE["verdict"],
                        "p_notch": round(p_notch, 4) if p_notch is not None else None,
                    }
                )

            if STATE["frames"] % 10 == 0:
                extra = f" {verdict} p_notch={p_notch:.3f}" if p_notch is not None else ""
                log(f"#{STATE['frames']:4d} {label:6s} p_cat={p_cat:.4f}{extra} {fps_smooth:.1f} FPS")

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
 .notched{color:#2ecc71;font-weight:600}.intact{color:#f39c12;font-weight:600}
 .uncertain{color:#95a5a6;font-weight:600}
 button{background:#2f6fed;color:#fff;border:0;padding:8px 14px;border-radius:8px;cursor:pointer}
 .hint{font-size:12px;color:#8b93a7;padding:0 16px 16px;line-height:1.6}
 .warn{display:none}
 .warn.on{display:block;margin:0 16px 12px;padding:10px 14px;border-radius:8px;
          background:#4a1d1d;border:1px solid #a33;color:#ffd9d9;font-size:13px}
 /* kiosk：只留全屏画面，给树莓派桌面快捷方式 / Chromium --kiosk 用 */
 body.kiosk{overflow:hidden;background:#000;cursor:none}
 body.kiosk header,body.kiosk .right,body.kiosk .hint,body.kiosk #warn{display:none}
 body.kiosk .wrap{padding:0;gap:0;display:block}
 body.kiosk .left{min-width:0}
 body.kiosk img{width:100vw;height:100vh;object-fit:contain;border-radius:0}
 #kstatus{display:none}
 body.kiosk #kstatus{display:block;position:fixed;left:50%;bottom:24px;transform:translateX(-50%);
   padding:8px 16px;border-radius:999px;background:rgba(0,0,0,.72);color:#fff;font-size:14px}
 body.kiosk #kstatus.ok{display:none}
</style></head><body>
<header>
  <h1>猫识别 · 剪耳（绝育）判定</h1>
  <span class="pill">判定：<span id="lab">--</span></span>
  <span class="pill" id="neuPill" style="display:none">绝育：<span id="neu">--</span></span>
  <span class="pill">p_cat：<span id="p">--</span></span>
  <span class="pill"><span id="fps">--</span> FPS</span>
  <span class="pill">帧数 <span id="n">0</span></span>
  <span class="pill">画面亮度 <span id="lum">--</span></span>
  <span class="pill" id="link">●</span>
  <button onclick="snap()">保存快照</button>
</header>
<div id="warn"></div>
<div id="kstatus"></div>
<div class="wrap">
  <div class="left"><img id="s" alt="等待画面…"></div>
  <div class="right"><table id="hist"></table></div>
</div>
<div class="hint">
 判定分两级：先看画面里有没有猫，有猫再判剪耳（绝育）状态。
 若画面上下颠倒，用 <code>--rotate 180</code> 启动。快照存在树莓派的 /dev/shm/shots。
</div>
<script>
let lastFrameTs = 0, lastOk = Date.now();
const img = document.getElementById('s');
const kstatus = document.getElementById('kstatus');
// /kiosk 或 ?kiosk=1：整页只留画面
let kpath = location.pathname;
while (kpath.length > 1 && kpath.endsWith('/')) kpath = kpath.slice(0, -1);
const KIOSK = kpath === '/kiosk'
  || new URLSearchParams(location.search).has('kiosk');
if (KIOSK) document.body.classList.add('kiosk');

const NEU_TEXT = {notched: '已剪耳 · 已绝育', intact: '未剪耳 · 未绝育',
                  uncertain: '看不清 · 不下结论', nocat: '没有猫', cat: '—'};
const NEU_SHORT = {notched: '已剪耳', intact: '未剪耳', uncertain: '看不清', nocat: '—', cat: ''};

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
    if (kstatus) kstatus.className = 'ok';
  };
  probe.onerror = () => {
    document.getElementById('link').textContent = '● 断线重连中';
    document.getElementById('link').style.color = '#e74c3c';
    if (kstatus) { kstatus.className = ''; kstatus.textContent = '断线重连中…'; }
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

    const neuPill = document.getElementById('neuPill');
    if (d.ear_enabled) {
      neuPill.style.display = '';
      const neu = document.getElementById('neu');
      neu.textContent = NEU_TEXT[d.verdict] || '—';
      neu.className = d.verdict === 'notched' ? 'notched'
        : (d.verdict === 'intact' ? 'intact' : '');
    }

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
      `<tr><td>${h.t.toFixed(1)}s</td><td class="${h.label}">${h.label.toUpperCase()}</td><td>${h.p_cat.toFixed(4)}</td><td class="${h.verdict}">${NEU_SHORT[h.verdict] || ''}</td></tr>`
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
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html", "/kiosk", "/kiosk/"):
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif path == "/stats":
            with STATE_LOCK:
                data = {
                    "label": STATE["label"],
                    "p_cat": STATE["p_cat"],
                    "fps": round(STATE["fps"], 2),
                    "frames": STATE["frames"],
                    "luma": round(STATE["luma"], 1),
                    "verdict": STATE["verdict"],
                    "p_notch": STATE["p_notch"],
                    "notched": STATE["notched"],
                    "ear_enabled": STATE["ear_enabled"],
                    "history": list(STATE["history"]),
                }
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif path.startswith(("/frame.jpg", "/snapshot.jpg")):
            with STATE_LOCK:
                jpg = STATE["jpeg"]
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpg)))
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.end_headers()
            self.wfile.write(jpg)

        elif path.startswith("/stream"):
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
    ap.add_argument("--threshold", type=float, default=0.5, help="猫/非猫判定阈值")
    ap.add_argument("--crop", type=float, default=1.0,
                    help="只对画面中央正方形推理（1.0=整帧，猫远时 0.5~0.7）")
    ap.add_argument("--earnotch", default="auto", choices=("auto", "on", "off"),
                    help="剪耳判定：auto=有模型就开，off=只看猫/非猫")
    ap.add_argument("--earnotch-model", default="",
                    help="剪耳 ONNX 路径；留空按平台自动选（Pi 用 resnet18）")
    ap.add_argument("--notch-threshold", type=float, default=None, help="覆盖权重里的剪耳阈值")
    ap.add_argument("--notch-band", type=float, default=None, help="覆盖不确定带宽度")
    ap.add_argument("--no-tta", action="store_true",
                    help="关掉剪耳模型的水平翻转 TTA（快一倍，但阈值是按 TTA 校准的）")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()
    args.interval = 1.0 / args.fps if args.fps > 0 else 0.0

    from modules.catface.cat_classifier import CatClassifier

    clf = CatClassifier(args.model, intra_op_threads=args.threads)
    log(f"猫/非猫模型 {args.model}")

    notch = None
    if args.earnotch != "off":
        from modules.earnotch import EarNotchModel

        try:
            notch = EarNotchModel(
                model_path=args.earnotch_model or None,
                threshold=args.notch_threshold,
                band=args.notch_band,
                tta=not args.no_tta,
                threads=args.threads,
            )
        except Exception as exc:
            if args.earnotch == "on":
                raise
            log(f"剪耳模型不可用，退回只看猫/非猫：{exc}")
        else:
            log(
                f"剪耳模型 {notch.model_path.name} input={notch.input_size} "
                f"thr={notch.threshold:.2f}±{notch.band:.2f} tta={notch.tta}"
            )

    with STATE_LOCK:
        STATE["ear_enabled"] = notch is not None

    frame_fn, close_fn = open_camera(args)
    worker = threading.Thread(
        target=capture_loop, args=(args, clf, notch, frame_fn, close_fn), daemon=True
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
