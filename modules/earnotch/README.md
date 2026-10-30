# 耳标识别模块

> 已提供可运行基线：`modules.earnotch:EarNotchModel`（ONNX 整图分类 +
> 左右耳启发式），部署与限制见 [docs/earnotch.md](../../docs/earnotch.md)。
> 下面仍是接口/协作规范。
>
> 输入是 `FramePacket + list[CatFace]`，输出 `list[EarNotch]`。
> **不要自己检测猫脸**——那是猫脸模块的活，你只管耳朵。

## 1. 你要实现的就一个方法

```python
from catvision_contracts import CatFace, EarNotch, FramePacket

class EarNotchModel:
    def analyze(self, packet: FramePacket, faces: list[CatFace]) -> list[EarNotch]:
        ...
```

返回长度必须和 `faces` 一一对应，用 `track_id` 对齐。顺序也建议保持一致。

## 2. 耳朵 ROI 怎么拿

猫脸模块会给你这 4 个点（外加 3 个脸部点）：

```
left_ear_base  / left_ear_tip
right_ear_base / right_ear_tip
```

裁 ROI 的正确做法是**绕两点向外扩边**，不要把两点当成矩形的对角线：

```python
def roi(face, which):
    lm = face.landmarks
    base = lm.left_ear_base if which == "left" else lm.right_ear_base
    tip = lm.left_ear_tip if which == "left" else lm.right_ear_tip
    if tip is None:
        return None                      # 看不见 → 见下面第 3 条
    fx, fy, fw, fh = face.bbox
    x0, x1 = sorted((base[0], tip[0]))
    y0, y1 = sorted((base[1], tip[1]))
    x0, x1 = x0 - 0.18 * fw, x1 + 0.18 * fw   # 横向各扩 0.18 脸宽
    y0, y1 = y0 - 0.12 * fh, y1 + 0.10 * fh   # 上扩 0.12、下扩 0.10 脸高
    if x1 - x0 < 0.30 * fw:                   # 保底宽度，别退化成窄条
        cx = (x0 + x1) / 2
        x0, x1 = cx - 0.15 * fw, cx + 0.15 * fw
    return [x0, y0, x1 - x0, y1 - y0]
```

**别用「两点当对角线」的老写法**：耳根和耳尖的连线只有约 0.08 脸宽，得到的是落在额头上的
窄条——而剪耳缺口正好在框外。实测 41/41 个样本都落在窄条之外。现行实现在
`EarNotchModel._ear_roi()` 里，扩边系数是几何估计，不是学出来的；换成真关键点模型后会自动变准。

`head_pose` 也不要浪费：`|yaw| > 45°` 时远侧耳朵基本不可信，直接判 `visible=false` 比硬猜强。

## 3. 三条硬规则（违反会被 schema 直接拒绝）

### (1) `visible=false` ⇒ `notched` 和 `score` 必须是 `null`

看不见就说看不见，禁止猜。这条同时写在 pydantic 的 `model_validator` 和
JSON Schema 的 `allOf/if-then` 里，两边都会拦你。

```python
EarSide(visible=False, notched=True, score=0.9, bbox=None)   # ✗ 直接抛 ValidationError
EarSide(visible=False, notched=None, score=None, bbox=None)  # ✓
```

为什么这么严：**猜错方向的后果是不对称的**。把已绝育的猫判成未绝育，志愿者白跑一趟；
把未绝育判成已绝育，这只猫永远不会被安排 TNR。前者麻烦，后者是事故。

### (2) 左右是猫的左右，不是画面的左右

和猫脸模块那边同一套约定。水平翻转做数据增强时**必须同步交换左右标签**，
这是这个模块最容易出的静默 bug。写个单测锁死。

### (3) 不要自己下「已绝育」的最终结论之外的判断

`neutered.value` 用 `EarNotch.from_ears(...)` 生成，规则（`any_ear_notched` 等）是**配置项**，
不要硬编码在模型里。默认规则「任一只耳剪过即认为已绝育」是 TNR 的通行做法。

```python
EarNotch.from_ears(
    packet_id=packet.packet_id,
    track_id=face.track_id,
    left=left_side, right=right_side,
    rule="any_ear_notched",
    model_version="earnotch-v0.1",   # 这个字段联调时必须能追溯
)
```

## 4. 怎么在没有摄像头的情况下开发

你自己不需要摄像头，也不需要猫脸模块——用它的 Mock：

```bash
python -m pipeline.runner --source synthetic:20 --mock-all          # 全 Mock 跑通
python -m pipeline.runner --source file:datasets/raw/mine/frames \
    --catface mocks:MockCatFaceModule --earnotch modules.earnotch:EarNotchModel
```

单独调你的模块：

```python
from modules.camera.capture import CameraStream
from mocks import MockCatFaceModule
from modules.earnotch import EarNotchModel

with CameraStream("synthetic:3", fps=1) as cam:
    for packet in cam.packets(max_frames=3):
        faces = MockCatFaceModule().analyze(packet)
        for ear in EarNotchModel().analyze(packet, faces):
            print(ear.to_json())
```

## 5. 你的提交里要有测试

- [ ] **水平翻转 → 左右标签交换**（必须有，评审重点看这个）
- [ ] 耳尖 `None` → `visible=false`、`notched=null`，不抛异常
- [ ] 两只耳都不可见 → `neutered.value` 为 `null`（不下结论）
- [ ] 左右判定矛盾（左剪右不剪）时，按 `rule` 得出正确结论
- [ ] 输出能过 `validate("ear_notch", ear)`

## 6. 采数据注意

- 剪耳标记在**耳廓边缘的缺口**，标的是「剪了/没剪」二分类，不是检测缺口框。
- 左右耳要**分别**标，别偷懒合成一个「是否绝育」标签——左右信息后面做 TNR 认猫要用。
- 难例一定要收：毛挡住的、逆光的、侧脸的、离得远的。这些占实际场景的 80%。
- 参考 `tests/fixtures/README.md` 的素材约定；大素材不进 Git。
