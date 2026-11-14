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
import ctypes
from dataclasses import dataclass

import numpy as np

# cv2 缺失降级:模块仍可加载, VisionObstacleDetector 变为空转(返回空列表)。
# c3 的 carrot_serv 跑在 .venv 里(顶层 import 本模块), 若 venv 无 opencv,
# 硬 import 会让整个 carrot_serv 崩溃。置 None 后 __init__/detect 短路。
try:
  import cv2
except Exception:
  cv2 = None  # type: ignore[assignment]

# TRT 注入:venv 无 tensorrt,系统 dist-packages 有(仅当 .plan 存在时才真正使用)
_trt = None
try:
  sys.path.insert(0, "/usr/lib/python3.12/dist-packages")
  import tensorrt as trt
  _trt = trt
except Exception:
  _trt = None

# 目标类别:优先用名字匹配(兼容 COCO 与 OIV7)
# COCO 索引(用于 yolov8n.onnx)
# COCO 80 类全索引中关注的部分。换 yolo11m(COCO) 后**必须包含车辆类**,
# 否则 cls_id not in INTEREST_CLASSES 会把 car/bus/truck 全部丢弃。
COCO_CLASSES = {
  0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck",
  9: "traffic light", 11: "stop sign",
  15: "cat", 16: "dog", 17: "horse", 18: "cow", 19: "sheep",
}
# Open Images V7 601 类中要检测的(索引见 open-images-v7.yaml)
# 实际运行时按输出通道数判断:601 类 → 用 OIV7 索引
OIV7_CLASS_NAMES = ["Barrel", "Box", "Traffic sign", "Traffic light", "Bicycle", "Motorcycle",
                    "Cat", "Dog", "Horse", "Cow", "Sheep", "Person"]
INTEREST_CLASSES = COCO_CLASSES  # 默认 COCO(向下兼容)

# 自定义小模型:交通信号灯 6 类(traffic_light/green/left/red/right/yellow)。
# 与障碍物类别互斥, 必须分开两个 detector 实例: 混用会把 green_light(1)
# 当 bicycle(1) 换算成 1.1m 高的"障碍物"从而误刹车。
SIGNAL_CLASSES = {0: "traffic_light", 1: "green_light", 2: "left_light",
                  3: "red_light", 4: "right_light", 5: "yellow_light"}
# 信号灯类别 -> carrot_serv.traffic_light() 的颜色语义
SIGNAL_COLOR = {"red_light": "Red Light", "yellow_light": "Yellow Light",
                "green_light": "Green Light", "left_light": "Left turn",
                "right_light": "Right turn"}
SIGNAL_CONF_THRESHOLD = 0.60   # 信号灯误检会直接导致红灯误停车, 阈值取高
# 灯存在性门限(与颜色门限分开): 泛类 traffic_light 实测最高 0.706, 而颜色类
# 全在 0.6 以下(red 0.182 / left 0.037 / right 0.000)。存在性只回答
# "画面里有没有信号灯", 用较低门限; 该结果**不参与任何车辆动作**。
LIGHT_PRESENCE_CONF = 0.45

# OIV7 车辆类(实测模型能稳定检出: dl.mp4 上 Car 命中 553 次)。
# 车辆不进"静止障碍"链路(那会把行驶中的车当停止目标误减速), 只用于
# 相邻车道占用 -> 给换道安全性提供左/右侧 blocked 判据。
VEHICLE_CLASSES = {90: "Car", 558: "Truck", 73: "Bus"}
VEHICLE_NAMES = frozenset(v.lower() for v in VEHICLE_CLASSES.values())

# 相机内参: 以本机实测标定为准(1920x1080, road fx=2637, intrinsic_calibd v4.1)。
# 原值 1344x760/f=2508 是 J501 模组的; 按帧宽缩放会得到 3583, 距离被放大 1.36 倍。
CAM_W = 1920
CAM_H = 1080
ROAD_FOCAL = 2637.0
CY = CAM_H / 2.0

_CALIB_CACHE = {"fx": ROAD_FOCAL, "height": 1.35, "checked": 0.0}


