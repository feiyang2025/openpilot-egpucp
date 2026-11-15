"""Static scan gate for the camera-calibration single-source rule (spec §10.6).

No runtime code may read the legacy calibration fields (rpyCalib,
wideFromDeviceEuler), the calibration parameter store, or DEVICE_CAMERAS to
compose its own matrices. Everything must go through
common/transformations/camera_calib.py (CameraCalibSet) or the to_json
gateway.

Legacy exceptions are explicit:
  - ALLOWED_FILES: the single implementation and the single writer.
  - a line carrying '# calib-legacy-allow: <reason>' is an allowed legacy read;
    each one must state why and is expected to be deleted as migration lands.
  - PARAM_KEY_ONLY files may name the CalibrationParams key (backup/erase/
    presence checks) but must not parse its fields.
"""

import re
from pathlib import Path

import pytest

OPENPILOT_ROOT = Path(__file__).resolve().parents[2]  # .../openpilot

BANNED_PATTERNS = [
  ("rpyCalib", re.compile(r"\brpyCalib\b")),
  ("wideFromDeviceEuler", re.compile(r"\bwideFromDeviceEuler\b")),
  ("CalibrationParams", re.compile(r"\bCalibrationParams\b")),
  ("DEVICE_CAMERAS[", re.compile(r"DEVICE_CAMERAS\s*\[")),
]

# Files exempted entirely (single implementation / single writer).
ALLOWED_FILES = {
  "common/transformations/camera_calib.py",
  "selfdrive/locationd/calibrationd.py",
}

# Files that may mention the CalibrationParams key name without parsing its
# fields (backup / erase / presence checks).
PARAM_KEY_ONLY = {
  "selfdrive/carrot/server/features/system.py",
  "selfdrive/carrot/server/features/tools/dispatcher.py",
  "selfdrive/carrot/server/features/intro/state.py",
  "selfdrive/ui/layouts/settings/device.py",
  "selfdrive/ui/mici/layouts/settings/device.py",
  "selfdrive/carrot/server/services/device_info.py",
}

MARKER = "calib-legacy-allow"


def _iter_targets():
  roots = ["selfdrive", "common", "system"]
  exclude = re.compile(
    r"(^|/)(tests?|cereal/gen|__pycache__)(/|$)|test_|_test|/tools/|replay|generated")
  for root in roots:
    base = OPENPILOT_ROOT / root
    if not base.exists():
      continue
    for p in base.rglob("*.py"):
      rel = str(p.relative_to(OPENPILOT_ROOT))
      if exclude.search(rel):
        continue
      yield rel, p


def _js_targets():
  web = OPENPILOT_ROOT / "selfdrive" / "carrot" / "web"
  exclude = re.compile(r"generated|node_modules|\.min\.js")
  if web.exists():
    for p in web.rglob("*.js"):
      rel = str(p.relative_to(OPENPILOT_ROOT))
      if exclude.search(rel):
        continue
      yield rel, p


def test_no_direct_calib_readers():
  violations = []
  for rel, path in _iter_targets():
    try:
      lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
      continue
    for lineno, line in enumerate(lines, 1):
      if MARKER in line:
        continue
      if rel in ALLOWED_FILES:
        continue
      for name, pattern in BANNED_PATTERNS:
        if not pattern.search(line):
          continue
        if name == "CalibrationParams" and rel in PARAM_KEY_ONLY:
          continue
        violations.append(f"{rel}:{lineno}: {name}: {line.strip()[:120]}")
  assert not violations, (
    "Direct calibration readers found (use CameraCalibSet / to_json gateway, "
    "or add '# calib-legacy-allow: <reason>' with a migration plan):\n"
    + "\n".join(violations))


def test_legacy_allow_markers_have_reasons():
  lazy = []
  for rel, path in _iter_targets():
    try:
      text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
      continue
    for lineno, line in enumerate(text.splitlines(), 1):
      if MARKER in line and not re.search(MARKER + r"\s*:\s*\S", line):
        lazy.append(f"{rel}:{lineno}")
  assert not lazy, "calib-legacy-allow markers must state a reason:\n" + "\n".join(lazy)


def test_web_js_no_intrinsics_mirror():
  violations = []
  js_banned = [re.compile(r"\bDEVICE_CAMERAS\b"), re.compile(r"\brpyCalib\b")]
  for rel, path in _js_targets():
    try:
      lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
      continue
    for lineno, line in enumerate(lines, 1):
      if "calib-legacy-allow" in line:
        continue
      for pattern in js_banned:
        if pattern.search(line):
          violations.append(f"{rel}:{lineno}: {line.strip()[:120]}")
  assert not violations, (
    "web/js must consume the to_json gateway, not mirror intrinsics/legacy "
    "fields (see spec §7.4):\n" + "\n".join(violations))
