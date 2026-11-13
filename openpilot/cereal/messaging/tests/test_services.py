import os
import tempfile
from typing import Dict
from openpilot.common.parameterized import parameterized

import openpilot.cereal as cereal
import openpilot.cereal.services as services
from openpilot.cereal.services import SERVICE_LIST


class TestServices:

  @parameterized.expand(SERVICE_LIST.keys())
  def test_services(self, s):
    service = SERVICE_LIST[s]
    assert service.frequency <= 104
    assert service.decimation != 0

  def test_generated_header(self):
    with tempfile.NamedTemporaryFile(suffix=".h") as f:
      ret = os.system(f"python3 {services.__file__} > {f.name} && clang++ {f.name} -std=c++11")
      assert ret == 0, "generated services header is not valid C"


def _new_event(service: str):
  # Equivalent of messaging.new_message(service), but built straight from the
  # capnp schema: cereal.messaging imports the native msgq extension, which only
  # exists for the target arch. The schema itself needs no codegen.
  evt = cereal.log.Event.new_message()
  evt.init(service)
  return evt


def test_new_live_calibration_fields_exist():
  lc = _new_event('liveCalibration').liveCalibration
  lc.calibSchemaVersion = 1
  lc.calibSeq = 7
  # R3: pycapnp 结构体列表用 init() 建，没有 .add()
  lc.init('cams', 2)
  assert lc.cams[0] is not None  # schema 层面存在即通过

def test_camera_calib_candidate_struct():
  cand = _new_event('cameraCalibCandidate').cameraCalibCandidate
  cand.init('cam', 1)
  e = cand.cam[0]
  e.id = 0
  e.intrinsics = [2637., 2637., 960., 540.]
  e.blocks = 12
  e.mode = "joint_lsq"
  e.std = 0.8
  e.span = 0.02

def test_services_registered():
  assert "cameraCalibCandidate" in SERVICE_LIST
  assert "cameraSyncState" in SERVICE_LIST
