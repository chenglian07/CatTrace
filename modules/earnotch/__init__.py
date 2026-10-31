"""耳标识别：ONNX 推理 + 左右耳定位（可运行的轻量基线）。

模型来源
--------
``train/train_earnotch.py`` 训练的二分类器，经
``train/export_earnotch_onnx.py`` 导出为 ONNX。树莓派只需要 onnxruntime，
不需要安装 torch。

当前模型是**整图级**分类器：它回答"这张图里的猫有没有剪耳"，而不是"左耳还是右耳"。
因此本模块做两件事：

1. 对整帧（或单猫画面）跑分类器，得到 ``P(notched)``；
2. 需要左右耳时，分别裁左右耳周边再分类，比较哪边更像剪耳。
   差异不够大就返回"无法判断"，不硬猜左右。

这个左右判定是启发式，不是训练出来的双头模型；``model_version`` 里会标注
``sidecrop``。等 ``ear_side`` 标注补齐后，应替换成左右耳双头模型。

契约硬规则：看不见/拿不准时 ``visible=false`` 且 ``notched=null``。

两道尺寸门槛，各自解决一个问题：
- ``min_face_px``（默认 96）：猫脸太小就整条返回 unknown，因为整图模型此时
  看到的是被放大到 288 的整帧，耳朵只剩几像素；
- ``min_ear_px``（默认 64）：耳部 ROI 太小时只放弃"左右耳"这一层结论，
  图像级"有没有剪耳"照给，model_version 带 ``+image``。
"""

from __future__ import annotations

import json
import platform
from pathlib import Path

import numpy as np
from catvision_contracts import CatFace, EarNotch, EarSide, FramePacket, NeuteredVerdict
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[2]
MODEL_CANDIDATES = (
    ROOT / "models" / "earnotch_convnext_tiny288_v0.onnx",
    ROOT / "models" / "earnotch_convnext288_v0.onnx",
    ROOT / "models" / "earnotch_resnet18224_v0.onnx",
    ROOT / "models" / "earnotch_resnet18_v0.onnx",
)
DEFAULT_BAND = 0.12


