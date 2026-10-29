#!/usr/bin/env python3
"""本地屏幕模式：摄像头实时画面直接显示在 Pi 的 DSI/HDMI 屏上。

不依赖浏览器，不跑 HTTP server，一个进程搞定 捕获 → 推理 → 渲染 全链路。

    ssh pi-cat
    cd ~/catvision && source ~/venvs/catvision/bin/activate
    pip install pygame         # 首次要装，约 2MB
    python scripts/pi_screen_demo.py

在屏幕上：大字 CAT / NOT CAT，p_cat，FPS，置信度条。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modules.catface.cat_classifier import CatClassifier  # noqa: E402


def get_font(size: int) -> ImageFont.FreeTypeFont:
    for p in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def annotate(rgb: np.ndarray, label: str, p_cat: float, fps: float, w: int, h: int) -> Image.Image:
    img = Image.fromarray(rgb)
    draw = ImageDraw.Draw(img, "RGBA")
    font = get_font(max(16, h // 18))
    small = get_font(max(11, h // 28))

    is_cat = label == "cat"
    color = (46, 204, 113) if is_cat else (231, 76, 60)
    text = "CAT" if is_cat else "NOT CAT"

    # 顶部半透明条
    bar_h = int(h * 0.16)
    draw.rectangle([0, 0, w, bar_h], fill=(0, 0, 0, 170))
    draw.text((8, int(h * 0.015)), text, font=font, fill=color + (255,))
    draw.text((8, int(h * 0.11)), f"p_cat={p_cat:.3f}  {fps:.1f} FPS", font=small,
              fill=(220, 220, 220, 255))

    # 右侧置信度条
    bar_w = max(8, w // 30)
    bx = w - bar_w - 6
    top, bottom = int(h * 0.20), int(h * 0.94)
    draw.rectangle([bx, top, bx + bar_w, bottom], fill=(0, 0, 0, 120))
    frac = max(0.0, min(1.0, p_cat))
    fill_h = int((bottom - top) * frac)
    draw.rectangle([bx, bottom - fill_h, bx + bar_w, bottom], fill=color + (255,))
    mid = bottom - int((bottom - top) * 0.5)
    draw.line([bx - 4, mid, bx + bar_w + 2, mid], fill=(255, 255, 255, 200), width=2)

    # 底部状态行
    footer_h = int(h * 0.05)
    luma = float(rgb.mean())
    if luma < 25:
        hint = f"亮度{luma:.0f} – 镜头被遮？"
    elif luma > 235:
        hint = f"亮度{luma:.0f} – 过曝，退远一点"
    else:
        hint = f"亮度 {luma:.0f}"
    draw.rectangle([0, h - footer_h, w, h], fill=(0, 0, 0, 140))
    draw.text((6, h - footer_h + 2), hint, font=small, fill=(180, 180, 180, 255))

    return img


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/cat_vs_notcat.onnx")
    ap.add_argument("--fps", type=float, default=5.0, help="推理帧率上限")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--rotate", type=int, default=180, choices=(0, 90, 180, 270))
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fullscreen", action="store_true", default=True)
    args = ap.parse_args()

    args.interval = 1.0 / args.fps if args.fps > 0 else 0.0

    # ---------- 加载模型 ----------
    print(f"加载模型 {args.model} ...", flush=True)
    clf = CatClassifier(args.model, intra_op_threads=args.threads)

    # ---------- 摄像头 ----------
    from picamera2 import Picamera2

    picam2 = Picamera2()
    cfg = picam2.create_preview_configuration(
        main={"size": (args.width, args.height), "format": "RGB888"}
    )
    picam2.configure(cfg)
    picam2.start()
    time.sleep(1.0)
    print(f"摄像头已启动 {args.width}x{args.height}", flush=True)

    # ---------- 初始化 pygame 全屏 ----------
    import pygame

    pygame.init()
    if args.fullscreen:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    else:
        screen = pygame.display.set_mode((args.width, args.height))
    sw, sh = screen.get_size()
    pygame.mouse.set_visible(False)
    print(f"屏幕 {sw}x{sh}", flush=True)

    fps_smooth = 0.0
    last = time.perf_counter()
    clock = pygame.time.Clock()

    try:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                        running = False

            # 取帧
            rgb = picam2.capture_array()
            if args.rotate == 180:
                rgb = rgb[::-1, ::-1]
            elif args.rotate == 90:
                rgb = np.rot90(rgb, k=-1)
            elif args.rotate == 270:
                rgb = np.rot90(rgb, k=1)

            # 推理
            probs = clf.predict_proba(rgb)
            label = "cat" if probs[0] >= args.threshold else "notcat"

            now = time.perf_counter()
            dt = now - last
            last = now
            if dt > 0:
                fps_smooth = 0.9 * fps_smooth + 0.1 * (1.0 / dt) if fps_smooth else 1.0 / dt

            # 标注 + 转 pygame surface（fromstring 拷贝数据，避免 buffer 悬垂指针）
            img = annotate(rgb, label, float(probs[0]), fps_smooth, args.width, args.height)
            surf = pygame.image.fromstring(img.tobytes(), img.size, img.mode)
            if (sw, sh) != (args.width, args.height):
                surf = pygame.transform.smoothscale(surf, (sw, sh))
            screen.blit(surf, (0, 0))
            pygame.display.flip()

            slack = args.interval - (time.perf_counter() - now)
            if slack > 0:
                time.sleep(slack)
            clock.tick()

    finally:
        picam2.stop()
        picam2.close()
        pygame.quit()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())