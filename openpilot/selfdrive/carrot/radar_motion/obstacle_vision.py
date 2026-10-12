#!/usr/bin/env python3
"""obstacle_vision.py —— 视觉小目标检测(行人/自行车/动物/锥桶等)。

用 YOLOv8n(COCO)在 roadCameraState 画面上检测小目标,
经内参投影换算成"虚拟障碍"(距离/横向偏移),供 avoidance 融合。

检测类别(COCO):person=0, bicycle=1, motorcycle=3, cat=15, dog=16, horse=17
动物/锥桶可扩展(锥桶需自定义模型,COCO 无;先用 person/bicycle/motorcycle/动物)。

关键点:
- 推理后端:优先 TensorRT GPU(同目录 .plan,如 yolov8n-oiv7.plan),无则回退 cv2.dnn CPU
- 只处理低频(每 3 帧)降低开销
- 检测框底部中点 = 目标着地点 → 用 pinhole 模型换算距离
- 只报告"足够近"的目标(< 40m),远处交给雷达/模型
"""
from __future__ import annotations

import os
import sys
import time
import ctypes
from dataclasses import dataclass

import numpy as np
import cv2

# TRT 注入:venv 无 tensorrt,系统 dist-packages 有(仅当 .plan 存在时才真正使用)
_trt = None
try:
  sys.path.insert(0, "/usr/lib/python3.12/dist-packages")
  import tensorrt as trt  # noqa: E402
  _trt = trt
except Exception:
  _trt = None

# 目标类别:优先用名字匹配(兼容 COCO 与 OIV7)
# COCO 索引(用于 yolov8n.onnx)
COCO_CLASSES = {
  0: "person", 1: "bicycle", 3: "motorcycle", 15: "cat", 16: "dog",
  17: "horse", 18: "cow", 19: "sheep",
}
# Open Images V7 601 类中要检测的(索引见 open-images-v7.yaml)
# 实际运行时按输出通道数判断:601 类 → 用 OIV7 索引
OIV7_CLASS_NAMES = ["Barrel", "Box", "Traffic sign", "Traffic light", "Bicycle", "Motorcycle",
                    "Cat", "Dog", "Horse", "Cow", "Sheep", "Person"]
INTEREST_CLASSES = COCO_CLASSES  # 默认 COCO(向下兼容)

# 相机内参(与 camera.py 的 J501 一致:1344x760, road f=2508)
CAM_W = 1344
CAM_H = 760
ROAD_FOCAL = 2508.0
CY = CAM_H / 2.0

MIN_DETECT_DREL_M = 2.0    # 最近检测距离
MAX_DETECT_DREL_M = 40.0   # 最远检测距离
CONF_THRESHOLD = 0.45      # 检测置信度
NMS_THRESHOLD = 0.45
DETECT_EVERY_N = 3         # 每 N 帧检测一次


@dataclass(frozen=True)
class VisionObstacle:
  cls: str
  d_rel: float    # 纵向距离 m
  y_rel: float    # 横向偏移 m(正=右)
  conf: float
  bbox: tuple     # (x1,y1,x2,y2) 原图坐标


