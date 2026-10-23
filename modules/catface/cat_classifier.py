import cv2
import numpy as np
import onnxruntime as ort

class CatClassifier:
    def __init__(self, model_path="models/cat_vs_notcat.onnx"):
        # 加载咱们生成的 ONNX 模型
        self.session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
        self.input_name = self.session.get_inputs()[0].name
        # 训练时的归一化参数
        self.mean = np.array([0.485, 0.456, 0.406]).reshape(1, 1, 3)
        self.std = np.array([0.229, 0.224, 0.225]).reshape(1, 1, 3)

    def predict(self, frame_bgr):
        # 1. 预处理：把图片变成模型需要的格式
        img = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (224, 224))
        img = img.astype(np.float32) / 255.0
        img = (img - self.mean) / self.std
        img = np.transpose(img, (2, 0, 1))
        img = np.expand_dims(img, axis=0)
        
        # 2. 推理：交给 AI 模型去算
        outputs = self.session.run(None, {self.input_name: img})
        logits = outputs[0][0]
        probs = np.exp(logits) / np.sum(np.exp(logits))
        
        # 3. 返回结果：是不是猫，置信度是多少
        is_cat = bool(probs[0] > 0.5)
        confidence = float(probs[0])
        return is_cat, confidence