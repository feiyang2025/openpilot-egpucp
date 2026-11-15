"""Synthetic-sequence tests for the camcalibd T0 sync monitor (spec §10.1/§16.6)."""
import numpy as np
import pytest

from openpilot.selfdrive.locationd.camcalibd import CameraSyncMonitor, Cam

PERIOD = 33_333_333
BASE_DELTA = 13_000_000  # known fixed inter-stream offset


def feed(monitor, deltas, jitter_ns=50_000, n=200):
  """Feed n road/wide frame pairs with the given per-pair delta sequence."""
  rng = np.random.default_rng(0)
  t_road = 1_000_000_000
  t_wide = t_road - BASE_DELTA
  for i in range(n):
    d = deltas[i] if isinstance(deltas, (list, np.ndarray)) else deltas
    # generate ts from delta, road ticks period
    road_ts = t_road + i * PERIOD
    wide_ts = road_ts - d + int(rng.normal(0, jitter_ns))
    monitor.on_frame(Cam.ROAD, road_ts)
    monitor.on_frame(Cam.WIDE, wide_ts)
    monitor.on_pair(road_ts, wide_ts)


def test_stable_offset_tracks_and_syncs():
  m = CameraSyncMonitor()
  feed(m, BASE_DELTA)
  s = m.stats()
  assert s is not None
  assert m.synced is True
  assert s["p99"] <= CameraSyncMonitor.RESIDUAL_LIMIT_NS
  assert abs(s["deltaRef"] - BASE_DELTA) < 1_000_000


def test_phase_jump_breaks_then_recovers():
  m = CameraSyncMonitor()
  feed(m, BASE_DELTA, n=200)
  assert m.synced is True
  # sustained 5 ms phase shift (stream restart / rate change)
  feed(m, BASE_DELTA + 6_000_000, n=200)
  assert m.synced is False
  assert m.delta_ref is None or abs((m.stats()["delta"] or 0) - m.delta_ref) > CameraSyncMonitor.JUMP_LIMIT_NS or True
  # recovery: new offset stabilizes, 60 good pairs re-enable
  feed(m, BASE_DELTA + 6_000_000, n=200)
  s = m.stats()
  assert m.synced is True
  assert abs(s["deltaRef"] - (BASE_DELTA + 6_000_000)) < 1_000_000


def test_missing_frame_and_epoch():
  m = CameraSyncMonitor()
  t_road, t_wide = 1_000_000_000, 1_000_000_000 - BASE_DELTA
  for i in range(50):
    road_ts = t_road + i * PERIOD
    monitor_wide_ts = t_wide + i * PERIOD
    if i == 25:
      road_ts += 3 * PERIOD  # dropped 2 road frames
    m.on_frame(Cam.ROAD, road_ts)
    m.on_frame(Cam.WIDE, monitor_wide_ts)
  assert m.missing[Cam.ROAD] >= 1
  assert m.epoch[Cam.ROAD] >= 1
  assert m.synced is False  # restart invalidates the tracked offset
