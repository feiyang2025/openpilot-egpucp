#!/usr/bin/env python3
"""intrinsic_calibd v4 —— 每镜头独立内参+外参联合自进化。

核心:消失点约束
    v0 = cy + f * tan(pitch_cam),  pitch_cam = pitch_device + pitch_offset
  小角线性化:
    v0 - cy = f * pitch_device + f * pitch_offset
            = a * pitch_device + b          (a = f, b = f * pitch_offset)
  行驶中 pitch_device 随加速/刹车/坡道变化,而 f 与 offset 不变:
  积累多组 (v0, pitch_device) 样本 → 最小二乘同时解出 f 与 pitch_offset。
  这就是"内参(f)+外参(pitch_offset)全部独立、全部自进化"。

可辨识性判据:
  pitch 样本跨度必须足够(全在同一俯仰下, a/b 不可分):
    跨度 < PITCH_SPAN_MIN → 只用当前平均 pitch 反解 f(退化单参数),标记未辨识
  跨度过关 → 联合 LSQ, f 与 pitch_offset 各自收敛。

输出 Params(每镜头一条,json):
  CamCalibRoad / CamCalibWide:
    {"f": ..., "pitch_offset": ..., "roll_offset": 0.0, "yaw_offset": 0.0,
     "samples": N, "span": ..., "converged": bool, "t": ...}
  modeld 启动时读取,同时覆盖该流内参(f)与外参(pitch_offset)。
"""
import json
import time
from collections import deque

import numpy as np
import cv2  # noqa: E402

from msgq.visionipc import VisionIpcClient, VisionStreamType
from openpilot.cereal import messaging, log
from openpilot.common.params import Params

EMIT_INTERVAL = 10.0
SAMPLE_EVERY_N = 3
MIN_LINES = 6
MIN_LINE_LEN = 60
MIN_PITCH = 0.001   # 相机装平+平路时 pitch 很小,过低会永不采样
MIN_SAMPLES = 30
CONVERGE_STD = 60.0
PITCH_SPAN_MIN = 0.015   # rad;pitch 样本跨度低于此值则不可辨识 offset
MAX_OFFSET = 0.15  # rad;每镜头外参偏置物理上限,LSQ 超出即病态拒绝

RANSAC_ITERS = 60
RANSAC_DIST = 30.0
VANISH_Y_MIN = 0.15
VANISH_Y_MAX = 0.9

HIST_LEN = 400  # 保留的 (v0, pitch) 样本数(滑动窗口 LSQ)


def _seg_angle_deg(dx, dy):
  return abs(float(np.degrees(np.arctan2(dy, dx))))


def compute_vanishing_point(img_gray):
  """RANSAC 估计消失点,返回 (v0, n_lines)。"""
  h, w = img_gray.shape[:2]
  blur = cv2.GaussianBlur(img_gray, (5, 5), 0)
  edges = cv2.Canny(blur, 50, 150)
  lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=60,
                          minLineLength=MIN_LINE_LEN, maxLineGap=12)
  if lines is None:
    return None, 0

  segs = []
  for l in lines:
    x1, y1, x2, y2 = l[0]
    dx, dy = x2 - x1, y2 - y1
    length = np.hypot(dx, dy)
    if length < MIN_LINE_LEN:
      continue
    ang = _seg_angle_deg(dx, dy)
    if ang < 30 or ang > 150:
      continue
    segs.append((dy, -dx, dx * y1 - dy * x1))
  n = len(segs)
  if n < MIN_LINES:
    return None, n

  def point_line_dist(px, py, s):
    a, b, c = s
    return abs(a * px + b * py + c) / (np.hypot(a, b) + 1e-6)

  best_v = None
  best_inliers = 0
  rng = np.random.default_rng()
  for _ in range(RANSAC_ITERS):
    i, j = rng.integers(0, n, 2)
    if i == j:
      continue
    a1, b1, c1 = segs[i]
    a2, b2, c2 = segs[j]
    det = a1 * b2 - a2 * b1
    if abs(det) < 1e-9:
      continue
    vx = (b1 * c2 - b2 * c1) / det
    vy = (c1 * a2 - c2 * a1) / det
    if not (-2 * w <= vx <= 3 * w):
      continue
    yn = vy / h
    if not (VANISH_Y_MIN <= yn <= VANISH_Y_MAX):
      continue
    inliers = sum(1 for s in segs if point_line_dist(vx, vy, s) < RANSAC_DIST)
    if inliers > best_inliers:
      best_inliers = inliers
      best_v = (vx, vy)

  if best_v is None or best_inliers < 3:
    return None, n

  vx0, vy0 = best_v
  ys = [vy0]
  for s in segs:
    if point_line_dist(vx0, vy0, s) < RANSAC_DIST:
      a, b, c = s
      if abs(b) > 1e-9:
        ys.append(-(a * vx0 + c) / b)
  return float(np.median(ys)), n


