"""耳标模块的 ROI / ONNX 运行时单测。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from catvision_contracts import (
    CatFace,
    FramePacket,
    HeadPose,
    Identity,
    Landmarks,
    Quality,
    SourceInfo,
    validate,
)
from PIL import Image

from modules.earnotch import EarNotchModel

MODEL = Path("models/earnotch_convnext_tiny288_v0.onnx")


def _packet(tmp_path) -> FramePacket:
    p = tmp_path / "blank.jpg"
    Image.new("RGB", (320, 240), (100, 120, 140)).save(p)
    return FramePacket.build(
        camera_id="cam-test",
        seq=0,
        width=320,
        height=240,
        image_path=str(p),
        source=SourceInfo(kind="file", uri=str(p)),
        captured_at=datetime.now(timezone.utc),
    )


def _face(packet: FramePacket) -> CatFace:
    """构造一只正脸猫：猫的左耳/左眼在画面右侧。"""
    return CatFace(
        packet_id=packet.packet_id,
        track_id="t-0001",
        bbox=[100.0, 80.0, 100.0, 100.0],
        det_score=0.9,
        landmarks=Landmarks(
            left_eye=[168.0, 122.0],
            right_eye=[132.0, 122.0],
            nose=[150.0, 142.0],
            left_ear_base=[176.0, 90.0],
            right_ear_base=[124.0, 90.0],
            left_ear_tip=[184.0, 72.0],
            right_ear_tip=[116.0, 72.0],
        ),
        head_pose=HeadPose(yaw=0.0, pitch=0.0, roll=0.0),
        identity=Identity(
            cat_id=None, name=None, similarity=None, decision="unknown", gallery_version="none"
        ),
        quality=Quality(blur=80.0, brightness=120.0, is_usable=True),
    )


def test_ear_roi_is_left_right_ordered(tmp_path) -> None:
    face = _face(_packet(tmp_path))
    left = EarNotchModel._ear_roi(face, "left")
    right = EarNotchModel._ear_roi(face, "right")
    assert left[2] > 0 and left[3] > 0
    assert right[2] > 0 and right[3] > 0
    assert left[0] > right[0]


def test_ear_roi_covers_tip_and_is_wide_enough(tmp_path) -> None:
    """ROI 必须包住耳尖（缺口位置），且不能退化成窄条。"""
    face = _face(_packet(tmp_path))
    fw, fh = face.bbox[2], face.bbox[3]
    for which in ("left", "right"):
        x, y, w, h = EarNotchModel._ear_roi(face, which)
        tip = face.landmarks.left_ear_tip if which == "left" else face.landmarks.right_ear_tip
        base = face.landmarks.left_ear_base if which == "left" else face.landmarks.right_ear_base
        assert w >= 0.30 * fw
        assert h >= 0.30 * fh
        assert y <= tip[1]
        assert y + h >= base[1]
        assert x <= base[0] <= x + w


@pytest.mark.skipif(not MODEL.is_file(), reason="本机没有导出 ONNX 权重")
def test_tiny_face_returns_unknown(tmp_path) -> None:
    """猫脸小于 min_face_px（默认 96）时不许硬猜，整条结论退成 unknown。"""
    pytest.importorskip("onnxruntime")
    packet = _packet(tmp_path)
    face = _face(packet).model_copy(update={"bbox": [100.0, 80.0, 40.0, 40.0]})
    out = EarNotchModel().analyze(packet, [face])[0]
    assert out.left.visible is False and out.right.visible is False
    assert out.neutered.value is None
    assert out.neutered.confidence is None


@pytest.mark.skipif(not MODEL.is_file(), reason="本机没有导出 ONNX 权重")
def test_side_is_skipped_when_roi_too_small(tmp_path) -> None:
    """耳部 ROI 太小时只放弃左右耳，不拿两侧概率差硬判。"""
    pytest.importorskip("onnxruntime")
    packet = _packet(tmp_path)
    face = _face(packet)
    image = Image.new("RGB", (320, 240), (120, 120, 120))
    assert EarNotchModel(min_ear_px=10_000)._estimate_side(image, face, 0.9) is None


def test_mask_ear_changes_only_one_side(tmp_path) -> None:
    face = _face(_packet(tmp_path))
    arr = np.zeros((240, 320, 3), dtype=np.uint8)
    arr[:, :, 0] = np.arange(320, dtype=np.uint8)[None, :]
    arr[:, :, 1] = np.arange(240, dtype=np.uint8)[:, None]
    image = Image.fromarray(arr, "RGB")
    obj = EarNotchModel.__new__(EarNotchModel)
    masked = obj._mask_ear(image, face, "left")
    assert masked.size == image.size
    assert np.any(np.asarray(masked) != np.asarray(image))


@pytest.mark.skipif(not MODEL.is_file(), reason="本机没有导出 ONNX 权重")
def test_onnx_model_runs(tmp_path) -> None:
    pytest.importorskip("onnxruntime")
    packet = _packet(tmp_path)
    face = _face(packet)
    model = EarNotchModel()
    out = model.analyze(packet, [face])
    assert len(out) == 1
    assert out[0].track_id == face.track_id
    assert out[0].model_version.startswith("earnotch")
    validate("ear_notch", out[0])
