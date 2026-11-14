#!/usr/bin/env python3
"""camcalibd: per-stream intrinsics / mounting-pitch candidate estimator.

Upgraded from selfdrive/carrot/intrinsic_calibd.py (v4.1) for the camera
calibration redesign (spec §5.1). The vanishing-point + robust-LSQ estimator
and every threshold constant are carried over unchanged. Differences:

  - Output is the cameraCalibCandidate message; calibrationd (the single
    writer) merges and persists it. No Params writes: CamCalibRoad/CamCalibWide
    were never registered in params_keys.h (UnknownKeyName crash at startup)
    and no code ever read them.
  - Registered in the manager (only_onroad).
  - cy comes from the factory K of the live CameraCalibSet, not buf.height/2
    (audit B3), and resets with the identity when the stream size changes.
  - Frames are received non-blocking (audit B1); the absolute MIN_PITCH gate is
    dropped (audit B2): sampling is decided by calibration convergence only.
  - Publishes cameraSyncState (T0 system-clock timebase, per-stream SOF delta
    vs the other road stream; synced is conservative until the full T0
    statistics in spec §16.4 land).
  - The 4x downsample from the spec is NOT applied yet: the RANSAC thresholds
    (7 px inlier radius etc.) are tuned at full resolution; downsampling first
    would change estimator behavior. Kept full-res for migration equivalence.
"""
import json
import os
import time
from collections import deque

import numpy as np
import cv2

from msgq.visionipc import VisionIpcClient, VisionStreamType
from openpilot.cereal import messaging, log
from openpilot.common.swaglog import cloudlog
from openpilot.common.transformations.camera_calib import Cam, from_live_calibration

SAMPLE_EVERY_N = 3
MIN_LINES = 20
MIN_LINE_LEN = 60
MIN_SAMPLES = 30
CONVERGE_STD = 60.0
PITCH_SPAN_MIN = 0.015
MAX_OFFSET = 0.15
SYNC_EMIT_INTERVAL = 1.0

RANSAC_ITERS = 60
RANSAC_DIST = 7.0
VANISH_Y_MIN = 0.15
VANISH_Y_MAX = 0.9

HIST_LEN = 400
ROLE_SOURCES = "/tmp/role_sources.json"

ROAD_ROI_TOP_FRAC = 0.52
LANE_BRIGHT_MIN = 165
VP_Y_MIN_FRAC = 0.35
VP_Y_MAX_FRAC = 0.8
VP_X_MIN_FRAC = 0.2
VP_X_MAX_FRAC = 0.8


def _seg_angle_deg(dx, dy):
  return abs(float(np.degrees(np.arctan2(dy, dx))))


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
  """单镜头:积累 (v0, pitch_device) 样本,估计安装俯仰 offset(必要时联合解 f)。"""

  def __init__(self, cam: Cam, stream_type, label, msg_name, focal_prior):
    self.cam = cam
    self.stream_type = stream_type
    self.label = label
    self.msg_name = msg_name
    self.focal_prior = float(focal_prior)
    self.samples = deque(maxlen=HIST_LEN)
    self.total_seen = 0
    self.last_v0 = None
    self.last_lines = 0
    self.cy = None
    self.cy_size = None
    self.best = None
    self.last_connect_attempt = 0.0

  def using_preferred(self):
    # 真 camerad(本机 GMSL)没有 webcamerad 的角色表,单路即首选。
    try:
      with open(ROLE_SOURCES) as f:
        status = json.load(f).get(self.msg_name, {})
    except Exception:
      return True
    return status.get("src") is not None and status.get("src") == status.get("preferred")

  def set_cy_from_set(self, calib_set):
    """cy from the single calibration source (audit B3); reset on size change."""
    entry = calib_set.cams.get(self.cam) if calib_set is not None else None
    if entry is None:
      self.cy, self.cy_size = None, None
      return
    size = (entry.width, entry.height)
    if size != self.cy_size:
      self.cy, self.cy_size = float(entry.cy), size

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
    与 calibrationd 的 body euler[1] 同符号空间,可直接加到该路的 rpy 上。
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
      mad = float(np.median(np.abs(v0 - v0_med)))
      keep = np.abs(v0 - v0_med) < max(5.0 * mad, 13.0)
      if keep.sum() >= MIN_SAMPLES // 2:
        v0_med = float(np.median(v0[keep]))
      pitch_cam = -float(np.arctan2(v0_med - self.cy, f))
      offset = pitch_cam - float(np.median(p))
      std = float(np.std(v0[keep] - v0_med)) if keep.sum() >= MIN_SAMPLES // 2 else float('inf')
      mode = "vp_offset"
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
      offset = float(b / a) if abs(a) > 1e-9 else 0.0
      std = float(np.std(y - A @ sol))
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


