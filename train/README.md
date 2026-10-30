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

## 数据增强

训练期由 `build_tf()` 给，验证/测试只做 resize + center crop，不做任何随机变换。

| 算子 | `--aug legacy`（v0 权重用的配方） | `--aug v2` |
|---|---|---|
| 随机裁剪 | RandomResizedCrop scale 0.45~1.0，ratio 0.75~1.33 | scale 0.65~1.0（可用 `--rrc-min` 改），ratio 0.8~1.25 |
| 水平翻转 | p=0.5 | p=0.5 |
| 旋转 | 固定 10° | p=0.7 的 12°，填充猫毛中性色 `(124,116,104)` |
| 颜色 | ColorJitter(0.35, 0.35, 0.25, 0.03)，hue 0.25 即色相环 ±45° | ColorJitter(0.30, 0.30, 0.20, 0.05) |
| 随机灰度 | 无 | p=0.08 |
| 随机擦除 | 由独立开关 `--erase` 控制，默认 0 | 同（不随预设打开） |

训练里另有 label smoothing 0.05 和可选的 `--mixup`；评估用 TTA（原图 + 水平翻转取均值）。

两个设计判断：

- **水平翻转是安全的。** 标签只问"有没有缺口"，与左右无关。左右耳判不出时模块会退回
  图像级结论（`model_version` 带 `+image`），不会因此编造左右耳。
- **不做垂直翻转。** 现实里没有倒挂的猫，翻了只是给模型灌不存在的外观。

RandomResizedCrop 下限 0.45 是有代价的：剪耳缺口只有几十像素，裁掉 55% 画面后缺口
常常连同整只耳朵一起出框，等于给正样本贴了"没有缺口"的标签。数据集文档已证实正样本
错标率约 10%，且形态集中在"看不清却标成正样本"。所以 `v2` 把下限收到 0.65。

## 增强对照实验（2026-10-30）

11 组训练，全部用 `dataset_v1` 的同一套 split，阈值照旧只在 val 上选、test 只看一次。

| 配置 | backbone | 分辨率 | val acc | val AUC | test acc | test AUC | 剪耳召回 | 漏绝育率 |
|---|---|---|---|---|---|---|---|---|
| legacy | resnet18 | 224 | 0.674 | 0.768 | 0.729 | 0.783 | 0.429 | 3.7% |
| legacy + mixup 0.2 | resnet18 | 224 | 0.674 | 0.796 | 0.729 | 0.820 | 0.429 | 3.7% |
| v2（裁剪 0.65） | resnet18 | 224 | 0.652 | 0.781 | 0.729 | 0.811 | 0.524 | 11.1% |
| v2 + 擦除 0.2 | resnet18 | 224 | 0.652 | 0.764 | 0.750 | 0.840 | 0.476 | 3.7% |
| v2（裁剪 0.45）+ 擦除 0.2 | resnet18 | 224 | 0.674 | 0.809 | 0.771 | 0.815 | 0.571 | 7.4% |
| legacy | convnext_tiny | 288 | 0.826 | 0.842 | 0.854 | 0.887 | 0.809 | 11.1% |
| **legacy + 擦除 0.2** | convnext_tiny | 288 | **0.848** | 0.867 | **0.854** | 0.889 | **0.857** | 14.8% |
| v2（裁剪 0.45）+ 擦除 0.2 | convnext_tiny | 288 | 0.848 | 0.871 | 0.812 | 0.892 | 0.714 | 11.1% |
| v2（裁剪 0.45），不加擦除 | convnext_tiny | 288 | 0.761 | 0.848 | 0.812 | 0.854 | 0.762 | 14.8% |
| 同上 + seed 7 | convnext_tiny | 288 | 0.717 | 0.834 | 0.792 | 0.876 | 0.714 | 14.8% |
| 同上 + seed 2026 | convnext_tiny | 288 | 0.696 | 0.819 | 0.750 | 0.910 | 0.476 | 3.7% |

**结论：增强改动的效应全部落在随机种子噪声里。**

同一配方（v2 + 擦除，convnext@288）只换种子，val acc 就跑到 0.696 / 0.717 / 0.848，
test acc 0.750~0.812。也就是说 test 上 **±3 张图（约 6 个百分点）以内的差异不可判**，
而这里所有增强配置之间的差距都在这个范围内。

能说的只有方向性观察，别当结论：

1. **RandomErasing 是唯一一致为正的改动。** convnext 上 val acc 0.761 → 0.848、
   AUC 0.854 → 0.892；resnet18 上 test AUC 0.811 → 0.840、acc 0.729 → 0.750。
   两套 backbone 同向，而且机制上讲得通：数据集里被判"看不清"的正样本，典型形态就是
   笼子栏杆、伊丽莎白圈挡耳朵，遮挡模拟正对这个失效模式。
2. **`v2` 的其余改动（弱色偏、随机灰度、降旋转概率）单独看没有收益**，convnext 上
   val acc 反而从 0.826 掉到 0.761。它们只在叠加擦除后才不亏。
3. **收窄随机裁剪没验证出好处**，0.45 和 0.65 的差距在噪声内。理论上仍建议收窄
   （减少正样本的错误标签），但这次的实验不足以支撑。

推荐配方：**`--aug legacy --erase 0.2`**——只动一个算子，其余保持与 v0 一致，
是这轮里 val 最优且改动最小的一档。`v2` 预设保留仅为复现上表。

按这套配方导出的 `models/earnotch_convnext_tiny288_v1.onnx` 已登记进 MANIFEST，
但**没有设为默认**：它的提升在噪声内，应该先在站点实拍上做 A/B 再决定是否替换 v0。

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
   还没模型，只能喂整图。训练时用 `RandomResizedCrop` 逼模型看局部，但接入真 ROI 后
   需要重新校准阈值。
2. **域偏移。** 训练图全是白天、图库品质；部署是夜间、闪光、猫只占画面一小块。
   错例里 4/8 是"耳朵根本看不见"，这类在真实场景只会更多。
3. **标签噪声。** 正样本 160 张没有逐张复核，实测错标率约 10%。
4. **没有左右耳。** 输出是图像级"有剪耳"，不分左右。要满足契约的
   `EarNotch.left/right` 还得补 `ear_side` 标注。
5. **测试集只有 48 张，单次训练的结果不可复现。** 一个样本 = 2 个百分点；同配方换随机
   种子，test acc 实测落在 0.750~0.812、val acc 落在 0.696~0.848。所以**任何小于约
   6 个百分点的差异都不要当作改进**，包括上面那张表里的名次。要判断改动真假，只能上
   交叉验证或扩测试集。

## 下一步优先级

1. **扩数据，别再调增强。** 已实测：增强改动的效应小于种子噪声，继续调是在拟合噪声。
   当前 277 张撑不起更细的结论。
2. 补 `ear_side` 标注 → 改成左右耳双头输出，才符合契约
3. 猫脸模块出 landmarks 后，用真 ROI 重训 + 重校阈值
4. 补站点夜间实拍，这是指标天花板
5. 用 5 折交叉验证替代单次 split，让"改好没好"可判
