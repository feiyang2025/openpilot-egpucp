#!/usr/bin/env python3
"""原车前雷达的「前侧盲区」检测（左/右相邻车道是否有妨碍变道的目标）。

移植并重写自 cpv9-dev ``controls/lib/desire_helper.py`` 的
``leftFrontBlind`` / ``rightFrontBlind`` 计算（约 700~734 行）。

**原实现的几个问题（本模块已改掉）**：

1. 用 ``abs(vLead) > 2.8`` —— 拿**绝对车速**当判据。侧后方静止的车
   （vLead≈0）永远判不出，而远处同向快车（vLead 很大）却会误判。
   侧车道威胁只与**相对速度** vRel 有关，这里改用 vRel。
2. ``side_object_dist = dRel + vLead * 3.0`` —— 同样把绝对速度当成接近
   速度用。改为 ``dRel + vRel * horizon``（相对速度外推）。
3. 没有横向判定：不区分"本车道前车 / 相邻车道目标 / 再远一条车道的车"，
   任何被雷达认成 leadLeft/leadRight 的目标都算数。这里按车道宽做横向门限。
4. 单点阈值、没有去抖 → 临界处来回跳。这里加了进入/退出延时（迟滞）。
5. 阈值全部硬编码（3.0s / 2.8 / v_ego*4），这里全部参数化（见 config.py）。

判据（单侧）::

  1) 雷达目标有效（present）
  2) 纵向：0 < dRel <= 前向窗口（原车前雷达只可能报前方目标）
  3) 风险（满足其一）：
       * 预测窗口后的剩余间距 < 安全间距(max(v_ego*时距, 最小间距))
       * 当前间距 < 安全间距
       * TTC < 阈值
  4) 去抖：连续 risky 达 on_time 才置位，连续不 risky 达 off_time 才清除

**横向不再判定**：``radarState.leadLeft/leadRight`` 由
``selfdrive/controls/lib/side_leads.py`` 产出，那里已经用 ``dPath``（雷达点到
**模型预测路径**的法向距离）把本车道目标（``|dPath| < 1.8``）和再外侧目标
（``|dPath| >= 3.5``）都滤掉了，并且提前做了 ``dRel > 5.0`` 的近距过滤。

所以这里既不需要按车道宽再判一次横向，也不需要"身后"窗口：
原先的 ``lat_min/lat_max/lat_lane_factor`` 门槛比 upstream 宽，
直路上永远不会触发（上游保证 ``|dPath| ∈ [1.8, 3.5)``，而门槛是
``[1.75, 5.0]``）；而 ``drel_min = -20m`` 更是不可能命中，因为上游已经
保证 ``dRel > 5.0``。

参数全部走 amapnavi 自己的参数模块（``config.py`` 的 ``UnifiedParams``），
不往 openpilot 的 ``params_keys.h`` 里加东西。
"""

from dataclasses import dataclass, field

from openpilot.selfdrive.carrot.amapnavi.config import unified_params

# 单位换算：参数以 0.1 为单位存储（与 amapnavi 其它参数一致）
_SCALE = 0.1

@dataclass
class StockFrontBlindConfig:
  """原车前侧盲区的判据参数。

  横向筛选不在这里：``side_leads`` 已经用 dPath 把范围限定在 [1.8, 3.5) m
  并把 dRel <= 5.0 的目标滤掉了，这里只负责纵向窗口与风险评估。
  """

  enable: bool = True
  drel_max_m: float = 80.0        # 纵向窗口：前向（上游已保证 dRel > 5.0）
  time_headway_s: float = 0.0     # 安全时距（0 = 不启用，danger 退化为 min_clearance）
  min_clearance_m: float = 4.0    # 绝对最小纵向间距（时距算出的下限兜底）
  ttc_threshold_s: float = 2.5    # TTC 阈值
  horizon_s: float = 3.0          # 预测窗口（一次完整变道）
  on_time_s: float = 0.3          # 置位需要持续 risky 的时间
  off_time_s: float = 0.8         # 清除需要持续不 risky 的时间

  @classmethod
  def from_params(cls, params=unified_params) -> "StockFrontBlindConfig":
    def i(key, default):
      try:
        value = int(params.get_int(key))
      except Exception:
        value = default
      return value

    return cls(
      enable=bool(i("StockFrontBlindEnable", 1)),
      drel_max_m=float(i("StockFrontDrelMax", 800) * _SCALE),
      time_headway_s=max(0.0, i("StockFrontTimeHeadway", 0) * _SCALE),
      min_clearance_m=max(0.5, i("StockFrontMinClearance", 40) * _SCALE),
      ttc_threshold_s=max(0.1, i("StockFrontTtc", 25) * _SCALE),
      horizon_s=max(0.5, i("StockFrontHorizon", 30) * _SCALE),
      on_time_s=max(0.0, i("StockFrontOnTime", 3) * _SCALE),
      off_time_s=max(0.0, i("StockFrontOffTime", 8) * _SCALE),
    )


