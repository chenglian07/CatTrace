#!/usr/bin/env python3
"""树莓派本地屏幕：摄像头画面 + 剪耳（绝育）判定，直接铺满 DSI/HDMI 屏。

不依赖浏览器、不起 HTTP 服务，一个进程跑完 取帧 → 推理 → 渲染。

    ssh pi-cat
    cd ~/catvision && source ~/venvs/catvision/bin/activate
    pip install pygame                    # 不在 requirements/pi.txt 里，要手动装
    python scripts/pi_screen_earnotch.py

屏幕上：大字判定（已剪耳 / 未剪耳 / 看不清 / 没有猫）、p_notch、阈值带、FPS。
按键：空格 冻结当前画面，S 存档，1/2 手工标成正/负样本，N 下一张（--source 为目录时），
Q 或 ESC 退出。

关于"能不能分左右耳"：不能。当前权重是**整图二分类**，只回答"这张画面里的猫有没有
剪耳"，左右耳要猫脸关键点，而猫脸模块仍是 NotImplementedYet。所以这里不做左右耳，
也不在屏幕上假装知道。

三种画面来源，方便先在开发机上验 HUD 再上板子：
    --source camera           CSI 摄像头（默认）
    --source dir:某目录       遍历目录里的图片，按 N 切下一张
    --source file:某张图.jpg   单张图片循环显示

分辨率/旋转按实际接线调：--rotate 默认 180 是因为这块板子的相机装反了（见 docs/部署.md）。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "contracts" / "python"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

VERDICT_COLOR = {
    "notched": (46, 204, 113),      # 绿：已绝育，目标状态
    "intact": (243, 156, 18),       # 橙：未绝育，待安排 TNR
    "uncertain": (149, 165, 166),   # 灰：落在不确定带，不猜
    "nocat": (231, 76, 60),         # 红：画面里没猫
}

TEXT = {
    "zh": {
        "notched": "已剪耳 · 已绝育",
        "intact": "未剪耳 · 未绝育",
        "uncertain": "看不清 · 不下结论",
        "nocat": "没有猫",
        "thr": "阈值",
        "frozen": "已冻结",
        "nocat_hint": "把猫脸放进框内",
        "keys": "空格 冻结   S 存档   1 标正   2 标负   Q 退出",
    },
    "en": {
        "notched": "NOTCHED / NEUTERED",
        "intact": "INTACT / NOT NEUTERED",
        "uncertain": "UNCERTAIN",
        "nocat": "NO CAT",
        "thr": "thr",
        "frozen": "FROZEN",
        "nocat_hint": "put the cat head in the box",
        "keys": "SPACE freeze   S snapshot   1 pos   2 neg   Q quit",
    },
}

_CJK_FONTS = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/msyh.ttc",
)
_LATIN_FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)

_font_cache: dict[tuple[int, bool], ImageFont.ImageFont] = {}


def _pick_font_path(cjk: bool) -> str | None:
    for p in (_CJK_FONTS if cjk else ()) + _LATIN_FONTS:
        if Path(p).is_file():
            return p
    return None


def cjk_available() -> bool:
    return _pick_font_path(True) is not None


def get_font(size: int, cjk: bool = False) -> ImageFont.ImageFont:
    key = (size, cjk)
    if key not in _font_cache:
        path = _pick_font_path(cjk)
        try:
            _font_cache[key] = ImageFont.truetype(path, size) if path else ImageFont.load_default()
        except Exception:
            _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


def classify(prob: float, threshold: float, band: float) -> str:
    """三档判定，与 modules.earnotch 的 `_one()` 保持完全一致的比较方向。"""
    if prob > threshold + band:
        return "notched"
    if prob < threshold - band:
        return "intact"
    return "uncertain"


def render(
    rgb: np.ndarray,
    *,
    verdict: str,
    prob: float | None,
    threshold: float,
    band: float,
    fps: float = 0.0,
    crop_frac: float = 1.0,
    frozen: bool = False,
    footer: str = "",
    detail: str = "",
    lang: str = "en",
) -> Image.Image:
    """把判定画到画面上。纯函数，不依赖 pygame，方便单测。"""
    t = TEXT[lang]
    img = Image.fromarray(rgb)
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size
    big = get_font(max(20, h // 11), cjk=True)
    mid = get_font(max(13, h // 24), cjk=True)
    small = get_font(max(11, h // 34), cjk=True)
    color = VERDICT_COLOR.get(verdict, VERDICT_COLOR["uncertain"])

    # ---- 顶部判定条
    bar_h = int(h * 0.20)
    draw.rectangle([0, 0, w, bar_h], fill=(0, 0, 0, 205))
    draw.text((10, int(h * 0.012)), t[verdict], font=big, fill=color + (255,))
    if prob is None:
        line = detail or f"{fps:.1f} FPS"
    else:
        line = f"p={prob:.3f}   {t['thr']} {threshold:.2f}±{band:.2f}   {fps:.1f} FPS"
        if detail:
            line += f"   {detail}"
    draw.text((12, bar_h - int(h * 0.062)), line, font=mid, fill=(225, 225, 225, 255))

    # ---- 右侧概率柱：先铺底、再填概率、最后盖不确定带与阈值线
    if prob is not None:
        bar_w = max(10, w // 26)
        bx = w - bar_w - 8
        top, bottom = int(h * 0.23), int(h * 0.93)
        span = bottom - top
        draw.rectangle([bx, top, bx + bar_w, bottom], fill=(0, 0, 0, 130))
        fill_h = int(span * max(0.0, min(1.0, prob)))
        draw.rectangle([bx, bottom - fill_h, bx + bar_w, bottom], fill=color + (255,))
        # 不确定带画在概率柱之上，否则会被不透明的填充色盖掉
        band_top = bottom - int(span * min(1.0, threshold + band))
        band_bottom = bottom - int(span * max(0.0, threshold - band))
        draw.rectangle([bx, band_top, bx + bar_w, band_bottom], fill=(255, 255, 255, 85))
        thr_y = bottom - int(span * max(0.0, min(1.0, threshold)))
        draw.line([bx - 5, thr_y, bx + bar_w + 3, thr_y], fill=(255, 255, 255, 230), width=2)

    # ---- 取景框：推理只吃框内，框外只用来给用户看上下文。
    # 描边用"外黑内白"双线，深色和浅色背景上都看得见。
    if crop_frac < 1.0:
        s = int(min(w, h) * crop_frac)
        cx, cy = w // 2, h // 2
        box = [cx - s // 2, cy - s // 2, cx + s // 2, cy + s // 2]
        draw.rectangle(box, outline=(0, 0, 0, 130), width=3)
        draw.rectangle(box, outline=(255, 255, 255, 200), width=1)

    # ---- 冻结标记
    if frozen:
        tag = t["frozen"]
        tw = draw.textlength(tag, font=small)
        draw.rectangle([w - tw - 26, 4, w - 6, 6 + small.size * 1.6], fill=(0, 0, 0, 170))
        draw.text((w - tw - 16, 6), tag, font=small, fill=(255, 235, 120, 255))

    # ---- 底部两行状态：按键提示 + 来源/亮度，都放进同一条底衬，避免压在照片上看不清
    footer_h = int(h * 0.105)
    if verdict == "nocat" and t["nocat_hint"] not in footer:
        footer = f"{footer}   {t['nocat_hint']}"
    luma = float(np.asarray(rgb).mean())
    if luma < 25:
        hint = f"{footer}   亮度{luma:.0f} – 镜头被遮？"
    elif luma > 235:
        hint = f"{footer}   亮度{luma:.0f} – 过曝，退远一点"
    else:
        hint = f"{footer}   亮度 {luma:.0f}"
    draw.rectangle([0, h - footer_h, w, h], fill=(0, 0, 0, 175))
    draw.text((8, h - footer_h + 4), t["keys"], font=small, fill=(150, 150, 150, 255))
    draw.text((8, h - footer_h + small.size + 9), hint.strip(), font=small,
              fill=(190, 190, 190, 255))
    return img


# ---------------------------------------------------------------- 画面来源
def _rotate(arr: np.ndarray, deg: int) -> np.ndarray:
    if deg == 180:
        return arr[::-1, ::-1]
    if deg == 90:
        return np.rot90(arr, k=-1)
    if deg == 270:
        return np.rot90(arr, k=1)
    return arr


class CameraSource:
    """Picamera2 预览流。只在树莓派上可用。"""

    label = "camera"

    def __init__(self, width: int, height: int, rotate: int) -> None:
        from picamera2 import Picamera2

        self.rotate = rotate
        self.picam2 = Picamera2()
        cfg = self.picam2.create_preview_configuration(
            main={"size": (width, height), "format": "RGB888"}
        )
        self.picam2.configure(cfg)
        self.picam2.start()
        time.sleep(1.0)

    def read(self) -> tuple[np.ndarray, bool]:
        return _rotate(self.picam2.capture_array(), self.rotate), True

    def next(self) -> None:
        return None

    def close(self) -> None:
        self.picam2.stop()
        self.picam2.close()


class StillSource:
    """静态图片或目录。`next()` 切下一张，`read()` 只在换图后重新解码。"""

    def __init__(self, paths: list[Path], rotate: int) -> None:
        if not paths:
            raise SystemExit("这个路径下没有图片")
        self.paths = paths
        self.rotate = rotate
        self.i = 0
        self._cache: np.ndarray | None = None
        self._dirty = True

    @property
    def label(self) -> str:
        return f"{self.paths[self.i].name} ({self.i + 1}/{len(self.paths)})"

    def read(self) -> tuple[np.ndarray, bool]:
        if self._cache is not None and not self._dirty:
            return self._cache, False
        with Image.open(self.paths[self.i]) as im:
            arr = np.asarray(im.convert("RGB"))
        self._cache = _rotate(arr, self.rotate)
        self._dirty = False
        return self._cache, True

    def next(self) -> None:
        self.i = (self.i + 1) % len(self.paths)
        self._dirty = True

    def close(self) -> None:
        return None


class SyntheticSource:
    """无摄像头、无图片时的冒烟用画面。"""

    label = "synthetic"

    def __init__(self, width: int, height: int) -> None:
        self.w, self.h = width, height
        self.n = 0

    def read(self) -> tuple[np.ndarray, bool]:
        self.n += 1
        xx, yy = np.meshgrid(np.linspace(0, 255, self.w), np.linspace(0, 255, self.h))
        r = (xx + self.n * 3) % 256
        g = (yy + self.n * 2) % 256
        b = np.full((self.h, self.w), 90.0)
        return np.stack([r, g, b], axis=-1).astype(np.uint8), True

    def next(self) -> None:
        return None

    def close(self) -> None:
        return None


def open_source(spec: str, width: int, height: int, rotate: int):
    if spec == "camera":
        return CameraSource(width, height, rotate)
    if spec == "synthetic":
        return SyntheticSource(width, height)
    if spec.startswith(("file:", "dir:")):
        kind, raw = spec.split(":", 1)
        p = Path(raw).expanduser()
        if kind == "file":
            return StillSource([p], rotate)
        exts = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
        return StillSource(sorted(q for q in p.iterdir() if q.suffix.lower() in exts), rotate)
    raise SystemExit(f"看不懂的 --source：{spec}（camera / file:… / dir:… / synthetic）")


# ---------------------------------------------------------------- 存档
def save_snapshot(rgb: np.ndarray, snap_dir: Path, bucket: str, info: dict) -> Path:
    d = snap_dir / bucket
    d.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    stem = f"{ts}_{info.get('verdict', 'na')}_p{info.get('prob') or 0:.3f}"
    img_path = d / f"{stem}.jpg"
    Image.fromarray(rgb).save(img_path, quality=92)
    with open(d / f"{stem}.json", "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    return img_path


def main() -> int:
    ap = argparse.ArgumentParser(description="树莓派屏幕：摄像头 + 剪耳判定")
    ap.add_argument("--model", default="", help="ONNX 路径；留空按平台自动选（Pi 用 resnet18）")
    ap.add_argument("--source", default="camera", help="camera / file:路径 / dir:目录 / synthetic")
    ap.add_argument("--fps", type=float, default=3.0, help="循环节流上限；实际受推理耗时限制")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--rotate", type=int, default=180, choices=(0, 90, 180, 270))
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--crop", type=float, default=1.0,
                    help="只对画面中央的正方形做推理，1.0 表示整帧。猫离得远时调 0.5~0.7")
    ap.add_argument("--no-tta", action="store_true", help="关掉水平翻转 TTA（快一倍，但阈值是按 TTA 定的）")
    ap.add_argument("--threshold", type=float, default=None, help="覆盖权重里的阈值")
    ap.add_argument("--band", type=float, default=None, help="覆盖不确定带宽度")
    ap.add_argument("--gate", default="auto", choices=("auto", "on", "off"),
                    help="用 cat_vs_notcat 先判有没有猫，auto=权重存在就开")
    ap.add_argument("--gate-threshold", type=float, default=0.5)
    ap.add_argument("--snap-dir", default="test_data/field_capture")
    ap.add_argument("--lang", default="auto", choices=("auto", "zh", "en"))
    ap.add_argument("--windowed", action="store_true", help="窗口模式，方便开发机调试")
    args = ap.parse_args()

    crop = max(0.2, min(1.0, args.crop))
    if args.lang == "zh" and not cjk_available():
        print("⚠ 本机没有中文字体，界面退回英文。装一个再试："
              "sudo apt install fonts-noto-cjk", flush=True)
        lang = "en"
    elif args.lang == "auto":
        lang = "zh" if cjk_available() else "en"
    else:
        lang = args.lang

    # ---------- 剪耳模型 ----------
    from modules.earnotch import EarNotchModel

    model = EarNotchModel(
        model_path=args.model or None,
        threshold=args.threshold,
        band=args.band,
        tta=not args.no_tta,
        threads=args.threads,
    )
    print(f"剪耳模型 {model.model_path.name}  input={model.input_size}  "
          f"thr={model.threshold:.2f}±{model.band:.2f}  tta={model.tta}", flush=True)

    # ---------- 可选：猫/非猫前置门 ----------
    gate = None
    gate_model = ROOT / "models" / "cat_vs_notcat.onnx"
    if args.gate != "off" and (args.gate == "on" or gate_model.is_file()):
        from modules.catface.cat_classifier import CatClassifier

        if gate_model.is_file():
            gate = CatClassifier(gate_model, intra_op_threads=max(1, args.threads // 2))
            print(f"猫/非猫门 {gate_model.name}  阈值 {args.gate_threshold}", flush=True)
        else:
            print(f"指定了 --gate on 但 {gate_model} 不存在，跳过门控", flush=True)

    src = open_source(args.source, args.width, args.height, args.rotate)
    print(f"画面来源 {src.label}", flush=True)

    # ---------- pygame ----------
    import pygame

    pygame.init()
    if args.windowed:
        screen = pygame.display.set_mode((args.width, args.height))
    else:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    sw, sh = screen.get_size()
    pygame.mouse.set_visible(False)
    pygame.display.set_caption("CatTrace · 剪耳判定")
    print(f"屏幕 {sw}x{sh}，Q/ESC 退出", flush=True)

    interval = 1.0 / args.fps if args.fps > 0 else 0.0
    fps_smooth = 0.0
    last_t = time.perf_counter()
    snap_dir = Path(args.snap_dir)
    frozen = False
    last_rgb: np.ndarray | None = None
    state = {"verdict": "uncertain", "prob": None, "p_cat": None}

    def infer(rgb: np.ndarray) -> None:
        """对一帧做门控 + 剪耳推理，结果写进 state。"""
        hh, ww = rgb.shape[:2]
        if crop < 1.0:
            s = int(min(ww, hh) * crop)
            cx, cy = ww // 2, hh // 2
            box = (cx - s // 2, cy - s // 2, cx + s // 2, cy + s // 2)
        else:
            box = (0, 0, ww, hh)
        roi = Image.fromarray(rgb).crop(box)

        state["p_cat"] = None
        if gate is not None:
            p_cat = float(gate.predict_proba(rgb)[0])
            state["p_cat"] = p_cat
            if p_cat < args.gate_threshold:
                state["verdict"], state["prob"] = "nocat", None
                return
        prob = model._predict(roi)
        state["prob"] = prob
        state["verdict"] = classify(prob, model.threshold, model.band)

    try:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        running = False
                    elif event.key == pygame.K_SPACE:
                        frozen = not frozen
                    elif event.key == pygame.K_n:
                        frozen = False
                        src.next()
                    elif event.key in (pygame.K_s, pygame.K_1, pygame.K_2):
                        if last_rgb is None:
                            continue
                        bucket = {pygame.K_s: state["verdict"], pygame.K_1: "pos",
                                  pygame.K_2: "neg"}[event.key]
                        info = {"verdict": state["verdict"], "prob": state["prob"],
                                "p_cat": state["p_cat"], "manual_bucket": bucket,
                                "model": model.model_path.name, "threshold": model.threshold,
                                "band": model.band, "tta": model.tta, "crop": crop,
                                "source": src.label}
                        path = save_snapshot(last_rgb, snap_dir, bucket, info)
                        print(f"存档 {path}", flush=True)

            rgb, changed = src.read()
            if changed and not frozen:
                t0 = time.perf_counter()
                infer(rgb)
                cost = time.perf_counter() - t0
                last_rgb = rgb.copy()
                inst = 1.0 / max(cost, 1e-6)
                fps_smooth = 0.85 * fps_smooth + 0.15 * inst if fps_smooth else inst
                # 以"本轮推理结束"为计时起点，节流只补渲染+空闲的时间，不与推理串行叠加
                last_t = time.perf_counter()
            elif last_rgb is None:
                last_rgb = rgb.copy()

            p_cat = state["p_cat"]
            img = render(
                last_rgb if last_rgb is not None else rgb,
                verdict=state["verdict"],
                prob=state["prob"],
                threshold=model.threshold,
                band=model.band,
                fps=fps_smooth,
                crop_frac=crop,
                frozen=frozen,
                footer=src.label,
                detail=f"猫{p_cat:.2f}" if p_cat is not None else "",
                lang=lang,
            )
            surf = pygame.image.frombytes(img.tobytes(), img.size, "RGB")
            if (sw, sh) != img.size:
                surf = pygame.transform.smoothscale(surf, (sw, sh))
            screen.blit(surf, (0, 0))
            pygame.display.flip()

            slack = interval - (time.perf_counter() - last_t)
            if slack > 0:
                time.sleep(slack)

    except KeyboardInterrupt:
        pass
    finally:
        src.close()
        pygame.quit()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
