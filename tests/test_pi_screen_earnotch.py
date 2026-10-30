"""树莓派屏幕演示的单测：只测能离屏跑的部分（HUD 渲染、三档判定、存档、静态帧源）。

真机部分（picamera2 / pygame 全屏）在 CI 里跑不了，这里不假装覆盖。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pi_screen_earnotch.py"


def _load():
    spec = importlib.util.spec_from_file_location("pi_screen_earnotch", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


hud = _load()


@pytest.mark.parametrize(
    "prob,expect",
    [
        (0.99, "notched"),
        (0.60, "notched"),      # 恰好越过上边界
        (0.59, "uncertain"),    # 带内
        (0.47, "uncertain"),    # 正中阈值，不猜
        (0.35, "uncertain"),    # 带内
        (0.34, "intact"),       # 恰好越过下边界
        (0.00, "intact"),
    ],
)
def test_classify_matches_module_band(prob: float, expect: str) -> None:
    assert hud.classify(prob, threshold=0.47, band=0.12) == expect


def test_classify_boundaries_are_strict() -> None:
    """与 modules.earnotch._one 一致：严格大于/小于才下结论，等于边界算不确定。"""
    assert hud.classify(0.59, 0.47, 0.12) == "uncertain"
    assert hud.classify(0.35, 0.47, 0.12) == "uncertain"


@pytest.mark.parametrize("verdict", ["notched", "intact", "uncertain", "nocat"])
@pytest.mark.parametrize("lang", ["zh", "en"])
def test_render_keeps_frame_size(verdict: str, lang: str) -> None:
    rgb = np.full((240, 320, 3), 128, dtype=np.uint8)
    img = hud.render(
        rgb, verdict=verdict, prob=None if verdict == "nocat" else 0.5,
        threshold=0.47, band=0.12, fps=2.0, crop_frac=0.6, frozen=True,
        footer="unit", detail="", lang=lang,
    )
    assert isinstance(img, Image.Image)
    assert img.size == (320, 240)
    assert img.mode == "RGB"


def test_render_marks_pixels_different_from_source() -> None:
    """HUD 必须真的画上去了，而不是原样返回。"""
    rgb = np.full((120, 160, 3), 255, dtype=np.uint8)
    img = np.asarray(hud.render(rgb, verdict="intact", prob=0.1, threshold=0.47,
                                band=0.12, lang="en"))
    assert img.shape == rgb.shape
    assert img.mean() < 250


def test_still_source_only_redraws_on_change(tmp_path: Path) -> None:
    for i, color in enumerate([(255, 0, 0), (0, 255, 0)]):
        Image.new("RGB", (32, 24), color).save(tmp_path / f"{i}.png")
    src = hud.StillSource(sorted(tmp_path.glob("*.png")), rotate=0)

    first, changed = src.read()
    assert changed is True
    assert tuple(first[0, 0]) == (255, 0, 0)

    _, changed = src.read()
    assert changed is False, "同一张图不该重复解码"

    src.next()
    second, changed = src.read()
    assert changed is True
    assert tuple(second[0, 0]) == (0, 255, 0)
    assert "2/2" in src.label


def test_rotate_is_reversible() -> None:
    rgb = np.arange(4 * 6 * 3, dtype=np.uint8).reshape(4, 6, 3)
    assert np.array_equal(hud._rotate(hud._rotate(rgb, 180), 180), rgb)


def test_save_snapshot_writes_image_and_sidecar(tmp_path: Path) -> None:
    rgb = np.full((24, 32, 3), 200, dtype=np.uint8)
    path = hud.save_snapshot(
        rgb, tmp_path, "notched",
        {"verdict": "notched", "prob": 0.912, "threshold": 0.47, "model": "x.onnx"},
    )
    assert path.is_file() and path.suffix == ".jpg"
    assert path.parent.name == "notched"

    meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    assert meta["prob"] == 0.912
    assert meta["verdict"] == "notched"


def test_open_source_rejects_unknown_spec() -> None:
    with pytest.raises(SystemExit):
        hud.open_source("webcam:0", 640, 480, 0)


def test_open_source_accepts_synthetic() -> None:
    src = hud.open_source("synthetic", 64, 48, 0)
    assert src.label == "synthetic"
    frame, changed = src.read()
    assert changed is True
    assert frame.shape == (48, 64, 3)
    src.close()


# ---------------- 两级识别：先判猫/非猫，再判剪耳 ----------------


class _FakeGate:
    """记录收到的图，固定返回 p_cat。"""

    def __init__(self, p_cat: float) -> None:
        self.p_cat = p_cat
        self.seen: list[Image.Image] = []

    def predict_proba(self, img) -> np.ndarray:
        im = img if isinstance(img, Image.Image) else Image.fromarray(np.asarray(img))
        self.seen.append(im.copy())
        return np.array([self.p_cat, 1.0 - self.p_cat], dtype=np.float32)


class _FakeEar:
    threshold = 0.58
    band = 0.12

    def __init__(self, prob: float) -> None:
        self.prob = prob
        self.seen: list[Image.Image] = []

    def _predict(self, img) -> float:
        im = img if isinstance(img, Image.Image) else Image.fromarray(np.asarray(img))
        self.seen.append(im.copy())
        return self.prob


def _rgb(h: int = 60, w: int = 80) -> np.ndarray:
    y = np.linspace(0, 255, h, dtype=np.float32)[:, None]
    x = np.linspace(0, 255, w, dtype=np.float32)[None, :]
    return np.stack([x + 0 * y, y + 0 * x, np.full((h, w), 90.0)], axis=-1).astype(np.uint8)


def test_gate_rejects_before_ear_notch_runs() -> None:
    """门控没过时不能跑剪耳：否则会对着一面墙给出"已绝育"。"""
    gate, ear = _FakeGate(0.02), _FakeEar(0.99)
    verdict, prob, p_cat = hud.two_stage(_rgb(), gate, ear, 0.5, 1.0)
    assert verdict == "nocat"
    assert prob is None
    assert p_cat == pytest.approx(0.02)
    assert ear.seen == [], "门控已判定没猫，剪耳不该被调用"


def test_gate_passes_then_ear_notch_decides() -> None:
    gate, ear = _FakeGate(0.97), _FakeEar(0.91)
    verdict, prob, p_cat = hud.two_stage(_rgb(), gate, ear, 0.5, 1.0)
    assert verdict == "notched" and prob == pytest.approx(0.91)
    assert p_cat == pytest.approx(0.97)


def test_gate_and_ear_notch_see_the_same_crop() -> None:
    """回归：门控若吃整图、剪耳吃取景框，猫在框外时会给出矛盾结论。"""
    gate, ear = _FakeGate(0.9), _FakeEar(0.5)
    hud.two_stage(_rgb(), gate, ear, 0.5, 0.5)
    assert len(gate.seen) == 1 and len(ear.seen) == 1
    assert gate.seen[0].size == ear.seen[0].size
    assert np.array_equal(np.asarray(gate.seen[0]), np.asarray(ear.seen[0]))


def test_gate_can_be_disabled() -> None:
    """--gate off：没有门控时直接进剪耳，p_cat 为 None。"""
    ear = _FakeEar(0.95)
    verdict, prob, p_cat = hud.two_stage(_rgb(), None, ear, 0.5, 1.0)
    assert verdict == "notched" and p_cat is None
    assert len(ear.seen) == 1


def test_gate_threshold_is_inclusive() -> None:
    """p_cat 恰好等于阈值时应放行（比较用严格小于）。"""
    gate, ear = _FakeGate(0.5), _FakeEar(0.95)
    assert hud.two_stage(_rgb(), gate, ear, 0.5, 1.0)[0] == "notched"


@pytest.mark.parametrize("frac,expect", [(1.0, (0, 0, 80, 60)), (0.5, (25, 15, 55, 45))])
def test_crop_box_geometry(frac: float, expect: tuple[int, int, int, int]) -> None:
    assert hud.crop_box(80, 60, frac) == expect

