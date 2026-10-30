"""
重算权重文件里的判定阈值（在 val 上，按业务约束）。

什么时候需要跑：
  - 权重是阈值写入逻辑加上之前训的，ckpt 里没有 threshold 字段
  - 换了数据或重新划分了 split，旧阈值不再对应当前 val 分布
  - 调整了漏绝育率上限（默认 10%）

为什么不直接给个 0.5：这个模型的输出概率不是校准过的，0.5 在这批数据上
等于把漏绝育率放到 30% 以上。阈值必须在 val 上按「漏绝育 <= 上限」选出来。

用法：
    python train/recalibrate_threshold.py models/xxx.pt
    python train/recalibrate_threshold.py models/xxx.pt --max-fp 0.05 --dry-run
"""
import argparse
import os
import sys

import torch
from torch.utils.data import DataLoader

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from train_earnotch import (  # noqa: E402
    CatEarDataset,
    best_threshold,
    build_model,
    build_tf,
    metrics,
    split_probs,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ckpt")
    ap.add_argument("--max-fp", type=float, default=0.10, help="允许的漏绝育率上限")
    ap.add_argument("--split", default="val", choices=["train", "val", "test"],
                    help="用哪个 split 定阈值，默认 val（test 不该参与调参）")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写回权重")
    args = ap.parse_args()

    ck = torch.load(args.ckpt, map_location="cpu", weights_only=False)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, _ = build_model(ck["backbone"], pretrained=False, dropout=0.0)
    model.load_state_dict(ck["state_dict"])
    model.to(device).eval()

    ds = CatEarDataset(args.split, build_tf(ck["img"], train=False))
    dl = DataLoader(ds, batch_size=32, shuffle=False, num_workers=4, pin_memory=True)
    y, p, _ = split_probs(model, dl, device, tta=True)

    thr = best_threshold(y, p, args.max_fp)
    m = metrics(y, p, thr)
    n_pos = int(sum(y))

    print(f"权重     {os.path.basename(args.ckpt)}")
    print(f"结构     {ck['backbone']} @ {ck['img']}")
    print(f"{args.split} 集   {len(y)} 张（pos {n_pos} / neg {len(y) - n_pos}）")
    print(f"阈值     {thr:.2f}   (原 {ck.get('threshold', '未写入')})")
    print(f"效果     AUC {m['auc']:.3f} | 剪耳召回 {m['recall_notched']:.3f} "
          f"| 完整耳召回 {m['recall_intact']:.3f} | 漏绝育 {m['missed_neuter_rate']:.3f}")
    if args.split == "test":
        print("\n注意：test 只该在最后看一次，用它调阈值等于把 test 变成 val。")

    if args.dry_run:
        print("\n--dry-run：未写回")
        return

    ck["threshold"] = thr
    ck["val_auc"] = float(m["auc"]) if args.split == "val" else ck.get("val_auc")
    ck["val_metrics"] = m if args.split == "val" else ck.get("val_metrics")
    torch.save(ck, args.ckpt)
    print(f"\n已写回 {args.ckpt}")


if __name__ == "__main__":
    main()
