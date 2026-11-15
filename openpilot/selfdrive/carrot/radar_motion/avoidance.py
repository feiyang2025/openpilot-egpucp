#!/usr/bin/env python3
"""c3 avoidance —— 主动避障(曲线避让)。

阶段1: 检测本车道静止/极慢障碍 -> 限速(纵向避险)。
阶段2: 从障碍物位置生成平滑避让曲线(偏出->保持->回中), 逐点输出曲率,
       注入 controlsd 的 desiredCurvature(横向绕过, 不跨线)。
阶段3: 相邻车道空旷且本车道障碍近时, 自动换道请求(LANECHANGE)。

与 egpucp 的差异: c3 无 lane_planner_2 路径偏移层, 横向直接由模型
curvature 驱动, 因此阶段2 改为"曲线避让": 以障碍相对位置为基准生成
y(s) 横向位移曲线(三段余弦拼接, 边界处 y=y'=0, 无限可导),
每周期按里程 s 查曲率 kappa = y''(s) 叠加到 desired_curvature。

安全:
- 40m 内对静止/极慢障碍线性限速(消除 12~40m 盲区)
- 避让偏移 <= 0.35m 不跨线; 两侧都不可绕则不横向避让(只减速)
- 横向加速度限制 <= 0.5 m/s^2; 曲率按速度夹取
- 换道仅 25m 内触发, 8s 冷却, 且模型判定可绕时才发
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass


MIN_TRIGGER_SPEED_KPH = 5.0
MAX_TRIGGER_DREL_M = 40.0
MAX_TRIGGER_DPATH_M = 3.5
# 前车绝对速度低于此值视为静止/极慢障碍(触发避障)。
# 注意不能用相对速度 v_rel 判据: 高速巡航时前车慢几 km/h 是常态,
# v_rel < -3 会把正常慢车误判为静止障碍(egpucp 原版即如此)。
STOPPED_VLEAD_KPH = 10.0
# 曲线绕行/避障换道只对"真静止"障碍触发(vLead<3km/h): 前车还在蠕动
# (3~10km/h 排队)只限速跟随, 不横向绕出车流/借对向道(队列里绕行危险)。
# 阶段1限速仍对排队生效(vLead<10), 这是纵向减速 vs 横向绕行的分界。
TRULY_STOPPED_VLEAD_KPH = 3.0
TARGET_GAP_M = 40.0
MAX_AVOID_SPEED_KPH = 80.0

# 时间基准防抖(与调用频率无关): 0.3s 确认 / 0.5s 释放
CONFIRM_GRACE_SEC = 0.45       # 短暂丢失容忍(视觉 5Hz 更新间隔的 2~3 倍)
# 行人快速通道: 视觉 5Hz 下行人常只出现 1 次采样(0.2s), 达不到 CONFIRM_SEC;
# 但 12m 内的行人必须响应。单帧高置信即限速, 不绕行(绕行轨迹会压到人)。
FAST_SINGLE_DREL_M = 12.0      # 快速通道距离上限
FAST_SINGLE_CONF = 0.60        # 快速通道置信度下限(与信号灯阈值一致)
CONFIRM_SEC = 0.30
RELEASE_SEC = 0.50

# ---- 阶段2 曲线避让参数 ------------------------------------------------ #
MAX_OFFSET_M = 0.35          # 最大横向偏移(车道内, 不跨线)
NEAR_AVOID_M = 25.0          # 近距触发下限(低速时的触发上限, 见下方窗口)
# ---- 横向避让的距离窗口(用户反馈实测修正) ------------------------------ #
# 横向偏移只有 0.35m, 近距离横向机动既躲不开目标、又会把车横过来, 比直行
# 刹车危险。所以曲线/换道只在"来得及"的距离窗口内启动; 窗口内偏近的一端
# 一律只做纵向减速(阶段1 限速一直有效, 不受本窗口影响)。
AVOID_MIN_DREL_M = 12.0      # 绝对下限: 任何速度下 <12m 不做横向避让
AVOID_MARGIN_M = 4.0         # 偏出段走完后留给障碍的最小余量(m)
AVOID_START_TIME_S = 2.5     # 预见性: 触发窗口上界按 v*该值(至少 NEAR_AVOID_M)
STOP_DREL_M = 6.0            # 近距刹停阈值: <6m 建议速度直接给最低值

# ---- 绕行间隙判据(用户: "安全避让距离不够就不要避让, 只能降速刹停") ---- #
# 横向偏移只有 offset(0.35m / 无车道线 0.9m), 绕行后与目标的实际间隙:
#   clearance = |y_o| - obj_half - ego_half + offset
# y=0 的正前方车 clearance 为负(必然重叠) -> 0.35m 偏移绕不过, 只能刹车。
# y>=1.5m 的骑线目标/邻车道目标才可能够。CLEAR_MARGIN_M 为要求的最小间隙。
SIDE_EGO_HALF_M = 0.9        # 自车半宽(含后视镜)
OBJ_HALF_HUMAN_M = 0.35      # 行人半宽
OBJ_HALF_BICYCLE_M = 0.40    # 自行车(含骑行者)半宽
OBJ_HALF_MOTORCYCLE_M = 0.50 # 摩托车(含车把)半宽
OBJ_HALF_VEHICLE_M = 0.95    # 车辆半宽
CLEAR_MARGIN_M = 0.5         # 绕行所需最小横向间隙
AVOID_MAX_CLEAR_M = 1.5      # 间隙已充足(>=此值)说明目标离本车道够远,
                             # 本车道无阻挡 -> 不限速、不绕行(邻道车不误触)

# ---- 无车道线允许压线 ------------------------------------------------ #
NO_LANE_MAX_OFFSET_M = 0.9   # 无车道线时最大横向偏移(压线宽度)
NO_LANE_PROB = 0.3           # 本车道左右线 probs 均低于此 -> 无车道线
NO_LANE_MAX_SPEED_KPH = 60.0 # 无车道线时超过此速度不允许压线
HOLD_SEC = 1.2               # 保持段时长(绕过障碍身位)
SIDE_SEC = 1.5               # 偏出/回中段时间基数(随速度: L = v*SIDE_SEC)
MIN_SIDE_M = 12.0            # 偏出/回中段最小长度
MAX_LAT_ACCEL_MPS2 = 0.5     # 避让横向加速度上限
# 曲线完成冷却: 走完一条曲线(偏出->保持->回中)后, 即使障碍仍在触发区
# 也至少等这么久再重触发, 防止同一障碍导致左右往复绕行(往复摆动)。
CURVE_COOLDOWN_S = 4.0

# ---- 阶段3 换道参数 ---------------------------------------------------- #
LC_COOLDOWN_S = 8.0
LC_MIN_SPEED_KPH = 40.0
LC_NEAR_M = 25.0
LC_MIN_DREL_M = 20.0   # 低于此距离不发起换道(只能刹车), 与曲线窗口同一安全观
LC_SIDE_CLEAR_M = 45.0
LC_SIDE_CLEAR_Y_M = 5.0

# ---- 自动超车(OVERTAKE)参数 -------------------------------------------- #
# 三档设置移植自 AmapNavi.apk OvertakeParams(反编译 MainActivityLaneDecisionKt
# <clinit>, 与手机端 evaluateOvertakeTrigger/Side 同参)。档位由
# OverTakeMode param 选择: 1=激进/2=常规/3=保守。
# 构造器参数顺序 (I String F F I F F I I J F I I F F F Z Z J J):
#   mode, name, triggerMaxDist, triggerMinDist, vrelThreshold, timeGapMax,
#   cruiseRatio, leadMinSpeedRoad, leadMinSpeedHighWay, cooldownFailedMs,
#   _?, rearMinDist, sideFrontMinDist, sideMinScore, sideSafetyMargin(bool侧?),
#   extra, allowRightOvertake, preferLeftFirst, cooldownSuccessMs, _?
OT_PARAMS = {
  # 激进: 距离区间8~72m, 前车慢1km/h即超, 高速限15/普通25, 冷成功6s失败400ms, 允许右侧
  1: {
    "trigger_min_m": 8.0, "trigger_max_m": 72.0,
    "vrel_threshold_kph": -1.0,
    "lead_min_road_kph": 25.0, "lead_min_highway_kph": 15.0,
    "rear_min_dist_m": 45.0, "side_front_min_dist_m": 5.0,
    "time_gap_max_s": 4.0, "cruise_ratio": 0.95,
    "cooldown_success_s": 6.0, "cooldown_failed_s": 0.4,
    "allow_right_overtake": True, "prefer_left_first": False,
  },
  # 常规: 12~80m, 慢3km/h, 高速20/普通35, 冷成功10s失败800ms, 优先左侧
  2: {
    "trigger_min_m": 12.0, "trigger_max_m": 80.0,
    "vrel_threshold_kph": -3.0,
    "lead_min_road_kph": 35.0, "lead_min_highway_kph": 20.0,
    "rear_min_dist_m": 60.0, "side_front_min_dist_m": 10.0,
    "time_gap_max_s": 3.0, "cruise_ratio": 0.90,
    "cooldown_success_s": 10.0, "cooldown_failed_s": 0.8,
    "allow_right_overtake": True, "prefer_left_first": True,
  },
  # 保守: 20~60m, 慢8km/h, 高速30/普通45, 冷成功15s失败1.2s
  3: {
    "trigger_min_m": 20.0, "trigger_max_m": 60.0,
    "vrel_threshold_kph": -8.0,
    "lead_min_road_kph": 45.0, "lead_min_highway_kph": 30.0,
    "rear_min_dist_m": 75.0, "side_front_min_dist_m": 15.0,
    "time_gap_max_s": 2.0, "cruise_ratio": 0.80,
    "cooldown_success_s": 15.0, "cooldown_failed_s": 1.2,
    "allow_right_overtake": True, "prefer_left_first": False,
  },
}
OT_DEFAULT_MODE = 2  # 常规
OT_MIN_SPEED_KPH = 40.0  # 低于该车速不主动超车(低速排队)


@dataclass(frozen=True)
class AvoidanceEstimate:
  active: bool
  speed_kph: float
  d_rel_m: float
  d_path_m: float
  v_rel_kph: float
  v_lead_kph: float = 999.0  # 前车绝对速度(km/h); 远/无数据时默认大值
  reason: str = ""


class ObstacleAvoidance:
  """阶目1+3 状态机: 时间防抖, 确认触发 -> 持续限速 -> 释放。"""

  def __init__(self) -> None:
    self._confirm_since = 0.0
    self._release_since = 0.0
    self._active = False
    self._last_estimate: AvoidanceEstimate | None = None
    self._last_y_rel: float = 0.0  # 障碍横向位置(右正), 阶段3 选边用
    self._fast_single = False      # 本轮是否由快速通道(单帧近距高置信)激活

  def reset(self) -> None:
    self._confirm_since = 0.0
    self._release_since = 0.0
    self._active = False
    self._last_estimate = None
    self._last_y_rel = 0.0
    self._fast_single = False

  def _detect_obstacle(self, lead, car_state) -> AvoidanceEstimate:
    if lead is None or car_state is None:
      return AvoidanceEstimate(False, 0.0, 0.0, 0.0, 0.0, reason="no-data")
    try:
      d_rel = float(lead.dRel)
      d_path = float(lead.dPath)
      v_rel = float(lead.vRel) * 3.6
      v_ego = float(car_state.vEgo) * 3.6
    except Exception:
      return AvoidanceEstimate(False, 0.0, 0.0, 0.0, 0.0, reason="bad-data")

    if abs(d_path) > MAX_TRIGGER_DPATH_M:
      return AvoidanceEstimate(False, 0.0, d_rel, d_path, v_rel, reason="off-path")
    if d_rel > MAX_TRIGGER_DREL_M:
      return AvoidanceEstimate(False, 0.0, d_rel, d_path, v_rel, reason="far")
    if v_ego < MIN_TRIGGER_SPEED_KPH:
      return AvoidanceEstimate(False, 0.0, d_rel, d_path, v_rel, reason="slow-ego")

    # 静止/极慢判定: 必须看前车绝对速度(vLead), 不能只看相对速度。
    # v_rel < -3 只说明"前车比我慢"——高速巡航时前车慢 3~5km/h 是常态,
    # 若误判为静止障碍会触发无谓限速+换道(复查发现, egpucp 原判据)。
    # 绝对速度 < STOPPED_VLEAD_KPH 才视为极慢/静止障碍。
    try:
      v_lead = float(lead.vLead) * 3.6
    except Exception:
      v_lead = v_ego + v_rel  # 无 vLead 字段时用自车速度+相对速度合成
    is_stopped = v_lead < STOPPED_VLEAD_KPH
    if not is_stopped:
      return AvoidanceEstimate(False, 0.0, d_rel, d_path, v_rel, v_lead_kph=v_lead, reason="moving-lead")
    if d_rel >= TARGET_GAP_M:
      return AvoidanceEstimate(False, 0.0, d_rel, d_path, v_rel, v_lead_kph=v_lead, reason="matching-lead")
    # 间隙充分: 目标横向已远离本车道, 本车道无阻挡 -> 不限速不避让。
    # 否则邻道静止车(d_path=3.5)会把本车从 40 压到 21, 属无谓减速。
    _clear_veh = abs(d_path) - OBJ_HALF_VEHICLE_M - SIDE_EGO_HALF_M + MAX_OFFSET_M
    if _clear_veh >= AVOID_MAX_CLEAR_M:
      return AvoidanceEstimate(False, 0.0, d_rel, d_path, v_rel, v_lead_kph=v_lead,
                               reason=f"clear-enough({_clear_veh:+.1f}m)")
    if d_rel < STOP_DREL_M:
      # 已经贴到跟前: 线性比例(v*d/40)此时仍会给几 km/h 的爬行速度,
      # 近距离目标必须刹停 —— 直接给最低可下发值(desiredSpeed=0 会被过滤)。
      speed_kph = 1.0
    else:
      speed_kph = v_ego * max(0.0, d_rel / TARGET_GAP_M)
      speed_kph = min(speed_kph, MAX_AVOID_SPEED_KPH)
    # desiredSpeed=0 会被 controlsd 过滤, 最低 1.0 kph 保证通道有效
    speed_kph = max(speed_kph, 1.0)
    return AvoidanceEstimate(True, speed_kph, d_rel, d_path, v_rel, v_lead_kph=v_lead, reason="stopped-obstacle")

  def update(self, lead, car_state, now: float | None = None) -> AvoidanceEstimate:
    now = time.monotonic() if now is None else now
    est = self._detect_obstacle(lead, car_state)
    self._last_reason = est.reason  # 诊断: 未触发时能看到卡在哪一环
    # 观测输入是 20Hz 主循环 + 5Hz 视觉, 视觉两次更新之间目标状态会翻转;
    # 原实现一遇 est.active=False 就把确认计时清零, 导致永远达不到 CONFIRM_SEC
    # (实测: 行人持续可见 3s, 激活 0 次)。改为允许 CONFIRM_GRACE_SEC 的短暂丢失。
    _lost_ok = (self._confirm_since != 0.0
                and (now - getattr(self, '_last_seen', 0.0)) <= CONFIRM_GRACE_SEC)
    if est.active:
      self._last_seen = now
    if lead is not None:
      try:
        self._last_y_rel = float(lead.yRel)
      except Exception:
        self._last_y_rel = 0.0

    if est.active:
      self._release_since = 0.0
      # 快速通道: 近距 + 高置信 单帧即激活限速(跳过 CONFIRM_SEC)。
      # 只对带 conf 的视觉虚拟 lead 生效(雷达 lead 无 conf -> 0.0 不命中)。
      _conf = 0.0
      try:
        _conf = float(getattr(lead, 'conf', 0.0) or 0.0)
      except Exception:
        _conf = 0.0
      if _conf >= FAST_SINGLE_CONF and est.d_rel_m <= FAST_SINGLE_DREL_M:
        if not self._active:
          self._fast_single = True
          self._active = True
          self._confirm_since = now
          self._last_estimate = est
        else:
          self._fast_single = True
          self._last_estimate = est
      elif self._confirm_since == 0.0:
        self._fast_single = False
        self._confirm_since = now
      elif now - self._confirm_since >= CONFIRM_SEC:
        self._fast_single = False
        self._active = True
        self._last_estimate = est
    else:
      if not _lost_ok:
        self._confirm_since = 0.0
      if self._active:
        if self._release_since == 0.0:
          self._release_since = now
        elif now - self._release_since >= RELEASE_SEC:
          self._active = False
          self._last_estimate = None
          # 释放后清快速通道标志: 否则下一轮 moving-lead(est 未激活)时
          # 探针仍显示 fast=True, 且曲线会误判为"快速通道目标"而永不启动。
          self._fast_single = False
      else:
        self._last_estimate = None

    if self._active and self._last_estimate is not None:
      return self._last_estimate
    return AvoidanceEstimate(False, 0.0, est.d_rel_m, est.d_path_m, est.v_rel_kph, reason=est.reason)

  def suggested_speed(self) -> float | None:
    if self._active and self._last_estimate is not None:
      return self._last_estimate.speed_kph
    return None

  def is_active(self) -> bool:
    return self._active

  def estimate(self) -> AvoidanceEstimate | None:
    return self._last_estimate if self._active else None

  # ---- 阶段3: 自动换道请求 --------------------------------------------- #
  def lane_change_request(self, v_ego_kph: float,
                          left_blocked: bool | None = None,
                          right_blocked: bool | None = None,
                          lane_change_active: bool = False,
                          highway: bool = False,
                          now: float | None = None) -> str | None:
    """评估是否应自动换道绕行。返回 "LEFT"/"RIGHT"/None。

    left_blocked/right_blocked 由调用方合成(carrot_man: lidar 盲区 +
    radarTracks 点云 + 模型 laneChangeAvailable + 视觉行人/车辆):
      None  = 无该侧信息(视为可绕, 保守性由调用方保证)
      True  = 该侧有风险(后方来车/盲区/行人/相邻车道占用) -> 不可绕
      False = 该侧安全

    highway: 道路类型(限速>=80 视为高速/快速路)。仅用于居中障碍的
    默认绕向——高速左绕(超车道, 国内标准); 普通路右绕(右侧路肩
    空间, 不借对向车道)。
    """
    now = time.monotonic() if now is None else now
    if now - getattr(self, "_lc_last_request", 0.0) < LC_COOLDOWN_S:
      return None
    if lane_change_active or not self._active:
      return None
    est = self._last_estimate
    if est is None or est.d_rel_m > LC_NEAR_M:
      return None
    # 换道需要更长距离: <20m 发起换道等于在目标跟前横移, 此时只能刹车。
    if est.d_rel_m < LC_MIN_DREL_M:
      return None
    if v_ego_kph < LC_MIN_SPEED_KPH:
      return None
    # 真静止门槛: 前车还在蠕动(排队)只限速跟随, 不借道换行。与曲线绕行
    # 同一语义(TRULY_STOPPED), 避免堵车排队时从车流里绕出去。
    if est.v_lead_kph >= TRULY_STOPPED_VLEAD_KPH:
      return None

    left_clear = left_blocked is not True
    right_clear = right_blocked is not True
    # 障碍反侧优先: yRel 左正(log.capnp), y_rel>0=障碍在左 -> 右绕
    # (离开障碍); y_rel<0=障碍在右 -> 左绕; 居中 -> 按道路类型:
    # 高速/快速路默认左绕(超车道), 普通路默认右绕(右侧空间, 不借对向道)。
    y = self._last_y_rel
    if y > 0.0:
      prefer_left = False
    elif y < 0.0:
      prefer_left = True
    else:
      prefer_left = highway
    if prefer_left and left_clear:
      direction = "LEFT"
    elif (not prefer_left) and right_clear:
      direction = "RIGHT"
    else:
      # 首选侧不安全: 不发起换道。反向换道等于朝障碍方向打灯, 比不换更危险。
      return None

    self._lc_last_request = now
    return direction

  # ---- 自动超车(OVERTAKE) ---- #
  def set_overtake_mode(self, mode: int) -> None:
    """设置超车档位(见 OT_PARAMS): 1=激进/2=常规/3=保守。"""
    if mode in OT_PARAMS:
      self.overtake_mode = mode

  def overtake_request(self, v_ego_kph: float, v_lead_kph: float | None,
                       left_blocked: bool | None = None,
                       right_blocked: bool | None = None,
                       lane_change_active: bool = False,
                       highway: bool = False,
                       now: float | None = None) -> str | None:
    """评估是否应自动超车, 返回 "LEFT"/"RIGHT"/None。

    与 AmapNavi.apk evaluateOvertakeTrigger 同参(按档位):
      前车低于档位最低速度(高速/普通路分开) -> 疑似排队, 不超;
      前车相对自车过慢(巡航比例 cruise_ratio) -> 值得超;
      距离区间(trigger_min~trigger_max)内 -> 可超;
      目标侧安全(left_blocked/right_blocked 由调用方合成) -> 发起。
    冷却按档位 cooldown_success_s(成功后)/cooldown_failed_s(失败后, 短),
    失败冷却由 overtake_result(False) 切换。
    """
    now = time.monotonic() if now is None else now
    p = OT_PARAMS.get(getattr(self, "overtake_mode", OT_DEFAULT_MODE), OT_PARAMS[OT_DEFAULT_MODE])

    if v_lead_kph is None:
      return None
    # 档位最低前车速度(排队/拥堵判定), 高速与普通路分开
    lead_min = p["lead_min_highway_kph"] if highway else p["lead_min_road_kph"]
    if v_lead_kph < lead_min:
      return None
    # 前车相对自车(巡航代理)过慢才值得超
    if v_lead_kph > v_ego_kph * p["cruise_ratio"]:
      return None
    if v_ego_kph < OT_MIN_SPEED_KPH:
      return None

    # 冷却: 成功/失败分开(APK cooldownSuccess/Failed)
    cooldown = p["cooldown_success_s"] if not getattr(self, "_ot_failed", False) else p["cooldown_failed_s"]
    if now - getattr(self, "_ot_last_request", 0.0) < cooldown:
      return None
    if lane_change_active:
      return None

    left_clear = left_blocked is not True
    right_clear = right_blocked is not True
    # 障碍反侧优先: yRel 左正, y_rel>0=障碍在左 -> 右绕; y_rel<0=障碍
    # 在右 -> 左绕; 居中 -> 按档位偏好(prefer_left_first)。
    y = self._last_y_rel
    if y > 0.0:
      prefer_left = False
    elif y < 0.0:
      prefer_left = True
    else:
      prefer_left = p["prefer_left_first"]
    if prefer_left and left_clear:
      direction = "LEFT"
    elif (not prefer_left) and right_clear and p["allow_right_overtake"]:
      direction = "RIGHT"
    elif left_clear:
      direction = "LEFT"
    elif right_clear and p["allow_right_overtake"]:
      direction = "RIGHT"
    else:
      return None

    self._ot_last_request = now
    return direction

  def overtake_result(self, success: bool) -> None:
    """超车结果回馈: 失败 -> 短冷却(快速重试); 成功 -> 长冷却(避免骚扰)。"""
    self._ot_failed = not success


class AvoidanceCurve:
  """阶段2: 从障碍物位置生成平滑避让曲线(偏出->保持->回中)。

  曲线以纵向里程 s 为参数, 三段 quintic 多项式拼接(y, y', y'' 全程连续):
    段1  s in [0, L1)     y = O * Q(r),  r=s/L1,  Q=10r^3-15r^4+6r^5
    段2  s in [L1, L1+L2) y = O
    段3  s in [L1+L2, L)  y = O * (1-Q(r)),  r=(s-L1-L2)/L3
  Q(r) 在 r=0 与 r=1 处 y=y'=y''=0, 故段2(保持)与段1/段3 边界处
  y''=0 连续, kappa 无阶跃(驾驶平顺, 无 jerk 冲击)。
  kappa = y''(s): 段1 = O*(60r-180r^2+120r^3)/L1^2, 段3 = -O*.../L3^2
  横向加速度限制 <= MAX_LAT_ACCEL_MPS2, 曲率按速度夹取。

  触发: 障碍 active 且 d_rel <= NEAR_AVOID_M, 且存在可绕方向。
  方向: 优先模型 laneChangeAvailable 判据; 否则倾向障碍所在侧的对面,
        两侧都不可绕则只限速不横向避让。
  """

  def __init__(self, detector: ObstacleAvoidance | None = None) -> None:
    self.detector = detector or ObstacleAvoidance()
    self._active = False
    self._s = 0.0
    self._L1 = MIN_SIDE_M
    self._L2 = 8.0
    self._L3 = MIN_SIDE_M
    self._O = 0.0          # 带符号最终偏移(右正左负)
    self._direction = 1
    self._reason = ""
    self._last_kappa = 0.0
    self._done_at = 0.0    # 最近一次曲线完成(或取消)时刻, 防往复重触发

  def reset(self, now: float | None = None) -> None:
    if self._active:
      self._done_at = now if now is not None else time.monotonic()
    self._active = False
    self._s = 0.0
    self._last_kappa = 0.0

  def is_active(self) -> bool:
    return self._active

  @staticmethod
  def _clearance(lead, offset: float) -> float | None:
    """横向绕行后与目标的实际最小间隙(m); None = 无目标/数据不足。

    clearance = |y_o| - obj_half - ego_half + offset
    负值或小于 CLEAR_MARGIN_M 表示偏移后仍会重叠/贴太近 -> 不允许绕行。
    """
    if lead is None:
      return None
    try:
      y = float(getattr(lead, 'yRel', 0.0))
    except Exception:
      return None
    _cls = str(getattr(lead, 'cls', '') or '').lower()
    # 半宽查表(语义单点定义在 vision_tracker.OBJ_HALF_BY_CLASS)。
    # 原实现把 motorcycle 归入行人 0.35m, 实际车把 0.45~0.5m, 间隙高估
    # 0.1~0.15m -> 可能误判"够绕"而刮到。未知类别按车辆 0.95m 保守估。
    try:
      from openpilot.selfdrive.carrot.radar_motion.vision_tracker import obj_half_for
      half = obj_half_for(_cls) if _cls else OBJ_HALF_VEHICLE_M
    except Exception:
      if _cls in ('person', 'pedestrian'):
        half = OBJ_HALF_HUMAN_M
      elif _cls in ('bicycle', 'bike', 'cyclist'):
        half = OBJ_HALF_BICYCLE_M
      elif _cls in ('motorcycle', 'motorbike'):
        half = OBJ_HALF_MOTORCYCLE_M
      elif _cls:
        half = OBJ_HALF_VEHICLE_M
      else:
        half = OBJ_HALF_VEHICLE_M   # 雷达 lead 无类别, 按车辆估
    return abs(y) - half - SIDE_EGO_HALF_M + offset

  def _pick_direction(self, lead, sm, left_blocked: bool | None = None,
                      right_blocked: bool | None = None,
                      highway: bool = False) -> int:
    """返回避让方向: +1 右绕, -1 左绕; 0 不避让(只限速)。

    侧后安全(左/右)由调用方合成: lidar 盲区 + radarTracks 点云 +
    模型 laneChangeAvailable + 视觉行人。None 表示无信息。

    yRel 为 car frame, 左正(log.capnp): y_rel>0 = 障碍在左 -> 右绕
    (离开障碍); y_rel<0 = 障碍在右 -> 左绕; 居中 -> 按道路类型:
    高速/快速路(highway)左绕(超车道), 普通路右绕(右侧空间, 不借
    对向车道)。
    """
    md = None
    lav_l = lav_r = None
    try:
      if sm is not None and sm.alive.get('modelV2', False):
        md = sm['modelV2']
        lav_l = bool(md.meta.laneChangeAvailableLeft)
        lav_r = bool(md.meta.laneChangeAvailableRight)
    except Exception:
      pass

    # 障碍侧: y_rel>0 障碍在左 -> 倾向右绕
    try:
      y_rel = float(lead.yRel) if lead is not None else 0.0
    except Exception:
      y_rel = 0.0
    try:
      self._last_dir_input = ("lead_cls=%s yRel=%+.2f dRel=%.1f vLead=%.1f "
        "pref_left=%s lav_l=%s lav_r=%s Lb=%s Rb=%s highway=%s\n" % (
          type(lead).__name__, y_rel, float(getattr(lead, 'dRel', -1)),
          float(getattr(lead, 'vLead', -1)) * 3.6, (y_rel > 0 and False) or (y_rel <= 0),
          lav_l, lav_r, left_blocked, right_blocked, highway))
    except Exception:
      pass
    if y_rel > 0.0:
      prefer_left = False
    elif y_rel < 0.0:
      prefer_left = True
    else:
      prefer_left = highway

    # 合成"该侧可绕": 无明确 blocked, 且模型未明确禁止
    left_ok = left_blocked is not True
    right_ok = right_blocked is not True
    if lav_l is not None and left_ok:
      left_ok = left_ok and lav_l
    if lav_r is not None and right_ok:
      right_ok = right_ok and lav_r

    if left_ok and prefer_left:
      return -1
    if right_ok and not prefer_left:
      return 1
    # 首选侧(远离障碍那侧)被占用/不可用 -> 不绕行, 返回 0 只保留限速。
    # 原实现会降级到"另一侧", 而另一侧正是障碍所在侧 -> 朝障碍偏, 危险。
    return 0

  def _setup_curve(self, v_ego: float, d_rel: float, direction: int,
                   no_lane: bool = False) -> None:
    """按当前速度与障碍距离初始化曲线段长。"""
    side = max(MIN_SIDE_M, min(v_ego * SIDE_SEC, max(d_rel - 4.0, MIN_SIDE_M)))
    self._L1 = side
    self._L3 = side
    self._L2 = max(6.0, v_ego * HOLD_SEC)
    _off = NO_LANE_MAX_OFFSET_M if no_lane else MAX_OFFSET_M
    self._O = _off * direction
    self._direction = direction
    self._s = 0.0

  def _kappa_at(self, s: float) -> float:
    if not self._active:
      return 0.0
    O, L1, L2, L3 = self._O, self._L1, self._L2, self._L3
    if s < L1:
      r = s / L1
      return O * (60.0 * r - 180.0 * r * r + 120.0 * r ** 3) / (L1 * L1)
    if s < L1 + L2:
      return 0.0
    r = (s - L1 - L2) / L3
    return -O * (60.0 * r - 180.0 * r * r + 120.0 * r ** 3) / (L3 * L3)

  def _total_len(self) -> float:
    return self._L1 + self._L2 + self._L3

  def update(self, v_ego: float, dt: float, sm=None, lead=None, now: float | None = None,
             left_blocked: bool | None = None, right_blocked: bool | None = None,
             lane_change_active: bool = False, highway: bool = False,
             vision_obstacles: list | None = None) -> float:
    """每控制周期调用, 返回应叠加的曲率(rad/m)。v_ego: m/s, dt: s。

    lane_change_active: 模型换道中 -> 抑制曲线(换道轨迹与曲线叠加打架,
    且换道本身就是在绕行)。detector 仍正常推进(限速持续有效)。
    highway: 道路类型(限速>=80), 居中障碍的默认绕向(高速左绕/普通路右绕)。
    vision_obstacles: YOLO 视觉小目标检测结果(list[VisionObstacle]),
    行人/自行车/动物/锥桶等雷达反射不到的目标 -> 折成虚拟 lead 融合,
    与雷达 leadOne 取更危险(更近)者喂状态机(阶段1 限速 + 阶段2 曲线)。
    """
    # 1. 障碍检测(时间防抖, 与 carrot_man 的频率无关)
    lead_cur = lead
    cs = None
    rs = None
    # carState 必须先取: 早期版本把它放在 radarState 分支之后, 而本树 LeadData
    # 没有 present 字段(只有 status), 读 .present 抛 AttributeError 被 except
    # 吞掉 -> cs 永远为 None -> _detect_obstacle 返回 no-data -> 只要 radarState
    # 活着避障就永久失效(台架实测 reason 恒为 "-")。
    if sm is not None:
      try:
        cs = sm['carState'] if sm.valid.get('carState', False) else None
      except Exception:
        cs = None
      try:
        rs = sm['radarState'] if sm.alive.get('radarState', False) else None
        if rs is not None:
          # 本树 log.capnp 的 LeadData 无 present 字段, 用 status 判定有无前车
          has_lead = bool(getattr(rs.leadOne, 'status', False))
          lead_cur = rs.leadOne if has_lead else None
      except Exception:
        rs = None
    if lead_cur is None and lead is not None:
      lead_cur = lead

    # 1a. 视觉小目标融合: 本车道内(横向偏移 < MAX_TRIGGER_DPATH_M)最近的
    # 视觉障碍 -> 虚拟 lead。行人/自行车/动物/锥桶雷达反射弱或不反射,
    # 只靠 radarState 检测不到(用户反馈: 检测不到避障就是扯蛋)。
    # 虚拟 lead 视为静止/极慢目标(vLead=0, 与真静止门槛一致), 驱动
    # 与雷达相同的状态机(限速 + 曲线 + 换道), 与雷达 lead 取更近者。
    if vision_obstacles:
      in_lane = [o for o in vision_obstacles
                 if abs(getattr(o, 'y_rel', 99.0)) <= MAX_TRIGGER_DPATH_M]
      if in_lane:
        nearest_vis = min(in_lane, key=lambda o: getattr(o, 'd_rel', 99.0))
        # VRU(行人/动物/自行车)优先于"移动中的"雷达前车。
        # 原逻辑只取更近者: 回放实测雷达 lead 在 14m 上下摆动, 与视觉行人的 14m
        # 交替主导 -> reason 在 moving-lead / stopped-obstacle 之间每拍翻转 ->
        # 防抖被反复清零, 行人一直在画面里也永远不触发。
        # 移动中的前车本来就该交给 ACC 跟车, 不该掩盖静止的 VRU。
        _lead_vlead_kph = float(getattr(lead_cur, 'vLead', 99.0)) * 3.6 if lead_cur is not None else 999.0
        if (lead_cur is None
            or nearest_vis.d_rel < float(getattr(lead_cur, 'dRel', 99.0))
            or _lead_vlead_kph > TRULY_STOPPED_VLEAD_KPH):
          class _VirtualLead:
            __slots__ = ('dRel', 'dPath', 'vRel', 'vLead', 'yRel', 'conf', 'cls')
          vlead = _VirtualLead()
          vlead.dRel = float(nearest_vis.d_rel)
          vlead.dPath = float(nearest_vis.y_rel)
          vlead.vRel = -3.0  # 视为静止/极慢(行人/动物不会快速让开)
          vlead.vLead = 0.0
          # VisionObstacle.y_rel 是"画面右正"; car frame 是"左正", 取负。
          # 缺这个属性时 _pick_direction 里的 try/except 会把方向永远当居中,
          # 于是只能按道路类型默认绕向, 无法按障碍实际位置选边。
          vlead.yRel = -float(nearest_vis.y_rel)
          # 置信度透传: 快速通道(近距单帧高置信)判据需要它
          vlead.conf = float(getattr(nearest_vis, 'conf', 0.0) or 0.0)
          # 类别透传: 间隙判据按人/车估半宽, 缺它会把行人按车算(0.95m),
          # clearance 被低估 -> 该绕的行人反而不绕。
          vlead.cls = str(getattr(nearest_vis, 'cls', '') or '')
          lead_cur = vlead

    # 状态机推进(结果由 detector.is_active()/estimate() 读取)
    self.detector.update(lead_cur, cs, now=now)

    # 1b. 换道中: 抑制曲线(但 detector 已推进, 限速继续)
    if lane_change_active:
      if self._active:
        self.reset(now)
      return 0.0

    # 1b2. 激活中被追近到窗口下界以内: 已经来不及走完曲线, 立即取消横向
    # 机动、直行刹车(继续按曲线打方向 = 车头横在目标跟前)。
    if self._active:
      _est_now = self.detector.estimate()
      if _est_now is not None and _est_now.d_rel_m < AVOID_MIN_DREL_M:
        self.reset(now)
        self._reason = "abort-curve: target too close, brake only"
        return 0.0

    # 1c. 激活中但目标侧突然 blocked: 立即取消曲线(侧后有车时不能继续
    # 贴边绕行), 只保留限速。方向检查只在触发时做过, 这里每帧复查。
    if self._active:
      dir_now = self._direction
      if dir_now < 0 and left_blocked is True:
        self.reset(now)
        return 0.0
      if dir_now > 0 and right_blocked is True:
        self.reset(now)
        return 0.0

    # 2. 曲线状态推进
    if self._active:
      self._s += max(v_ego, 1.0) * dt
      # 障碍消失且已过保持段 -> 走完回中段后归零
      if not self.detector.is_active() and self._s >= self._L1 + self._L2:
        pass  # 继续回中段
      if self._s >= self._total_len():
        self.reset(now)
        return 0.0

    # 3. 未激活: 评估是否触发
    if not self._active:
      if self.detector.is_active():
        # 快速通道目标(近距高置信单帧): 只限速, 不横向绕行。
        # 12m 内绕行曲线的轨迹会从行人身上压过去, 减速等其通过才安全。
        if getattr(self.detector, '_fast_single', False):
          self._reason = "fast-single: brake only"
          return 0.0
        # 曲线完成/取消后冷却期内不重触发(防同一障碍往复绕行)
        if now is not None and now - self._done_at < CURVE_COOLDOWN_S:
          return 0.0
        est_d = self.detector.estimate()
        d_rel = est_d.d_rel_m if est_d is not None else 40.0
        v_ego_kph = v_ego * 3.6
        # 只对"真静止"障碍绕行曲线: 前车还在蠕动(vLead 3~10km/h 排队)只
        # 限速跟随, 不横向绕出车流(在队列里绕行危险, 且对向借道易撞)。
        # 限速(阶段1)仍对排队生效(vLead<10), 曲线/LC 仅针对 vLead<3。
        v_lead_kph = est_d.v_lead_kph if est_d is not None else 999.0
        # 无车道线(乡镇/村/县城): 允许更大偏移压线, 但限速。
        _no_lane = False
        try:
          if sm is not None and sm.alive.get("modelV2", False):
            _p = list(sm["modelV2"].laneLineProbs)
            _no_lane = (len(_p) >= 4 and _p[1] < NO_LANE_PROB and _p[2] < NO_LANE_PROB)
        except Exception:
          pass
        self._no_lane = _no_lane
        _off_now = NO_LANE_MAX_OFFSET_M if _no_lane else MAX_OFFSET_M
        # 间隙判据: 偏移 _off_now 后与目标的横向间隙是否够。不足 -> 不绕只刹车。
        _clear = self._clearance(lead_cur, _off_now)
        if _clear is not None and _clear < CLEAR_MARGIN_M:
          self._reason = f"no-clearance({_clear:+.1f}m): brake only"
          return 0.0
        # 间隙已充足: 本车道无阻挡, 不需要横移(邻道目标不误触曲线)。
        if _clear is not None and _clear >= AVOID_MAX_CLEAR_M:
          self._reason = f"clear-enough({_clear:+.1f}m): no steer"
          return 0.0
        # 距离窗口(来不及就只刹车):
        #   d_need  = 偏出段长度(与 _setup_curve 同源: max(MIN_SIDE, v*SIDE_SEC))
        #             + 余量, 保证"偏出完成时还离目标足够远";
        #   d_start = 太远也不触发(等靠近), 但按 v*2.5 提前, 高速才有预见性。
        _l1_full = max(MIN_SIDE_M, v_ego * SIDE_SEC)
        d_need = max(AVOID_MIN_DREL_M,
                     min(_l1_full + AVOID_MARGIN_M, MAX_TRIGGER_DREL_M))
        d_start = min(MAX_TRIGGER_DREL_M,
                      max(NEAR_AVOID_M, v_ego * AVOID_START_TIME_S))
        _too_close = d_rel < d_need
        if _too_close:
          self._reason = f"too-close({d_rel:.0f}m<{d_need:.0f}m): brake only"
        if (not _too_close and d_rel <= d_start and v_ego_kph >= MIN_TRIGGER_SPEED_KPH
            and v_lead_kph < TRULY_STOPPED_VLEAD_KPH
            and not (_no_lane and v_ego_kph > NO_LANE_MAX_SPEED_KPH)):
          direction = self._pick_direction(lead_cur, sm, left_blocked, right_blocked, highway=highway)
          if direction != 0:
            self._setup_curve(v_ego, d_rel, direction, no_lane=_no_lane)
            self._active = True
            self._reason = f"avoid-curve d={d_rel:.0f}m dir={'L' if direction < 0 else 'R'}"
            return self._kappa_at(0.0)
      return 0.0

    # 4. 激活中: 查曲线曲率, 限幅
    kappa = self._kappa_at(self._s)
    # 横向加速度限制: a = kappa * v^2 <= MAX_LAT_ACCEL
    max_k = MAX_LAT_ACCEL_MPS2 / max(v_ego * v_ego, 0.25)
    if abs(kappa) > max_k:
      kappa = math.copysign(max_k, kappa)
    self._last_kappa = kappa
    return kappa

  @property
  def offset_now(self) -> float:
    """当前横向偏移(m, 右正左负), 用于调试/UI。"""
    if not self._active:
      return 0.0
    O, L1, L2, L3 = self._O, self._L1, self._L2, self._L3
    s = self._s

    def _q(r: float) -> float:
      return 10.0 * r ** 3 - 15.0 * r ** 4 + 6.0 * r ** 5

    if s < L1:
      return O * _q(s / L1)
    if s < L1 + L2:
      return O
    return O * (1.0 - _q((s - L1 - L2) / L3))
