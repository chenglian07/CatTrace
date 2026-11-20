#!/usr/bin/env python3
"""一条命令把「带真实摄像头的网页」跑起来。

省掉手抄三个 CATTRACE_* 环境变量的步骤，并在启动前先探一次树莓派，告诉你到底通没通。

两种跑法（脚本都支持）：

  1) 在树莓派本机跑（手机热点/陌生网络下最省事，只依赖一个设备）
       python scripts/serve_live.py --pi 127.0.0.1
       电脑/手机打开  http://<树莓派IP>:5000/live

  2) 在自己的电脑上跑，树莓派只当摄像头节点
       python scripts/serve_live.py --pi 192.168.43.12
       本机打开      http://127.0.0.1:5000/live
       手机打开      http://<电脑IP>:5000/live

脚本会先请求 http://<pi>:<camera-port>/stats 和 /snapshot.jpg：

  * 通了 → 绿色提示，打印模型的判定（cat / nocat、p_cat、已推多少帧），然后启动 Flask；
  * 不通 → 打印常见原因（不在同一网段 / 热点开了客户端隔离 / 服务没起 / 防火墙），
           但仍然启动网页，页面会显示「设备离线」而不是白屏。

其它参数：

  --camera-port 8000   树莓派 pi_phone_demo.py 的端口
  --host 0.0.0.0       Flask 监听地址（0.0.0.0 手机才能访问）
  --port 5000          Flask 端口
  --force              预检失败也照样启动（默认就会启动，这个参数只为显式表达）
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.error
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


def local_lan_ip() -> str:
    """猜一个能给手机用的本机局域网地址（只是用来打印提示）。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return "127.0.0.1"


def probe(url: str, timeout: float = 3.0):
    """返回 (ok, 说明, 原始字节)。"""
    req = urllib.request.Request(url, headers={"User-Agent": "CatTrace-serve-live/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"HTTP {resp.status}", resp.read(4_000_000)
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}", b""
    except urllib.error.URLError as exc:
        return False, str(exc.reason), b""
    except OSError as exc:
        return False, str(exc), b""


def main() -> int:
    ap = argparse.ArgumentParser(description="启动带真实摄像头画面的 CatTrace 网页")
    ap.add_argument("--pi", required=True, help="树莓派地址，本机跑就填 127.0.0.1")
    ap.add_argument("--camera-port", type=int, default=8000, help="树莓派摄像头服务端口")
    ap.add_argument("--host", default="0.0.0.0", help="Flask 监听地址")
    ap.add_argument("--port", type=int, default=5000, help="Flask 端口")
    ap.add_argument("--force", action="store_true", help="预检失败也启动（默认就会启动）")
    args = ap.parse_args()

    base = f"http://{args.pi}:{args.camera_port}"

    print(f"==> 预检摄像头节点 {base}")
    stats_ok, stats_msg, stats_raw = probe(base + "/stats")
    snap_ok, snap_msg, snap_raw = probe(base + "/snapshot.jpg")

    if stats_ok:
        try:
            stats = json.loads(stats_raw.decode("utf-8"))
            print(
                f"    /stats      OK   判定={stats.get('verdict')}  p_cat={stats.get('p_cat')}"
                f"  已推 {stats.get('stream_frames')} 帧  推流 {stats.get('stream_fps') or 0:.1f} fps"
            )
        except Exception:
            print(f"    /stats      OK   但返回不是 JSON：{stats_msg}")
    else:
        print(f"    /stats      失败 {stats_msg}")

    if snap_ok and snap_raw[:3] == b"\xff\xd8\xff":
        print(f"    /snapshot   OK   {len(snap_raw)} 字节 JPEG")
    else:
        print(f"    /snapshot   失败 {'不是 JPEG' if snap_ok else snap_msg}")

    if not (stats_ok and snap_ok):
        print()
        print("!! 摄像头节点暂时连不上，网页仍会启动，但 /live 会显示「设备离线」。")
        print("   常见原因，按顺序看：")
        print("   1. 树莓派上的服务没起来： systemctl --user status catvision-camera")
        print("   2. 两台设备不在同一个网络：树莓派上 `hostname -I` 看 IP 是不是同一网段")
        print("   3. 手机热点开了「客户端隔离」：热点里两台设备互 ping 不通，改用网线或 Tailscale")
        print(f"   4. 树莓派防火墙挡了 {args.camera_port}： sudo ufw allow {args.camera_port}/tcp")
        print()

    os.environ["CATTRACE_LIVE_URL"] = base + "/stream"
    os.environ["CATTRACE_LIVE_STATS"] = base + "/stats"
    os.environ["CATTRACE_LIVE_SNAPSHOT"] = base + "/snapshot.jpg"
    os.environ["PROJECTCAT_HOST"] = args.host
    os.environ["PROJECTCAT_PORT"] = str(args.port)

    from app import app  # 环境变量必须在 import 前设好，live_proxy 是读环境变量的

    lan = local_lan_ip()
    print()
    print("==> 网页已就绪")
    print(f"    本机：  http://127.0.0.1:{args.port}/live")
    if args.host == "0.0.0.0":
        print(f"    手机：  http://{lan}:{args.port}/live   （同一局域网）")
    print("    退出：  Ctrl+C")
    print()
    app.run(host=args.host, port=args.port, debug=False, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
