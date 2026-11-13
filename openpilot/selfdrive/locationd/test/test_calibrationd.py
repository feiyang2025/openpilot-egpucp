import numpy as np
from openpilot.selfdrive.locationd.calibrationd import Calibrator
from openpilot.common.transformations.camera_calib import build_factory_set, Cam


def _calibrator_with_set():
  c = Calibrator(param_put=False)
  c.set_calib_set(build_factory_set("pc", "imx390"))
  return c


def test_get_msg_contains_cams():
  c = _calibrator_with_set()
  c.handle_v_ego(20.)
  c.handle_cam_odom([20., 0., 0.], [0., 0., 0.], [0., 0., 0.03], [0., 0., 0.],
                    [0., 0., 1.22], [0., 0., 0.5e-3])
  c.update_status()
  msg = c.get_msg(True)
  assert len(msg.liveCalibration.cams) == 3
  ids = [m.id for m in msg.liveCalibration.cams]
  assert set(ids) == {0, 1, 5}
  assert msg.liveCalibration.calibSchemaVersion == 1


def test_get_msg_no_calib_set_emits_legacy_only():
  c = Calibrator(param_put=False)
  msg = c.get_msg(True)
  assert len(msg.liveCalibration.cams) == 0
  assert msg.liveCalibration.rpyCalib  # 旧字段仍在


def test_seq_monotonic_across_writes():
  # R8: seq 随 write_this_cycle 递增，与 param_put 无关
  c = _calibrator_with_set()
  c.block_idx, c.idx = 5, 0
  c.update_status()
  s1 = c.calib_set.seq
  c.block_idx, c.idx = 15, 0
  c.update_status()
  assert c.calib_set.seq > s1