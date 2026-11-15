#!/usr/bin/env python3
"""P3 横向避让状态机(台架)——L0 in-lane S / L1 跨线 / L2 变道,全部已签判据,零发明。

判据索引:
  §7.6 可行性: 车宽1.8+目标0.8+余量0.3 → 中心 δ_req=1.6 > 可用 ≈0.85 → 中心档 in-lane 不可行;
      横向名义上限 v ≤ 40 km/h(R79 门控),错误横移尾部风险大 → 几何硬约束优先
  §7.8 S 型: 仅限目标中心压线(|y|≥0.75)成人/两轮车,δ=0.75;儿童须联合降速(§7.9)
  §7.9 联合: lead 折扣 a·(2T_out)²/2 已并入剖面 L;AEB/|a|>3.0 → offset 命令首 tick 归零,
      实际偏移沿 ≤0.3 m/s 限速退出
  §7.10 跨线双门: 虚线(视觉+地图双源一致,conf≥0.9) + 安全窗 gap ≥ T_full+T_margin;
      L1 深度 ≤0.75 m;中止三条(出段前退 L0/出段中驻位不回拉/驻段>2s 走 L2 不自动回原道);
      rebase 无回冲 <0.1 m
  §9.8 剖面域: T_out=(60δ/J)^(1/3)、a_lat_peak=5.7735δ/T_out²、恒减速仅 v_end≥v_min 才可用,
      否则分段降到 v_min 保持,再不行 pure braking;负速度恒减速一律拒绝;+10.2 为夹具距离常数
  G8/G9/G10;诚实边界: 输出 offset cmd 与档位,不接 EPS;实车几何由 G15_steer 复测。
"""
import math

J = 3.0
VMIN = 1.0               # §9.8 候选
L_CONST = 10.2           # §9.8 剖面距离常数(夹具)
V_MAX_KMH = 40.0         # §7.6/R79
DELTA_EDGE = 0.75        # 压线 S 档位移
DELTA_CENTER = 1.6       # 中心档需求(§7.6)
LANE_HALF_AVAIL = 0.85   # 车道宽内可用横移
Y_EDGE_TH = 0.75         # 压线判定
CROSS_DEPTH_MAX = 0.75   # L1 深度上限(§7.10)
T_MARGIN_S = 2.0         # 安全窗裕量(G10: 9s 过 / 6s 拒)
OFFSET_RATE = 0.3        # 偏移速率上限 m/s(§7.9)
CONF_GATE = 0.9          # 门 A 置信(§7.10)
HOLD_TO_L2_S = 2.0       # 驻段>2s 走 L2(§7.10)
RESIDUAL_MAX = 0.15      # 回摆残余(G8)
LOW_CLS = (4, 5, 6)      # animal/cone/debris: 一律不横向

# 档位
LAT_NONE, LAT_S, LAT_CROSS, LAT_CHANGE = 0, 1, 2, 3
LAT_NAME = {0: "NONE", 1: "L0_S_INLANE", 2: "L1_CROSS", 3: "L2_CHANGE"}
# 阶段
PH_IDLE, PH_OUT, PH_HOLD, PH_BACK = 0, 1, 2, 3
PH_NAME = {0: "IDLE", 1: "OUT", 2: "HOLD", 3: "BACK"}


def t_out(delta: float) -> float:
  return (60.0 * delta / J) ** (1.0 / 3.0)


def a_lat_peak(delta: float) -> float:
  tt = t_out(delta)
  return 5.7735 * delta / (tt * tt)


def plan_profile(delta: float, v_kmh: float, a: float = 0.0,
                 a_peak: float | None = None, T_p: float = 0.0) -> dict:
  """§9.8 剖面: 先判恒减速适用域(v_end≥v_min),不适用且给 a_peak 则分段,再不行拒绝。"""
  v = v_kmh / 3.6
  Tout = t_out(delta)
  T_full = 2 * Tout + T_p
  v_end = v - a * T_full
  if v_end >= VMIN:
    return {"model": "constant", "T_out": Tout, "T_full": T_full, "T_b": None,
            "L": v * T_full - a * T_full * T_full / 2 + L_CONST,
            "v_end": v_end, "feasible": True, "reason": "const"}
  if a_peak:
    T_b = (v - VMIN) / a_peak
    if T_b <= T_full:
      L = (v * v - VMIN * VMIN) / (2 * a_peak) + VMIN * (T_full - T_b) + L_CONST
      return {"model": "peak_to_floor", "T_out": Tout, "T_full": T_full, "T_b": T_b,
              "L": L, "v_end": VMIN, "feasible": True, "reason": "piecewise"}
    return {"model": "rejected", "T_out": Tout, "T_full": T_full, "T_b": T_b,
            "L": None, "v_end": v_end, "feasible": False, "reason": "T_b_gt_T_full"}
  # 恒减速不适用仍报原始 L/v_end(§9.8 夹具口径),feasible=False 即拒绝
  return {"model": "rejected", "T_out": Tout, "T_full": T_full, "T_b": None,
          "L": v * T_full - a * T_full * T_full / 2 + L_CONST,
          "v_end": v_end, "feasible": False, "reason": "neg_v_end"}


