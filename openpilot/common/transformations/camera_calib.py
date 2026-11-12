"""Camera calibration data model and the matrices derived from it.

Single home of the calibration types shared by calibrationd, modeld, the UI and
the diagnostic tools. It deliberately knows nothing about any on-wire or
persisted representation: producers/consumers convert between those and these
dataclasses.
"""
from dataclasses import dataclass
from enum import IntEnum

import numpy as np

from openpilot.common.transformations.camera import view_frame_from_device_frame
from openpilot.common.transformations.model import calib_from_medmodel, calib_from_sbigmodel
from openpilot.common.transformations.orientation import rot_from_euler


class Cam(IntEnum):
  ROAD = 0
  WIDE = 1
  LEFT = 2
  RIGHT = 3
  REAR = 4
  DCAM = 5


class CalibSource(IntEnum):
  FACTORY = 0
  PRIOR = 1
  AUTO = 2
  MANUAL = 3


# Mutable: calibrationd is the single writer and updates rpy/height/seq in place
# every cycle.
@dataclass
class CameraCalib:
  uid: str
  width: int
  height: int
  fx: float
  fy: float
  cx: float
  cy: float
  dist: np.ndarray            # (5,)
  rpy: np.ndarray | None      # (3,) cam_from_body; None when there is no extrinsic (DCAM)
  mount_height: float | None
  extrinsic_valid: bool       # always False for DCAM
  valid: bool
  source: CalibSource
  blocks: int
  rms_reproj: float
  spread: np.ndarray          # (3,)
  updated_at_ns: int


@dataclass(frozen=True)
class CalibIdentity:
  device_type: str
  sensor: str
  sizes: dict[int, tuple[int, int]]   # Cam.id -> (width, height)


# Mutable: see the note on CameraCalib.
@dataclass
class CameraCalibSet:
  schema_version: int
  seq: int
  identity: CalibIdentity
  height: float                      # compatibility field, mirrors cams[ROAD].mount_height
  body_from_calib: np.ndarray        # (3,) euler; v1 == legacy rpyCalib
  cams: dict[Cam, CameraCalib]       # indexed by Cam; the capnp id field holds the enum value
  wide_warp_physical: bool = False

  def K(self, cam: Cam) -> np.ndarray:
    c = self.cams[cam]
    return np.array([
      [c.fx, 0.0, c.cx],
      [0.0, c.fy, c.cy],
      [0.0, 0.0, 1.0],
    ])

  def _require_extrinsic(self, cam: Cam) -> np.ndarray:
    c = self.cams[cam]
    if not c.extrinsic_valid or c.rpy is None:
      raise ValueError(f"camera {cam.name} has no valid extrinsic")
    return c.rpy

  def camera_from_body(self, cam: Cam) -> np.ndarray:
    return view_frame_from_device_frame @ rot_from_euler(self._require_extrinsic(cam))

  def camera_from_calib(self, cam: Cam) -> np.ndarray:
    return self.camera_from_body(cam) @ rot_from_euler(self.body_from_calib)

  def device_from_calib(self) -> np.ndarray:
    return rot_from_euler(self.body_from_calib)

  def calib_from_device(self) -> np.ndarray:
    return rot_from_euler(self.body_from_calib).T

  def warp_matrix(self, cam: Cam, bigmodel_frame: bool = False) -> np.ndarray:
    calib_from_model = calib_from_sbigmodel if bigmodel_frame else calib_from_medmodel
    # 外参有效性以请求相机为准（spec §4.3）；gate 仅决定宽路 warp 的旋转源。
    self._require_extrinsic(cam)
    rpy_cam = self._require_extrinsic(Cam.ROAD) if (cam == Cam.WIDE and not self.wide_warp_physical) else self.cams[cam].rpy
    camera_from_body = view_frame_from_device_frame @ rot_from_euler(rpy_cam)
    return (self.K(cam) @ camera_from_body @ rot_from_euler(self.body_from_calib) @ calib_from_model).astype(np.float32)

  def project_calib_points(self, cam: Cam, pts_calib: np.ndarray) -> np.ndarray:
    # UI/diagnostic full projection: calib frame -> view frame, then K.
    pts_view = self.camera_from_calib(cam) @ pts_calib
    pts = self.K(cam) @ pts_view
    return pts[:2] / pts[2]
