# CatVision · 猫脸识别 + 剪耳识别树莓派原型

团队协作的 AI 识别原型：**摄像头 → 猫脸识别（个体ID）→ 剪耳识别（绝育状态）→ 决策（投粮 / TNR）→ 网页展示**。

> **新成员先看 [docs/接手流程.md](./docs/接手流程.md)**：要装哪些软件、怎么拉代码、
> 怎么分工、提 PR 前必做哪些检查，一条条列好了。

运行平台：Raspberry Pi 4 Model B（`pi4-cat` / `192.168.31.252`，Debian 13，Python 3.13）

---

## 0. 三十秒上手

```bash
git clone git@github.com:chenglian07/TNR.git && cd TNR
python3 -m venv --system-site-packages .venv      # Pi 上必须带 --system-site-packages，否则看不到 picamera2
source .venv/bin/activate                          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# D0 验收命令：无摄像头、无模型也能跑通全链路
python -m pipeline.runner --source synthetic:60 --mock-all
```

看到 `PIPELINE OK` 和 `DetectionEvent` / `ActionEvent` 就算通过。

完整自证（L1~L5 五层，逐项 PASS/FAIL）：

```bash
python scripts/verify_catvision.py
```

> **D0 通过之前，谁都不许开始写模型。**
> 第一周唯一的交付物是「契约 + Mock + 数据管道」。模型晚一天不致命，接口对不上会让三个模块互相卡死。

---

## 1. 三条铁律

1. **只通过 `contracts/` 交互。** 禁止 import 别人模块内部的代码。跨模块只有「契约对象」一条路。
2. **改契约要走 PR + 其余两个模块 approve。** 字段名改动会让 CI 的契约测试直接失败。
3. **每人必须交 Mock。** 没有 Mock 就没有并行，只有排队。

---

## 2. 分工与目录

三个模块**互不阻塞**，任意成员可认领其中一块（或全部）：

| 角色 | 负责目录 | 输入 → 输出 | 交付物 |
|---|---|---|---|
| **摄像头与联调** | `modules/camera/` `pipeline/` | 摄像头 → `FramePacket` | 五种采集源、固定帧率抽帧、事件总线、决策引擎、部署脚本 |
| **猫脸识别** | `modules/catface/` | `FramePacket` → `CatFace[]` | 检测 + 7 关键点 + 个体ID + 跨帧追踪 |
| **耳标识别** | `modules/earnotch/` | `FramePacket` + `CatFace[]` → `EarNotch[]` | 左右耳剪耳判定 + 绝育结论 |

```
catvision/
├─ contracts/            # ⭐ 唯一权威接口定义（三个模块共管）
│  ├─ v1/*.schema.json   # JSON Schema（机器可读规范）
│  └─ python/catvision_contracts/   # pydantic 绑定 + 模块接口 Protocol
├─ modules/
│  ├─ camera/            # 摄像头与联调：CSI / USB / RTSP / 文件回放 / 合成源
│  ├─ catface/           # 猫脸识别：接手请看该目录 README
│  └─ earnotch/          # 耳标识别：接手请看该目录 README
├─ mocks/                # 每人一份 mock，保证并行
├─ pipeline/             # 联调：runner / 聚合投票 / 决策 / 存储 / 事件总线
├─ tests/
│  ├─ contract/          # 契约测试（改接口必挂）
│  └─ fixtures/          # 小样本素材
├─ scripts/              # 部署、录制、模型导出
├─ docs/                 # 接口规范 / 联调 checklist / 部署 / 摄像头选型
└─ models/MANIFEST.json  # 模型登记表（模型文件本身不进 Git）
```

### 接手步骤（拉下代码后照做）

不管认领哪一块，前三步都一样：

```bash
git clone git@github.com:chenglian07/TNR.git && cd TNR
python3 -m venv --system-site-packages .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q && python -m pipeline.runner --source synthetic:60 --mock-all   # 看到 PIPELINE OK 再往下
```

然后按分工往下走：

