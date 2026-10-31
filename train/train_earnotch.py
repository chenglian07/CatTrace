"""
耳标识别（剪耳 = 已绝育）二分类训练脚本。

数据来源：dataset_v1/manifest.csv 的 train/val/test 划分，只读 splits/ 里的硬链接视图。
标签：pos=有剪耳缺口（已绝育）=1，neg=双耳完整=0。

用法：
    python train/train_earnotch.py
    python train/train_earnotch.py --epochs 40 --backbone convnext_tiny

产物写到 train/runs/<时间戳>/：
    metrics.json        各 split 指标（含阈值扫描）
    test_predictions.csv 逐张概率，便于人工看错例
    confusion_test.png
    best.pt             最佳权重

注意：当前数据没有耳部 ROI 标注，只能做整图分类。脚本按"ROI 会来"的方式预埋：
训练时用较狠的 RandomResizedCrop 逼模型只看局部，将来接入 catface landmarks
裁出的 ROI 时分布不会差太远。

增强策略用 --aug 切换（默认 legacy，与 v0 权重训练时一致，便于复现）：
    legacy  随机裁剪 scale 0.45~1.0 + 水平翻转 + 旋转 10° + ColorJitter(hue 0.25)
    v2      随机裁剪 scale 0.65~1.0 + 水平翻转 + 旋转 12°(p=0.7) + 弱色偏
            + 随机灰度 + 可选 RandomErasing
数据集默认读 仓库根/dataset_v1，可用 --data 或环境变量 CATTRACE_DATASET 指向别处。
"""
import argparse
import csv
import json
import os
import random
import time

import numpy as np
import torch
import torch.nn as nn
import torchvision
from PIL import Image, ImageOps
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms as T

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# 数据集不进 Git（体积 + 版权），默认就地读仓库根下的 dataset_v1，
# 也可用环境变量指向独立的数据盘。
DATA = os.environ.get("CATTRACE_DATASET") or os.path.join(ROOT, "dataset_v1")
SPLITS = os.path.join(DATA, "splits")

MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]


# ---------------------------------------------------------------- 数据
class CatEarDataset(Dataset):
    """从 splits/<split>/<label>/ 读图，标签由目录名给出。"""

    def __init__(self, split, tf, root=None):
        self.tf = tf
        self.items = []
        root = root or SPLITS
        for label, name in ((1, "pos"), (0, "neg")):
            d = os.path.join(root, split, name)
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d)):
                p = os.path.join(d, f)
                if os.path.isfile(p):
                    self.items.append((p, label, f))
        if not self.items:
            raise RuntimeError(f"{split} 为空，检查 {root}")

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        p, y, _ = self.items[i]
        with Image.open(p) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            x = self.tf(im)
        return x, y, i


def build_tf(img, train, aug="legacy", rrc_min=0.45, erase=0.0):
    """训练/验证的预处理。

    aug="legacy" 是 v0 权重训练时用的配方，保留是为了让旧指标可复现；
    aug="v2" 收窄了随机裁剪的下限——0.45 会把 55% 的画面裁掉，剪耳缺口只有
    几十像素，很容易连同整只耳朵一起被裁出框外，等于给正样本贴了个"没有缺口"
    的标签。其余改动见各分支注释。
    """
    if not train:
        return T.Compose([
            T.Resize(int(img * 1.14)),
            T.CenterCrop(img),
            T.ToTensor(),
            T.Normalize(MEAN, STD),
        ])

    if aug == "legacy":
        ops = [
            T.RandomResizedCrop(img, scale=(0.45, 1.0), ratio=(0.75, 1.333)),
            T.RandomHorizontalFlip(0.5),
            T.RandomRotation(10),
            # hue 0.25 = 色相环 ±45°，橘猫能被转成绿色，对形状任务过头了
            T.ColorJitter(0.35, 0.35, 0.25, 0.03),
        ]
    elif aug == "v2":
        ops = [
            T.RandomResizedCrop(img, scale=(rrc_min, 1.0), ratio=(0.8, 1.25),
                                interpolation=T.InterpolationMode.BICUBIC),
            # 标签是"有没有缺口"，与朝向无关，水平翻转安全；
            # 不做垂直翻转——现实里没有倒挂的猫，翻了只是纯噪声
            T.RandomHorizontalFlip(0.5),
            # 填猫毛的中性色，避免旋转后四角出现纯黑三角
            T.RandomApply([T.RandomRotation(12, fill=(124, 116, 104))], p=0.7),
            T.ColorJitter(0.30, 0.30, 0.20, 0.05),
            # 夜间/红外摄像头的画面近似灰度，让模型别依赖毛色
            T.RandomGrayscale(0.08),
        ]
    else:
        raise ValueError(f"未知增强预设：{aug}")

    tail = [T.ToTensor(), T.Normalize(MEAN, STD)]
    if erase > 0:
        # 遮挡鲁棒性：真实画面有草丛、栏杆、另一只猫挡住耳朵。
        # 面积上限压在 10%，再大就可能整只耳朵被抹掉，反而制造噪声标签。
        tail.append(T.RandomErasing(p=erase, scale=(0.02, 0.10), ratio=(0.5, 2.0)))
    return T.Compose(ops + tail)


