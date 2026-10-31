"""
用训好的耳标模型判断一张图里的猫是否剪耳（= 已绝育）。

用法：
    python train/predict_earnotch.py 图片路径
    python train/predict_earnotch.py 某个目录 --recursive
    python train/predict_earnotch.py a.jpg b.jpg --json

输出三种判定，刻意区分「判得了」和「判不了」：
    notched   有剪耳缺口  → 已绝育
    intact    双耳完整    → 未绝育
    uncertain 概率落在阈值 ±band 之间，或图太小 → 不下结论，交人工

对应 contracts/python/catvision_contracts 里 EarNotch 的规则：
看不见/拿不准就返回 null，禁止猜。猜错方向不对称——把未绝育判成已绝育，
这只猫可能永远不会被安排 TNR。
"""
import argparse
import json
import os
import sys

import torch
from PIL import Image, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from torchvision import transforms as T  # noqa: E402
from train_earnotch import MEAN, STD, build_model  # noqa: E402

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def load(ckpt_path, device):
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    model, _ = build_model(ck["backbone"], pretrained=False)
    model.load_state_dict(ck["state_dict"])
    model.to(device).eval()
    tf = T.Compose([
        T.Resize(int(ck["img"] * 1.14)),
        T.CenterCrop(ck["img"]),
        T.ToTensor(),
        T.Normalize(MEAN, STD),
    ])
    return model, tf, ck


@torch.no_grad()
def predict(model, tf, path, device, tta=True):
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        x = tf(im.convert("RGB")).unsqueeze(0).to(device)
    with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
        prob = torch.softmax(model(x).float(), 1)[:, 1]
        if tta:
            prob = (prob + torch.softmax(model(torch.flip(x, dims=[3])).float(), 1)[:, 1]) / 2
    return float(prob.item())


def decide(prob, thr, band):
    if prob >= thr + band:
        return "notched"
    if prob <= thr - band:
        return "intact"
    return "uncertain"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--ckpt", default=os.path.join(ROOT, "models", "earnotch_convnext288_v0.pt"))
    ap.add_argument("--thr", type=float, default=None, help="默认用权重里存的阈值")
    ap.add_argument("--band", type=float, default=0.12, help="不确定带半宽")
    ap.add_argument("--recursive", action="store_true")
    ap.add_argument("--no-tta", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, tf, ck = load(args.ckpt, device)
    if args.thr is not None:
        thr = args.thr
    elif "threshold" in ck:
        thr = float(ck["threshold"])
    else:
        # 阈值必须在 val 上按「漏绝育率约束」选出来，不能猜。
        # 悄悄退回 0.5 会让模型在错误的工作点上跑，而且完全不报错。
        raise SystemExit(
            f"权重里没有 threshold：{args.ckpt}\n"
            "这个权重是阈值尚未写入的旧版本。先重算：\n"
            f"  python train/recalibrate_threshold.py {args.ckpt}\n"
            "或显式传 --thr 指定。"
        )
    ver = os.path.basename(args.ckpt)

    files = []
    for p in args.paths:
        if os.path.isdir(p):
            walk = os.walk(p) if args.recursive else [(p, [], os.listdir(p))]
            for root, _, fs in walk:
                files += [os.path.join(root, f) for f in sorted(fs)
                          if os.path.splitext(f)[1].lower() in IMG_EXT]
        else:
            files.append(p)

    out = []
    for p in files:
        prob = predict(model, tf, p, device, tta=not args.no_tta)
        d = decide(prob, thr, args.band)
        # 原图太小说明耳朵像素不足，强制转人工
        with Image.open(p) as im:
            w, h = im.size
        if min(w, h) < 96:
            d = "uncertain"
        out.append({"file": os.path.basename(p), "path": os.path.abspath(p),
                    "prob_notched": round(prob, 4), "decision": d,
                    "size": [w, h], "model": ver})

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"模型 {ver}  阈值 {thr:.2f} ± {args.band:.2f}")
        for r in out:
            tag = {"notched": "已绝育(剪耳)", "intact": "未绝育(完整)",
                   "uncertain": "判不了/待人工"}[r["decision"]]
            print(f"  {r['prob_notched']:.3f}  {tag:12s} {r['file']}")
        n = {k: sum(1 for r in out if r["decision"] == k)
             for k in ("notched", "intact", "uncertain")}
        print(f"\n合计 {len(out)}：剪耳 {n['notched']} / 完整 {n['intact']} / 待人工 {n['uncertain']}")


if __name__ == "__main__":
    main()