| 步骤 | 摄像头与联调 | 猫脸识别 | 耳标识别 |
|---|---|---|---|
| **只改自己的目录** | `modules/camera/` `pipeline/` | `modules/catface/` | `modules/earnotch/` |
| **要实现的东西** | 采集源 / 抽帧 / 决策引擎 | `CatFaceModule.analyze()` | `EarNotchModule.analyze()` |
| **接口定义在哪** | `contracts/python/catvision_contracts/interfaces.py` | 同左（`CatFaceModule`） | 同左（`EarNotchModule`） |
| **没设备怎么开发** | `--source synthetic:10` | `--source file:<图片目录>` | `--source synthetic:20 --mock-all` |
| **单模块自测** | `pytest tests/test_camera.py -q` | `pytest tests/contract -q` | `pytest tests/contract -q` |
| **详细交接文档** | [`docs/部署.md`](docs/部署.md)、[`docs/camera-selection.md`](docs/camera-selection.md) | [`modules/catface/README.md`](modules/catface/README.md) | [`modules/earnotch/README.md`](modules/earnotch/README.md) |

---

## 3. 数据流与接口（**衔接就是这张表**）

```
摄像头 ──FramePacket──▶ 猫脸识别 ──CatFace[]──▶ 剪耳识别 ──EarNotch[]──▶ 决策引擎
                                                                          │
                                                        DetectionEvent ◀──┘
                                                              │
                                          ActionEvent（投粮 / TNR）──▶ 网页
```

| 契约 | 产出方 | 消费方 | 说明 |
|---|---|---|---|
| `FramePacket` | 摄像头与联调 | 猫脸、耳标 | 帧 + 元数据；**只给图片路径，不塞 base64** |
| `CatFace` | 猫脸识别 | 耳标、决策层 | bbox + 7 关键点 + 头部朝向 + 个体ID + track_id |
| `EarNotch` | 耳标识别 | 决策层 | 左右耳可见性 + 是否剪耳 + 绝育结论 |
| `DetectionEvent` | 决策层 | 前端 | **投票聚合后**对外，单帧结果不对外 |
| `ActionEvent` | 决策层 | 前端/执行器 | `FEED_DISPENSE` / `TNR_TASK_CREATED` / `ALERT` |

完整字段表见 [`docs/接口规范.md`](docs/接口规范.md)。

### 两条卡脖子的硬要求

- **猫脸模块必须输出 7 个关键点**（双眼、鼻、双耳根、双耳尖）。耳标模块裁耳部 ROI 完全依赖它，不交关键点两个模块合不上。
- **耳标模块必须遵守：`visible=false` 时 `notched` 只能是 `null`。** 看不见就说看不见，禁止猜。这条已经写进 JSON Schema，违反会直接校验失败。

### 三个模块怎么并行（重点）

因为「源等价」——`csi://` / `file:` / `synthetic:` 对下游完全一样，所以：

| 模块 | 前置依赖 | 怎么不等别人 |
|---|---|---|
| 摄像头与联调 | **无**，全 Mock 就能跑 | 先用 Mock 跑通全链路，再逐个换真实现 |
| 猫脸识别 | **无**。用 `file:` 回放或 `synthetic:` 就有输入 | 自己做 `--catface` 单独跑 |
| 耳标识别 | 猫脸的关键点。但用 `MockCatFaceModule` 就有一份合法关键点 | `--catface mocks:MockCatFaceModule --earnotch modules.earnotch:XXX` |

```bash
# 真实现换进来的那一刻，流水线一行都不用改
python -m pipeline.runner --source csi://0 \
    --catface modules.catface:M1CatFaceModule \
    --earnotch modules.earnotch:EarNotchModel
```

**接口联调前先各自自测**，用对方发布的 Mock。
联调当天的流程见 [`docs/联调checklist.md`](docs/联调checklist.md)。

---

## 4. 摄像头模块怎么用

```bash
python -m modules.camera --source csi://0 --fps 3 --frames 10          # Pi 上的 CSI 摄像头
python -m modules.camera --source file:/path/to/frames_dir --fps 3      # 图片目录回放
python -m modules.camera --source file:sample.mp4 --loop                # 视频文件回放
python -m modules.camera --source rtsp://user:pass@192.168.1.10/stream1
python -m modules.camera --source synthetic:10                          # 无硬件合成源
```

