#!/usr/bin/env python3
"""v4.1: make the extrinsic (mounting pitch) actually estimable and published.

Why this deviates from upstream bed5f1af3d:
  Upstream pinned pitch_offset = 0.0 on the theory that calibrationd already
  owns mounting pitch. That holds for a factory-mounted camera; on this bench
  the GMSL camera is mounted by hand, and calibrationd only estimates device
  attitude, so the mounting angle is never absorbed anywhere. With the offset
  forced to zero the whole daemon had zero effect on the model output.

  The focal length (intrinsic) part is kept, but it cannot move the metrically
  scaled outputs: get_warp_matrix maps the principal point to a fixed place and
  f only scales the image about it, which monocular geometry is invariant to.
  Verified on-device: sweeping f 2087 -> 3600 changes lane width by 0.02 m.
  So the extrinsic is what actually aligns the far end of the plan.
"""
import json
import os
import time
from collections import deque

import numpy as np
import cv2  # noqa: E402

from msgq.visionipc import VisionIpcClient, VisionStreamType
from openpilot.cereal import messaging, log
from openpilot.common.params import Params

EMIT_INTERVAL = 10.0
SAMPLE_EVERY_N = 3
MIN_LINES = 20
MIN_LINE_LEN = 60
MIN_PITCH = 0.001
MIN_SAMPLES = 30
CONVERGE_STD = 60.0
PITCH_SPAN_MIN = 0.015
MAX_OFFSET = 0.15

RANSAC_ITERS = 60
RANSAC_DIST = 7.0
VANISH_Y_MIN = 0.15
VANISH_Y_MAX = 0.9

HIST_LEN = 400
ROLE_SOURCES = "/tmp/role_sources.json"

# 只写参数需要的最小外参改动量:低于此值视为"标定已正确",不打扰 modeld
OFFSET_WRITE_MIN = 0.0005   # rad ~= 0.03 deg


def _seg_angle_deg(dx, dy):
  return abs(float(np.degrees(np.arctan2(dy, dx))))


ROAD_ROI_TOP_FRAC = 0.52
LANE_BRIGHT_MIN = 165
VP_Y_MIN_FRAC = 0.35
VP_Y_MAX_FRAC = 0.8
VP_X_MIN_FRAC = 0.2
VP_X_MAX_FRAC = 0.8


