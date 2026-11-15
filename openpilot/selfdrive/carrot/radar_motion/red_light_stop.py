"""阶段1: 红灯在停止线前刹停。

距离源分级(优先级从上到下):
  1. 导航路口距离 xDistToTurn —— 实车精确, 停止线 ≈ 路口 - NAV_STOP_OFFSET_M
  2. 视觉信号灯 bbox 反推距离 —— 保守近似, 见 vision_worker.sig_distance

设计原则:
  - 只降不升: 目标速度 >= 当前车速时不介入(绝不影响加速)
  - 只对红灯(traffic_state==1)生效; 绿灯/黄灯/无灯立即释放
  - 距离不可靠时不介入(宁可不管, 也不能误急刹)
  - 停车点留 STOP_GAP_M 余量, 且给最低可下发速度 1.0kph
"""

import math
import time

RED_CONFIRM_S = 0.5        # 红灯需持续确认(单帧误检不刹)
STOP_GAP_M = 3.0           # 停在停止线前多远
NAV_STOP_OFFSET_M = 8.0    # 停止线相对导航路口点: 向前 8m(停止线在路口前)
VIS_STOP_OFFSET_M = 8.0    # 停止线相对信号灯: 向前 8m(灯在停止线后上方)
DECEL_MPS2 = 1.5           # 舒适减速度
MAX_STOP_DIST_M = 150.0    # 超过此距离不介入
MIN_ACTIVE_KPH = 3.0       # 低于此速度视为已停(不介入, 避免蠕动干扰)
MIN_SIGNAL_CONF = 0.5      # 视觉距离要求的检出置信度


class RedLightStop:
  def __init__(self) -> None:
    self._red_since = 0.0
    self._active = False
    self._reason = "idle"
    self._stop_dist = None   # 停止线距离(m)
    self._target_kph = None
    self._source = "none"

  def reset(self, reason: str = "reset") -> None:
    self._red_since = 0.0
    self._active = False
    self._reason = reason
    self._stop_dist = None
    self._target_kph = None
    self._source = "none"

  def stop_distance(self, nav_dist_m: float | None, sig_rows: list | None) -> tuple:
    """返回 (停止线距离 m 或 None, 来源字符串)。"""
    # 1. 导航优先(精确)
    try:
      if nav_dist_m is not None and math.isfinite(float(nav_dist_m)) and 0.0 < float(nav_dist_m) < MAX_STOP_DIST_M + 50.0:
        d = float(nav_dist_m) - NAV_STOP_OFFSET_M
        # 已过停止线(<=0): 钳到 0 给最低速刹停(停在停止线处, 不冲路口);
        # 明显越过(>STOP_GAP_M)视为已通过, 不再介入。
        if d >= -STOP_GAP_M:
          return max(d, 0.0), "nav"
    except Exception:
      pass
    # 2. 视觉信号灯(取最近的可信红灯)
    best = None
    for row in (sig_rows or []):
      try:
        cls = str(row[0]).lower()
        if "red" not in cls:
          continue
        if len(row) > 4 and row[4] is not None:
          d_vis = float(row[4]) - VIS_STOP_OFFSET_M
          if 0.0 < d_vis < MAX_STOP_DIST_M and (best is None or d_vis < best):
            best = d_vis
      except Exception:
        continue
    if best is not None:
      return best, "vision"
    return None, "none"

  def update(self, v_ego_kph: float, traffic_state: int, nav_dist_m: float | None,
             sig_rows: list | None, now: float | None = None,
             enabled: bool = True) -> float | None:
    """返回应叠加的目标速度(kph); None = 不介入。"""
    now = time.monotonic() if now is None else now
    if not enabled or traffic_state != 1:
      self.reset("not-red" if traffic_state != 1 else "disabled")
      return None
    if self._red_since == 0.0:
      self._red_since = now
    if now - self._red_since < RED_CONFIRM_S:
      self._reason = "confirming"
      return None
    if v_ego_kph < MIN_ACTIVE_KPH:
      self._reason = "already-stopped"
      return None

    d, src = self.stop_distance(nav_dist_m, sig_rows)
    if d is None:
      self._reason = "no-reliable-distance"
      self._active = False
      return None

    remaining = max(0.0, d - STOP_GAP_M)
    v_ms = math.sqrt(2.0 * DECEL_MPS2 * remaining) if remaining > 0.05 else 0.0
    target_kph = max(v_ms * 3.6, 1.0)   # 0 会被 controlsd 过滤
    # 只降不升: 目标高于当前车速 -> 不介入
    if target_kph >= v_ego_kph:
      self._reason = "no-need"
      self._active = False
      self._stop_dist = d
      self._target_kph = target_kph
      self._source = src
      return None
    self._active = True
    self._reason = "slowing"
    self._stop_dist = d
    self._target_kph = target_kph
    self._source = src
    return target_kph

  def debug(self) -> str:
    if self._stop_dist is None:
      return "RED:%s" % self._reason
    return "RED:%s %s %.0fm->%.1fk" % (self._reason, self._source,
                                       self._stop_dist, self._target_kph or 0.0)
