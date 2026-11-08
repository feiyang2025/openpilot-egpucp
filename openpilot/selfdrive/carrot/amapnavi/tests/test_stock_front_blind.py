#!/usr/bin/env python3
"""原车前侧盲区（stock_front_blind）的判据测试。

覆盖三件事：

1. **横向不再判定**：``leadLeft/leadRight`` 由 ``controls/lib/side_leads.py``
   产出，那里已经用 ``dPath`` 把本车道（``|dPath| < 1.8``）和更外侧
   （``|dPath| >= 3.5``）的目标滤掉了，并且提前做了 ``dRel > 5.0`` 的近距
   过滤。本模块再按 ``yRel`` 判一遍是重复的，而且 ``yRel``（到车中心线）与
   ``dPath``（到预测路径）在弯道上结论相反，只会把上游判对的结果推翻。
   所以横向偏移现在只出现在 ``SideDecision.lateral_m`` 里供调试，不参与判定。

2. **时距默认关闭**（``StockFrontTimeHeadway = 0``）：``safe`` 退化为
   ``min_clearance``（默认 4.0m），即纯绝对距离判据。是否启用时距由该参数
   决定，两条路径都在下面覆盖。

3. **间距在变大时不该一直报盲区**：早期只用 ``safe = v_ego × 时距`` 去比
   纵向间距，侧前车加速远离到二三十米外黄圈还挂着（高速下 safe 可达 30m+）。
"""

import unittest
from dataclasses import replace
from types import SimpleNamespace

from openpilot.selfdrive.carrot.amapnavi.stock_front_blind import (
  StockFrontBlindConfig, StockFrontBlindMonitor, evaluate_side,
)

# 出厂默认配置（time_headway_s = 0 → 只用绝对距离）
CFG = StockFrontBlindConfig()

# 复现"时距打开"的旧配置，用来锁住 receding 那条修复
TH_CFG = replace(CFG, time_headway_s=1.5)


def lead(drel, vrel, dpath=3.0, present=True):
  """造一个 LeadData 替身。dpath/yRel 只影响 lateral_m 诊断字段。"""
  return SimpleNamespace(dRel=drel, vRel=vrel, yRel=dpath, dPath=dpath,
                         present=present)


class TestLateralNoLongerGated(unittest.TestCase):
  """横向筛选已交给 side_leads，本模块不应因 yRel/dPath 改变结论。"""

  def test_any_lateral_offset_gives_same_result(self):
    for lat in (0.5, 1.0, 1.8, 2.5, 3.4, 6.0, 20.0):
      d = evaluate_side(lead(25.0, -10.0, dpath=lat), v_ego_mps=20.0, cfg=CFG)
      self.assertTrue(d.raw, f"lat={lat} 不应被横向拦掉: {d}")
      self.assertEqual(d.reason, "clearance", f"lat={lat}: {d}")

  def test_lateral_still_available_for_debug(self):
    d = evaluate_side(lead(25.0, -10.0, dpath=2.75), v_ego_mps=20.0, cfg=CFG)
    self.assertAlmostEqual(d.lateral_m, 2.75, places=3)


class TestTimeHeadwayDisabledByDefault(unittest.TestCase):
  """默认 time_headway_s = 0，safe 恒为 min_clearance，跟车速无关。"""

  def test_safe_equals_min_clearance(self):
    for v in (0.0, 10.0, 20.0, 30.0):
      safe = max(v * CFG.time_headway_s, CFG.min_clearance_m)
      self.assertAlmostEqual(safe, CFG.min_clearance_m, places=6)

  def test_same_speed_far_target_not_blind(self):
    """时距关闭 → 25m 等速不报。"""
    d = evaluate_side(lead(25.0, 0.0), v_ego_mps=20.0, cfg=CFG)
    self.assertFalse(d.raw, d)
    self.assertEqual(d.reason, "clear", d)

  def test_same_speed_blind_when_time_headway_enabled(self):
    """时距 1.5s：20m/s → safe = 30m，25m 等速就会报。"""
    d = evaluate_side(lead(25.0, 0.0), v_ego_mps=20.0, cfg=TH_CFG)
    self.assertTrue(d.raw, d)
    self.assertEqual(d.reason, "clearance", d)

  def test_slow_closing_not_blind_by_default(self):
    """25m、相对 -5 m/s：窗口末 10m，> 4m 兜底 → 不报（时距关闭时）。"""
    d = evaluate_side(lead(25.0, -5.0), v_ego_mps=20.0, cfg=CFG)
    self.assertFalse(d.raw, d)
    self.assertAlmostEqual(d.clearance_m, 10.0, places=3)

  def test_fast_closing_zeroes_clearance(self):
    """接近速度够大 → 窗口内会并肩通过，clearance 归零，必报。"""
    d = evaluate_side(lead(25.0, -10.0), v_ego_mps=20.0, cfg=CFG)
    self.assertTrue(d.raw, d)
    self.assertEqual(d.reason, "clearance", d)
    self.assertEqual(d.clearance_m, 0.0, d)

  def test_slow_target_at_high_speed_still_blind(self):
    """侧前车很慢（5 m/s）而本车 20 m/s —— clearance 归零，必须报。"""
    d = evaluate_side(lead(40.0, -15.0), v_ego_mps=20.0, cfg=CFG)
    self.assertTrue(d.raw, d)
    self.assertEqual(d.clearance_m, 0.0, d)

  def test_ttc_value_reported(self):
    d = evaluate_side(lead(20.0, -10.0), v_ego_mps=5.0, cfg=CFG)
    self.assertIsNotNone(d.ttc_s, d)
    self.assertAlmostEqual(d.ttc_s, 2.0, places=3)