class CameraSyncMonitor:
  """T0 system-clock sync statistics (spec §16.4).

  Tracks the frame-pair delta Δ = ts_road − ts_wide over a sliding window.
  Every gate is on the residual Δ − deltaRef, never on the absolute delta:
  the fixed inter-stream offset (measured 12-13 ms on this stack) is a
  tracked quantity, not jitter. missingFrames counts adjacent-SOF gaps
  (audit C2/C3: the V4L2 sequence number is a dequeue counter, unusable for
  this), and a backwards/gapped SOF bumps streamEpoch.
  """

  WINDOW = 600                      # ~30 s of pairs at ~20 Hz sampling
  RESIDUAL_LIMIT_NS = 2_000_000     # |Δ − deltaRef| ≤ 2 ms -> usable pair
  JUMP_LIMIT_NS = 5_000_000         # residual jump > 5 ms -> phase break
  FRAME_PERIOD_NS = 33_333_333      # prior (30 fps); refined per stream online
  RECOVERY_FRAMES = 60              # consecutive good pairs before re-sync

  def __init__(self):
    self.deltas: deque = deque(maxlen=self.WINDOW)      # ns
    self.pair_ts: deque = deque(maxlen=self.WINDOW)     # road SOF ns per pair
    self.delta_ref: int | None = None
    self.skew_ppm = 0.0
    self.synced = False
    self.good_streak = 0
    self.missing = {Cam.ROAD: 0, Cam.WIDE: 0}
    self.epoch = {Cam.ROAD: 0, Cam.WIDE: 0}
    self.last_ts: dict = {}
    self.gaps: dict = {Cam.ROAD: deque(maxlen=60), Cam.WIDE: deque(maxlen=60)}

  def _period(self, cam: Cam) -> int:
    gaps = self.gaps[cam]
    if len(gaps) >= 10:
      return int(np.median(gaps))
    return self.FRAME_PERIOD_NS

  def on_frame(self, cam: Cam, ts_sof: int) -> None:
    last = self.last_ts.get(cam)
    if last is not None:
      gap = ts_sof - last
      if 0 < gap < 2 * self.FRAME_PERIOD_NS:
        self.gaps[cam].append(gap)
      if gap < 0 or gap > 1.5 * self._period(cam):
        self.missing[cam] += 1
        self.epoch[cam] += 1
        # a restart invalidates the tracked offset
        self.delta_ref = None
        self.synced = False
        self.good_streak = 0
    self.last_ts[cam] = ts_sof

  def on_pair(self, ts_road: int, ts_wide: int) -> None:
    delta = int(ts_road - ts_wide)
    self.deltas.append(delta)
    self.pair_ts.append(ts_road)
    if self.delta_ref is not None:
      resid = abs(delta - self.delta_ref)
      if resid > self.JUMP_LIMIT_NS:
        self.delta_ref = None
        self.synced = False
        self.good_streak = 0
        return
      self.good_streak = self.good_streak + 1 if resid <= self.RESIDUAL_LIMIT_NS else 0
    arr = np.asarray(self.deltas, dtype=float)
    if len(arr) >= 30:
      self.delta_ref = int(np.median(arr))
    if len(arr) >= 120:
      # skew against wall time (ns): slope ns/ns * 1e6 = ppm, tracked on the
      # pair's road SOF, not the sample index (index spacing is irregular)
      t = np.asarray(self.pair_ts, dtype=float)
      t0 = t[0]
      if t[-1] - t0 > 10e9:
        slope = float(np.polyfit((t - t0) / 1e9, arr, 1)[0])
        self.skew_ppm = slope  # ns delta per s == ppm of frame period
    if self.delta_ref is not None and self.good_streak >= self.RECOVERY_FRAMES:
      self.synced = True

  def stats(self) -> dict | None:
    if not self.deltas or self.delta_ref is None:
      return None
    arr = np.asarray(self.deltas, dtype=float)
    resid = np.abs(arr - self.delta_ref)
    mad = float(np.median(np.abs(arr - np.median(arr))))
    return {
      "delta": int(self.deltas[-1]),
      "deltaRef": int(self.delta_ref),
      "p50": int(float(np.percentile(resid, 50))),
      "p99": int(float(np.percentile(resid, 99.9))),
      "jitter": int(mad),
      "skewPpm": self.skew_ppm,
      "synced": self.synced,
      "missing": dict(self.missing),
      "epoch": dict(self.epoch),
    }


