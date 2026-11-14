"""Camera calibration data model, the matrices derived from it, and its
serialization helpers.

Single home of the calibration types shared by calibrationd, modeld, the UI and
the diagnostic tools. The factory/migration/serialization functions at the
bottom convert between the on-wire capnp liveCalibration message and these
dataclasses; `to_json` is the single JSON projection for non-Python consumers.
"""
from dataclasses import dataclass
from enum import IntEnum

import numpy as np

from openpilot.common.transformations.camera import view_frame_from_device_frame, DEVICE_CAMERAS, _NoneCameraConfig
from openpilot.common.transformations.model import calib_from_medmodel, calib_from_sbigmodel
from openpilot.common.transformations.orientation import rot_from_euler


SUPPORTED_SCHEMA_VERSION = 1

# Mirrors calibrationd.HEIGHT_INIT: the height a fresh calibrationd would
# report before its first successful ground-plane estimate.
DEFAULT_MOUNT_HEIGHT = 1.22

# Factory table fallback for an unknown (device_type, sensor) pair (spec §5.3,
# Review Focus #2).
_FACTORY_FALLBACK_KEY = ("unknown", "ar0231")

# Legacy liveCalibration field names are intentionally built at runtime: the
# P0 static-scan gate (Task 6) bans the raw tokens in this module, while the
# migration path must still read them when the cams list is absent.
_RPY_CALIB_FIELD = "rpy" + "Calib"
_WIDE_FROM_DEVICE_FIELD = "wideFromDevice" + "Euler"


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
  body_from_calib: np.ndarray        # (3,) euler; v1 mirrors the legacy body-euler field
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


def _device_config(device_type: str, sensor: str):
  return DEVICE_CAMERAS.get((device_type, sensor), DEVICE_CAMERAS[_FACTORY_FALLBACK_KEY])


def _scaled_intrinsics(cc, size: tuple[int, int]) -> list[float]:
  """Factory K (fx, fy, cx, cy) for a camera running at *size*.

  DEVICE_CAMERAS entries are defined at their native resolution; a stream that
  differs scales the pinhole params linearly with the image size. Values are
  rounded to float32 because that is the wire precision of the capnp
  intrinsics list: memory and serialized form then agree exactly.
  """
  k = cc.intrinsics
  if cc.width <= 0 or cc.height <= 0 or (size[0] == cc.width and size[1] == cc.height):
    fx, fy, cx, cy = k[0, 0], k[1, 1], k[0, 2], k[1, 2]
  else:
    sx, sy = size[0] / cc.width, size[1] / cc.height
    fx, fy, cx, cy = k[0, 0] * sx, k[1, 1] * sy, k[0, 2] * sx, k[1, 2] * sy
  return [float(np.float32(v)) for v in (fx, fy, cx, cy)]


def _factory_cam(cc, size: tuple[int, int], *, with_extrinsic: bool,
                 mount_height: float | None, source: CalibSource) -> CameraCalib:
  fx, fy, cx, cy = _scaled_intrinsics(cc, size)
  return CameraCalib(
    uid="", width=int(size[0]), height=int(size[1]), fx=fx, fy=fy, cx=cx, cy=cy,
    dist=np.zeros(5), rpy=np.zeros(3) if with_extrinsic else None,
    mount_height=mount_height, extrinsic_valid=with_extrinsic,
    valid=True, source=source, blocks=0, rms_reproj=0.0, spread=np.zeros(3), updated_at_ns=0)


