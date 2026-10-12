import itertools
import numpy as np
from dataclasses import dataclass

import openpilot.common.transformations.orientation as orient

## -- hardcoded hardware params --
@dataclass(frozen=True)
class CameraConfig:
  width: int
  height: int
  focal_length: float

  @property
  def size(self):
    return (self.width, self.height)

  @property
  def intrinsics(self):
    # aka 'K' aka camera_frame_from_view_frame
    return np.array([
      [self.focal_length,  0.0, float(self.width)/2],
      [0.0, self.focal_length, float(self.height)/2],
      [0.0,  0.0, 1.0]
    ])

  @property
  def intrinsics_inv(self):
    # aka 'K_inv' aka view_frame_from_camera_frame
    return np.linalg.inv(self.intrinsics)

@dataclass(frozen=True)
class _NoneCameraConfig(CameraConfig):
  width: int = 0
  height: int = 0
  focal_length: float = 0

@dataclass(frozen=True)
class DeviceCameraConfig:
  fcam: CameraConfig
  dcam: CameraConfig
  ecam: CameraConfig

  def all_cams(self):
    for cam in ['fcam', 'dcam', 'ecam']:
      if not isinstance(getattr(self, cam), _NoneCameraConfig):
        yield cam, getattr(self, cam)

def _read_calib_from_params(param_key, width, height, default_fl):
  from openpilot.common.params import Params
  import json
  raw = Params().get(param_key)
  if raw is None:
    data = {"fl": default_fl, "cx": width / 2.0, "cy": height / 2.0,
            "calibrations": {f"{width}x{height}": {"fl": default_fl, "cx": width / 2.0, "cy": height / 2.0}}}
    try:
      Params().put(param_key, data, block=True)
    except Exception:
      pass
  else:
    data = raw if isinstance(raw, dict) else json.loads(raw)
  calibs = data.get("calibrations")
  if calibs:
    key = f"{width}x{height}"
    entry = calibs.get(key)
    if entry is not None:
      return float(entry.get("fl", default_fl)), float(entry.get("cx", width / 2.0)), float(entry.get("cy", height / 2.0))
    # No exact match: scale from first available calibration entry by width ratio
    for cal_key, cal_entry in calibs.items():
      try:
        cal_w = int(cal_key.split("x")[0])
        scale = width / cal_w
        scaled_fl = float(cal_entry.get("fl", default_fl)) * scale
        return scaled_fl, float(cal_entry.get("cx", width / 2.0)), float(cal_entry.get("cy", height / 2.0))
      except (ValueError, KeyError, IndexError):
        continue
  fl = float(data.get("fl", default_fl))
  return fl, float(data.get("cx", width / 2.0)), float(data.get("cy", height / 2.0))


def _env_or(val, env_key, cast=int):
  import os
  # env_key 可以是单个键或键列表 (按顺序取第一个非空的): 本树 launcher 用 CAM_WIDTH/HEIGHT,
  # 移植脚本身份用 ROAD_/WIDE_CAM_WIDTH —— 名字分家就会让 K 的像素空间与 camerad 实际
  # 送的帧不一致 (1344x760 的帧配 1920x1080 的 K = 模型 warp 尺度偏 1.43 倍)。
  if isinstance(env_key, (list, tuple)):
    for k in env_key:
      env = os.environ.get(k)
      if env:
        return cast(env)
    return val
  env = os.environ.get(env_key)
  return cast(env) if env else val


def _camera_config_from_params(width_env, height_env, base_fl: float, param_key: str, base_w: int = 1920) -> CameraConfig:
  width = _env_or(1920, width_env)
  height = _env_or(1080, height_env)
  fl = base_fl * (width / base_w)
  try:
    calib_fl, _, _ = _read_calib_from_params(param_key, width, height, fl)
    return CameraConfig(width, height, calib_fl)
  except Exception:
    return CameraConfig(width, height, fl)