class EarNotchModel:
    """实现 ``EarNotchModule`` 协议：输入帧 + 猫脸，输出逐猫耳标结果。"""

    def __init__(
        self,
        *,
        model_path: str | Path | None = None,
        threshold: float | None = None,
        band: float | None = None,
        side_mode: str = "crop",
        tta: bool = False,
        threads: int = 2,
        min_ear_px: int = 64,
        min_face_px: int = 96,
    ) -> None:
        try:
            import onnxruntime as ort
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "耳标推理需要 onnxruntime：pip install onnxruntime\n"
                "并先运行 python train/export_earnotch_onnx.py 导出 ONNX。"
            ) from exc

        path = Path(model_path) if model_path else self._default_model()
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file():
            raise FileNotFoundError(
                f"找不到 ONNX 权重：{path}\n"
                "先在训练机执行：python train/export_earnotch_onnx.py\n"
                "再把 models/earnotch_*.onnx 和同名 .json 拷到树莓派。"
            )

        meta_path = Path(str(path) + ".json")
        meta: dict = {}
        if meta_path.is_file():
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)

        self.model_path = path
        self.input_size = int(meta.get("input_size", 288))
        self.mean = np.asarray(meta.get("mean", [0.485, 0.456, 0.406]), dtype=np.float32)
        self.std = np.asarray(meta.get("std", [0.229, 0.224, 0.225]), dtype=np.float32)
        self.threshold = float(threshold if threshold is not None else meta.get("threshold", 0.58))
        self.band = float(band if band is not None else meta.get("band", DEFAULT_BAND))
        self.tta = bool(tta)
        self.side_mode = side_mode
        # 耳部 ROI 最小边（像素）。低于这个尺寸时左右耳的概率差是噪声，
        # 只影响"能不能判左右"，不影响图像级结论。64 是经验值。
        self.min_ear_px = int(min_ear_px)
        # 猫脸最小边（像素）。低于这个尺寸连图像级结论都不给：整图模型看到的是
        # 放大后的整帧，脸只占几十像素时耳朵已经没有可判的细节。与推理脚本的 96 对齐。
        self.min_face_px = int(min_face_px)

        so = ort.SessionOptions()
        so.intra_op_num_threads = max(1, int(threads))
        so.inter_op_num_threads = 1
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            str(path), sess_options=so, providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name
        self.model_version = f"{path.stem}-onnx"
        if self.side_mode == "occlusion":
            self.model_version += "+occ"
        elif self.side_mode == "crop":
            self.model_version += "+sidecrop"

    @staticmethod
    def _default_model() -> Path:
        # Pi 4 是 4 核 A72：convnext 单次 288 推理约 3.2s，实时性不够；
        # ARM 上默认用 resnet18（约 0.65s），开发机保留精度更高的 convnext。
        if platform.machine().lower() in ("aarch64", "arm64", "armv7l"):
            for p in (ROOT / "models" / "earnotch_resnet18224_v0.onnx",
                      ROOT / "models" / "earnotch_resnet18_v0.onnx"):
                if p.is_file():
                    return p
        for p in MODEL_CANDIDATES:
            if p.is_file():
                return p
        return MODEL_CANDIDATES[0]

    # ------------------------------------------------------------------ API
    def analyze(self, packet: FramePacket, faces: list[CatFace]) -> list[EarNotch]:
        if not faces:
            return []
        with Image.open(packet.image_path) as im:
            image = ImageOps.exif_transpose(im).convert("RGB")
        return [self._one(packet, face, image) for face in faces]

    # -------------------------------------------------------------- internal
    def _one(self, packet: FramePacket, face: CatFace, image: Image.Image) -> EarNotch:
        if not face.quality.is_usable or not self._has_ear_tips(face):
            return self._unknown(packet, face, "看不见/画质不足")

        face_px = min(float(face.bbox[2]), float(face.bbox[3]))
        if face_px < self.min_face_px:
            # 整图分类器吃的是整帧：脸只有几十像素时，288 的输入里耳朵只剩几像素，
            # 这时候给出的高置信度是假的。门槛与 predict_earnotch.py 的 96 一致。
            return self._unknown(packet, face, f"猫脸太小（{face_px:.0f}px < {self.min_face_px}）")

        try:
            prob = self._predict(image)
        except Exception as exc:  # 单帧失败不应该拖垮整条流水线
            return self._unknown(packet, face, f"推理失败: {exc}")

        if prob < self.threshold - self.band:
            return self._both_intact(packet, face, image, prob)
        if prob > self.threshold + self.band:
            return self._notched(packet, face, image, prob)
        return self._unknown(packet, face, f"概率 {prob:.3f} 落在不确定带")

    def _notched(self, packet: FramePacket, face: CatFace, image: Image.Image, prob: float) -> EarNotch:
        side = None
        if self.side_mode in ("crop", "occlusion"):
            side = self._estimate_side(image, face, prob)

        if side is None:
            # 知道"有剪耳"，但不知道哪只耳：左右耳保持 null，绝育结论仍给 true。
            # 这是图像级结论，model_version 里带 +image，不能当作左右耳标注。
            left = self._side(face, "left", visible=True, notched=None, score=prob)
            right = self._side(face, "right", visible=True, notched=None, score=prob)
            return EarNotch(
                packet_id=packet.packet_id,
                track_id=face.track_id,
                left=left,
                right=right,
                neutered=NeuteredVerdict(
                    value=True,
                    confidence=round(float(prob), 4),
                    rule="any_ear_notched",
                ),
                model_version=self.model_version + "+image",
            )
        else:
            left = self._side(
                face, "left", visible=True, notched=(side == "left"),
                score=prob if side == "left" else 1.0 - prob,
            )
            right = self._side(
                face, "right", visible=True, notched=(side == "right"),
                score=prob if side == "right" else 1.0 - prob,
            )

        return EarNotch.from_ears(
            packet_id=packet.packet_id,
            track_id=face.track_id,
            left=left,
            right=right,
            rule="any_ear_notched",
            model_version=self.model_version,
        )

    def _both_intact(self, packet: FramePacket, face: CatFace, image: Image.Image, prob: float) -> EarNotch:
        score = round(1.0 - prob, 4)
        left = self._side(face, "left", visible=True, notched=False, score=score)
        right = self._side(face, "right", visible=True, notched=False, score=score)
        return EarNotch.from_ears(
            packet_id=packet.packet_id,
            track_id=face.track_id,
            left=left,
            right=right,
            rule="any_ear_notched",
            model_version=self.model_version,
        )

    def _unknown(self, packet: FramePacket, face: CatFace, _reason: str = "") -> EarNotch:
        left = EarSide(visible=False, notched=None, score=None, bbox=None)
        right = EarSide(visible=False, notched=None, score=None, bbox=None)
        return EarNotch.from_ears(
            packet_id=packet.packet_id,
            track_id=face.track_id,
            left=left,
            right=right,
            rule="any_ear_notched",
            model_version=self.model_version,
        )

    def _side(
        self,
        face: CatFace,
        which: str,
        *,
        visible: bool,
        notched: bool | None,
        score: float | None = None,
    ) -> EarSide:
        if not visible:
            return EarSide(visible=False, notched=None, score=None, bbox=None)
        return EarSide(
            visible=True,
            notched=notched,
            score=None if score is None else round(float(score), 4),
            bbox=self._ear_roi(face, which),
        )

    @staticmethod
    def _has_ear_tips(face: CatFace) -> bool:
        return face.landmarks.left_ear_tip is not None and face.landmarks.right_ear_tip is not None

    def _estimate_side(self, image: Image.Image, face: CatFace, prob: float) -> str | None:
        """估计是哪只耳剪了；证据不足就返回 None。"""
        if self.side_mode == "occlusion":
            # 旧方案：遮住一只耳看整图概率掉多少。保留用于对比。
            base = self._context_image(image, face)
            p_l = self._predict(self._mask_ear(base, face, "left"))
            p_r = self._predict(self._mask_ear(base, face, "right"))
            drop_l = prob - p_l
            drop_r = prob - p_r
            if max(drop_l, drop_r) < 0.015 or abs(drop_l - drop_r) < 0.015:
                return None
            return "left" if drop_l > drop_r else "right"

        # 新方案：分别裁左右耳及其周边，谁更像"剪耳"就投谁。
        roi_l = self._ear_roi(face, "left")
        roi_r = self._ear_roi(face, "right")
        if min(min(roi_l[2], roi_l[3]), min(roi_r[2], roi_r[3])) < self.min_ear_px:
            # 耳部只有几十像素时，两侧概率差是噪声，不能拿来判左右
            return None
        p_l = self._predict_ear(image, face, "left")
        p_r = self._predict_ear(image, face, "right")
        if p_l is None or p_r is None:
            return None
        if max(p_l, p_r) < self.threshold - self.band:
            return None
        if abs(p_l - p_r) < 0.08:
            return None
        return "left" if p_l > p_r else "right"

    def _predict_ear(self, image: Image.Image, face: CatFace, which: str) -> float | None:
        x, y, w, h = self._ear_roi(face, which)
        pad = 0.8 * max(w, h)
        box = (max(0, int(x - pad)), max(0, int(y - pad)),
               min(image.width, int(x + w + pad)), min(image.height, int(y + h + pad)))
        if box[2] - box[0] < 24 or box[3] - box[1] < 24:
            return None
        return self._predict(image.crop(box))

    def _context_image(self, image: Image.Image, face: CatFace) -> Image.Image:
        """把画面裁到猫脸附近，减少多猫/背景干扰；边界外补边。"""
        x, y, w, h = face.bbox
        side = int(max(w, h) * 2.2)
        cx = int(x + w / 2)
        cy = int(y + h / 2 - 0.10 * h)
        left = cx - side // 2
        top = cy - side // 2
        return image.crop((left, top, left + side, top + side))

    def _mask_ear(self, image: Image.Image, face: CatFace, which: str) -> Image.Image:
        out = image.copy()
        draw = ImageDraw.Draw(out)
        # 把原图坐标里的耳部 ROI 映射到 context crop 坐标
        x, y, w, h = face.bbox
        side = int(max(w, h) * 2.2)
        cx = int(x + w / 2)
        cy = int(y + h / 2 - 0.10 * h)
        left = cx - side // 2
        top = cy - side // 2
        bx, by, bw, bh = self._ear_roi(face, which)
        x0 = int(bx - left - 0.15 * bw)
        y0 = int(by - top - 0.25 * bh)
        x1 = int(bx - left + 1.15 * bw)
        y1 = int(by - top + 1.25 * bh)
        # 用局部平均色填充，避免纯黑/纯白制造新的强特征
        patch = out.crop((max(0, x0), max(0, y0), max(1, x1), max(1, y1)))
        arr = np.asarray(patch)
        fill = tuple(int(v) for v in arr.reshape(-1, arr.shape[-1]).mean(axis=0)) if arr.size else (127, 127, 127)
        draw.rectangle([x0, y0, x1, y1], fill=fill)
        return out

    @staticmethod
    def _ear_roi(face: CatFace, which: str) -> list[float]:
        """由耳根/耳尖两个锚点生成耳部 ROI。

        旧实现把这两个点当成矩形的对角，得到一条宽约 0.08 脸宽的窄条；
        而 Haar 脸框本来只包到耳根、耳尖又是按比例外推到框上方 8% 的，
        窄条实际落在额头和头顶上——剪耳缺口正好在框外（实测 41/41 样本如此）。

        现在改成绕两点扩边：横向各 0.18 脸宽、上方 0.12 脸高、下方 0.10 脸高，
        并保证横向不小于 0.30 脸宽，让整只耳（含耳尖缺口）都进 ROI。
        扩边系数是几何估计，不是从数据里学出来的；换真关键点模型时这层自动变准。
        """
        lm = face.landmarks
        base = lm.left_ear_base if which == "left" else lm.right_ear_base
        tip = lm.left_ear_tip if which == "left" else lm.right_ear_tip
        fx, fy, fw, fh = (float(v) for v in face.bbox)

        if tip is None or base is None:
            # 没有耳尖时按脸框比例给一个固定位置，不能退化成 1x1 的框
            sign = 1.0 if which == "left" else -1.0
            cx = fx + (0.5 + sign * 0.28) * fw
            base = [cx, fy + 0.10 * fh]
            tip = [cx + sign * 0.06 * fw, fy - 0.08 * fh]

        x0, x1 = sorted((float(base[0]), float(tip[0])))
        y0, y1 = sorted((float(base[1]), float(tip[1])))
        x0, x1 = x0 - 0.18 * fw, x1 + 0.18 * fw
        y0, y1 = y0 - 0.12 * fh, y1 + 0.10 * fh

        min_w = 0.30 * fw
        if x1 - x0 < min_w:
            cx = (x0 + x1) / 2.0
            x0, x1 = cx - min_w / 2.0, cx + min_w / 2.0

        return [round(x0, 2), round(y0, 2), round(x1 - x0, 2), round(y1 - y0, 2)]

    # -------------------------------------------------------------- inference
    def _predict(self, image: Image.Image) -> float:
        x = self._preprocess(image)
        logits = self.session.run([self.output_name], {self.input_name: x})[0]
        prob = self._softmax(logits)[0, 1]
        if self.tta:
            logits2 = self.session.run([self.output_name], {self.input_name: x[:, :, :, ::-1]})[0]
            prob = (prob + self._softmax(logits2)[0, 1]) / 2.0
        return float(prob)

    def _preprocess(self, image: Image.Image) -> np.ndarray:
        size = self.input_size
        im = image.convert("RGB")
        w, h = im.size
        scale = (size * 1.14) / max(min(w, h), 1)
        im = im.resize((max(size, int(round(w * scale))), max(size, int(round(h * scale)))),
                       Image.Resampling.BILINEAR)
        left = max(0, (im.width - size) // 2)
        top = max(0, (im.height - size) // 2)
        im = im.crop((left, top, left + size, top + size))
        arr = np.asarray(im, dtype=np.float32) / 255.0
        arr = (arr - self.mean) / self.std
        return np.transpose(arr, (2, 0, 1))[None, ...]

    @staticmethod
    def _softmax(logits: np.ndarray) -> np.ndarray:
        z = logits - logits.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)


# 更明确的名字，pipeline 里用哪个都可以
EarNotchONNX = EarNotchModel
