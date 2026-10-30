"""把训练好的耳标 .pt 权重导出为 ONNX，并写出推理所需的元数据。

树莓派上只安装 onnxruntime，没有 torch，所以部署前必须在训练机上跑一次：

    python train/export_earnotch_onnx.py
    python train/export_earnotch_onnx.py --ckpt models/earnotch_resnet18_v0.pt \
        --out models/earnotch_resnet18_v0.onnx

默认导出当前效果最好的 convnext_tiny / 288。导出完成后会在 ONNX 旁边生成
``*.onnx.json``，记录阈值、输入尺寸和归一化参数，供 modules.earnotch 读取。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from train_earnotch import MEAN, STD, build_model  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default=os.path.join(ROOT, "models", "earnotch_convnext288_v0.pt"))
    ap.add_argument("--out", default="")
    ap.add_argument("--opset", type=int, default=17)
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(args.ckpt):
        raise SystemExit(f"找不到权重：{args.ckpt}")

    ck = torch.load(args.ckpt, map_location="cpu", weights_only=False)
    img_size = int(ck.get("img", 224))
    backbone = ck["backbone"]
    model, _ = build_model(backbone, pretrained=False)
    model.load_state_dict(ck["state_dict"])
    model.eval()

    out = args.out or os.path.join(
        ROOT, "models", f"earnotch_{backbone}{img_size}_v0.onnx"
    )
    os.makedirs(os.path.dirname(out), exist_ok=True)

    dummy = torch.randn(1, 3, img_size, img_size)
    torch.onnx.export(
        model,
        dummy,
        out,
        export_params=True,
        opset_version=args.opset,
        do_constant_folding=True,
        input_names=["input"],
        output_names=["logits"],
        dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
        dynamo=False,
    )
    print(f"已导出：{out}")

    meta = {
        "format": "catvision.earnotch.onnx/1",
        "backbone": backbone,
        "input_size": img_size,
        "opset": args.opset,
        "mean": MEAN,
        "std": STD,
        "threshold": float(ck.get("threshold", 0.58)),
        "band": 0.12,
        "source_checkpoint": os.path.basename(args.ckpt),
        "checkpoint_epoch": ck.get("epoch"),
        "val_auc": ck.get("val_auc"),
    }

    if not args.no_verify:
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise SystemExit(
                "导出完成，但本机没有 onnxruntime，无法验证。"
                "请先 pip install onnxruntime，或加 --no-verify。"
            ) from exc

        sess = ort.InferenceSession(out, providers=["CPUExecutionProvider"])
        got = sess.run(["logits"], {"input": dummy.numpy()})[0]
        with torch.no_grad():
            want = model(dummy).numpy()
        diff = float(np.max(np.abs(got - want)))
        print(f"ONNX Runtime 校验：max_abs_diff={diff:.6g}")
        if diff > 1e-4:
            raise SystemExit("ONNX 输出与 PyTorch 差异过大，导出失败。")
        meta["onnx_max_abs_diff"] = diff

    meta_path = out + ".json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"元数据：{meta_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
