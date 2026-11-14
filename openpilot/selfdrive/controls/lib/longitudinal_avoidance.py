#!/usr/bin/env python3
"""P1 避让执行器——AvoidanceState → 纵向命令 floor(台架层)。

文档判据映射(全部已签,零新决策):
  PREPARE   → 松油门/预建压,|a|≤0.2 m/s²(§4.1 无感准备)
  COMFORT   → 舒适减速 floor -3.0 m/s²(§4.1;单目 D1 仅 ≤45kmh,decider 已门,此处双保险)
  EMERGENCY → ≥6 m/s²(§0.7 低矮/静止类 AEB 交接语义;单目实车=AEB 移交,台架仿真直验证命令层)
只取 min:不放松已有更深制动(MPC 更狠时原样保留)。
失效安全:avoidanceState 陈旧(>300ms)/无效/总闸关 → 恒等不变(行车链零扰动)。
总闸:AvoidanceExecEnabled(PERSISTENT 默认 OFF)——实车永不默认生效。
"""
import json
import time


class AvoidanceExecutor:
  A_PREPARE = -0.2
  A_COMFORT = -3.0
  A_EMERGENCY = -6.0
  MONO_COMFORT_CAP_MS = 45.0 / 3.6          # D1 单目(45 kmh)
  STALE_S = 0.30
  HB = "/tmp/avoidance_exec.json"

  def __init__(self, mono_profile: bool = True):
    self.mono = mono_profile
    self.hb_t = 0.0
    self.last = {"applied": False}

  def floor_for(self, tiers, v_ego_ms: float, now_mono: float, mono_time_ns: int,
                enabled: bool, engaged: bool):
    """tiers=[tier...](activity tiers);返回 (a_floor 或 None=不动, reason)"""
    if not enabled or not engaged:
      return None, "disabled"
    age = now_mono - mono_time_ns * 1e-9
    if age > self.STALE_S:
      return None, "stale"
    ft = max(tiers) if tiers else 0
    if ft <= 0:
      return None, "no_gate"
    if ft == 1:  # ALERT_ONLY
      return None, "alert_only"
    if ft == 2:  # PREPARE
      return self.A_PREPARE, "prepare"
    if ft == 3:  # COMFORT
      if self.mono and v_ego_ms > self.MONO_COMFORT_CAP_MS:
        return None, "mono_veto"
      return self.A_COMFORT, "comfort"
    return self.A_EMERGENCY, "emergency"

  def apply(self, a_target: float, targets, v_ego_ms: float, now_mono: float,
            mono_time_ns: int, enabled: bool, engaged: bool, hb: bool = True):
    """targets=AvoidanceState.targets 列表;返回 conditioning 后 a_target。"""
    tiers = [int(t.tier) for t in targets] if targets is not None else []
    ftier = max(tiers) if tiers else 0
    floor, reason = self.floor_for(tiers, v_ego_ms, now_mono, mono_time_ns, enabled, engaged)
    if floor is None:
      out = a_target
    else:
      out = min(a_target, floor)
    self.last = {"applied": floor is not None and out < a_target,
                 "floor": floor, "reason": reason, "maxTier": ftier,
                 "a_in": round(a_target, 2), "a_out": round(out, 2)}
    if hb and now_mono - self.hb_t >= 0.5:
      self.hb_t = now_mono
      try:
        with open(self.HB, "w") as f:
          json.dump(dict(self.last, t=time.time()), f)
      except Exception:
        pass
    return out
