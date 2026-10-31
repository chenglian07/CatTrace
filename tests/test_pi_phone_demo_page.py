"""网页端 kiosk 模式的回归测试：不碰摄像头，也不依赖 onnxruntime。"""

from __future__ import annotations

import importlib.util
import json
import threading
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path

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
        module.STATE.update(label="cat", p_cat=0.93, fps=3.0, frames=12, luma=120.0)
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
