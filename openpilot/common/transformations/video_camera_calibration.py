"""Shared video-bench camera calibration for modeld and UI.

Video input (USE_WEBCAM) has different intrinsics from the real vehicle
camera. Both modeld (image warp) and the on-road UI (3D projection) must use
the same focal length and pitch offset, otherwise the same metric trajectory
is projected at different scales.

Real-vehicle mode returns None: callers keep their existing
DEVICE_CAMERAS + liveCalibration path untouched.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Any

VIDEO_FOCAL_PRIORS = {"road": 446.1, "wide": 564.6}
VIDEO_FRAME_SIZE = (1920, 1080)
STREAM_PARAMS = {"road": "CamCalibRoad", "wide": "CamCalibWide"}

MIN_FOCAL = 300.0
MAX_FOCAL = 4000.0
MAX_PITCH_OFFSET = 0.6  # rad; video bench mount only


@dataclass(frozen=True)
class VideoCameraCalibration:
  focal_length: float
  pitch_offset: float
  yaw_offset: float
  x_shift_px: float
  x_shear: float
  source: str
  converged: bool


def _video_mode(video_mode: bool | None) -> bool:
  if video_mode is not None:
    return bool(video_mode)
  return os.getenv("USE_WEBCAM") is not None


def _decode(raw: Any) -> dict | None:
  if raw is None:
    return None
  try:
    if isinstance(raw, (bytes, bytearray)):
      raw = raw.decode("utf-8", errors="strict")
    value = json.loads(raw)
  except Exception:
    return None
  return value if isinstance(value, dict) else None


def _prior(stream: str) -> VideoCameraCalibration:
  return VideoCameraCalibration(
    focal_length=VIDEO_FOCAL_PRIORS[stream],
    pitch_offset=0.0,
    yaw_offset=0.0,
    x_shift_px=0.0,
    x_shear=0.0,
    source="fov_prior",
    converged=False,
  )


def resolve_video_camera_calibration(
  params_reader,
  stream: str,
  *,
  video_mode: bool | None = None,
) -> VideoCameraCalibration | None:
  """Return validated video calibration, or None outside video mode."""
  if stream not in STREAM_PARAMS:
    raise ValueError(f"unknown camera stream: {stream!r}")
  if not _video_mode(video_mode):
    return None

  prior = _prior(stream)
  info = _decode(params_reader.get(STREAM_PARAMS[stream]))
  if info is None:
    return prior

  # A persisted prior record is not evidence that this camera converged.
  mode = info.get("mode")
  if mode == "fov_prior" or not bool(info.get("converged", False)):
    return prior

  try:
    focal = float(info.get("f"))
    offset = float(info.get("pitch_offset", 0.0))
    yaw = float(info.get("yaw_offset", 0.0))
    xshift = float(info.get("x_shift_px", 0.0))
    xshear = float(info.get("x_shear", 0.0))
  except (TypeError, ValueError):
    return prior

  if not (math.isfinite(focal) and math.isfinite(offset) and math.isfinite(yaw) and math.isfinite(xshift) and math.isfinite(xshear)):
    return prior
  if not (MIN_FOCAL < focal < MAX_FOCAL):
    return prior
  if abs(offset) > MAX_PITCH_OFFSET or abs(yaw) > MAX_PITCH_OFFSET or abs(xshift) > 400.0 or abs(xshear) > 2.0:
    return prior

  return VideoCameraCalibration(
    focal_length=focal,
    pitch_offset=offset,
    yaw_offset=yaw,
    x_shift_px=xshift,
    x_shear=xshear,
    source=str(mode or "learned"),
    converged=True,
  )
