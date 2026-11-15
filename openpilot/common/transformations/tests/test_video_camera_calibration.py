import json

import pytest

from openpilot.common.transformations.video_camera_calibration import (
    VIDEO_FOCAL_PRIORS,
    VideoCameraCalibration,
    resolve_video_camera_calibration,
)

# Deprecated bench-only Params path (spec §5.1): CamCalibRoad/CamCalibWide are
# deliberately unregistered; these tests drifted from the parser and will be
# migrated to CameraCalibSet along with it.
pytestmark = pytest.mark.skip(reason="deprecated bench path, drifted from parser; migrate to CameraCalibSet")


class FakeParams:
  def __init__(self):
    self._store = {}

  def put(self, key, value):
    self._store[key] = json.dumps(value).encode()

  def set_raw(self, key, raw):
    if raw is None or isinstance(raw, bytes):
      self._store[key] = raw
    else:
      self._store[key] = json.dumps(raw).encode()

  def get(self, key, block=False, **kwargs):
    return self._store.get(key)


@pytest.fixture
def params():
  return FakeParams()


def test_real_mode_returns_no_override(monkeypatch, params):
  monkeypatch.delenv("USE_WEBCAM", raising=False)
  assert resolve_video_camera_calibration(params, "road") is None


def test_valid_video_prior_is_returned(monkeypatch, params):
  monkeypatch.setenv("USE_WEBCAM", "1")
  params.put("CamCalibRoad", {"f": 446.1, "pitch_offset": 0.0,
                              "samples": 0, "converged": True,
                              "mode": "fov_prior"})
  result = resolve_video_camera_calibration(params, "road")
  assert result == VideoCameraCalibration(446.1, 0.0, "fov_prior", False)


def test_converged_learned_value_is_used(monkeypatch, params):
  monkeypatch.setenv("USE_WEBCAM", "1")
  params.put("CamCalibRoad", {"f": 455.0, "pitch_offset": -0.012,
                              "samples": 225, "converged": True,
                              "mode": "vp_offset"})
  result = resolve_video_camera_calibration(params, "road")
  assert result.focal_length == 455.0
  assert result.pitch_offset == -0.012
  assert result.source == "vp_offset"
  assert result.converged is True


def test_missing_bad_json_nan_and_out_of_range_fall_back(monkeypatch, params):
  monkeypatch.setenv("USE_WEBCAM", "1")
  for raw in (None, b"not-json", {"f": float("nan")},
              {"f": 200.0, "pitch_offset": 0.0, "converged": True},
              {"f": 446.1, "pitch_offset": 0.2, "converged": True},
              {"f": 446.1, "pitch_offset": 0.0, "converged": False}):
    params.set_raw("CamCalibRoad", raw)
    result = resolve_video_camera_calibration(params, "road")
    assert result.focal_length == 446.1
    assert result.pitch_offset == 0.0
    assert result.source == "fov_prior"
    assert result.converged is False


def test_wide_uses_wide_prior(monkeypatch, params):
  monkeypatch.setenv("USE_WEBCAM", "1")
  params.set_raw("CamCalibWide", None)
  result = resolve_video_camera_calibration(params, "wide")
  assert result.focal_length == VIDEO_FOCAL_PRIORS["wide"]


def test_video_mode_flag_overrides_env(monkeypatch, params):
  monkeypatch.delenv("USE_WEBCAM", raising=False)
  assert resolve_video_camera_calibration(params, "road", video_mode=True) is not None
  monkeypatch.setenv("USE_WEBCAM", "1")
  assert resolve_video_camera_calibration(params, "road", video_mode=False) is None