class TestRecedingTargetClearsBlindSpot(unittest.TestCase):
  """间距在变大时不该一直报盲区（时距打开时最严重）。"""

  def test_fast_car_pulling_away_is_not_blind(self):
    """侧前车比本车快、已经跑到 25m 外 —— 不报。

    时距 1.5s 时 safe = 30m，若按纯距离判 25 < 30 会报；
    间距在变大时改用 min_clearance 兜底，25m 远不需要管。
    """
    d = evaluate_side(lead(25.0, +5.0), v_ego_mps=20.0, cfg=TH_CFG)
    self.assertFalse(d.raw, d)
    self.assertEqual(d.reason, "receding", d)

  def test_higher_speed_makes_old_bug_worse(self):
    """车速越高 safe 越大，误报越容易 —— 逐个速度点确认都已消除。"""
    for v in (10.0, 15.0, 20.0, 25.0, 30.0):
      safe = max(v * TH_CFG.time_headway_s, TH_CFG.min_clearance_m)
      drel = safe + 5.0
      d = evaluate_side(lead(drel - 1.0, +5.0), v_ego_mps=v, cfg=TH_CFG)
      self.assertFalse(d.raw, f"v_ego={v} safe={safe:.1f} drel={drel - 1.0}: {d}")

  def test_very_close_receding_still_blind(self):
    """间距在变大，但已经近到快要并肩 —— 仍然必须报（安全底线）。"""
    d = evaluate_side(lead(2.0, +5.0), v_ego_mps=20.0, cfg=CFG)
    self.assertTrue(d.raw, d)
    self.assertEqual(d.reason, "clearance", d)

  def test_receding_threshold_boundary(self):
    """刚好等于 min_clearance 不算冲突（严格小于），避免边界抖动。"""
    inside = evaluate_side(lead(CFG.min_clearance_m - 0.01, +1.0), v_ego_mps=20.0, cfg=CFG)
    outside = evaluate_side(lead(CFG.min_clearance_m, +1.0), v_ego_mps=20.0, cfg=CFG)
    self.assertTrue(inside.raw, inside)
    self.assertFalse(outside.raw, outside)


class TestLongitudinalWindow(unittest.TestCase):
  """原车前雷达只可能探测到前方目标。"""

  def test_target_behind_ignored(self):
    """dRel <= 0 一律不纳入（上游 side_leads 也已保证 dRel > 5.0）。"""
    d = evaluate_side(lead(-10.0, +5.0), v_ego_mps=20.0, cfg=CFG)
    self.assertFalse(d.raw, d)
    self.assertEqual(d.reason, "out_of_range", d)

  def test_zero_drel_ignored(self):
    d = evaluate_side(lead(0.0, -5.0), v_ego_mps=20.0, cfg=CFG)
    self.assertFalse(d.raw, d)
    self.assertEqual(d.reason, "out_of_range", d)

  def test_beyond_longitudinal_window_ignored(self):
    d = evaluate_side(lead(CFG.drel_max_m + 1.0, -5.0), v_ego_mps=20.0, cfg=CFG)
    self.assertFalse(d.raw, d)
    self.assertEqual(d.reason, "out_of_range", d)

  def test_inside_longitudinal_window_still_evaluated(self):
    """窗口内要进入风险评估（不因距离远就 early-return）。"""
    d = evaluate_side(lead(CFG.drel_max_m - 1.0, 0.0), v_ego_mps=20.0, cfg=CFG)
    self.assertNotEqual(d.reason, "out_of_range", d)
    self.assertFalse(d.raw, d)


class TestMissingTarget(unittest.TestCase):

  def test_absent_target(self):
    d = evaluate_side(lead(25.0, -5.0, present=False), v_ego_mps=20.0, cfg=CFG)
    self.assertFalse(d.raw, d)
    self.assertEqual(d.reason, "no_target", d)

  def test_none_target(self):
    d = evaluate_side(None, v_ego_mps=20.0, cfg=CFG)
    self.assertFalse(d.raw, d)
    self.assertEqual(d.reason, "no_target", d)


class TestMonitorHysteresis(unittest.TestCase):
  """迟滞照旧：进入要 on_time，退出要 off_time。"""

  def test_receding_target_clears_after_off_time(self):
    cfg = StockFrontBlindConfig()
    cfg.enable = True
    mon = StockFrontBlindMonitor(cfg=cfg)
    dt = 0.05

    # 5m 处正在被追上 → clearance 归零，置位
    closing = {"left": lead(5.0, -5.0)}
    for _ in range(int(cfg.on_time_s / dt) + 2):
      mon.update(dt, 20.0, closing)
    self.assertTrue(mon.detail("left").active, mon.detail("left"))

    # 同一位置但加速远离 → raw 立刻变 False
    receding = {"left": lead(5.0, +5.0)}
    mon.update(dt, 20.0, receding)
    self.assertFalse(mon.detail("left").raw, mon.detail("left"))

    # 超过 off_time 后状态清掉
    for _ in range(int(cfg.off_time_s / dt) + 2):
      mon.update(dt, 20.0, receding)
    self.assertFalse(mon.detail("left").active, mon.detail("left"))

  def test_disabled_returns_false(self):
    cfg = StockFrontBlindConfig()
    cfg.enable = False
    mon = StockFrontBlindMonitor(cfg=cfg)
    out = mon.update(0.05, 20.0, {"left": lead(5.0, -5.0)})
    self.assertEqual(out, {"left": False, "right": False})


if __name__ == "__main__":
  unittest.main()