def compute_vanishing_point(img_gray):
  """RANSAC 消失点:只在路面 ROI 内用亮色车道线,并限制中心视野。"""
  h, w = img_gray.shape[:2]
  y_top = int(h * ROAD_ROI_TOP_FRAC)
  roi = img_gray[y_top:, :]
  bright = (roi > LANE_BRIGHT_MIN).astype(np.uint8) * 255
  bright = cv2.GaussianBlur(bright, (5, 5), 0)
  edges = cv2.Canny(bright, 50, 150)
  lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=70,
                          minLineLength=MIN_LINE_LEN, maxLineGap=16)
  if lines is None:
    return None, 0
  segs = []
  for l in lines:
    x1, y1, x2, y2 = l[0]
    y1 += y_top
    y2 += y_top
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
    i2, j2 = rng.integers(0, n, 2)
    if i2 == j2:
      continue
    a1, b1, c1 = segs[i2]
    a2, b2, c2 = segs[j2]
    det = a1 * b2 - a2 * b1
    if abs(det) < 1e-9:
      continue
    vx = (b1 * c2 - b2 * c1) / det
    vy = (c1 * a2 - c2 * a1) / det
    if not (VP_X_MIN_FRAC * w <= vx <= VP_X_MAX_FRAC * w):
      continue
    if not (VP_Y_MIN_FRAC * h <= vy <= VP_Y_MAX_FRAC * h):
      continue
    inliers = sum(1 for s in segs if point_line_dist(vx, vy, s) < RANSAC_DIST)
    if inliers > best_inliers:
      best_inliers = inliers
      best_v = (vx, vy)
  if best_v is None or best_inliers < max(6, int(0.20 * n)):
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
  """单镜头:积累 (v0, pitch_device) 样本,估计外参 pitch_offset(必要时联合解 f)。"""

  def __init__(self, stream_type, param_name, label, msg_name, focal_prior):
    self.stream_type = stream_type
    self.param_name = param_name
    self.label = label
    self.msg_name = msg_name
    self.focal_prior = float(focal_prior)
    self.samples = deque(maxlen=HIST_LEN)
    self.total_seen = 0
    self.last_emit = 0.0
    self.vipc = VisionIpcClient("camerad", stream_type, False)
    self.cy = None
    self.last_connect_attempt = 0.0
    self.best = None
    self.last_v0 = None
    self.last_lines = 0

  def using_preferred(self):
    # 真 camerad(本机 GMSL)没有 webcamerad 的角色表,单路即首选。
    try:
      with open(ROLE_SOURCES) as f:
        status = json.load(f).get(self.msg_name, {})
    except Exception:
      return True
    cur = status.get("src")
    pref = status.get("preferred")
    return cur is not None and cur == pref

  def add_sample(self, v0, pitch_device, cy):
    if self.cy is None:
      self.cy = cy
    # 物理门限:消失点偏离光学中心超过约 17 度视为错检,不进入估计
    if abs(float(v0) - self.cy) > 0.30 * self.focal_prior:
      return
    self.samples.append((float(pitch_device), float(v0)))
    self.total_seen += 1

  def estimate(self):
    """v0 - cy = f * pitch_cam with pitch_cam = pitch_dev + offset.

    符号约定按本树 euler: 相机下俯时 v0 > cy 而 euler[1] 为负,故
        pitch_cam = -atan2(v0 - cy, f),  offset = pitch_cam - pitch_dev
    与 calibrationd 的 rpyCalib[1] 同符号空间,modeld 可直接把 offset 加到
    euler[1] 上。
    """
    if len(self.samples) < MIN_SAMPLES or self.cy is None:
      return None
    arr = np.array(self.samples)
    p = arr[:, 0]
    v0 = arr[:, 1]
    span = float(np.ptp(p))
    if span < PITCH_SPAN_MIN:
      # 退化: pitch 跨度不足, a 与 b 不可分。用消失点直接反解相机绝对
      # pitch,再减设备 pitch 得安装外参偏置(逐帧可解,不依赖 pitch 变化)。
      f = self.focal_prior
      v0_med = float(np.median(v0))
      # MAD 剔除离群消失点(护栏/阴影造成的错检)
      mad = float(np.median(np.abs(v0 - v0_med)))
      keep = np.abs(v0 - v0_med) < max(5.0 * mad, 13.0)
      if keep.sum() >= MIN_SAMPLES // 2:
        v0_med = float(np.median(v0[keep]))
      pitch_cam = -float(np.arctan2(v0_med - self.cy, f))
      offset = pitch_cam - float(np.median(p))
      std = float(np.std(v0[keep] - v0_med)) if keep.sum() >= MIN_SAMPLES // 2 else float('inf')
      mode = "vp_offset"
      fitted = None
    else:
      # 联合 LSQ: v0 - cy = -(f*pitch) - f*offset -> y = a*p + b
      y = -(v0 - self.cy)
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
      # v0 = cy - f*pitch_cam, y = -(v0-cy) = f*pitch_dev + f*offset
      # => a = f, b = f*offset
      offset = float(b / a) if abs(a) > 1e-9 else 0.0
      fitted = A @ sol
      std = float(np.std(y - fitted))
      mode = "joint_lsq"
    if not (300.0 <= f <= 4000.0):
      return None
    if abs(offset) > MAX_OFFSET:
      return None
    return {
      "f": round(f, 1),
      "pitch_offset": round(offset, 6),
      "samples": self.total_seen,
      "span": round(span, 4),
      "std": round(std, 1),
      "converged": std < CONVERGE_STD,
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
    if info is None:
      print(f"[intrinsic_calibd][{self.label}] no-estimate "
            f"(samples={self.total_seen}, v0={self.last_v0}, lines={self.last_lines})", flush=True)
      return
    if not info["converged"]:
      print(f"[intrinsic_calibd][{self.label}] not-converged "
            f"(f={info['f']:.0f} off={info['pitch_offset']:+.5f} std={info['std']:.1f} "
            f"samples={info['samples']})", flush=True)
      return
    # 只进不退;且外参变化小于 0.03deg 时不必打扰 modeld
    if (self.best is not None and self.best.get("mode") != "fov_prior"
            and info["std"] >= self.best["std"]
            and abs(info["pitch_offset"] - self.best.get("pitch_offset", 0.0)) < OFFSET_WRITE_MIN):
      return
    self.best = info
    Params().put(self.param_name, json.dumps(info).encode())
    self.last_emit = time.monotonic()
    print(f"[intrinsic_calibd][{self.label}] WRITE f={info['f']:.1f} "
          f"pitch_off={info['pitch_offset']:+.5f} ({np.degrees(info['pitch_offset']):+.2f}deg) "
          f"std={info['std']:.1f} samples={info['samples']} mode={info['mode']}", flush=True)


class IntrinsicCalib:
  def __init__(self):
    self.sm = messaging.SubMaster(["liveCalibration"])
    # 真车用本机 GMSL 内参;视频台架用视频焦距先验,与 modeld/UI 共享同一来源。
    video_mode = os.getenv("USE_WEBCAM") is not None
    if video_mode:
      from openpilot.common.transformations.video_camera_calibration import VIDEO_FOCAL_PRIORS
      road_f, wide_f = VIDEO_FOCAL_PRIORS["road"], VIDEO_FOCAL_PRIORS["wide"]
    else:
      road_f, wide_f = 2637.0, 564.6
    self.streams = [
      StreamCalib(VisionStreamType.VISION_STREAM_ROAD, "CamCalibRoad", "road", "roadCameraState", road_f),
      StreamCalib(VisionStreamType.VISION_STREAM_WIDE_ROAD, "CamCalibWide", "wide", "wideRoadCameraState", wide_f),
    ]
    for stream in self.streams:
      stream.seed_prior()

  def get_pitch(self):
    if not self.sm.updated["liveCalibration"]:
      return None
    lc = self.sm["liveCalibration"]
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

      now = time.monotonic()
      for s in self.streams:
        if not s.vipc.is_connected() and now - s.last_connect_attempt > 2.0:
          s.last_connect_attempt = now
          if s.vipc.connect(False):
            print(f"[intrinsic_calibd][{s.label}] connected", flush=True)

      video_mode = os.getenv("USE_WEBCAM") is not None
      if pitch is None or (not video_mode and abs(pitch) < MIN_PITCH):
        time.sleep(0.05)
        continue
      sample_pitch = 0.0 if video_mode else pitch
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
          s.last_lines = n_lines
          if v0 is not None:
            s.last_v0 = round(v0, 1)
            cy = 540.0 if video_mode else buf.height / 2.0
            s.add_sample(v0, sample_pitch, cy)
          if time.monotonic() - s.last_emit > EMIT_INTERVAL:
            s.emit()
      time.sleep(0.02)


def main():
  IntrinsicCalib().run()


if __name__ == "__main__":
  main()