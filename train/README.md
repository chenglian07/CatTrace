# 耳标识别（剪耳 = 已绝育）

二分类器：输入一张猫图，判断耳朵是否有 TNR 剪耳缺口。

> **数据与权重不进 Git。** `dataset_v1/`、`splits/`、`train/runs/`、`models/*.pt` 都在
> `.gitignore` 里；复现训练时把它们放到仓库根目录。推理只需 `models/earnotch_*.onnx`
> 和同名 `.json`（部署到树莓派时 scp 过去即可，不需要装 torch）。

## 环境

训练需要 PyTorch（CUDA 版更快，CPU 也能跑但很慢），建议单独建环境：

```bash
python -m venv .venv-train && source .venv-train/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
```

> 记录一个踩过的坑：老环境的 torch 2.5.1+cu121 只编译到 sm_90，
> 在 RTX 5070（sm_120）上会静默退回 CPU，训练时间差一个数量级。换新 wheel 即可。

## 脚本

| 脚本 | 用途 |
|---|---|
| `train_earnotch.py` | 训练整图二分类器，产物在 `train/runs/<时间戳>_<backbone>/` |
| `export_earnotch_onnx.py` | `.pt` → `.onnx` + 同名 `.json`（阈值/尺寸/归一化参数） |
| `predict_earnotch.py` | 单图/目录推理，三档输出（notched / intact / uncertain） |
| `recalibrate_threshold.py` | 在 val 上重算阈值并写回权重 |

> 源仓库里的 `train_ear_heads.py`（左右耳双头）没有一并搬过来：它训练出的双头权重
> 与当前运行时 `EarNotchModel`（单输出二分类）不兼容，导出脚本也不支持。
> 等运行时改成双头输出后再引入，避免留下跑不通的死代码。

## 数据

来自 `dataset_v1/splits/`，只读，不复制：

| split | pos（剪耳） | neg（完整） |
|---|---|---|
| train | 118 | 114 |
| val | 21 | 25 |
| test | 21 | 27 |

`hold_sanity`（2 张水印）和 `hold_unjudgeable`（42 张耳形判不了）不在任何 split 里，
从源头就不进训练。按 `group_id` 整组划分，无跨 split 泄漏。

## 训练

```bash
python train/train_earnotch.py --backbone convnext_tiny --img 288 --bs 24 --epochs 40
```

常用参数：`--mixup 0.4`、`--dropout 0.3`、`--lr`、`--patience`、`--out`。
产物在 `train/runs/<时间戳>_<backbone>/`：`metrics.json`（含逐 epoch 曲线）、
`test_predictions.csv`、`confusion_test.png`。

阈值不是固定 0.5，训练结束时在 **val 上按业务约束重选**：先保证漏绝育率 ≤ 10%，
再最大化剪耳召回，最后写进权重文件。理由见 `contracts` 里 EarNotch 的注释——
把未绝育判成已绝育，这只猫可能永远不会被安排 TNR。

## 预测

```bash
python train/predict_earnotch.py 图片路径
python train/predict_earnotch.py 某个目录 --recursive --json
```

三档输出，不确定时**不下结论**：

| decision | 含义 | 对应 `EarNotch` |
|---|---|---|
| `notched` | 有剪耳缺口，已绝育 | `notched=true` |
| `intact` | 双耳完整，未绝育 | `notched=false` |
| `uncertain` | 概率落在阈值 ±band 内，或原图短边 < 96px | `visible=false, notched=null` |

### 阈值缺失怎么办

权重里没有 `threshold` 字段时，推理脚本会**直接报错退出**，不会退回 0.5。
用 val 重算并写回：

```bash
python train/recalibrate_threshold.py models/earnotch_convnext288_v0.pt
python train/recalibrate_threshold.py models/xxx.pt --max-fp 0.05 --dry-run
```

阈值 0.58 用该脚本复算可以完全复现，说明写入逻辑是幂等的。

## 实测结果（2026-10-26）

test 集 48 张（21 剪耳 / 27 完整），阈值在 val 上选定后**只在 test 上跑一次**：

| backbone | 分辨率 | test acc | test AUC | 剪耳召回 | 完整耳召回 | 漏绝育率 |
|---|---|---|---|---|---|---|
| resnet18 | 224 | 0.750 | 0.840 | 0.857 | 0.667 | 33.3% |
| resnet18 + mixup | 224 | 0.750 | 0.822 | 0.857 | 0.667 | 33.3% |
| convnext_tiny | 224 | 0.833 | 0.882 | 0.809 | 0.852 | 14.8% |
| **convnext_tiny** | **288** | **0.896** | **0.896** | **0.857** | **0.926** | **7.4%** |

当前默认权重：`models/earnotch_convnext288_v0.pt`（阈值 0.58，带 TTA）。

## 已知局限（按严重程度）

1. **整图分类，不是 ROI 分类。** 契约要求输入是 landmarks 裁出的耳部 ROI，现在猫脸模块
   还没模型，只能喂整图。训练时用 `RandomResizedCrop(scale 0.45~1.0)` 逼模型看局部，
   但接入真 ROI 后需要重新校准阈值。
2. **域偏移。** 训练图全是白天、图库品质；部署是夜间、闪光、猫只占画面一小块。
   错例里 4/8 是"耳朵根本看不见"，这类在真实场景只会更多。
3. **标签噪声。** 正样本 160 张没有逐张复核，实测错标率约 10%。
4. **没有左右耳。** 输出是图像级"有剪耳"，不分左右。要满足契约的
   `EarNotch.left/right` 还得补 `ear_side` 标注。
5. **测试集只有 48 张。** 一个样本 = 2 个百分点，指标波动大，别当成精确值。

## 下一步优先级

1. 补 `ear_side` 标注 → 改成左右耳双头输出，才符合契约
2. 猫脸模块出 landmarks 后，用真 ROI 重训 + 重校阈值
3. 补站点夜间实拍，这是指标天花板