@dataclass
class SideDecision:
  """单侧一帧的判定明细（便于调试与单元测试）。"""

  active: bool = False
  raw: bool = False
  lateral_m: float = 0.0
  drel_m: float = 0.0
  vrel_mps: float = 0.0
  clearance_m: float = 999.0
  ttc_s: float | None = None
  reason: str = "no_target"


@dataclass
class _SideState:
  active: bool = False
  on_timer: float = 0.0
  off_timer: float = 0.0
  last: SideDecision = field(default_factory=SideDecision)


def lateral_offset(lead) -> float:
  """目标相对本车行驶轨迹的横向偏移（m，左正右负由调用方按侧别处理）。

  优先用 ``dPath``（用模型预测路径算的横向距离，弯道更准），
  没有时退回雷达自身的 ``yRel``。
  """
  d_path = float(getattr(lead, "dPath", 0.0) or 0.0)
  if abs(d_path) > 0.05:
    return d_path
  return float(getattr(lead, "yRel", 0.0) or 0.0)


def _lead_present(lead) -> bool:
  """LeadData 里到底有没有目标。

  上游 capnp 的字段名是 ``present``；carrot 原版代码写的是 ``status``（旧字段名），
  直接照搬过来会永远取到 False —— 表现为"前侧盲区从来没触发过"。两个都兼容。
  """
  if lead is None:
    return False
  return bool(getattr(lead, "present", False) or getattr(lead, "status", False))


def evaluate_side(lead, v_ego_mps: float, cfg: StockFrontBlindConfig) -> SideDecision:
  """评估单侧原车前雷达目标是否构成「前侧盲区」。

  横向筛选已由 ``side_leads`` 完成（``|dPath| ∈ [1.8, 3.5)``、``dRel > 5.0``），
  这里不再重复判定，只做纵向窗口与风险评估。
  """
  if lead is None or not _lead_present(lead):
    return SideDecision(reason="no_target")

  drel = float(getattr(lead, "dRel", 0.0) or 0.0)
  vrel = float(getattr(lead, "vRel", 0.0) or 0.0)
  lat = abs(lateral_offset(lead))            # 仅用于诊断，不参与判定

  # ---- 纵向窗口：原车前雷达只可能探测到前方目标 ----
  if drel <= 0.0 or drel > cfg.drel_max_m:
    return SideDecision(raw=False, lateral_m=lat, drel_m=drel, vrel_mps=vrel, reason="out_of_range")

  # ---- 风险：预测窗口内的最小间距 + TTC ----
  d_end = drel + vrel * cfg.horizon_s
  if drel * d_end < 0:                       # 窗口内会并肩通过 → 间距按 0 算
    clearance = 0.0
  else:
    clearance = min(abs(drel), abs(d_end))
  # 安全间距：时距为主、绝对距离兜底。time_headway_s = 0 表示不启用时距，
  # 此时 safe 恒等于 min_clearance_m（纯绝对距离判据）。
  safe = max(v_ego_mps * cfg.time_headway_s, cfg.min_clearance_m)

  ttc = None
  if vrel < 0.0:                             # 正在被追上（drel 已保证 > 0）
    ttc = drel / -vrel

  ttc_risk = ttc is not None and 0.0 <= ttc < cfg.ttc_threshold_s

  # 目标在前方、且比本车快 → 纵向间距在**变大**。
  # 这时拿 safe = v_ego × 时距 去比较是错的尺度：它衡量的是"我多久会追上去"，
  # 而间距在扩大时这个风险根本不成立。实测表现就是侧前车已经加速远离到
  # 二三十米外、盲区图标还挂着不放（高速下 safe 可到 30m 以上）。
  # 间距在变大时，只有已经小到"快要并肩"才算真冲突（min_clearance 兜底）。
  receding_ahead = drel > 0.0 and vrel > 0.0
  if receding_ahead:
    clearance_risk = drel < cfg.min_clearance_m
  else:
    clearance_risk = clearance < safe
  raw = bool(ttc_risk or clearance_risk)

  reason = "clear"
  if ttc_risk:
    reason = "ttc"
  elif clearance_risk:
    reason = "clearance"
  elif receding_ahead:
    reason = "receding"

  return SideDecision(raw=raw, lateral_m=lat, drel_m=drel, vrel_mps=vrel,
                      clearance_m=clearance, ttc_s=ttc, reason=reason)


