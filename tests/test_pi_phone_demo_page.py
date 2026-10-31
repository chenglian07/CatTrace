"""网页端（含 kiosk、剪耳判定）的回归测试：不碰摄像头，也不依赖 onnxruntime。"""

from __future__ import annotations

import importlib.util
import json
import threading
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pi_phone_demo.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("pi_phone_demo_page", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@contextmanager
def _running(module):
    """起一个只服务页面的 HTTP 服务，端口交给系统分配。"""
    with module.STATE_LOCK:
        module.STATE.update(
            label="cat",
            p_cat=0.93,
            fps=3.0,
            frames=12,
            luma=120.0,
            verdict="notched",
            p_notch=0.91,
            notched=True,
            ear_enabled=True,
        )
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _get(url: str):
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.status, resp.headers.get("Content-Type", ""), resp.read()


def test_kiosk_page_has_fullscreen_layout():
    module = _load_module()
    with _running(module) as base:
        status, content_type, body = _get(base + "/kiosk")
    text = body.decode("utf-8")
    assert status == 200
    assert "text/html" in content_type
    assert "body.kiosk" in text
    assert 'id="kstatus"' in text
    assert 'id="neuPill"' in text


def test_kiosk_query_param_and_stats():
    module = _load_module()
    with _running(module) as base:
        status, _, _ = _get(base + "/?kiosk=1")
        assert status == 200
        status, content_type, body = _get(base + "/stats")
    data = json.loads(body)
    assert status == 200
    assert "application/json" in content_type
    assert data["label"] == "cat"
    assert data["p_cat"] == 0.93
    assert data["verdict"] == "notched"
    assert data["p_notch"] == 0.91
    assert data["notched"] is True
    assert data["ear_enabled"] is True


def test_classify_notch_boundaries():
    module = _load_module()
    # 阈值 0.58、带宽 0.12：>0.70 已剪耳，<0.46 未剪耳，中间不确定
    assert module.classify_notch(0.71, 0.58, 0.12) == "notched"
    assert module.classify_notch(0.70, 0.58, 0.12) == "uncertain"
    assert module.classify_notch(0.58, 0.58, 0.12) == "uncertain"
    assert module.classify_notch(0.46, 0.58, 0.12) == "uncertain"
    assert module.classify_notch(0.45, 0.58, 0.12) == "intact"


def test_crop_box_center_square():
    module = _load_module()
    assert module.crop_box(640, 480, 1.0) == (0, 0, 640, 480)
    x0, y0, x1, y1 = module.crop_box(640, 480, 0.5)
    assert x1 - x0 == 240 and y1 - y0 == 240
    assert (x0 + x1) // 2 == 320 and (y0 + y1) // 2 == 240


def test_annotate_returns_frame_with_verdict():
    module = _load_module()
    rgb = np.zeros((480, 640, 3), dtype=np.uint8)
    img = module.annotate(
        rgb,
        label="cat",
        p_cat=0.97,
        fps=1.2,
        verdict="notched",
        p_notch=0.91,
        notch_threshold=0.58,
        notch_band=0.12,
    )
    assert img.size == (640, 480)
    assert img.mode == "RGB"