def road_calib():
  """(fx, mount_height) from the single persisted calibration store (spec §10.5).

  Single source of truth: the CameraCalibSet persisted by calibrationd.
  Cached for 5 s (read is cheap but not free). Falls back to the measured
  constants above only while no calibrated value exists.
  """
  import time
  now = time.monotonic()
  if now - _CALIB_CACHE["checked"] > 5.0:
    _CALIB_CACHE["checked"] = now
    try:
      from openpilot.common.params import Params
      from openpilot.cereal import log
      from openpilot.common.transformations.camera_calib import Cam, from_live_calibration
      # calib-legacy-allow: single-store read (the ONLY sanctioned runtime
      # pattern outside calibrationd: Params -> from_live_calibration)
      data = Params().get("CalibrationParams")  # calib-legacy-allow: single-store read via from_live_calibration (the only sanctioned runtime pattern outside calibrationd)
      if data:
        with log.Event.from_bytes(data) as ev:
          calib_set = from_live_calibration(ev, device_type="pc", sensor="imx390")
        road = calib_set.cams.get(Cam.ROAD)
        if road is not None and road.fx > 0:
          _CALIB_CACHE["fx"] = float(road.fx)
        if road is not None and road.mount_height and road.mount_height > 0.5:
          _CALIB_CACHE["height"] = float(road.mount_height)
    except Exception:
      pass
  return _CALIB_CACHE["fx"], _CALIB_CACHE["height"]

MIN_DETECT_DREL_M = 2.0    # 最近检测距离
MAX_DETECT_DREL_M = 80.0   # 最远检测距离(仅影响UI可见范围;
                           # 避让仍由 avoidance.MAX_TRIGGER_DREL_M=40 限制, 安全边界不变)