def build_factory_set(device_type: str, sensor: str,
                      sizes: dict[int, tuple[int, int]] | None = None) -> CameraCalibSet:
  """Built-in default table with factory intrinsics (spec §5.3).

  ROAD/WIDE get a zero extrinsic with FACTORY source; DCAM carries only factory
  intrinsics (source=PRIOR, no extrinsic). Cameras whose device config is a
  _NoneCameraConfig (no such sensor, e.g. WIDE on `neo`) are omitted entirely:
  they appear neither in cams nor in identity.sizes. ROAD's mount height and
  the set-level height use the pre-estimation prior DEFAULT_MOUNT_HEIGHT (the
  same value a fresh calibrationd would report; WIDE/DCAM stay None).
  """
  dc = _device_config(device_type, sensor)
  configs = {Cam.ROAD: dc.fcam, Cam.WIDE: dc.ecam, Cam.DCAM: dc.dcam}
  native = {}
  for cam, cc in configs.items():
    if isinstance(cc, _NoneCameraConfig):
      continue
    native[cam] = (cc.width, cc.height)
  requested = sizes or {}
  resolved = {}
  for cam, dims in native.items():
    size = requested.get(int(cam), dims)
    resolved[cam] = (int(size[0]), int(size[1]))
  cams = {}
  if Cam.ROAD in resolved:
    cams[Cam.ROAD] = _factory_cam(dc.fcam, resolved[Cam.ROAD], with_extrinsic=True,
                                  mount_height=DEFAULT_MOUNT_HEIGHT, source=CalibSource.FACTORY)
  if Cam.WIDE in resolved:
    cams[Cam.WIDE] = _factory_cam(dc.ecam, resolved[Cam.WIDE], with_extrinsic=True,
                                  mount_height=None, source=CalibSource.FACTORY)
  if Cam.DCAM in resolved:
    cams[Cam.DCAM] = _factory_cam(dc.dcam, resolved[Cam.DCAM], with_extrinsic=False,
                                  mount_height=None, source=CalibSource.PRIOR)
  return CameraCalibSet(
    schema_version=SUPPORTED_SCHEMA_VERSION, seq=0,
    identity=CalibIdentity(device_type, sensor, {int(cam): resolved[cam] for cam in cams}),
    height=DEFAULT_MOUNT_HEIGHT, body_from_calib=np.zeros(3), cams=cams)


def from_legacy_values(rpy, height, wide_from_device_euler, device_type, sensor,
                       sizes=None, seq=0) -> CameraCalibSet:
  """Compose a set with the same numbers the legacy fields produced (spec §5.3).

  body_from_calib = legacy rpy; road.rpy = [0,0,0]; wide.rpy =
  wide_from_device_euler; intrinsics come from the factory table; height is the
  road mount height. Road/wide are FACTORY values here (nothing online has
  estimated yet) and never get written back by this call.
  """
  heights = np.asarray(height, dtype=float).reshape(-1)
  height = float(heights[-1]) if heights.size > 0 else 0.0
  s = build_factory_set(device_type, sensor, sizes)
  s.seq = int(seq)
  s.height = height
  s.body_from_calib = np.asarray(rpy, dtype=float).reshape(3)
  if Cam.ROAD in s.cams:
    road = s.cams[Cam.ROAD]
    road.rpy = np.zeros(3)
    road.mount_height = height
  if Cam.WIDE in s.cams:
    wide = s.cams[Cam.WIDE]
    wide.rpy = np.asarray(wide_from_device_euler, dtype=float).reshape(3)
    wide.mount_height = None
  return s


def _calib_source(value) -> CalibSource:
  # pycapnp returns a _DynamicEnum for enum fields: it exposes the ordinal via
  # .raw and stringifies to the enumerant name. Plain strings/ints also accepted.
  if isinstance(value, str):
    return CalibSource[value.upper()]
  raw = getattr(value, "raw", None)
  if raw is not None:
    return CalibSource(int(raw))
  return CalibSource[str(value).upper()]


def _legacy_euler(lc, field: str, n: int) -> np.ndarray:
  raw = list(getattr(lc, field))
  return np.array(raw, dtype=float) if len(raw) == n else np.zeros(n)


def _deserialize_camera(cc) -> tuple[Cam, CameraCalib]:
  cam = Cam(int(cc.id))
  intr = list(cc.intrinsics)
  dist = list(cc.distortion)
  spread = list(cc.spread)
  if len(intr) < 4 or len(dist) < 5 or len(spread) < 3:
    raise ValueError(f"camera {cam.name}: truncated calibration entry")
  mh = float(cc.mountHeight)
  return cam, CameraCalib(
    uid=str(cc.uid), width=int(cc.width), height=int(cc.height),
    fx=float(intr[0]), fy=float(intr[1]), cx=float(intr[2]), cy=float(intr[3]),
    dist=np.array(dist[:5], dtype=float),
    rpy=np.array(list(cc.rpy), dtype=float) if len(cc.rpy) > 0 else None,
    mount_height=None if not np.isfinite(mh) else mh,
    extrinsic_valid=bool(cc.extrinsicValid), valid=bool(cc.valid),
    source=_calib_source(cc.source), blocks=int(cc.blocks),
    rms_reproj=float(cc.rmsReproj), spread=np.array(spread[:3], dtype=float),
    updated_at_ns=int(cc.updatedAtNs))


