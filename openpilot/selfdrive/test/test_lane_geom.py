"""Synthetic-sequence tests for the L3 lane-geometry focal fit (spec §10.1)."""
import numpy as np

from openpilot.selfdrive.locationd.camcalibd import LaneGeomFitter
from openpilot.common.transformations.camera_calib import build_factory_set, Cam

FX_TRUE_SCALE = 1.03
H, W = 1080, 1920


class FakeLane:
  def __init__(self, side):
    # modelV2 convention: x = forward distance, y = lateral, z = height
    self.x = np.linspace(12, 55, 40).astype(np.float32)
    self.y = np.full(40, side, dtype=np.float32)
    self.z = np.full(40, -0.4, dtype=np.float32)


class FakeModelV2:
  def __init__(self):
    self.laneLines = [None, FakeLane(-1.8), FakeLane(1.8), None]


def render_lane_image():
  """Paint strong edges where the TRUE K (fx scaled 3%) projects the lines."""
  from openpilot.common.transformations.camera import view_frame_from_device_frame
  from openpilot.common.transformations.orientation import rot_from_euler
  cs_true = build_factory_set("pc", "imx390")
  road = cs_true.cams[Cam.ROAD]
  # fx-only deviation: the fitter estimates fx (1 param); scaling fy too would
  # shift rows and hide the fx signal from the ±5 px row-wise snap
  road.fx *= FX_TRUE_SCALE
  K = cs_true.K(Cam.ROAD)
  cam_from_calib = view_frame_from_device_frame @ rot_from_euler(cs_true.body_from_calib) @ np.diag([1.0, -1.0, -1.0])
  img = np.zeros((H, W), dtype=np.uint8)
  for side in (-1.8, 1.8):
    pts = []
    for x_fwd in np.linspace(12, 55, 60):
      p = K @ (cam_from_calib @ np.array([x_fwd, side, -0.4]))
      pts.append((p[0] / p[2], p[1] / p[2]))
    # continuous lane line: connect consecutive projections so the nearest
    # edge is the same line point's edge (real lanes are continuous)
    for (u1, v1), (u2, v2) in zip(pts[:-1], pts[1:]):
      i1, j1, i2, j2 = int(round(v1)), int(round(u1)), int(round(v2)), int(round(u2))
      n = max(abs(i2 - i1), abs(j2 - j1), 1)
      for t in range(n + 1):
        v = int(v1 + (v2 - v1) * t / n)
        u = int(u1 + (u2 - u1) * t / n)
        if 0 < u < W - 1 and 0 < v < H:
          img[v, u] = 255
  return img


def test_lane_geom_recovers_focal():
  cs = build_factory_set("pc", "imx390")
  fitter = LaneGeomFitter(cs)
  img = render_lane_image()
  m = FakeModelV2()
  for _ in range(250):
    fitter.add_sample(m, img)
  info = fitter.fit()
  assert info is not None
  scale = info["f"] / float(cs.cams[Cam.ROAD].fx)
  assert abs(scale - FX_TRUE_SCALE) < 0.01, f"recovered {scale:.4f}, want ~{FX_TRUE_SCALE}"


def test_lane_geom_no_data_returns_none():
  cs = build_factory_set("pc", "imx390")
  fitter = LaneGeomFitter(cs)
  assert fitter.fit() is None
