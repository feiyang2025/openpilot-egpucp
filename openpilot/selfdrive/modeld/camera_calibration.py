"""UI 用的相机标定缓存 —— 本树缺失模块的本地补齐 (local shim)。

`openpilot/selfdrive/ui/onroad/augmented_road_view.py` 第 18 行 import 本模块的
`CalibrationCache`，每帧调用一次 `resolve(params, device_camera, now)`，只用返回值里的
`.road` / `.wide` 的 `.focal_length` 来拼路口投影矩阵。但这个文件在整条链上都不存在：
本树 git 全历史、朋友那棵原树 (feiyang2025/openpilot-egpucp)、sunnypilot 树、overlay 里都没有，
只有 UI 在引用它 —— 少了它就 `ModuleNotFoundError`，UI 直接起不来。

实现刻意不另造一套"当前焦距"口径：数值来自
`openpilot/common/transformations/camera.py` 的 `_camera_config_from_params()`
（它按 FcamIntrinsics / EcamIntrinsics 这两个 Params 的 JSON、以分辨率键取 fl 并缩放，
正是 tools/calib 写入、modeld 也读的那一份）。`resolve()` 最多每 CACHE_TTL 秒重读一次，
所以标定面板写完之后 UI 会在一个 TTL 内跟上，同时不占每帧的热路径。
"""
from __future__ import annotations

import time
from dataclasses import dataclass

CACHE_TTL = 2.0

# 与 camera.py 模块级构造 imx390 配置时用的同一组参数 (见 camera.py 中
# `_imx390_fcam` / `_imx390_ecam`): (宽度 env 键, 高度 env 键, 兜底焦距, Params 键)。
# 单位是 1920x1080 基分辨率下的像素焦距, 由 _camera_config_from_params 按实际宽度缩放。
_ROAD_ARGS = (("ROAD_CAM_WIDTH", "CAM_WIDTH"), ("ROAD_CAM_HEIGHT", "CAM_HEIGHT"), 961.76, "FcamIntrinsics")
_WIDE_ARGS = (("WIDE_CAM_WIDTH", "CAM_WIDTH"), ("WIDE_CAM_HEIGHT", "CAM_HEIGHT"), 1740.0, "EcamIntrinsics")


@dataclass(frozen=True)
class CameraCalibration:
  focal_length: float
  width: int
  height: int
  source: str = "device_camera"  # "device_camera" | "params" | "fallback"

  # 旧代码里焦距有 fx/fy 两种叫法, 这里统一成同一个值 (本树的 CameraConfig 只有一个焦距)
  @property
  def fx(self) -> float:
    return self.focal_length

  @property
  def fy(self) -> float:
    return self.focal_length


@dataclass(frozen=True)
class CalibrationSnapshot:
  road: CameraCalibration
  wide: CameraCalibration
  timestamp: float


def _fallback(config, now: float, label: str) -> CameraCalibration:
  if config is None:
    return CameraCalibration(0.0, 0, 0, source="fallback")
  return CameraCalibration(float(getattr(config, "focal_length", 0.0) or 0.0),
                           int(getattr(config, "width", 0) or 0),
                           int(getattr(config, "height", 0) or 0),
                           source=label)


def _live_config(args, fallback, label: str) -> CameraCalibration:
  try:
    from openpilot.common.transformations.camera import _camera_config_from_params
    cfg = _camera_config_from_params(args[0], args[1], args[2], args[3])
    if cfg is not None and float(getattr(cfg, "focal_length", 0.0) or 0.0) > 0.0:
      return CameraCalibration(float(cfg.focal_length), int(cfg.width), int(cfg.height), source="params")
  except Exception:
    # 读 Params 失败不该让 UI 挂掉, 退回启动时那份 device_camera 配置
    pass
  return _fallback(fallback, 0.0, label)


def _pick(device_camera, *names):
  """按两代命名取相机配置 (narrow_road/fcam, wide_road/ecam)。"""
  for name in names:
    cfg = getattr(device_camera, name, None) if device_camera is not None else None
    if cfg is not None and float(getattr(cfg, "focal_length", 0.0) or 0.0) > 0.0:
      return cfg
  return None


class CalibrationCache:
  """低频刷新的 (road, wide) 内参缓存。``resolve()`` 是 UI 每帧都会调的那一个入口。"""

  def __init__(self, ttl: float = CACHE_TTL):
    self.ttl = float(ttl)
    self._snapshot: CalibrationSnapshot | None = None

  def resolve(self, params=None, device_camera=None, now: float | None = None) -> CalibrationSnapshot:
    now = time.monotonic() if now is None else float(now)
    snap = self._snapshot
    if snap is not None and (now - snap.timestamp) < self.ttl:
      return snap

    # device_camera 是启动时由 camera.py 按 Params 建好的配置, 作为读 Params 失败时的兜底
    road_fallback = _pick(device_camera, "narrow_road", "fcam")
    wide_fallback = _pick(device_camera, "wide_road", "ecam")

    snap = CalibrationSnapshot(
      road=_live_config(_ROAD_ARGS, road_fallback, "device_camera"),
      wide=_live_config(_WIDE_ARGS, wide_fallback, "device_camera"),
      timestamp=now,
    )
    self._snapshot = snap
    return snap