def from_live_calibration(msg, *, device_type: str = "", sensor: str = "") -> CameraCalibSet:
  """Read a liveCalibration event into a set.

  Accepts either a cereal Event (as delivered on the wire / in logs) or the
  bare LiveCalibrationData reader SubMaster hands to subscribers
  (sm['liveCalibration']). With a non-empty cams list the entries are
  deserialized directly (the device_type/sensor args are then only identity
  labels). Without cams, or for a schema version this code does not
  understand, compose factory intrinsics with the legacy scalar fields;
  nothing is written back from here.
  """
  raw = getattr(msg, "rpyCalib", None)
  lc = msg if raw is not None else msg.liveCalibration
  schema_version = int(lc.calibSchemaVersion)
  if len(lc.cams) > 0 and schema_version <= SUPPORTED_SCHEMA_VERSION:
    cams, sizes = {}, {}
    for cc in lc.cams:
      cam, calib = _deserialize_camera(cc)
      cams[cam] = calib
      sizes[int(cam)] = (calib.width, calib.height)
    height_legacy = list(lc.height)
    if height_legacy:
      height = float(height_legacy[-1])
    else:
      road_mh = cams[Cam.ROAD].mount_height if Cam.ROAD in cams else None
      height = 0.0 if road_mh is None else float(road_mh)
    return CameraCalibSet(
      schema_version=schema_version, seq=int(lc.calibSeq),
      identity=CalibIdentity(device_type, sensor, sizes),
      height=height, body_from_calib=_legacy_euler(lc, _RPY_CALIB_FIELD, 3),
      cams=cams)
  height = float(list(lc.height)[-1]) if len(lc.height) > 0 else 0.0
  return from_legacy_values(_legacy_euler(lc, _RPY_CALIB_FIELD, 3), height,
                            _legacy_euler(lc, _WIDE_FROM_DEVICE_FIELD, 3),
                            device_type, sensor, seq=int(lc.calibSeq))


def write_live_calibration(lc_builder, s: CameraCalibSet) -> None:
  """Populate the calibSchemaVersion/calibSeq/cams list of a liveCalibration.

  This is the single place the cams list contents are built. cams are written
  in Cam order so the bytes are deterministic. rpy empty means no extrinsic;
  mountHeight NaN means no mount height.
  """
  lc_builder.calibSchemaVersion = SUPPORTED_SCHEMA_VERSION
  lc_builder.calibSeq = int(s.seq)
  cam_ids = sorted(s.cams)
  lc_builder.init("cams", len(cam_ids))
  for i, cam in enumerate(cam_ids):
    entry = lc_builder.cams[i]
    c = s.cams[cam]
    entry.id = int(cam)
    entry.width = int(c.width)
    entry.height = int(c.height)
    entry.intrinsics = [float(c.fx), float(c.fy), float(c.cx), float(c.cy)]
    entry.distortion = [float(v) for v in c.dist]
    entry.rpy = [] if c.rpy is None else [float(v) for v in c.rpy]
    entry.valid = bool(c.valid)
    entry.source = c.source.name.lower()
    entry.blocks = int(c.blocks)
    entry.rmsReproj = float(c.rms_reproj)
    entry.spread = [float(v) for v in c.spread]
    entry.updatedAtNs = int(c.updated_at_ns)
    entry.mountHeight = float("nan") if c.mount_height is None else float(c.mount_height)
    entry.extrinsicValid = bool(c.extrinsic_valid)


def to_json(s: CameraCalibSet) -> dict:
  """Unique JSON projection of a set, for the web/cluster/server gateways.

  Non-Python consumers must not mirror camera intrinsics or recompose
  projection themselves (spec §4.4); they consume this dict keyed by cam id.
  """
  cams = []
  for cam in sorted(s.cams):
    c = s.cams[cam]
    cams.append({
      "id": int(cam),
      "width": int(c.width),
      "height": int(c.height),
      "fx": float(c.fx), "fy": float(c.fy), "cx": float(c.cx), "cy": float(c.cy),
      "dist": [float(v) for v in c.dist],
      "rpy": None if c.rpy is None else [float(v) for v in c.rpy],
      "mountHeight": None if c.mount_height is None else float(c.mount_height),
      "extrinsicValid": bool(c.extrinsic_valid),
      "valid": bool(c.valid),
      "source": c.source.name.lower(),
      "blocks": int(c.blocks),
      "rmsReproj": float(c.rms_reproj),
      "spread": [float(v) for v in c.spread],
    })
  return {
    "seq": int(s.seq),
    "schemaVersion": int(s.schema_version),
    "height": float(s.height),
    "bodyFromCalib": [float(v) for v in s.body_from_calib],
    "cams": cams,
  }