class CamCalibd:
  def __init__(self):
    self.sm = messaging.SubMaster(['liveCalibration', 'cameraOdometry', 'carState'])
    self.pm = messaging.PubMaster(['cameraCalibCandidate', 'cameraSyncState'])
    video_mode = os.getenv("USE_WEBCAM") is not None
    if video_mode:
      from openpilot.common.transformations.video_camera_calibration import VIDEO_FOCAL_PRIORS
      road_f, wide_f = VIDEO_FOCAL_PRIORS["road"], VIDEO_FOCAL_PRIORS["wide"]
    else:
      road_f, wide_f = 2637.0, 564.6
    self.streams = [
      StreamCalib(Cam.ROAD, VisionStreamType.VISION_STREAM_ROAD, "road", "roadCameraState", road_f),
      StreamCalib(Cam.WIDE, VisionStreamType.VISION_STREAM_WIDE_ROAD, "wide", "wideRoadCameraState", wide_f),
    ]
    self.vipcs = {s.cam: VisionIpcClient("camerad", s.stream_type, False) for s in self.streams}
    self.sync = CameraSyncMonitor()
    self.calib_set = None
    self.generation = 0
    self.last_sync_emit = 0.0
    self.frame_idx = 0

  def get_pitch(self):
    lc = self.sm['liveCalibration']
    if lc.calStatus != log.LiveCalibrationData.Status.calibrated:
      return None
    rpy = np.array(lc.rpyCalib)  # calib-legacy-allow: estimator-input (mounting-pitch observation)
    if not np.isfinite(rpy).all() or len(rpy) != 3:
      return None
    return float(rpy[1])

  def publish_candidate(self, s: StreamCalib, info: dict):
    self.generation += 1
    msg = messaging.new_message('cameraCalibCandidate', valid=True)
    cand = msg.cameraCalibCandidate
    cand.generation = self.generation
    entries = cand.init('cam', 1)
    e = entries[0]
    e.id = int(s.cam)
    # intrinsics candidate: square-pixel pinhole around the current cy (audit B3)
    cy = s.cy if s.cy is not None else 0.0
    e.intrinsics = [float(info['f']), float(info['f']), cy, cy]
    # mounting pitch offset on this camera's own rpy (spec §6.3: extrinsic layer)
    e.rpy = [0.0, float(info['pitch_offset']), 0.0]
    e.blocks = int(info['samples'])
    e.rmsReproj = float(info['std'])
    e.mode = str(info['mode'])
    e.std = float(info['std'])
    e.span = float(info['span'])
    self.pm.send('cameraCalibCandidate', msg)
    cloudlog.info(f"[camcalibd][{s.label}] CANDIDATE f={info['f']:.1f} "
                  f"pitch_off={info['pitch_offset']:+.5f} ({np.degrees(info['pitch_offset']):+.2f}deg) "
                  f"std={info['std']:.1f} samples={info['samples']} mode={info['mode']}")

  def emit(self, s: StreamCalib):
    info = s.estimate()
    if info is None:
      cloudlog.debug(f"[camcalibd][{s.label}] no-estimate (samples={s.total_seen}, v0={s.last_v0}, lines={s.last_lines})")
      return
    if not info['converged']:
      cloudlog.debug(f"[camcalibd][{s.label}] not-converged (f={info['f']:.0f} off={info['pitch_offset']:+.5f} std={info['std']:.1f} samples={info['samples']})")
      return
    # 只进不退:收敛结果比当前 best 差且外参变化 < 0.03deg 时不再发布
    if (s.best is not None and info['std'] >= s.best['std']
            and abs(info['pitch_offset'] - s.best.get('pitch_offset', 0.0)) < 0.0005):
      return
    s.best = info
    self.publish_candidate(s, info)

  def publish_sync_state(self) -> None:
    stats = self.sync.stats()
    if stats is None:
      return
    for cam in (Cam.ROAD, Cam.WIDE):
      msg = messaging.new_message('cameraSyncState', valid=True)
      ss = msg.cameraSyncState
      ss.cam = int(cam)
      ss.deltaNs = stats['delta']
      ss.deltaP50Ns = stats['p50']
      ss.deltaP99Ns = stats['p99']
      ss.jitterNs = stats['jitter']
      ss.skewPpm = stats['skewPpm']
      ss.missingFrames = stats['missing'][cam]
      ss.streamEpoch = stats['epoch'][cam]
      ss.synced = stats['synced']
      ss.timebase = 'systemClock'
      ss.timestampSource = 'kernelRecv'
      ss.quantizationNs = 1000
      self.pm.send('cameraSyncState', msg)

  def run(self):
    while True:
      self.sm.update(0)

      # keep the factory K current (cy source, identity resets)
      if self.sm.updated['liveCalibration']:
        device_type = ''
        sensor = ''
        try:
          from openpilot.common.hardware import HARDWARE
          device_type = HARDWARE.get_device_type()
        except Exception:
          pass
        self.calib_set = from_live_calibration(self.sm['liveCalibration'], device_type=device_type, sensor=sensor)
        for s in self.streams:
          s.set_cy_from_set(self.calib_set)

      now = time.monotonic()
      for s in self.streams:
        vipc = self.vipcs[s.cam]
        if not vipc.is_connected() and now - s.last_connect_attempt > 2.0:
          s.last_connect_attempt = now
          if vipc.connect(False):
            cloudlog.info(f"[camcalibd][{s.label}] connected")

      # T0 sync statistics run regardless of the calibration gate: the sync
      # numbers are themselves the gating input (spec §16.4/§16.6).
      fresh: dict = {}
      fresh_bufs: dict = {}
      ts_bufs: dict = getattr(self, 'ts_bufs', None) or {s.cam: deque(maxlen=8) for s in self.streams}
      self.ts_bufs = ts_bufs
      for s in self.streams:
        vipc = self.vipcs[s.cam]
        if vipc.is_connected() and s.using_preferred():
          buf = vipc.recv(0)
          if buf is not None:
            ts = int(vipc.timestamp_sof)
            fresh[s.cam] = ts
            fresh_bufs[s.cam] = buf
            ts_bufs[s.cam].append(ts)
            self.sync.on_frame(s.cam, ts)

      # nearest-neighbour pairing (spec §16.4): latest-of-each mis-pairs when
      # one stream delivers two frames between loops, which shows up as a
      # frame-slip trend in delta and a bogus skew. Each frame pairs once.
      while len(ts_bufs[Cam.ROAD]) > 0 and len(ts_bufs[Cam.WIDE]) > 0:
        best = None
        for tr in ts_bufs[Cam.ROAD]:
          for tw in ts_bufs[Cam.WIDE]:
            d = abs(tr - tw)
            if best is None or d < best[0]:
              best = (d, tr, tw)
        _, tr, tw = best
        ts_bufs[Cam.ROAD].remove(tr)
        ts_bufs[Cam.WIDE].remove(tw)
        # a nearest pair may still straddle a frame boundary when one stream
        # is briefly starved: only feed pairs within a half frame period
        if abs(tr - tw) <= self.sync._period(Cam.ROAD) // 2:
          self.sync.on_pair(tr, tw)
        else:
          break

      if now - self.last_sync_emit > SYNC_EMIT_INTERVAL:
        self.last_sync_emit = now
        self.publish_sync_state()

      pitch = self.get_pitch()
      if pitch is None:
        time.sleep(0.02)
        continue

      # sampling gate (§16.4 step 6): a stream is only sampled while the pair
      # residual tracking is synced
      if not self.sync.synced:
        time.sleep(0.02)
        continue

      for s in self.streams:
        vipc = self.vipcs[s.cam]
        if not (vipc.is_connected() and s.using_preferred() and s.cam in fresh):
          continue
        buf = fresh_bufs.get(s.cam)
        if buf is None:
          continue
        try:
          y_plane = np.frombuffer(buf.data[:buf.height * buf.stride], dtype=np.uint8)
          img_gray = y_plane.reshape(buf.height, buf.stride)[:, :buf.width]
        except Exception:
          continue
        self.frame_idx += 1
        if self.frame_idx % SAMPLE_EVERY_N != 0:
          continue
        v0, n_lines = compute_vanishing_point(img_gray)
        s.last_lines = n_lines
        if v0 is not None:
          s.last_v0 = round(v0, 1)
          s.add_sample(v0, pitch, s.cy if s.cy is not None else buf.height / 2.0)
        self.emit(s)


def main():
  from openpilot.common.realtime import config_realtime_process
  config_realtime_process([0, 1, 2, 3], 1)
  CamCalibd().run()


if __name__ == "__main__":
  main()