class TrtYolo:
  """TensorRT GPU 推理封装:加载 .plan,ctypes 调 libcuda 搬运输入输出。

  输入/输出形状固定(与 trtexec 编译的 plan 一致):
    in:  (1,3,640,640) float32
    out: (1,605,8400) float32
  """

  def __init__(self, plan_path: str):
    if _trt is None:
      raise RuntimeError("tensorrt 不可用")
    # cudart runtime API(nvgpu libcuda 只有 cu* driver API,无 cudaMalloc)
    self._libcuda = ctypes.CDLL("/usr/local/cuda/targets/sbsa-linux/lib/libcudart.so.13")
    self._libcuda.cudaMalloc.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t]
    self._libcuda.cudaMemcpy.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    self._libcuda.cudaFree.argtypes = [ctypes.c_void_p]

    logger = _trt.Logger(_trt.Logger.WARNING)
    runtime = _trt.Runtime(logger)
    with open(plan_path, "rb") as f:
      self.engine = runtime.deserialize_cuda_engine(f.read())
    self.context = self.engine.create_execution_context()

    # I/O 尺寸
    in_name, out_name = "images", "output0"
    self._in_shape = tuple(self.engine.get_tensor_shape(in_name))
    self._out_shape = tuple(self.engine.get_tensor_shape(out_name))
    in_bytes = int(np.prod(self._in_shape)) * 4
    out_bytes = int(np.prod(self._out_shape)) * 4

    # 设备内存
    self._d_in = ctypes.c_void_p()
    self._d_out = ctypes.c_void_p()
    ret1 = self._libcuda.cudaMalloc(ctypes.byref(self._d_in), in_bytes)
    ret2 = self._libcuda.cudaMalloc(ctypes.byref(self._d_out), out_bytes)
    if ret1 != 0 or ret2 != 0:
      raise RuntimeError(f"cudaMalloc failed: {ret1} {ret2}")
    self._in_bytes = in_bytes
    self._out_bytes = out_bytes
    self._out = np.empty(self._out_shape, np.float32)

  def infer(self, blob: np.ndarray) -> np.ndarray:
    """blob: (1,3,640,640) float32 C-contiguous → (1,605,8400) float32。"""
    blob = np.ascontiguousarray(blob, dtype=np.float32)
    src_ptr = blob.ctypes.data_as(ctypes.c_void_p)
    # H2D (kind=1)
    self._libcuda.cudaMemcpy(self._d_in, src_ptr, self._in_bytes, 1)
    # 同步推理
    ok = self.context.execute_v2([int(self._d_in.value), int(self._d_out.value)])
    if not ok:
      raise RuntimeError("TRT execute_v2 failed")
    # D2H (kind=2)
    self._libcuda.cudaMemcpy(self._out.ctypes.data_as(ctypes.c_void_p), self._d_out, self._out_bytes, 2)
    return self._out

  def close(self):
    self._libcuda.cudaFree(self._d_in)
    self._libcuda.cudaFree(self._d_out)