class StockFrontBlindMonitor:
  """带迟滞的原车前侧盲区监视器（左右各一份状态）。"""

  def __init__(self, cfg: StockFrontBlindConfig | None = None, params=unified_params):
    # 容错：把参数对象当 cfg 位置参数传进来时自动纠正（历史踩过的坑——
    # self.cfg 成了 UnifiedParams，每帧在 cfg.enable 上抛 AttributeError，
    # 而本模块跑在 amapnavi 主数据循环里，异常会连带跳过该帧后续所有逻辑）。
    if cfg is not None and not isinstance(cfg, StockFrontBlindConfig):
      params = cfg
      cfg = None
    self.params = params
    self.cfg = cfg or StockFrontBlindConfig.from_params(params)
    self._sides = {"left": _SideState(), "right": _SideState()}
    self._param_frame = 0

  # ------------------------------------------------------------------ 参数
  def refresh_config(self, every_n_frames: int = 20) -> None:
    """周期性刷新参数（默认每秒左右一次，DATA_HZ=20）。"""
    self._param_frame += 1
    if self._param_frame % max(1, every_n_frames) == 0:
      self.cfg = StockFrontBlindConfig.from_params(self.params)

  # ------------------------------------------------------------------ 主入口
  def update(self, dt: float, v_ego_mps: float, leads: dict) -> dict:
    """:param leads: ``{"left": LeadData|None, "right": LeadData|None}``
       :return: ``{"left": bool, "right": bool}``"""
    if not self.cfg.enable:
      for st in self._sides.values():
        st.active = False
        st.on_timer = 0.0
        st.off_timer = 0.0
        st.last = SideDecision(reason="disabled")
      return {"left": False, "right": False}

    out = {}
    for side, st in self._sides.items():
      decision = evaluate_side(leads.get(side), v_ego_mps, self.cfg)
      st.last = decision

      if decision.raw:
        st.on_timer = min(st.on_timer + dt, max(self.cfg.on_time_s, dt))
        st.off_timer = 0.0
        if st.on_timer >= self.cfg.on_time_s:
          st.active = True
      else:
        st.off_timer = min(st.off_timer + dt, max(self.cfg.off_time_s, dt))
        st.on_timer = 0.0
        if st.off_timer >= self.cfg.off_time_s:
          st.active = False

      decision.active = st.active
      out[side] = st.active
    return out

  # ------------------------------------------------------------------ 诊断
  def detail(self, side: str) -> SideDecision:
    return self._sides[side].last


def _model_front_blind(sm, side: str) -> bool:
  """模型（视觉）给的前侧盲区：本 fork 的 modelV2.meta 未必有该字段，取不到按 False。"""
  if not sm.alive['modelV2']:
    return False
  meta = sm['modelV2'].meta
  key = f"{side}FrontBlind"
  if not hasattr(meta, key):
    return False
  return bool(getattr(meta, key))


def apply_stock_front_blind(shared_data, sm, dt: float,
                            monitor: "StockFrontBlindMonitor | None" = None,
                            v_ego_mps: float | None = None) -> StockFrontBlindMonitor:
  """用原车前雷达补算 ``shared_data.leftFrontBlind`` / ``rightFrontBlind``。

  与模型的视觉结果按 **OR** 合并（与本 fork "视觉盲区与 OEM 盲区 OR 合并、
  视觉结果永不清除 OEM 盲区" 的约定一致）：任一方判盲区即为盲区。
  功能关闭时直接返回，此时 messages.py 会退回模型自身的值。
  """
  monitor = monitor if monitor is not None else StockFrontBlindMonitor()
  monitor.refresh_config()
  if not monitor.cfg.enable:
    # 功能关闭时清掉标志，避免关掉之后图标/护栏还挂在关闭前的 True 上
    shared_data.leftFrontBlind = False
    shared_data.rightFrontBlind = False
    return monitor

  v_ego = v_ego_mps if v_ego_mps is not None else (shared_data.v_ego_m or 0.0)

  radar = sm['radarState'] if sm.alive['radarState'] else None
  leads = {"left": None, "right": None}
  if radar is not None:
    leads["left"] = getattr(radar, "leadLeft", None)
    leads["right"] = getattr(radar, "leadRight", None)

  result = monitor.update(dt, v_ego, leads)

  shared_data.leftFrontBlind = bool(result["left"]) or _model_front_blind(sm, "left")
  shared_data.rightFrontBlind = bool(result["right"]) or _model_front_blind(sm, "right")
  return monitor