CONF_THRESHOLD = 0.30      # 检测置信度(城市路段放低, 多检目标; UI 上限 20)
INPUT_SIZE = 640           # 默认 letterbox 边长(320 模型按文件名自动降)
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

  def __init__(self, model_path: str = ""):
    if cv2 is None:  # type: ignore[truthy-function]
      # opencv 不可用:空转检测器(不抛错, 由调用方 try/except 包裹)
      self.model_path = model_path
      self.net = None
      self._trt = None
      self._frame_count = 0
      self._oiv7 = False
      self._name_to_idx = {}
      self._is_signal_model = False
      return
    if not model_path:
      # 默认用仓库内 models 目录(与 .plan 同目录),避免硬编码 /home/nvidia
      model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "yolo11m_1280.onnx")
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
    # 信号灯专用模型: 文件名含 traffic_light 或 tl_ 前缀
    _base = os.path.basename(model_path).lower()
    self._is_signal_model = ('traffic_light' in _base) or _base.startswith('tl_')
    # 320 模型 CPU 推理约 53ms(640 要 180ms), 文件名含 320 即用小输入
    # 输入边长按文件名: 320 / 1280 / 默认 640。1280 模型必须让 _input_size=1280,
    # 否则 letterbox 到 640 再送进 1280 引擎 -> TRT 形状不匹配。
    if '1280' in _base:
      self._input_size = 1280
    elif '320' in _base:
      self._input_size = 320
    else:
      self._input_size = INPUT_SIZE

  def _pixel_to_meter(self, bbox_bottom_center_x: float, bbox_bottom_y: float) -> tuple[float, float]:
    """检测框底部中点(着地点)→ (d_rel, y_rel)。
    pinhole: d_rel = f * h / (y - cy)?? 这里用简化:假设相机高 1.3m, pitch≈0
    实际:y_rel = (x - cx) * d_rel / f; d_rel 由目标高度估算。
    简化:用目标框高度反推距离(目标典型高度 person 1.7m)。
    """
    return 0.0, 0.0  # 由调用方按类别高度计算

  def detect(self, y_plane: np.ndarray) -> list[VisionObstacle]:
    """输入 road Y 平面(1344x760 uint8),返回障碍列表。"""
    if self.net is None and self._trt is None:
      return []  # opencv/TRT 均不可用, 空转
    if getattr(self, '_is_signal_model', False):
      return []  # 信号灯模型不产出障碍物(见 detect_signals)
    self._frame_count += 1
    if self._frame_count % DETECT_EVERY_N != 0:
      return []

    # YOLO 输入 640x640,letterbox(保持宽高比)
    h_in, w_in = y_plane.shape[:2]
    scale = self._input_size / max(w_in, h_in)
    nw, nh = int(w_in * scale), int(h_in * scale)
    # 单通道 Y → 3 通道(blobFromImage 单通道会导致检测为空)
    if y_plane.ndim == 2:
      img3 = cv2.cvtColor(y_plane, cv2.COLOR_GRAY2BGR)
    else:
      img3 = y_plane
    resized = cv2.resize(img3, (nw, nh))
    canvas = np.full((self._input_size, self._input_size, 3), 114, np.uint8)
    dx, dy = (self._input_size - nw) // 2, (self._input_size - nh) // 2
    canvas[dy:dy + nh, dx:dx + nw] = resized
    blob = cv2.dnn.blobFromImage(canvas, 1 / 255.0, (self._input_size, self._input_size), swapRB=True, crop=False)
    try:
      if self._trt is not None:
        outs = self._trt.infer(blob)
      else:
        self.net.setInput(blob)
        outs = self.net.forward()
    except Exception:
      return []

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
               "cat": 0.3, "dog": 0.4, "horse": 1.5, "cow": 1.4, "sheep": 0.8,
               "deer": 1.3, "goat": 0.8, "cattle": 1.4, "barrel": 0.9, "box": 0.8,
               "car": 1.5, "truck": 3.0, "bus": 3.0,
               "traffic light": 0.6, "traffic sign": 0.7}.get(cls.lower(), 1.0)
      box_h = max(y2 - y1, 10.0)
      # 焦距按实际帧宽换算: 本机 1920x1080 时 fx≈2637; 原硬编码 2508/1344x760 是
      # J501 模组的, 用在 1920 流上会让横偏放大 1.43 倍 -> 全部被判为"偏离路径"。
      fx = road_calib()[0] * (w_in / CAM_W)
      d_rel = fx * obj_h / box_h  # f * 高度 / 像素高
      if not (MIN_DETECT_DREL_M <= d_rel <= MAX_DETECT_DREL_M):
        continue
      # 横向:底部中点相对图像中心
      bottom_cx = (x1 + x2) / 2
      y_rel = (bottom_cx - w_in / 2.0) * d_rel / fx
      result.append(VisionObstacle(cls, d_rel, y_rel, conf, (x1, y1, x2, y2)))
    return result

  def detect_light_presence(self, y_plane: np.ndarray) -> tuple[bool, float, str, tuple | None]:
    """灯存在性: 画面里有没有信号灯(不承诺颜色/方向可靠)。

    **语义限制**: 颜色类原始 conf 实测 green 0.599 / red 0.182 / yellow 0.143 /
    left 0.037 / right 0.000, 不足以驱动刹车或转向。调用方不得用 cls 做车辆
    动作决策; 颜色/方向须来自外部明确命令或规则推断。

    返回 (present, best_conf, best_cls, bbox)。
    """
    if self.net is None and self._trt is None:
      return False, 0.0, "", None

    h_in, w_in = y_plane.shape[:2]
    scale = self._input_size / max(w_in, h_in)
    nw, nh = int(w_in * scale), int(h_in * scale)
    img3 = cv2.cvtColor(y_plane, cv2.COLOR_GRAY2BGR) if y_plane.ndim == 2 else y_plane
    resized = cv2.resize(img3, (nw, nh))
    canvas = np.full((self._input_size, self._input_size, 3), 114, np.uint8)
    dx, dy = (self._input_size - nw) // 2, (self._input_size - nh) // 2
    canvas[dy:dy + nh, dx:dx + nw] = resized
    blob = cv2.dnn.blobFromImage(canvas, 1 / 255.0, (self._input_size, self._input_size), swapRB=True, crop=False)
    try:
      if self._trt is not None:
        outs = self._trt.infer(blob)
      else:
        self.net.setInput(blob)
        outs = self.net.forward()
    except Exception:
      return False, 0.0, "", None

    outs = outs[0].T
    best_conf, best_cls, best_box = 0.0, "", None
    for row in outs:
      cls_scores = row[4:]
      cid = int(np.argmax(cls_scores))
      conf = float(cls_scores[cid])
      if conf < LIGHT_PRESENCE_CONF or cid not in SIGNAL_CLASSES:
        continue
      cx, cy_, bw, bh = float(row[0]), float(row[1]), float(row[2]), float(row[3])
      if bw < 4 or bh < 4:
        continue
      # 巨型框是背景误检(实测小输入上采样会输出覆盖整幅画面的框)
      if bw / scale > w_in * 0.25 or bh / scale > h_in * 0.25:
        continue
      if conf > best_conf:
        best_conf, best_cls = conf, SIGNAL_CLASSES[cid]
        best_box = ((cx - bw / 2 - dx) / scale, (cy_ - bh / 2 - dy) / scale,
                    (cx + bw / 2 - dx) / scale, (cy_ + bh / 2 - dy) / scale)
    return (best_conf > 0.0), best_conf, best_cls, best_box

  def detect_signals(self, y_plane: np.ndarray) -> list[tuple[str, float, float, float, tuple]]:
    """信号灯检测(自定义 6 类小模型)。返回 [(color, cx, cy, conf, bbox)], 原图坐标。

    与 detect() 用两个独立实例(本实例模型必须是信号灯模型), 因为类别表互斥。
    只做检测与坐标换算, 由调用方决定是否写入 carrotMan.trafficState。
    """
    if self.net is None and self._trt is None:
      return []

    h_in, w_in = y_plane.shape[:2]
    scale = self._input_size / max(w_in, h_in)
    nw, nh = int(w_in * scale), int(h_in * scale)
    img3 = cv2.cvtColor(y_plane, cv2.COLOR_GRAY2BGR) if y_plane.ndim == 2 else y_plane
    resized = cv2.resize(img3, (nw, nh))
    canvas = np.full((self._input_size, self._input_size, 3), 114, np.uint8)
    dx, dy = (self._input_size - nw) // 2, (self._input_size - nh) // 2
    canvas[dy:dy + nh, dx:dx + nw] = resized
    blob = cv2.dnn.blobFromImage(canvas, 1 / 255.0, (self._input_size, self._input_size), swapRB=True, crop=False)
    try:
      if self._trt is not None:
        outs = self._trt.infer(blob)
      else:
        self.net.setInput(blob)
        outs = self.net.forward()
    except Exception:
      return []

    outs = outs[0].T  # (8400, 4+nc)
    boxes, scores, classes = [], [], []
    for row in outs:
      cls_scores = row[4:]
      cid = int(np.argmax(cls_scores))
      conf = float(cls_scores[cid])
      if conf < SIGNAL_CONF_THRESHOLD or cid not in SIGNAL_CLASSES:
        continue
      cx, cy_, w, h = row[:4]
      boxes.append([(cx - w / 2 - dx) / scale, (cy_ - h / 2 - dy) / scale,
                    (cx + w / 2 - dx) / scale, (cy_ + h / 2 - dy) / scale])
      scores.append(conf)
      classes.append(cid)
    if not boxes:
      return []
    idxs = cv2.dnn.NMSBoxes(boxes, scores, SIGNAL_CONF_THRESHOLD, NMS_THRESHOLD)
    out = []
    for i in idxs:
      i = int(i)
      x1, y1, x2, y2 = boxes[i]
      # 几何合理性: 320 输入上采样回 1920 时, 背景误检会输出覆盖整幅画面的巨型框
      # (实测 1878x1060 @conf0.63)。真实交通灯在画面里很小, 超过画面 25% 一律拒绝,
      # 否则会直接触发红灯误停车。
      if (x2 - x1) > w_in * 0.25 or (y2 - y1) > h_in * 0.25:
        continue
      if (x2 - x1) < 4 or (y2 - y1) < 4:
        continue
      out.append((SIGNAL_CLASSES[classes[i]], (x1 + x2) / 2.0, (y1 + y2) / 2.0,
                  scores[i], (x1, y1, x2, y2)))
    return out

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
      # 车辆(供相邻车道占用判定, 不参与静止障碍避让)
      90: "Car", 558: "Truck", 73: "Bus",
    }
    return OIV7_IDX
