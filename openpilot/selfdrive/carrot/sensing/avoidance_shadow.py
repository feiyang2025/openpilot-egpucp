#!/usr/bin/env python3
"""P2 纵向避让影子层(台架)——反事实"若生效会怎样" + 幽灵刹车计数(G2 口径)。

判据索引(已签,零新决策):
  §10 P2 准入: 影子期"若生效会怎样"离线反事实,误触发 <0.5/1000 km;G15 基线齐才可放量
  G2: |a|≥1.0 ghost ≤0.5/1000 km;>1.5 m/s² 误减速 0 次(逐次阻断);>3.0 不得由本功能请求
      (EMERGENCY 属 AEB 交接语义,单列计数不进 ghost)
  §7.15/G15: 充分性反事实——最近 tier≥3 目标 d ≥ D(v,T0) 才判"若生效能停住";
      未实测只出候选结论,不冒充实车证据
  §7.11: 信号链停车是"有真实约束"的停车,不计 ghost 分母(由调用方 genuine 门保证)

诚实边界: 本层不碰控制链、不动 plannerd;genuine 由剧情源(已知真值)供给,
G2 正式验收以实车 qlog 为准,本层计数只做台架影子证据。
"""
import json
import time

from openpilot.selfdrive.controls.lib.longitudinal_avoidance import AvoidanceExecutor
from openpilot.selfdrive.carrot.sensing.avoidance_decider import D_check

HB_PATH = "/tmp/avoidance_shadow.json"


class AvoidanceShadow:
  def __init__(self, mono_profile: bool = True):
    self.exec = AvoidanceExecutor(mono_profile=mono_profile)
    self.reset()

  def reset(self):
    self.km = 0.0
    self.n_ghost = 0          # |a|≥1.0 且剧情无真实冲突(误触发,G2 分子)
    self.n_ghost_1p5 = 0      # >1.5 m/s² 误减速(G2 必须 0)
    self.n_emerg_req = 0      # EMERGENCY 请求(AEB 交接,单列)
    self.n_prepare = self.n_comfort = 0
    self.n_suff = self.n_insuff = 0   # 反事实充分/不足
    self.events = []          # 最近 32 条环形证据
    self.hb_t = 0.0

  # ---- G2 频次口径 ----
  def ghost_per_1000km(self) -> float:
    return self.n_ghost / max(self.km, 1e-6) * 1000.0

  def g2_pass(self) -> bool:
    """台架影子口径: ghost ≤0.5/1000km 且 >1.5 误减速 0 次。"""
    return self.n_ghost_1p5 == 0 and self.ghost_per_1000km() <= 0.5

  @staticmethod
  def _td(t):
    """兼容 dict(avoidanced 决策输出)与属性对象(capnp 列容/测试桩)。"""
    if isinstance(t, dict):
      return int(t.get("tier", 0)), float(t.get("dM", 0.0))
    return int(t.tier), float(t.dM)

  def update(self, targets, v_ego_ms, a_target, enabled, engaged,
             now_mono: float, mono_time_ns: int, genuine: bool = True,
             dist_km: float | None = None, hb: bool = True):
    """targets=dict/属性对象混合列表;genuine=剧情真值(默认 True=有真实冲突,
    生产接线不供真值时绝不虚增 ghost)。返回 (would_apply, floor, reason)。"""
    tiers = [self._td(t)[0] for t in targets] if targets is not None else []
    floor, reason = self.exec.floor_for(tiers, v_ego_ms, now_mono, mono_time_ns, enabled, engaged)
    would = floor is not None and floor < a_target
    if dist_km is not None:
      self.km = max(self.km, dist_km)
    if would:
      af = abs(floor)
      if af >= 1.0 and not genuine:
        self.n_ghost += 1
        if af > 1.5:
          self.n_ghost_1p5 += 1
      if reason == "prepare":
        self.n_prepare += 1
      elif reason == "comfort":
        self.n_comfort += 1
      elif reason == "emergency":
        self.n_emerg_req += 1
      # 充分性反事实: 最近 tier≥3 目标距离 vs D(v,T0)
      cand = [self._td(t)[1] for t in (targets or []) if self._td(t)[0] >= 3]
      if cand:
        d_near = min(cand)
        if d_near >= D_check(v_ego_ms * 3.6):
          self.n_suff += 1
        else:
          self.n_insuff += 1
      self.events.append({"t": time.time(), "reason": reason, "floor": floor,
                          "genuine": genuine, "vEgoMs": round(v_ego_ms, 2)})
      del self.events[:-32]
    if hb and now_mono - self.hb_t >= 0.5:
      self.hb_t = now_mono
      try:
        with open(HB_PATH, "w") as f:
          json.dump({"t": time.time(), "km": round(self.km, 3),
                     "ghost": self.n_ghost, "ghost_1p5": self.n_ghost_1p5,
                     "ghost_per_1000km": round(self.ghost_per_1000km(), 3),
                     "emerg_req": self.n_emerg_req,
                     "suff": self.n_suff, "insuff": self.n_insuff,
                     "g2_pass": self.g2_pass()}, f)
      except Exception:
        pass
    return would, floor, reason
