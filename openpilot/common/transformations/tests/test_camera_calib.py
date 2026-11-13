import numpy as np
import pytest
import openpilot.cereal as cereal
from openpilot.common.transformations.camera import view_frame_from_device_frame
from openpilot.common.transformations.orientation import rot_from_euler
from openpilot.common.transformations.model import get_warp_matrix
from openpilot.common.transformations.camera_calib import (Cam, CalibSource, CameraCalib, CameraCalibSet, CalibIdentity,
                                                           build_factory_set, from_legacy_values,
                                                           from_live_calibration, write_live_calibration, to_json)


def _new_event(service: str):
  # Equivalent of messaging.new_message(service), built straight from the capnp
  # schema: cereal.messaging imports the native msgq extension, which only
  # exists for the target arch.
  evt = cereal.log.Event.new_message()
  evt.init(service)
  return evt

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

def test_factory_set_matches_device_cameras():
  from openpilot.common.transformations.camera import DEVICE_CAMERAS
  s = build_factory_set("pc", "imx390")
  dc = DEVICE_CAMERAS[("pc", "imx390")]
  assert np.allclose(s.K(Cam.ROAD), dc.fcam.intrinsics)
  assert np.allclose(s.K(Cam.WIDE), dc.ecam.intrinsics)
  assert np.allclose(s.K(Cam.DCAM), dc.dcam.intrinsics)
  assert s.cams[Cam.DCAM].extrinsic_valid is False and s.cams[Cam.DCAM].source == CalibSource.PRIOR
  assert Cam.LEFT not in s.cams

def test_factory_set_unknown_sensor_falls_back():
  s = build_factory_set("tici", "something_new")
  assert s.cams[Cam.ROAD].width > 0   # 不抛 KeyError

def test_legacy_composition_matches_doc():
  rpy = np.array([0., 0.05, 0.01])
  height = np.array([1.22])
  wide = np.array([0., 0., 0.03])
  s = from_legacy_values(rpy, height, wide, "pc", "imx390")
  assert np.allclose(s.body_from_calib, rpy)
  assert np.allclose(s.cams[Cam.ROAD].rpy, np.zeros(3))
  assert np.allclose(s.cams[Cam.WIDE].rpy, wide)
  assert s.height == 1.22 and s.cams[Cam.WIDE].mount_height is None

def test_live_calibration_roundtrip_preserves_values():
  s0 = from_legacy_values(np.array([0., 0.05, 0.01]), np.array([1.22]),
                          np.array([0., 0., 0.03]), "pc", "imx390")
  msg = _new_event('liveCalibration')
  write_live_calibration(msg.liveCalibration, s0)
  s1 = from_live_calibration(msg)
  assert s1.schema_version == 1 and s1.seq == s0.seq
  for cam in (Cam.ROAD, Cam.WIDE, Cam.DCAM):
    a, b = s0.cams[cam], s1.cams[cam]
    assert (a.fx, a.fy, a.cx, a.cy) == (b.fx, b.fy, b.cx, b.cy)
    assert np.allclose(a.rpy if a.rpy is not None else [], b.rpy if b.rpy is not None else [])
    assert a.valid == b.valid and a.source == b.source

def test_legacy_bytes_without_cams_falls_back():
  # 构造一个只有旧字段的 liveCalibration 消息
  msg = _new_event('liveCalibration')
  msg.liveCalibration.rpyCalib = [0., 0.05, 0.01]
  msg.liveCalibration.height = [1.22]
  msg.liveCalibration.wideFromDeviceEuler = [0., 0., 0.03]
  s = from_live_calibration(msg, device_type="pc", sensor="imx390")
  assert s.cams[Cam.ROAD].source == CalibSource.FACTORY  # 降级，非 AUTO

def test_to_json_shape():
  s = from_legacy_values(np.zeros(3), np.array([1.22]), np.zeros(3), "pc", "imx390")
  j = to_json(s)
  assert set(j) == {"seq", "schemaVersion", "height", "bodyFromCalib", "cams"}
  assert {c["id"] for c in j["cams"]} == {0, 1, 5}