class LateralAvoidance:
  def __init__(self):
    self.level = LAT_NONE
    self.phase = PH_IDLE
    self.offset = 0.0        # 平滑后的命令偏移(状态,非车体)
    self._target_offset = 0.0
    self._ph_t0 = 0.0
    self.last_now = 0.0
    self.last = {}

  def reset(self):
    self.__init__()

  # ---- 内部门 ----
  def _slew(self, target: float, now: float) -> float:
    """offset 命令限速 ≤0.3 m/s(§7.9);AEB 首帧归零由调用方直接置 0。"""
    dt = max(0.0, min(0.1, now - self.last_now)) if self.last_now else 0.0
    step = OFFSET_RATE * dt
    if target > self.offset:
      self.offset = min(target, self.offset + step)
    else:
      self.offset = max(target, self.offset - step)
    return self.offset

  def update(self, targets, v_kmh: float, now: float,
             line_vis: str = "unknown", line_map: str = "unknown",
             line_conf: float = 0.0, gap_s: float | None = None,
             aeb_active: bool = False, degraded: bool = False):
    """targets: [{x,y,cls,hEst,tier}...](decider 输出同源);
    line_vis/line_map ∈ {dashed,solid,double,none,unknown};gap_s=同向邻道时距。
    返回 dict(level,phase,offsetCmd,aJointFloor,reason,profile)。"""
    self.last_now = now
    out_reason = ""
    prof = None
    a_joint = None

    # 遮挡/degraded: 禁一切横向档(§7.13),沿限速回 0
    if degraded:
      self._slew(0.0, now)
      self.level, self.phase = LAT_NONE, PH_IDLE
      self.last = {"level": 0, "phase": 0, "offsetCmd": round(self.offset, 3),
                   "aJointFloor": None, "reason": "degraded_suppressed", "profile": None}
      return self.last

    # AEB 激活: offset 命令首 tick 归零(G9),横向档全部让位
    if aeb_active:
      self.offset = 0.0
      self._target_offset = 0.0
      self.level, self.phase = LAT_NONE, PH_IDLE
      self.last = {"level": 0, "phase": 0, "offsetCmd": 0.0, "aJointFloor": None,
                   "reason": "aeb_offset_zero", "profile": None}
      return self.last

    # R79/速度门: >40 不新增横向档,存量沿限速退出
    if v_kmh > V_MAX_KMH:
      self._slew(0.0, now)
      self.level, self.phase = LAT_NONE, PH_IDLE
      self.last = {"level": 0, "phase": 0, "offsetCmd": round(self.offset, 3),
                   "aJointFloor": None, "reason": "v_over_40", "profile": None}
      return self.last

    # 目标选择: tier≥2 且 |y|<2.0 中最近
    cand = [t for t in (targets or [])
            if int(t.get("tier", 0)) >= 2 and abs(float(t.get("y", 0))) < 2.0]
    cand.sort(key=lambda t: float(t.get("x", 1e9)))

    if not cand:
      # 无目标: 若在机动中 → 回摆(PH_BACK),否则空闲
      if self.phase == PH_OUT:            # 出段前中止 → 退 L0 制动(§7.10 中止①)
        self._slew(0.0, now)
        self.level, self.phase = LAT_NONE, PH_IDLE
        out_reason = "abort_before_out_brake"
      elif self.phase in (PH_HOLD, PH_BACK):
        self._slew(0.0, now)
        if abs(self.offset) <= RESIDUAL_MAX:
          self.offset = 0.0
          self.level, self.phase = LAT_NONE, PH_IDLE
          out_reason = "returned"
        else:
          out_reason = "back_slew"
      else:
        out_reason = "no_target"
      self.last = {"level": self.level, "phase": self.phase,
                   "offsetCmd": round(self.offset, 3), "aJointFloor": None,
                   "reason": out_reason, "profile": None}
      return self.last

    t0 = cand[0]
    x, y = float(t0["x"]), float(t0["y"])
    cls, h_est = int(t0.get("cls", 7)), float(t0.get("hEst", 0.0))

    # 低矮类: 一律不横向(§7.8 覆盖域/§9.8 低矮反证)
    if cls in LOW_CLS or 0 < h_est < 1.0:
      self._slew(0.0, now)
      self.level, self.phase = LAT_NONE, PH_IDLE
      self.last = {"level": 0, "phase": 0, "offsetCmd": round(self.offset, 3),
                   "aJointFloor": None, "reason": "low_class_brake_only", "profile": None}
      return self.last

    is_child = (cls == 1) or (0 < h_est < 1.45 and cls == 0)  # 修订25: 1.40-1.45 归 50 档儿童处置
    edge = abs(y) >= Y_EDGE_TH

    # 已在机动中: 推进阶段机(保持既有档位语义,不每帧重判)
    if self.phase == PH_OUT:
      if now - self._ph_t0 >= self._out_T:
        self.phase, self._ph_t0 = PH_HOLD, now
        out_reason = "out_done_hold"
      else:
        out_reason = "out_phase"
      self._slew(self._target_offset, now)
      self.last = {"level": self.level, "phase": self.phase,
                   "offsetCmd": round(self.offset, 3), "aJointFloor": self._a_joint,
                   "reason": out_reason, "profile": self._prof}
      return self.last
    if self.phase == PH_HOLD:
      if now - self._ph_t0 > HOLD_TO_L2_S:
        self.level = LAT_CHANGE          # 驻段>2s: L2 不自动回原道(§7.10 中止③)
        out_reason = "hold_over_2s_L2"
      else:
        out_reason = "hold"
      self._slew(self._target_offset, now)
      self.last = {"level": self.level, "phase": self.phase,
                   "offsetCmd": round(self.offset, 3), "aJointFloor": self._a_joint,
                   "reason": out_reason, "profile": self._prof}
      return self.last

    # ---- 新机动准入 ----
    if edge:
      delta, lead_gate_dir = DELTA_EDGE, "edge"
      a_joint = -2.0 if is_child else None      # 儿童: 压线也须联合降速(§7.9)
    else:
      delta, lead_gate_dir = DELTA_CENTER, "center"
      a_joint = -2.0 if is_child else None      # 中心档儿童: 联合 a_peak=2(§9.8 夹具)

    # in-lane 可行性(§7.6)
    inlane_ok = delta <= LANE_HALF_AVAIL
    a_use = 0.0 if (not is_child and edge) else 1.5   # 成人压线纯 S;其余联合 ≥1.5
    prof = plan_profile(delta, v_kmh, a=a_use, a_peak=2.0 if is_child else None)

    # lead 门: 目标距离 ≥ 剖面 L
    lead_ok = prof["feasible"] and x >= prof["L"]

    if inlane_ok and lead_ok and edge:
      # L0 压线 S(成人纯 S / 儿童联合)
      self.level, self.phase = LAT_S, PH_OUT
      self._ph_t0, self._out_T = now, prof["T_out"]
      self._target_offset = -math.copysign(delta, y)   # 向目标反侧偏
      self._a_joint, self._prof = a_joint, prof
      out_reason = "L0_edge_S" + ("_joint" if is_child else "_pure")
    elif not inlane_ok or (not lead_ok and self._cross_gate(line_vis, line_map, line_conf, gap_s, prof)):
      # L1 跨线: 双门(§7.10);中心档成人也须过双门
      if not self._cross_gate(line_vis, line_map, line_conf, gap_s, prof):
        self._slew(0.0, now)
        out_reason = "cross_gate_denied_brake"
        self.level, self.phase = LAT_NONE, PH_IDLE
      else:
        depth = min(delta, CROSS_DEPTH_MAX)
        self.level, self.phase = LAT_CROSS, PH_OUT
        self._ph_t0, self._out_T = now, prof["T_out"]
        self._target_offset = -math.copysign(depth, y)
        self._a_joint, self._prof = a_joint, prof
        out_reason = "L1_cross"
    else:
      self._slew(0.0, now)
      self.level, self.phase = LAT_NONE, PH_IDLE
      out_reason = "lead_insufficient_brake" if not lead_ok else "inlane_infeasible_brake"

    self.last = {"level": self.level, "phase": self.phase,
                 "offsetCmd": round(self.offset, 3), "aJointFloor": self._a_joint if self.phase == PH_OUT else None,
                 "reason": out_reason, "profile": prof}
    return self.last

  def _cross_gate(self, line_vis, line_map, line_conf, gap_s, prof) -> bool:
    """§7.10 门 A 线型(双源一致虚线+conf≥0.9) + 门 B 安全窗(gap ≥ T_full+T_margin)。"""
    if not (line_vis == "dashed" and line_map == "dashed" and line_conf >= CONF_GATE):
      return False
    if gap_s is None or prof is None or not prof["feasible"]:
      return False
    return gap_s >= prof["T_full"] + T_MARGIN_S
