"""CatTrace 实时直播代理。

浏览器**不**直接连树莓派，统一走 Flask 同源代理：

    浏览器 --/api/live/stream--> Flask(app.py) --http--> 树莓派 MJPEG

这样手机访问、局域网外访问、页面以后上 HTTPS 都不用改前端，
也不会踩 mixed-content / CORS。

环境变量（都可不填，不填 = 直播功能关闭，页面回退到占位动画）：

    CATTRACE_LIVE_URL       树莓派 MJPEG 地址  http://<pi-ip>:8000/stream
    CATTRACE_LIVE_STATS     可选，识别状态 JSON http://<pi-ip>:8000/stats
    CATTRACE_LIVE_SNAPSHOT  可选，单帧 JPEG  http://<pi-ip>:8000/snapshot.jpg
    CATTRACE_LIVE_TIMEOUT   可选，读超时秒数，默认 8

对外接口：

    GET /api/live/info      直播是否可用 + 各端点地址
    GET /api/live/stream    MJPEG 视频流（原样转发）
    GET /api/live/snapshot  取当前一帧 JPEG（单帧接口优先，MJPEG 抽帧兜底）
    GET /api/live/stats     识别状态（配置了才可用）
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from flask import Response, jsonify

JPEG_SOI = b"\xff\xd8\xff"
JPEG_EOI = b"\xff\xd9"
CHUNK = 16384


def _env_url(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _timeout() -> float:
    try:
        return float(os.environ.get("CATTRACE_LIVE_TIMEOUT", "8"))
    except ValueError:
        return 8.0


def _open(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "CatTrace-live/1.0"})
    return urllib.request.urlopen(req, timeout=_timeout())


def _unavailable(msg: str):
    return jsonify({"ok": False, "error": msg}), 503


def _extract_jpeg(data: bytes) -> bytes | None:
    """从 MJPEG 分片或单张图片响应里取出完整 JPEG。"""
    start = data.find(JPEG_SOI)
    if start < 0:
        return None
    end = data.find(JPEG_EOI, start + 3)
    if end < 0:
        return None
    return data[start : end + 2]


def _snapshot_response(jpg: bytes) -> Response:
    return Response(
        jpg,
        headers={"Content-Type": "image/jpeg", "Cache-Control": "no-store"},
    )


def register(app) -> None:
    """把直播相关路由挂到 Flask app 上。"""

    def enabled() -> bool:
        return bool(_env_url("CATTRACE_LIVE_URL"))

    @app.route("/api/live/info")
    def live_info():
        has_stream = enabled()
        has_stats = bool(_env_url("CATTRACE_LIVE_STATS"))
        return jsonify(
            {
                "ok": True,
                "enabled": has_stream,
                "stream_url": "/api/live/stream" if has_stream else None,
                "snapshot_url": "/api/live/snapshot" if has_stream else None,
                "stats_url": "/api/live/stats" if (has_stream and has_stats) else None,
            }
        )

    @app.route("/api/live/stream")
    def live_stream():
        url = _env_url("CATTRACE_LIVE_URL")
        if not url:
            return _unavailable("未配置 CATTRACE_LIVE_URL")
        try:
            upstream = _open(url)
        except (urllib.error.URLError, OSError) as exc:
            return _unavailable(f"连不上摄像头节点: {exc}")

        ctype = upstream.headers.get("Content-Type", "multipart/x-mixed-replace; boundary=frame")

        def pump():
            # read1 返回当前已到达的字节，不会为了凑满 CHUNK 而等待下一帧。
            reader = getattr(upstream, "read1", upstream.read)
            try:
                while True:
                    buf = reader(CHUNK)
                    if not buf:
                        break
                    yield buf
            except Exception:
                pass
            finally:
                try:
                    upstream.close()
                except Exception:
                    pass

        return Response(
            pump(),
            headers={
                "Content-Type": ctype,
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.route("/api/live/snapshot")
    def live_snapshot():
        """取当前一帧 JPEG。

        优先调用摄像头节点的单帧接口；未配置或失败时，从 MJPEG 流里抽帧。
        这样既能低延迟出首屏，也能兼容只提供 MJPEG 的普通网络摄像头。
        """
        # 优先使用摄像头节点提供的单帧接口：首屏快，也不会占用一条 MJPEG 连接。
        snapshot_url = _env_url("CATTRACE_LIVE_SNAPSHOT")
        if snapshot_url:
            try:
                with _open(snapshot_url) as upstream:
                    data = upstream.read(4_000_000)
                jpg = _extract_jpeg(data)
                if jpg:
                    return _snapshot_response(jpg)
            except (urllib.error.URLError, OSError):
                pass  # 单帧接口失配时回退到通用 MJPEG 抽帧

        url = _env_url("CATTRACE_LIVE_URL")
        if not url:
            return _unavailable("未配置 CATTRACE_LIVE_URL")
        try:
            upstream = _open(url)
        except (urllib.error.URLError, OSError) as exc:
            return _unavailable(f"连不上摄像头节点: {exc}")
        try:
            data = b""
            while len(data) < 4_000_000:
                chunk = upstream.read(CHUNK)
                if not chunk:
                    break
                data += chunk
                jpg = _extract_jpeg(data)
                if jpg:
                    return _snapshot_response(jpg)
        finally:
            try:
                upstream.close()
            except Exception:
                pass
        return _unavailable("流里没有取到完整帧")

    @app.route("/api/live/stats")
    def live_stats():
        url = _env_url("CATTRACE_LIVE_STATS")
        if not url:
            return _unavailable("未配置 CATTRACE_LIVE_STATS")
        try:
            with _open(url) as upstream:
                body = upstream.read(65536)
                ctype = upstream.headers.get("Content-Type", "application/json")
        except (urllib.error.URLError, OSError) as exc:
            return _unavailable(f"连不上识别节点: {exc}")
        try:
            json.loads(body.decode("utf-8"))
        except Exception:
            return _unavailable("识别节点返回的不是 JSON")
        return Response(body, headers={"Content-Type": ctype, "Cache-Control": "no-store"})