# ---------------------------------------------------------------- 指标
def auc_score(y, p):
    """Mann-Whitney U 形式的 AUC，不依赖 sklearn。"""
    y = np.asarray(y)
    p = np.asarray(p, dtype=np.float64)
    n1 = int((y == 1).sum())
    n0 = int((y == 0).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty(len(p), dtype=np.float64)
    ranks[order] = np.arange(1, len(p) + 1)
    # 处理并列：同分取平均秩
    sp = p[order]
    i = 0
    while i < len(sp):
        j = i
        while j + 1 < len(sp) and sp[j + 1] == sp[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + j + 2) / 2.0
        i = j + 1
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def metrics(y, p, thr=0.5):
    y = np.asarray(y)
    pred = (np.asarray(p) >= thr).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    acc = (tp + tn) / max(len(y), 1)
    sens = tp / max(tp + fn, 1)          # 剪耳召回
    spec = tn / max(tn + fp, 1)          # 完整耳召回
    return {
        "n": int(len(y)), "thr": round(float(thr), 4),
        "acc": round(acc, 4), "auc": round(auc_score(y, p), 4),
        "recall_notched": round(sens, 4), "recall_intact": round(spec, 4),
        "balanced_acc": round((sens + spec) / 2, 4),
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        # fp = 完整耳被判成剪耳 → 漏绝育，业务上最不能接受
        "missed_neuter_rate": round(fp / max(tn + fp, 1), 4),
    }


def best_threshold(y, p, max_fp_rate=0.10):
    """选阈值：在"漏绝育率 ≤ max_fp_rate"的前提下，尽量提高剪耳召回。

    业务约束来自契约注释——把未绝育判成已绝育，这只猫可能永远不会被安排 TNR，
    属于事故；反过来把已绝育判成未绝育，只是志愿者白跑一趟。
    所以先卡 FP 上限，再谈召回。约束不可达时退化为单纯压 FP。
    """
    cand = []
    for t in np.arange(0.02, 0.99, 0.01):
        m = metrics(y, p, t)
        cand.append((float(t), m))
    ok = [(t, m) for t, m in cand if m["missed_neuter_rate"] <= max_fp_rate]
    if ok:
        return max(ok, key=lambda x: (x[1]["recall_notched"], x[1]["balanced_acc"]))[0]
    return min(cand, key=lambda x: (x[1]["missed_neuter_rate"], -x[1]["recall_notched"]))[0]


def split_probs(model, loader, device, tta=False):
    model.eval()
    out_p, out_y, out_i = [], [], []
    with torch.no_grad():
        for x, y, idx in loader:
            x = x.to(device, non_blocking=True)
            with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
                logit = model(x)
                prob = torch.softmax(logit.float(), 1)[:, 1]
                if tta:
                    logit2 = model(torch.flip(x, dims=[3]))
                    prob = (prob + torch.softmax(logit2.float(), 1)[:, 1]) / 2
            out_p += prob.cpu().tolist()
            out_y += y.tolist()
            out_i += idx.tolist()
    return out_y, out_p, out_i


# ---------------------------------------------------------------- 模型
def build_model(name, pretrained=True, dropout=0.0):
    if name == "resnet18":
        w = torchvision.models.ResNet18_Weights.IMAGENET1K_V1 if pretrained else None
        m = torchvision.models.resnet18(weights=w)
        feat = m.fc.in_features
        m.fc = nn.Sequential(nn.Dropout(dropout), nn.Linear(feat, 2)) if dropout else nn.Linear(feat, 2)
        head = ["fc"]
        freeze = ["conv1", "bn1", "layer1", "layer2"]
    elif name == "resnet34":
        w = torchvision.models.ResNet34_Weights.IMAGENET1K_V1 if pretrained else None
        m = torchvision.models.resnet34(weights=w)
        m.fc = nn.Linear(m.fc.in_features, 2)
        head = ["fc"]
        freeze = ["conv1", "bn1", "layer1", "layer2"]
    elif name == "convnext_tiny":
        w = torchvision.models.ConvNeXt_Tiny_Weights.IMAGENET1K_V1 if pretrained else None
        m = torchvision.models.convnext_tiny(weights=w)
        m.classifier[2] = nn.Linear(m.classifier[2].in_features, 2)
        # convnext 自带 Dropout，不用再加
        head = ["classifier"]
        freeze = []
    else:
        raise ValueError(name)
    for n, p in m.named_parameters():
        if any(n.startswith(f) for f in freeze):
            p.requires_grad = False
    return m, head


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backbone", default="resnet18")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--bs", type=int, default=32)
    ap.add_argument("--img", type=int, default=224)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--wd", type=float, default=1e-4)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--patience", type=int, default=10)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--mixup", type=float, default=0.0, help="mixup 的 beta 参数，0 表示关闭")
    ap.add_argument("--dropout", type=float, default=0.0)
    ap.add_argument("--no-pretrained", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--data", default="", help="数据集根目录（含 splits/），默认读 CATTRACE_DATASET 或 仓库根/dataset_v1")
    ap.add_argument("--aug", default="legacy", choices=("legacy", "v2"), help="数据增强预设")
    ap.add_argument("--rrc-min", type=float, default=0.45, help="RandomResizedCrop 面积下限（v2 建议 0.65）")
    ap.add_argument("--erase", type=float, default=0.0, help="RandomErasing 概率，0 表示关闭")
    ap.add_argument("--tag", default="", help="写进 runs/ 目录名，便于区分对照实验")
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.backends.cudnn.benchmark = True

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type == "cuda":
        print("GPU:", torch.cuda.get_device_name(0))

    stamp = time.strftime("%Y%m%d_%H%M%S")
    suffix = f"{args.backbone}"
    if args.tag:
        suffix += f"_{args.tag}"
    run_dir = os.path.join(HERE, "runs", f"{stamp}_{suffix}")
    os.makedirs(run_dir, exist_ok=True)

    data_root = os.path.join(args.data, "splits") if args.data else SPLITS
    tr = CatEarDataset("train", build_tf(args.img, True, args.aug, args.rrc_min, args.erase), data_root)
    va = CatEarDataset("val", build_tf(args.img, False), data_root)
    te = CatEarDataset("test", build_tf(args.img, False), data_root)
    print(f"train {len(tr)} / val {len(va)} / test {len(te)}  | aug={args.aug} rrc_min={args.rrc_min} "
          f"erase={args.erase} mixup={args.mixup}")

    dl_tr = DataLoader(tr, batch_size=args.bs, shuffle=True, num_workers=args.workers,
                       pin_memory=True, drop_last=len(tr) > args.bs, persistent_workers=args.workers > 0)
    dl_va = DataLoader(va, batch_size=args.bs, shuffle=False, num_workers=args.workers,
                       pin_memory=True, persistent_workers=args.workers > 0)
    dl_te = DataLoader(te, batch_size=args.bs, shuffle=False, num_workers=args.workers,
                       pin_memory=True, persistent_workers=args.workers > 0)

    model, head_prefix = build_model(args.backbone, not args.no_pretrained, args.dropout)
    model = model.to(device)

    head_params, base_params = [], []
    for n, p in model.named_parameters():
        if not p.requires_grad:
            continue
        (head_params if any(n.startswith(h) for h in head_prefix) else base_params).append(p)
    opt = torch.optim.AdamW([
        {"params": base_params, "lr": args.lr * 0.1},
        {"params": head_params, "lr": args.lr},
    ], weight_decay=args.wd)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    crit = nn.CrossEntropyLoss(label_smoothing=0.05)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")

    best = {"score": -1, "epoch": -1}
    bad = 0
    hist = []
    for ep in range(1, args.epochs + 1):
        model.train()
        tot, n = 0.0, 0
        for x, y, _ in dl_tr:
            x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
            opt.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
                if args.mixup > 0 and np.random.rand() < 0.5:
                    lam = float(np.random.beta(args.mixup, args.mixup))
                    perm = torch.randperm(x.size(0), device=device)
                    out = model(lam * x + (1 - lam) * x[perm])
                    loss = lam * crit(out, y) + (1 - lam) * crit(out, y[perm])
                else:
                    loss = crit(model(x), y)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            tot += loss.item() * y.size(0)
            n += y.size(0)
        sched.step()

        vy, vp, _ = split_probs(model, dl_va, device)
        vm = metrics(vy, vp)
        hist.append({"epoch": ep, "train_loss": round(tot / n, 4), **vm})
        print(f"ep{ep:02d} loss {tot/n:.4f} | val acc {vm['acc']:.3f} auc {vm['auc']:.3f} "
              f"rec_notched {vm['recall_notched']:.3f} rec_intact {vm['recall_intact']:.3f}")

        if vm["balanced_acc"] > best["score"]:
            best = {"score": vm["balanced_acc"], "epoch": ep, "state": {k: v.detach().cpu().clone()
                                                                      for k, v in model.state_dict().items()}}
            bad = 0
        else:
            bad += 1
            if bad >= args.patience:
                print(f"验证集 {args.patience} 轮无提升，早停于 ep{ep}")
                break

    model.load_state_dict(best["state"])
    out = args.out or os.path.join(ROOT, "models", f"earnotch_{args.backbone}_v0.pt")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    # ---- 最终评估（val 选阈值，test 只看一次）
    # 阈值在"带 TTA 的 val 概率"上选，和 predict 脚本的默认行为保持一致
    vy, vp, _ = split_probs(model, dl_va, device)
    vty, vtp, _ = split_probs(model, dl_va, device, tta=True)
    thr = best_threshold(vty, vtp)
    ty, tp_, ti = split_probs(model, dl_te, device)
    tty, ttp, _ = split_probs(model, dl_te, device, tta=True)

    torch.save({"state_dict": best["state"], "backbone": args.backbone,
                "img": args.img, "epoch": best["epoch"], "threshold": thr,
                "val_auc": metrics(vty, vtp, thr)["auc"], "args": vars(args)}, out)

    report = {
        "backbone": args.backbone, "epochs_run": len(hist), "best_epoch": best["epoch"],
        "val": metrics(vy, vp, thr), "val_tta": metrics(vty, vtp, thr),
        "test": metrics(ty, tp_, thr),
        "test_tta": metrics(tty, ttp, thr),
        "threshold": thr, "checkpoint": out,
        "history": hist,
    }
    with open(os.path.join(run_dir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    rows = []
    for i, (yy, pp) in enumerate(zip(ty, tp_, strict=True)):
        p, y, name = te.items[i]
        rows.append({"file": name, "y": yy, "prob": round(pp, 4),
                     "pred": int(pp >= thr), "correct": int((pp >= thr) == yy)})
    with open(os.path.join(run_dir, "test_predictions.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["file", "y", "prob", "pred", "correct"])
        w.writeheader()
        w.writerows(rows)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        m = report["test"]
        cm = np.array([[m["tn"], m["fp"]], [m["fn"], m["tp"]]])
        fig, ax = plt.subplots(figsize=(3.6, 3.2), dpi=150)
        ax.imshow(cm, cmap="Blues")
        for (i, j), v in np.ndenumerate(cm):
            ax.text(j, i, str(v), ha="center", va="center",
                    color="white" if v > cm.max() / 2 else "#222", fontsize=13)
        ax.set_xticks([0, 1], ["intact", "notched"])
        ax.set_yticks([0, 1], ["intact", "notched"])
        ax.set_xlabel("predicted")
        ax.set_ylabel("actual")
        ax.set_title(f"test  acc {m['acc']:.3f}  auc {m['auc']:.3f}", fontsize=9)
        fig.tight_layout()
        fig.savefig(os.path.join(run_dir, "confusion_test.png"))
        plt.close(fig)
    except Exception as e:
        print("混淆矩阵没画出来:", e)

    print("\n" + "=" * 58)
    print(f"阈值 {thr:.2f}（在 val 上按\"漏绝育率≤10% 时最大化剪耳召回\"选）")
    for k in ("val", "test", "test_tta"):
        m = report[k]
        print(f"{k:9s} acc {m['acc']:.3f} auc {m['auc']:.3f} | "
              f"剪耳召回 {m['recall_notched']:.3f} 完整耳召回 {m['recall_intact']:.3f} | "
              f"漏绝育 {m['missed_neuter_rate']:.3f}")
        print(f"          TP{m['tp']} TN{m['tn']} FP{m['fp']} FN{m['fn']}")
    print("=" * 58)
    print("权重:", out)
    print("报告:", os.path.join(run_dir, "metrics.json"))


if __name__ == "__main__":
    main()