class StreamCalib:
  """单镜头:积累 (v0, pitch_device) 样本,联合估计 f 与 pitch_offset。"""

  def __init__(self, stream_type, param_name, label, msg_name, focal_prior):
    self.stream_type = stream_type
    self.param_name = param_name
    self.label = label
    self.msg_name = msg_name
    self.focal_prior = float(focal_prior)
    self.samples = deque(maxlen=HIST_LEN)   # (pitch_device, v0)
    self.total_seen = 0
    self.last_emit = 0.0
    self.vipc = VisionIpcClient("camerad", stream_type, False)
    self.cy = None
    self.last_connect_attempt = 0.0
    self.best = None  # 收敛后的最优估计(冻结,只进不退)

  def using_preferred(self):
    try:
      with open("/tmp/role_sources.json") as f:
        status = json.load(f).get(self.msg_name, {})
      cur = status.get("src")
      pref = status.get("preferred")
      return cur is not None and cur == pref
    except Exception:
      return False

  def add_sample(self, v0, pitch_device, cy):
    if self.cy is None:
      self.cy = cy
    self.samples.append((float(pitch_device), float(v0)))
    self.total_seen += 1

  def estimate(self):
    """联合 LSQ: v0 - cy = a*pitch + b, a=f, b=f*pitch_offset。
    返回 dict 或 None(样本不足/跨度不足)。"""
    if len(self.samples) < MIN_SAMPLES or self.cy is None:
      return None
    arr = np.array(self.samples)          # (pitch, v0)
    p = arr[:, 0]
    y = arr[:, 1] - self.cy
    span = float(np.ptp(p))
    if span < PITCH_SPAN_MIN:
      f = self.focal_prior
      angular_offsets = y / f - p
      observed_offset = float(np.median(angular_offsets))
      residual = angular_offsets - observed_offset
      mad = float(np.median(np.abs(residual)))
      keep = np.abs(residual) < max(3.0 * mad, 0.003)
      if keep.sum() >= MIN_SAMPLES // 2:
        observed_offset = float(np.median(angular_offsets[keep]))
        residual = angular_offsets[keep] - observed_offset
      fitted = None
      std = float(np.std(residual) * f)
      conv_ok = std < CONVERGE_STD
      mode = "focal_prior"
    else:
      # 离群过滤:先粗拟合(MAD 阈值剔除大残差样本),再用内点精拟合。
      # 真实 v0 检测噪声 10-30px,个别错检(护栏/阴影线)会严重污染 LSQ。
      A = np.column_stack([p, np.ones_like(p)])
      sol, *_ = np.linalg.lstsq(A, y, rcond=None)
      resid = np.abs(y - A @ sol)
      mad = np.median(resid)
      keep = resid < max(3.0 * mad, 20.0)
      if keep.sum() >= MIN_SAMPLES // 2:
        A = A[keep]
        y = y[keep]
        sol, *_ = np.linalg.lstsq(A, y, rcond=None)
      a, b = sol
      f = float(a)
      observed_offset = float(b / a) if abs(a) > 1e-9 else 0.0
      fitted = A @ sol
      conv_ok = True
      mode = "joint_lsq"
    if not (300.0 <= f <= 4000.0):
      return None
    if fitted is not None:
      std = float(np.std(y - fitted))
    return {
      "f": round(f, 1),
      # Mounting pitch belongs exclusively to calibrationd.rpyCalib and
      # wideFromDeviceEuler. Publishing it here would apply it twice in modeld.
      "pitch_offset": 0.0,
      "samples": self.total_seen,
      "span": round(span, 4),
      "std": round(std, 1),
      "converged": conv_ok and std < CONVERGE_STD,
      "mode": mode,
      "t": int(time.time()),
    }

  def seed_prior(self):
    info = {
      "f": self.focal_prior,
      "pitch_offset": 0.0,
      "samples": 0,
      "span": 0.0,
      "std": 0.0,
      "converged": True,
      "mode": "fov_prior",
      "t": int(time.time()),
    }
    if not Params().get(self.param_name):
      Params().put(self.param_name, json.dumps(info).encode())
    self.best = info

  def emit(self):
    info = self.estimate()
    # 绝不写入未收敛值:坏标定比无标定更危险(modeld 会采用它)
    if info is None:
      print(f"[intrinsic_calibd][{self.label}] no-estimate "
            f"(samples={self.total_seen}, best={self.best is not None})", flush=True)
      return
    if not info["converged"]:
      print(f"[intrinsic_calibd][{self.label}] not-converged "
            f"(f={info['f']:.0f} span={info['span']:.4f} std={info['std']:.1f} "
            f"samples={info['samples']})", flush=True)
      return
    # 冻结 best:收敛后滑窗移动可能让 std 波动变大,仅当 std 更小才更新(只进不退)
    if self.best is not None and self.best.get("mode") != "fov_prior" and info["std"] >= self.best["std"]:
      return
    self.best = info
    Params().put(self.param_name, json.dumps(info).encode())
    self.last_emit = time.monotonic()
    print(f"[intrinsic_calibd][{self.label}] WRITE f={info['f']:.1f} "
          f"pitch_off={info['pitch_offset']:.5f} span={info['span']:.4f} "
          f"std={info['std']:.1f} samples={info['samples']}", flush=True)


