"""直播代理单测：配置开关、MJPEG 转发、快照优先/兜底、状态代理。"""

from __future__ import annotations

import urllib.error

import pytest
from flask import Flask

import live_proxy

JPEG = b"\xff\xd8\xfffake-jpeg\xff\xd9"


class FakeUpstream:
    def __init__(self, chunks: list[bytes], content_type: str = "image/jpeg") -> None:
        self.chunks = chunks
        self.headers = {"Content-Type": content_type}
        self.closed = False
        self.read1_called = False

    def read(self, _size: int = -1) -> bytes:
        return self.chunks.pop(0) if self.chunks else b""

    def read1(self, _size: int = -1) -> bytes:
        self.read1_called = True
        return self.read(_size)

    def close(self) -> None:
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self.close()


@pytest.fixture()
def client():
    app = Flask(__name__)
    live_proxy.register(app)
    app.testing = True
    return app.test_client()


def test_info_disabled_without_url(client, monkeypatch) -> None:
    monkeypatch.delenv("CATTRACE_LIVE_URL", raising=False)
    monkeypatch.delenv("CATTRACE_LIVE_STATS", raising=False)

    response = client.get("/api/live/info")
    body = response.get_json()

    assert response.status_code == 200
    assert body["enabled"] is False
    assert body["stream_url"] is None


def test_info_lists_configured_endpoints(client, monkeypatch) -> None:
    monkeypatch.setenv("CATTRACE_LIVE_URL", "http://pi/stream")
    monkeypatch.setenv("CATTRACE_LIVE_STATS", "http://pi/stats")
    monkeypatch.setenv("CATTRACE_LIVE_SNAPSHOT", "http://pi/snapshot.jpg")

    body = client.get("/api/live/info").get_json()

    assert body == {
        "ok": True,
        "enabled": True,
        "stream_url": "/api/live/stream",
        "snapshot_url": "/api/live/snapshot",
        "stats_url": "/api/live/stats",
    }


def test_stream_passes_upstream_bytes(client, monkeypatch) -> None:
    monkeypatch.setenv("CATTRACE_LIVE_URL", "http://pi/stream")
    upstream = FakeUpstream([b"frame-1", b"frame-2"], "multipart/x-mixed-replace")
    monkeypatch.setattr(live_proxy, "_open", lambda _url: upstream)

    response = client.get("/api/live/stream")

    assert response.status_code == 200
    assert response.data == b"frame-1frame-2"
    assert response.content_type.startswith("multipart/x-mixed-replace")
    assert upstream.read1_called


def test_snapshot_prefers_single_frame_endpoint(client, monkeypatch) -> None:
    monkeypatch.setenv("CATTRACE_LIVE_URL", "http://pi/stream")
    monkeypatch.setenv("CATTRACE_LIVE_SNAPSHOT", "http://pi/snapshot.jpg")
    called: list[str] = []

    def fake_open(url: str) -> FakeUpstream:
        called.append(url)
        return FakeUpstream([b"header" + JPEG + b"trailer"])

    monkeypatch.setattr(live_proxy, "_open", fake_open)

    response = client.get("/api/live/snapshot")

    assert response.status_code == 200
    assert response.data == JPEG
    assert called == ["http://pi/snapshot.jpg"]


def test_snapshot_falls_back_to_stream(client, monkeypatch) -> None:
    monkeypatch.setenv("CATTRACE_LIVE_URL", "http://pi/stream")
    monkeypatch.setenv("CATTRACE_LIVE_SNAPSHOT", "http://pi/snapshot.jpg")

    def fake_open(url: str) -> FakeUpstream:
        if url.endswith("snapshot.jpg"):
            raise urllib.error.URLError("snapshot unavailable")
        return FakeUpstream([b"prefix" + JPEG[:3], JPEG[3:]])

    monkeypatch.setattr(live_proxy, "_open", fake_open)

    response = client.get("/api/live/snapshot")

    assert response.status_code == 200
    assert response.data == JPEG


def test_stats_proxies_valid_json(client, monkeypatch) -> None:
    monkeypatch.setenv("CATTRACE_LIVE_URL", "http://pi/stream")
    monkeypatch.setenv("CATTRACE_LIVE_STATS", "http://pi/stats")
    monkeypatch.setattr(
        live_proxy,
        "_open",
        lambda _url: FakeUpstream([b'{"label":"cat","p_cat":0.9,"fps":2.1}'], "application/json"),
    )

    response = client.get("/api/live/stats")

    assert response.status_code == 200
    assert response.get_json()["label"] == "cat"
    assert response.content_type == "application/json"


def test_stats_rejects_invalid_json(client, monkeypatch) -> None:
    monkeypatch.setenv("CATTRACE_LIVE_STATS", "http://pi/stats")
    monkeypatch.setattr(live_proxy, "_open", lambda _url: FakeUpstream([b"not-json"], "text/plain"))

    response = client.get("/api/live/stats")

    assert response.status_code == 503
    assert response.get_json()["ok"] is False
