# 剪耳识别（耳标模块）

> 状态：**可运行的基线（bootstrap），不是生产级模型。**
> 它能让 `pipeline.runner` 从 Mock 切换到真实推理并跑通，
> 但精度、域适应和左右耳判定都还需要补数据/换模型。

## 1. 它到底是什么

`modules/earnotch:EarNotchModel` 是一个**整图级二分类器**：

- 输入：一帧图（整张，不做 ROI 裁剪）+ 猫脸模块给的 `CatFace`
- 输出：这只猫"有没有剪耳"的概率 `P(notched)`
- 左右耳：分别裁左右耳周边再各跑一次，谁的概率高投谁；两侧差 < 0.08 时不猜，
  返回 `visible=true, notched=null`

它不是"检测剪耳缺口"的检测器，也不输出缺口框。**没有猫脸/关键点时它无法裁耳**，
所以下游仍依赖猫脸模块（当前 `modules/catface/` 还是占位，可用
`--catface mocks:MockCatFaceModule` 提供合法关键点）。

## 2. 三道判断，宁可不结论

| 条件 | 结果 | 原因 |
|---|---|---|
| 猫脸短边 < `min_face_px`（96） | 整条 `unknown` | 整图模型此时等于在看放大后的整帧，耳朵只剩几像素 |
| 耳部 ROI 短边 < `min_ear_px`（64） | 只放弃左右耳，图像级结论照给 | 两侧概率差在几十像素上是噪声 |
| 概率落在 `threshold ± band`（0.58 ± 0.12） | `unknown` | 不确定就不下结论 |

`visible=false` 时 `notched` 和 `score` 必须为 `null`，这条由 pydantic 的
`model_validator` 和 JSON Schema 的 `if-then` 双重拦截。

## 3. 指标（不要当成生产精度）

test 集 48 张（21 剪耳 / 27 完整），阈值在 val 上选定后**只在 test 上跑一次**：

| backbone | 分辨率 | acc | AUC | 剪耳召回 | 完整耳召回 | 未绝育被判已绝育 |
|---|---|---|---|---|---|---|
| resnet18 | 224 | 0.750 | 0.840 | 0.857 | 0.667 | **33.3%** |
| convnext_tiny | 288 | **0.896** | 0.896 | 0.857 | 0.926 | **7.4%** |

两个方向必须分开看：表里最后一列是 `fp/(tn+fp)`，即**未绝育被判成已绝育**——
这只猫可能永远排不上 TNR；反方向（已绝育判成未绝育，白跑一趟）是 14.3%（3/21）。
前者更危险，阈值就是按"先把漏绝育率压到 ≤10%"来选的。

> 这些数字来自图库白天图，不是站点夜间实拍。一个样本 = 2 个百分点，别当精确值。
> 上游仓库还有一份"端到端"指标（猫脸→耳标，定判准确率 0.893），它依赖一个 Haar
> 猫脸检测器；那个检测器**没有并入本分支**，所以这里不复述那组数字。

### 2026-10-30 重训：增强不是瓶颈

按"加数据增强能不能提精度"做了 11 组对照（详见 `train/README.md`），结论是
**不能**：同一配方只换随机种子，val acc 就落在 0.696~0.848、test acc 落在
0.750~0.812，而各增强配置之间的差距全在这个范围内。

唯一同向为正的是 RandomErasing（遮挡模拟），机制上对得上数据集里"笼子栏杆挡住耳朵
导致误标"的失效模式。按 `--aug legacy --erase 0.2` 导出的
`earnotch_convnext_tiny288_v1.onnx` 已登记在 `MANIFEST.json` 的 `variants` 里，
**但没有设为默认**——提升在噪声内，应先在站点实拍上 A/B。

## 4. 怎么跑

### 单图/目录推理（不需要摄像头）

```bash
python train/predict_earnotch.py 某张猫图.jpg
python train/predict_earnotch.py 某个目录 --recursive --json
```

三档输出：`notched` / `intact` / `uncertain`。

### 接进流水线

```bash
python -m pipeline.runner --source synthetic:30 \
    --catface mocks:MockCatFaceModule \
    --earnotch modules.earnotch:EarNotchModel
```

猫脸模块出真模型后，把 `--catface` 换成 `modules.catface:M1CatFaceModule` 即可，
流水线一行不用改。

### 网页实时（树莓派）

```bash
python scripts/pi_phone_demo.py --rotate 180 --port 8000
```

`/` 和 `/kiosk` 都是两级串联：先判有没有猫，有猫再判剪耳，顶部直接显示
「已剪耳，已绝育 / 未剪耳，未绝育 / 看不清，不下结论 / 没有猫」。
`--earnotch off` 关掉第二级，`--earnotch-model` 换权重，`--crop 0.6` 收缩取景框。
桌面 kiosk 的安装见 [pi-kiosk.md](./pi-kiosk.md)。

### 树莓派

`EarNotchModel._default_model()` 会按架构自动选权重：

| 平台 | 默认权重 | 单帧耗时（Pi 4B 实测） |
|---|---|---|
| aarch64 / arm64 | `earnotch_resnet18224_v0.onnx` | 约 0.65s |
| 开发机 x86 | `earnotch_convnext_tiny288_v0.onnx` | 约 3.2s |

板上只装 `onnxruntime`，不需要 torch。帧率建议 `--fps 1~2`，别按 3fps 配——
推理跟不上会一直丢帧。

## 5. 权重从哪来

`models/*.onnx` 在 `.gitignore` 里，**不在 Git 中**。原因有两个：

1. convnext 权重 106.2MB，超过 GitHub 单文件 100MB 硬上限，推不上去；
2. 权重是训练产物，仓库只保留可复现的脚本。

获取方式（二选一）：

```bash
# A. 从训练机拷
scp models/earnotch_resnet18224_v0.onnx* pi@pi-cat:~/catvision/models/

# B. 自己导出（需要 .pt 权重和 torch）
python train/export_earnotch_onnx.py --ckpt models/earnotch_resnet18_v0.pt \
    --out models/earnotch_resnet18224_v0.onnx
```

导出会在 ONNX 旁边生成同名 `.json`，记录 `input_size / mean / std / threshold / band`。
**缺这个 json 时阈值会退回 0.58**，换模型后一定要重新校准：

```bash
python train/recalibrate_threshold.py models/xxx.pt --max-fp 0.05 --dry-run
```

校验和与体积登记在 [`models/MANIFEST.json`](../models/MANIFEST.json)。

## 6. 已知局限

1. **整图分类，不是 ROI 分类。** 契约设想的是 landmarks 裁出的耳部 ROI；现在只能喂整图。
   训练时用 `RandomResizedCrop(0.45~1.0)` 逼模型看局部，但接真 ROI 后必须重训+重校阈值。
2. **域偏移。** 训练图全是白天、图库品质；部署是夜间、闪光、猫只占画面一小块。
3. **标签噪声。** 正样本约 160 张未逐张复核，实测错标率约 10%。
4. **没有真正的左右耳。** 输出是图像级"有剪耳"，左右靠启发式猜，不是双头模型。
5. **测试集只有 48 张。** 指标波动大。

## 7. 下一步

1. 猫脸模块出 landmarks → 用真 ROI 重训
2. 补 `ear_side` 标注 → 换成左右耳双头输出，才真正满足契约
3. 补站点夜间实拍，这是指标天花板