class VisionObstacleDetector:
  """YOLOv8n 小目标检测 → 虚拟障碍。推理优先 TRT GPU,回退 cv2.dnn CPU。"""

  def __init__(self, model_path: str = "/home/nvidia/yolov8n.onnx"):
    self.model_path = model_path
    self.net = None
    self._trt = None
    # TRT plan 优先(同目录同名前缀 .plan)
    plan_path = os.path.splitext(model_path)[0] + ".plan"
    if os.path.exists(plan_path):
      try:
        self._trt = TrtYolo(plan_path)
      except Exception as e:
        print(f"[obstacle_vision] TRT init failed, fallback cv2.dnn: {e}")
        self._trt = None
    if self._trt is None:
      self.net = cv2.dnn.readNetFromONNX(model_path)
    self._frame_count = 0
    self._oiv7 = "oiv7" in model_path or "oiv" in model_path
    # 建立 名字→索引 映射(检测时用名字判断是否关注)
    self._name_to_idx = self._build_name_map()

  def _pixel_to_meter(self, bbox_bottom_center_x: float, bbox_bottom_y: float) -> tuple[float, float]:
    """检测框底部中点(着地点)→ (d_rel, y_rel)。
    pinhole: d_rel = f * h / (y - cy)?? 这里用简化:假设相机高 1.3m, pitch≈0
    实际:y_rel = (x - cx) * d_rel / f; d_rel 由目标高度估算。
    简化:用目标框高度反推距离(目标典型高度 person 1.7m)。
    """
    return 0.0, 0.0  # 由调用方按类别高度计算

  def detect(self, y_plane: np.ndarray) -> list[VisionObstacle]:
    """输入 road Y 平面(1344x760 uint8),返回障碍列表。"""
    self._frame_count += 1
    if self._frame_count % DETECT_EVERY_N != 0:
      return []

    # YOLO 输入 640x640,letterbox(保持宽高比)
    h_in, w_in = y_plane.shape[:2]
    scale = 640 / max(w_in, h_in)
    nw, nh = int(w_in * scale), int(h_in * scale)
    # 单通道 Y → 3 通道(blobFromImage 单通道会导致检测为空)
    if y_plane.ndim == 2:
      img3 = cv2.cvtColor(y_plane, cv2.COLOR_GRAY2BGR)
    else:
      img3 = y_plane
    resized = cv2.resize(img3, (nw, nh))
    canvas = np.full((640, 640, 3), 114, np.uint8)
    dx, dy = (640 - nw) // 2, (640 - nh) // 2
    canvas[dy:dy + nh, dx:dx + nw] = resized
    blob = cv2.dnn.blobFromImage(canvas, 1 / 255.0, (640, 640), swapRB=True, crop=False)
    t0 = time.time()
    try:
      if self._trt is not None:
        outs = self._trt.infer(blob)
      else:
        self.net.setInput(blob)
        outs = self.net.forward()
    except Exception:
      return []
    infer_ms = (time.time() - t0) * 1000

    # YOLOv8 输出: [1, 84, 8400] → 转置 [8400, 84]
    outs = outs[0].T
    boxes = []
    scores = []
    classes = []
    for row in outs:
      classes_scores = row[4:]
      cls_id = int(np.argmax(classes_scores))
      conf = float(classes_scores[cls_id])
      if conf < CONF_THRESHOLD:
        continue
      # OIV7:按映射后名字判定;COCO:按索引
      if self._oiv7:
        if cls_id not in self._name_to_idx:
          continue
      else:
        if cls_id not in INTEREST_CLASSES:
          continue
      cx, cy_, w, h = row[:4]
      # letterbox 逆映射回原图坐标
      x1n = (cx - w / 2 - dx) / scale
      y1n = (cy_ - h / 2 - dy) / scale
      x2n = (cx + w / 2 - dx) / scale
      y2n = (cy_ + h / 2 - dy) / scale
      boxes.append([x1n, y1n, x2n, y2n])
      scores.append(conf)
      classes.append(cls_id)

    if not boxes:
      return []
    idxs = cv2.dnn.NMSBoxes(boxes, scores, CONF_THRESHOLD, NMS_THRESHOLD)
    result = []
    for i in idxs:
      i = int(i)
      x1, y1, x2, y2 = boxes[i]
      conf = scores[i]
      if self._oiv7:
        cls = self._name_to_idx.get(classes[i], "unknown")
      else:
        cls = INTEREST_CLASSES[classes[i]]
      # 目标典型高度(米)按类别估算,用框高反推距离
      obj_h = {"person": 1.7, "bicycle": 1.1, "motorcycle": 1.3,
               "cat": 0.3, "dog": 0.4, "horse": 1.5, "cow": 1.4, "sheep": 0.8}.get(cls, 1.0)
      box_h = max(y2 - y1, 10.0)
      d_rel = ROAD_FOCAL * obj_h / box_h  # f * 高度 / 像素高
      if not (MIN_DETECT_DREL_M <= d_rel <= MAX_DETECT_DREL_M):
        continue
      # 横向:底部中点相对图像中心
      bottom_cx = (x1 + x2) / 2
      y_rel = (bottom_cx - CAM_W / 2) * d_rel / ROAD_FOCAL
      result.append(VisionObstacle(cls, d_rel, y_rel, conf, (x1, y1, x2, y2)))
    return result

  def _build_name_map(self) -> dict[int, str]:
    """OIV7 601 类索引→名字映射(仅关注类别;从 .yaml 读取或硬编码关键索引)。
    索引按 open-images-v7.yaml:Barrel=25, Box=62, Traffic sign=549,
    Traffic light=548, Person 需确认(非 COCO 0)。这里用名字映射表。
    """
    # OIV7 类名索引(open-images-v7.yaml 确认)
    # 注意:OIV7 将[人]细分为 Man/Woman/Boy/Girl/Person → 全部归一 "person"
    OIV7_IDX = {
      25: "Barrel",       # 桶/路障
      62: "Box",          # 箱子
      42: "Bicycle",
      342: "Motorcycle",
      96: "Cat",
      160: "Dog",
      255: "Horse",
      219: "Goat",
      452: "Sheep",
      99: "Cattle",       # 牛
      152: "Deer",        # 鹿(野生动物)
      322: "person",      # Man
      594: "person",      # Woman
      63: "person",       # Boy
      216: "person",      # Girl
      381: "person",      # Person
      548: "Traffic light",
      549: "Traffic sign",
    }
    return OIV7_IDX