class IntrinsicCalib:
  def __init__(self):
    self.sm = messaging.SubMaster(["liveCalibration"])
    self.streams = [
      StreamCalib(VisionStreamType.VISION_STREAM_ROAD, "CamCalibRoad", "road30", "roadCameraState", 2508.0),
      StreamCalib(VisionStreamType.VISION_STREAM_WIDE_ROAD, "CamCalibWide", "wide196", "wideRoadCameraState", 405.2),
    ]
    for stream in self.streams:
      stream.seed_prior()

  def get_pitch(self):
    if not self.sm.updated["liveCalibration"]:
      return None
    lc = self.sm["liveCalibration"]
    # 仅接受已校准的外参:calibrationd 未收敛时 rpy 在漂移,采样的样本全无效
    if lc.calStatus != log.LiveCalibrationData.Status.calibrated:
      return None
    rpy = np.array(lc.rpyCalib)
    if not np.isfinite(rpy).all():
      return None
    return float(rpy[1])

  def run(self):
    frame_idx = 0
    while True:
      self.sm.update(0)
      pitch = self.get_pitch()

      # 连接管理:未连接的流周期重试(webcamerad 并行启动可能晚于本进程)
      now = time.monotonic()
      for s in self.streams:
        if not s.vipc.is_connected() and now - s.last_connect_attempt > 2.0:
          s.last_connect_attempt = now
          if s.vipc.connect(False):
            print(f"[intrinsic_calibd][{s.label}] connected", flush=True)

      if pitch is None or abs(pitch) < MIN_PITCH:
        time.sleep(0.05)
        continue
      frame_idx += 1
      if frame_idx % SAMPLE_EVERY_N != 0:
        time.sleep(0.02)
        continue
      for s in self.streams:
        if s.vipc.is_connected() and s.using_preferred():
          buf = s.vipc.recv()
          if buf is None:
            continue
          try:
            y_plane = np.frombuffer(buf.data[:buf.height * buf.stride], dtype=np.uint8)
            img_gray = y_plane.reshape(buf.height, buf.stride)[:, :buf.width]
          except Exception:
            continue
          v0, n_lines = compute_vanishing_point(img_gray)
          if v0 is not None:
            s.add_sample(v0, pitch, buf.height / 2.0)
          if time.monotonic() - s.last_emit > EMIT_INTERVAL:
            s.emit()
      time.sleep(0.02)


def main():
  IntrinsicCalib().run()


if __name__ == "__main__":
  main()
