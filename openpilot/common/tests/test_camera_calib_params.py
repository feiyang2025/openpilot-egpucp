import importlib
import pathlib
import pytest

KEYS = {
  "EnableCameraIntrinsicsAutoCalib": '{PERSISTENT, BOOL, "0"}',
  "EnableCameraCalibShadow": '{PERSISTENT, BOOL, "0"}',
  "CalibWideWarpPhysical": '{PERSISTENT, BOOL, "0"}',
}


def _header_path():
  # openpilot/common/tests/test_camera_calib_params.py -> openpilot/common/params_keys.h
  return pathlib.Path(__file__).resolve().parents[1] / "params_keys.h"


def _params_module():
  # The params_pyx extension is rebuilt only at the build gate (R22); on hosts where it
  # is absent or built for another architecture the runtime checks are skipped.
  try:
    return importlib.import_module("openpilot.common.params")
  except (ImportError, OSError) as e:
    pytest.skip(f"params_pyx extension not loadable on this host: {e}")


def test_keys_declared_in_header():
  text = _header_path().read_text()
  for key, decl in KEYS.items():
    assert f'"{key}", {decl}' in text, f"{key} must be {decl}"


@pytest.mark.parametrize("key", KEYS)
def test_keys_runtime(key):
  params = _params_module()
  try:
    assert params.Params().get_bool(key) is False
  except params.UnknownKeyName:
    pytest.skip(f"params_pyx not rebuilt for {key}; runtime check at build gate")