#!/usr/bin/env python3
"""avoidance.py —— 障碍感知与避险(避障绕行 阶段1+2)。

阶段1:检测本车道静止/极慢障碍,输出限速(纵向减速避险)。
阶段2:检测障碍 + 相邻车道空隙,输出车道内横向偏移(贴边绕过)。
安全:40m 内对静止/极慢障碍线性限速(消除 12~40m 盲区)、
偏移 ≤0.4m 不跨线、两侧都有车不横移、横向偏移/自动换道仅 15m 内触发。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


MIN_TRIGGER_SPEED_KPH = 5.0
MAX_TRIGGER_DREL_M = 40.0
MAX_TRIGGER_DPATH_M = 3.5
STOPPED_VREL_KPH = -3.0
CONFIRM_FRAMES = 3
RELEASE_FRAMES = 5
TARGET_GAP_M = 40.0
# 横向偏移/自动换道仅在近距离触发(远距离只做限速,避免 40m 外就贴边/变道)
NEAR_AVOID_M = 15.0
MAX_AVOID_SPEED_KPH = 80.0
MIN_AVOID_SPEED_KPH = 0.0
SAFE_DECEL_MPS2 = 1.5


@dataclass(frozen=True)
class AvoidanceEstimate:
  active: bool
  speed_kph: float
  d_rel_m: float
  d_path_m: float
  v_rel_kph: float
  reason: str = ""


class ObstacleAvoidance:
  """状态机:确认触发 -> 持续限速 -> 释放。"""

  def __init__(self) -> None:
    self._confirm_count = 0
    self._release_count = 0
    self._active = False
    self._last_estimate: AvoidanceEstimate | None = None
    self._stats: dict = field(default_factory=dict)

  def reset(self) -> None:
    self._confirm_count = 0
    self._release_count = 0
    self._active = False
    self._last_estimate = None

  def _detect_obstacle(self, lead: object | None, car_state: object | None) -> AvoidanceEstimate:
    """从 leadOne 检测本车道静止/极慢障碍。lead/car_state 为 None 时不触发。"""
    if lead is None or car_state is None:
      return AvoidanceEstimate(False, 0.0, 0.0, 0.0, 0.0, "no-data")

    d_rel = float(lead.dRel)
    d_path = float(lead.dPath)
    v_rel = float(lead.vRel) * 3.6  # m/s -> kph
    v_ego = float(car_state.vEgo) * 3.6
    v_lead = float(lead.vLead) * 3.6 if hasattr(lead, "vLead") else v_ego + v_rel

    # 非本车道(偏移过大)
    if abs(d_path) > MAX_TRIGGER_DPATH_M:
      return AvoidanceEstimate(False, 0.0, d_rel, d_path, v_rel, "off-path")

    # 距离过远
    if d_rel > MAX_TRIGGER_DREL_M:
      return AvoidanceEstimate(False, 0.0, d_rel, d_path, v_rel, "far")

    # 本车太慢(已在排队,让 MPC 处理)
    if v_ego < MIN_TRIGGER_SPEED_KPH:
      return AvoidanceEstimate(False, 0.0, d_rel, d_path, v_rel, "slow-ego")

    # 障碍物判定:静止/极慢(相对速度显著为负 或 前车速度接近 0)
    is_stopped = v_rel < STOPPED_VREL_KPH or v_lead < 1.0
    if not is_stopped:
      return AvoidanceEstimate(False, 0.0, d_rel, d_path, v_rel, "moving-lead")

    # 计算建议限速:40m(TARGET_GAP)内线性递减,越近越慢
    if d_rel >= TARGET_GAP_M:
      return AvoidanceEstimate(False, 0.0, d_rel, d_path, v_rel, "matching-lead")
    speed_kph = v_ego * max(0.0, d_rel / TARGET_GAP_M)
    speed_kph = min(speed_kph, MAX_AVOID_SPEED_KPH)
    # 下限保护:desiredSpeed=0 会被 controlsd 过滤(0<desiredSpeed<=250),
    # 最低 1.0 kph 保证通道有效;真正刹停由 MPC 接管。
    speed_kph = max(speed_kph, 1.0)
    return AvoidanceEstimate(True, speed_kph, d_rel, d_path, v_rel, "stopped-obstacle")

  def update(self, lead: object | None, car_state: object | None) -> AvoidanceEstimate:
    est = self._detect_obstacle(lead, car_state)

    if est.active:
      self._confirm_count += 1
      self._release_count = 0
      if self._confirm_count >= CONFIRM_FRAMES:
        self._active = True
        self._last_estimate = est
    else:
      self._confirm_count = 0
      if self._active:
        self._release_count += 1
        if self._release_count >= RELEASE_FRAMES:
          self._active = False
          self._last_estimate = None
      else:
        self._last_estimate = None

    if self._active and self._last_estimate is not None:
      return self._last_estimate
    return AvoidanceEstimate(False, 0.0, est.d_rel_m, est.d_path_m, est.v_rel_kph, est.reason)

  def suggested_speed(self) -> float | None:
    if self._active and self._last_estimate is not None:
      return self._last_estimate.speed_kph
    return None

  def is_active(self) -> bool:
    return self._active

  # ---- 阶段2:横向避让 ----
  def lateral_offset(self, leads_left: object | None, leads_right: object | None,
                     max_offset: float = 0.35,
                     lane_avail_left: bool | None = None,
                     lane_avail_right: bool | None = None) -> float:
    """返回车道内避让偏移:障碍在正前方时,靠向无车一侧。
    leads_left/leads_right: 相邻车道最近障碍(LeadData 或 None)
    返回: 右偏正、左偏负;无避让需求返回 0。
    """
    if not self._active:
      return 0.0
    # 仅在近距离障碍时横向避让;40m 外远障碍只限速,不贴边
    if self._last_estimate is None or self._last_estimate.d_rel_m > NEAR_AVOID_M:
      return 0.0
    # 相邻车道判定:该侧最近障碍距离远(>40m 视为空旷)或不存在
    def side_clear(lead) -> bool:
      if lead is None:
        return True
      # status=False 的无效雷达点(dRel=0)视为空旷,与 DesireHelper 一致
      if not getattr(lead, "status", True):
        return True
      return float(lead.dRel) > 40.0 or abs(float(lead.yRel)) > 5.0

    # 优先模型融合判据(车道线+路缘+BSD);None 时退回雷达 side_clear
    left_clear = lane_avail_left if lane_avail_left is not None else side_clear(leads_left)
    right_clear = lane_avail_right if lane_avail_right is not None else side_clear(leads_right)
    if left_clear and not right_clear:
      return -max_offset   # 左侧可绕,向左避让
    if right_clear and not left_clear:
      return max_offset    # 右侧可绕,向右避让
    return 0.0             # 两侧都不可绕或都空:不横向避让(只减速)

  # ---- 阶段3:自动绕行请求 ----
  def lane_change_request(self, v_ego_kph: float, leads_left: object | None,
                          leads_right: object | None, leads_left2: object | None = None,
                          leads_right2: object | None = None,
                          lane_change_active: bool = False,
                          lane_avail_left: bool | None = None,
                          lane_avail_right: bool | None = None) -> str | None:
    """评估是否应自动换道绕行。返回 "LEFT"/"RIGHT"/None。"""
    import time
    now = time.monotonic()

    if now - getattr(self, "_lc_last_request", 0.0) < 8.0:  # COOLDOWN_S
      return None
    if lane_change_active:
      return None
    if not self._active:
      return None
    # 仅在近距离障碍时自动换道;远障碍只限速(40m 外变道太激进)
    if self._last_estimate is None or self._last_estimate.d_rel_m > NEAR_AVOID_M:
      return None
    if v_ego_kph < 40.0:  # MIN_LC_SPEED_KPH
      return None

    def side_clear(lead) -> bool:
      if lead is None:
        return True
      # status=False 的无效雷达点视为空旷(与 DesireHelper 判据一致)
      if not getattr(lead, "status", True):
        return True
      d = float(lead.dRel)
      y = abs(float(lead.yRel))
      return d > 45.0 or y > 5.0

    # 优先模型融合判据(车道线+路缘);None 时退回雷达 side_clear
    if lane_avail_left is not None:
      left_clear = lane_avail_left
    else:
      left_clear = side_clear(leads_left) and side_clear(leads_left2)
    if lane_avail_right is not None:
      right_clear = lane_avail_right
    else:
      right_clear = side_clear(leads_right) and side_clear(leads_right2)

    if left_clear and right_clear:
      direction = "LEFT"
    elif left_clear:
      direction = "LEFT"
    elif right_clear:
      direction = "RIGHT"
    else:
      return None

    self._lc_last_request = now
    return direction

  # ---- 视觉小目标融合(行人/自行车/动物/锥桶) ----
  # 用 YOLO 检测结果(视觉)作为额外"虚拟前车"输入,
  # 与雷达 leadOne 取"更危险者"喂给状态机。
  # vision_obstacle: VisionObstacle(cls, d_rel, y_rel, conf, bbox) 或 None
  def update_vision(self, vision_obstacle, car_state) -> None:
    """把视觉障碍折成虚拟 lead 喂进 update()。只有本车道内的才触发。"""
    if vision_obstacle is None or car_state is None:
      return
    # 只看本车道内目标(横向偏移 < 3.5m,与雷达 dPath 判据一致)
    if abs(vision_obstacle.y_rel) > 3.5:
      return

    class _VirtualLead:
      pass

    vlead = _VirtualLead()
    vlead.dRel = vision_obstacle.d_rel
    vlead.dPath = vision_obstacle.y_rel
    vlead.vRel = -3.0  # 视为静止/极慢目标(行人/动物不会快速让开)
    vlead.vLead = 0.0
    # 用虚拟 lead 驱动同一状态机(阶段1 减速 + 防抖)
    self.update(vlead, car_state)