_ar_ox_fisheye = CameraConfig(1928, 1208, 567.0)  # focal length probably wrong? magnification is not consistent across frame
_os_fisheye = CameraConfig(2688 // 2, 1520 // 2, 567.0 / 4 * 3)
_ar_ox_config = DeviceCameraConfig(CameraConfig(1928, 1208, 2648.0), _ar_ox_fisheye, _ar_ox_fisheye)
_os_config = DeviceCameraConfig(CameraConfig(2688 // 2, 1520 // 2, 1522.0 * 3 / 4), _os_fisheye, _os_fisheye)
_neo_config = DeviceCameraConfig(CameraConfig(1164, 874, 910.0), CameraConfig(816, 612, 650.0), _NoneCameraConfig())

# J501 dual IMX390 first-pass calibration. Both sensors are captured at
# 1920x1080 and resized to 1344x760 by tools/webcam/camera.py.
# video0: rectilinear road camera, stated horizontal FOV 30 degrees.
#   fx = (1344 / 2) / tan(30deg / 2) = 2508.0 px.
# video1: equidistant fisheye wide camera, stated horizontal FOV 190 degrees.
#   f = 1344 / radians(190deg) = 405.2 px.
# CameraConfig currently has one focal value, so fx == fy for this coarse
# alignment. Replace with measured intrinsics/distortion during fine tuning.
_j501_imx390_road = CameraConfig(1344, 760, 2508.0)
_j501_imx390_fisheye = CameraConfig(1344, 760, 405.2)
# USB IMX678 90°(driver 路): rectilinear, fx = (1344/2)/tan(90deg/2) = 672.0 px
# 供 dmonitoring / lane 推理与顶替场景参考;精确值需棋盘格标定。
_j501_usb90_config = CameraConfig(1344, 760, 672.0)
_j501_imx390_config = DeviceCameraConfig(
  _j501_imx390_road,
  _j501_usb90_config,
  _j501_imx390_fisheye,
)

DEVICE_CAMERAS = {
  # A "device camera" is defined by a device type and sensor

  # sensor type was never set on eon/neo/two
  ("neo", "unknown"): _neo_config,
  # unknown here is AR0231, field was added with OX03C10 support
  ("tici", "unknown"): _ar_ox_config,

  # before deviceState.deviceType was set, assume tici AR config
  ("unknown", "ar0231"): _ar_ox_config,
  ("unknown", "ox03c10"): _ar_ox_config,

  # J501/webcam: video0 road (30 deg), video1 wide fisheye (190 deg)
  ("pc", "unknown"): _j501_imx390_config,
  ("pc", "imx390"): _j501_imx390_config,
}
prods = itertools.product(('tici', 'tizi', 'mici'), (('ar0231', _ar_ox_config), ('ox03c10', _ar_ox_config), ('os04c10', _os_config)))
DEVICE_CAMERAS.update({(d, c[0]): c[1] for d, c in prods})


# ---- AGX Orin + Sensing/twgmsl IMX390 GMSL dual camera (PC webcamerad path) ----
#   fcam = road camera: vendor pinhole fl ~= 961.76 @1920x1080
#   ecam = the second camera (exposed as WIDE stream): vendor fl 1740.0 @1920x1080
# Live values are stored in the FcamIntrinsics / EcamIntrinsics Params
# (resolution-keyed JSON written by tools/calib/*); the numbers below are the
# fallback used the first time those Params are created.
# camerad's roadCameraState.sensor enum cannot report imx390, so the ("pc",
# "unknown") entry is replaced instead - the PC path only hits this one entry.
_imx390_fcam = _camera_config_from_params(("ROAD_CAM_WIDTH", "CAM_WIDTH"), ("ROAD_CAM_HEIGHT", "CAM_HEIGHT"), 961.76, "FcamIntrinsics")
_imx390_ecam = _camera_config_from_params(("WIDE_CAM_WIDTH", "CAM_WIDTH"), ("WIDE_CAM_HEIGHT", "CAM_HEIGHT"), 1740.0, "EcamIntrinsics")
DEVICE_CAMERAS[("pc", "unknown")] = DeviceCameraConfig(_imx390_fcam, _imx390_ecam, _imx390_ecam)

# ---- AGX 移植兼容: DeviceCameraConfig 的两代字段名 ----
# 本树 camera.py 的 dataclass 用的是旧名 fcam/dcam/ecam, sp-cuda (连跑 1 个多月
# 的那套) 的 modeld.py / modeld_bigcombo.py / ui 也直接写 dc.fcam / dc.ecam;
# 而 tools/calib/* 读的是新上游名 narrow_road/wide_road/cabin。谁缺就给谁补一个
# 指向另一名的 property, 两个世代都能取到, 不再是"某一边静默 AttributeError"。
# 注意判据必须读 __dataclass_fields__: 无默认值的 dataclass 字段不会生成类属性,
# hasattr(cls, "fcam") 恒为 False —— 之前正是用它做判据, 于是给 fcam/dcam/ecam
# 装上了指向 narrow_road/cabin 的 property, 任何 dc.dcam 访问都 AttributeError。
def _sp_camera_config_aliases():
  fields = set(getattr(DeviceCameraConfig, "__dataclass_fields__", {}))
  if not fields:
    fields = set(getattr(DeviceCameraConfig, "__annotations__", {}))
  for _new, _old in (("narrow_road", "fcam"), ("wide_road", "ecam"), ("cabin", "dcam")):
    if _old in fields and _new not in fields:
      setattr(DeviceCameraConfig, _new, property(lambda self, _o=_old: getattr(self, _o)))
    elif _new in fields and _old not in fields:
      setattr(DeviceCameraConfig, _old, property(lambda self, _n=_new: getattr(self, _n)))


_sp_camera_config_aliases()

# device/mesh : x->forward, y-> right, z->down
# view : x->right, y->down, z->forward
device_frame_from_view_frame = np.array([
  [ 0.,  0.,  1.],
  [ 1.,  0.,  0.],
  [ 0.,  1.,  0.]
])
view_frame_from_device_frame = device_frame_from_view_frame.T


# aka 'extrinsic_matrix'
# road : x->forward, y -> left, z->up
def get_view_frame_from_road_frame(roll, pitch, yaw, height):
  device_from_road = orient.rot_from_euler([roll, pitch, yaw]).dot(np.diag([1, -1, -1]))
  view_from_road = view_frame_from_device_frame.dot(device_from_road)
  return np.hstack((view_from_road, [[0], [height], [0]]))



# aka 'extrinsic_matrix'
def get_view_frame_from_calib_frame(roll, pitch, yaw, height):
  device_from_calib= orient.rot_from_euler([roll, pitch, yaw])
  view_from_calib = view_frame_from_device_frame.dot(device_from_calib)
  return np.hstack((view_from_calib, [[0], [height], [0]]))


def vp_from_ke(m):
  """
  Computes the vanishing point from the product of the intrinsic and extrinsic
  matrices C = KE.

  The vanishing point is defined as lim x->infinity C (x, 0, 0, 1).T
  """
  return (m[0, 0]/m[2, 0], m[1, 0]/m[2, 0])


def roll_from_ke(m):
  # note: different from calibration.h/RollAnglefromKE: i think that one's just wrong
  return np.arctan2(-(m[1, 0] - m[1, 1] * m[2, 0] / m[2, 1]),
                    -(m[0, 0] - m[0, 1] * m[2, 0] / m[2, 1]))


def normalize(img_pts, intrinsics):
  # normalizes image coordinates
  # accepts single pt or array of pts
  intrinsics_inv = np.linalg.inv(intrinsics)
  img_pts = np.array(img_pts)
  input_shape = img_pts.shape
  img_pts = np.atleast_2d(img_pts)
  img_pts = np.hstack((img_pts, np.ones((img_pts.shape[0], 1))))
  img_pts_normalized = img_pts.dot(intrinsics_inv.T)
  img_pts_normalized[(img_pts < 0).any(axis=1)] = np.nan
  return img_pts_normalized[:, :2].reshape(input_shape)


def denormalize(img_pts, intrinsics, width=np.inf, height=np.inf):
  # denormalizes image coordinates
  # accepts single pt or array of pts
  img_pts = np.array(img_pts)
  input_shape = img_pts.shape
  img_pts = np.atleast_2d(img_pts)
  img_pts = np.hstack((img_pts, np.ones((img_pts.shape[0], 1), dtype=img_pts.dtype)))
  img_pts_denormalized = img_pts.dot(intrinsics.T)
  if np.isfinite(width):
    img_pts_denormalized[img_pts_denormalized[:, 0] > width] = np.nan
    img_pts_denormalized[img_pts_denormalized[:, 0] < 0] = np.nan
  if np.isfinite(height):
    img_pts_denormalized[img_pts_denormalized[:, 1] > height] = np.nan
    img_pts_denormalized[img_pts_denormalized[:, 1] < 0] = np.nan
  return img_pts_denormalized[:, :2].reshape(input_shape)


def get_calib_from_vp(vp, intrinsics):
  vp_norm = normalize(vp, intrinsics)
  yaw_calib = np.arctan(vp_norm[0])
  pitch_calib = -np.arctan(vp_norm[1]*np.cos(yaw_calib))
  roll_calib = 0
  return roll_calib, pitch_calib, yaw_calib


def device_from_ecef(pos_ecef, orientation_ecef, pt_ecef):
  # device from ecef frame
  # device frame is x -> forward, y-> right, z -> down
  # accepts single pt or array of pts
  input_shape = pt_ecef.shape
  pt_ecef = np.atleast_2d(pt_ecef)
  ecef_from_device_rot = orient.rotations_from_quats(orientation_ecef)
  device_from_ecef_rot = ecef_from_device_rot.T
  pt_ecef_rel = pt_ecef - pos_ecef
  pt_device = np.einsum('jk,ik->ij', device_from_ecef_rot, pt_ecef_rel)
  return pt_device.reshape(input_shape)


def img_from_device(pt_device):
  # img coordinates from pts in device frame
  # first transforms to view frame, then to img coords
  # accepts single pt or array of pts
  input_shape = pt_device.shape
  pt_device = np.atleast_2d(pt_device)
  pt_view = np.einsum('jk,ik->ij', view_frame_from_device_frame, pt_device)

  # This function should never return negative depths
  pt_view[pt_view[:, 2] < 0] = np.nan

  pt_img = pt_view/pt_view[:, 2:3]
  return pt_img.reshape(input_shape)[:, :2]