帧默认落在 `/dev/shm/catvision/frames/`（内存盘，不写 SD 卡），只保留最近 120 帧。

---

## 5. 常用命令

```bash
pytest -q                                      # 全部单测
pytest tests/contract -q                       # 只跑契约测试（改接口必跑）
ruff check .                                   # 静态检查

python -m pipeline.runner --source synthetic:30 --mock-all            # D0 验收
python -m pipeline.runner --source synthetic:30 --mock-all --mock-intact  # 演未绝育 → TNR
python -m pipeline.runner --source synthetic:30 --mock-all --mock-multi-cat-ratio 1.0  # 演多猫 → 不投粮
python -m pipeline.runner --source csi://0 --fps 2 --db catvision.db --jsonl events.jsonl

bash scripts/setup_pi.sh                       # 树莓派一键部署
bash scripts/install_pi_kiosk.sh               # 桌面图标：Chromium kiosk 全屏打开摄像头页面
python scripts/record_frames.py --source csi://0 --fps 2 --seconds 300 --out datasets/raw/2026-10-22
```

---

## 6. 决策规则（`pipeline/decide.py`，全是配置项）

| 动作 | 条件 |
|---|---|
| `FEED_DISPENSE` | `matched` + `similarity ≥ 0.80` + **画面只有一只猫** + 距上次投粮 > 6h + 10s 防抖 |
| `TNR_TASK_CREATED` | `neutered.value = false` + `confidence ≥ 0.80` + 10s 防抖 |
| `ALERT` | 预留 |

原型阶段默认 **dry-run**：事件照常入队，执行端看到 `payload.dry_run=true` 就不开电机。

---

## 7. 分支与提交

```
main        保护分支，只接受 dev 的 PR
dev         集成分支，各模块往这里合
feat/<模块>-<简述>    例：feat/earnotch-flip-augmentation
```

- 提交信息：`模块: 做了什么` → `earnotch: 加入水平翻转左右标签互换`
- PR 要求：CI 全绿 + 1 名非本模块 reviewer
- **改 `contracts/` 需另外两个模块 approve**，并更新 `contracts/CHANGELOG.md`（CI 会检查）

### 在树莓派上更新代码

`/home/lyx/catvision` 已是 git 仓库（配好只读 deploy key），直接拉：

```bash
cd /home/lyx/catvision && git pull
source /home/lyx/venvs/catvision/bin/activate && pytest -q
```

Pi 只能拉不能推 —— 代码一律从开发机 push。

---

## 8. 其他文档

| 文档 | 用途 | 相关角色 |
|---|---|---|
| [`docs/接口规范.md`](docs/接口规范.md) | 字段级说明 | 全部 |
| [`contracts/README.md`](contracts/README.md) | 契约细节与变更流程 | 全部 |
| [`docs/联调checklist.md`](docs/联调checklist.md) | 联调当天打勾表 | 全部 |
| [`docs/验收记录.md`](docs/验收记录.md) | 当前跑到哪一步 / 实测数据 | 全部 |
| [`modules/catface/README.md`](modules/catface/README.md) | 猫脸模块完整交接 | 猫脸识别 |
| [`modules/earnotch/README.md`](modules/earnotch/README.md) | 耳标模块完整交接 | 耳标识别 |
| [`docs/部署.md`](docs/部署.md) | Pi 环境 + 故障排查 | 摄像头与联调 |
| [`docs/pi-kiosk.md`](docs/pi-kiosk.md) | 桌面 kiosk：网页全屏 + 剪耳判定 + 排障 | 摄像头与联调 |
| [`docs/pi-kiosk-实测记录.md`](docs/pi-kiosk-实测记录.md) | 2026-10-31 实测记录与摄像头 CSI 超时 | 摄像头与联调 |
| [`docs/camera-selection.md`](docs/camera-selection.md) | 选型决策 | 摄像头与联调 |
