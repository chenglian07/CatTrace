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
