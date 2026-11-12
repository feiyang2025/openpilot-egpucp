import numpy as np
import pytest
from openpilot.common.transformations.camera import view_frame_from_device_frame
from openpilot.common.transformations.orientation import rot_from_euler
from openpilot.common.transformations.model import get_warp_matrix
from openpilot.common.transformations.camera_calib import Cam, CalibSource, CameraCalib, CameraCalibSet, CalibIdentity

def _calib(rpy=(0., 0., 0.), wide=False, extrinsic=True):
  cams = {
    Cam.ROAD: CameraCalib("road:x", 1920, 1080, 2637.0, 2637.0, 960., 540., np.zeros(5),
                          np.array(rpy, dtype=float), 1.22, extrinsic, True, CalibSource.AUTO, 10, 0.5, np.zeros(3), 0),
    Cam.WIDE: CameraCalib("wide:x", 1920, 1080, 564.6, 564.6, 960., 540., np.zeros(5),
                          np.array((0., 0., 0.03) if wide else (0., 0., 0.), dtype=float), None,
                          extrinsic, True, CalibSource.AUTO, 10, 0.5, np.zeros(3), 0),
  }
  return CameraCalibSet(1, 0, CalibIdentity("pc", "imx390", {}), 1.22,
                        np.array((0., 0.05, 0.01)), cams)

def test_K_geometry():
  s = _calib()
  K = s.K(Cam.ROAD)
  assert K[0, 0] == 2637.0 and K[1, 1] == 2637.0 and K[0, 2] == 960. and K[1, 2] == 540.

def test_camera_from_calib_road_matches_legacy_formula():
  s = _calib()
  expected = view_frame_from_device_frame @ rot_from_euler([0., 0.05, 0.01])
  assert np.allclose(s.camera_from_calib(Cam.ROAD), expected)

def test_wide_warp_legacy_matches_old_modeld():
  # gate off: wide warp 旋转用 cams[ROAD].rpy（此处为 0），内参用 K(WIDE)
  s = _calib(wide=True)
  legacy_intr = np.array([[564.6, 0, 960.], [0, 564.6, 540.], [0, 0, 1.]])
  expected = get_warp_matrix(np.array([0., 0.05, 0.01]), legacy_intr, False)
  assert np.allclose(s.warp_matrix(Cam.WIDE, False), expected)

def test_wide_warp_physical_uses_wide_rotation():
  import dataclasses
  s = _calib(wide=True)
  s2 = dataclasses.replace(s, wide_warp_physical=True)   # rpy(0,0,0.03)
  legacy = get_warp_matrix(np.array([0., 0.05, 0.01]), np.array([[564.6,0,960.],[0,564.6,540.],[0,0,1.]]), False)
  assert not np.allclose(s2.warp_matrix(Cam.WIDE, False), legacy)

def test_dcam_projection_raises():
  cams = {Cam.DCAM: CameraCalib("dcam:x", 1920, 1080, 564.6, 564.6, 960., 540., np.zeros(5),
                                None, None, False, True, CalibSource.PRIOR, 0, 0., np.zeros(3), 0)}
  s = CameraCalibSet(1, 0, CalibIdentity("pc", "imx390", {}), 1.22, np.zeros(3), cams)
  with pytest.raises(ValueError):
    s.camera_from_calib(Cam.DCAM)
  with pytest.raises(ValueError):
    s.warp_matrix(Cam.DCAM)

def test_device_from_calib_inverse():
  s = _calib()
  R = s.device_from_calib()
  assert np.allclose(R @ s.calib_from_device(), np.eye(3))
