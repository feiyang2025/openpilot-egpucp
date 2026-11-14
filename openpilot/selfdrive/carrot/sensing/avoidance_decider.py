#!/usr/bin/env python3
"""避让决策核(原型,P0 台架)——按已签设计 v1.24 判据实现,零发明。

输入均为 SmallObjectTracks 消息一手字段 + carState.vEgo;
输出 per-track 动作档 tier(词义=修订19: 感知三态与动作分层)。

已签判据索引:
  §0.7 名义包络: adult 60(维持65)/child 50(维持55)/low 40(维持45);横向另行
  D1 单目车型: 舒适档上限 45、TTC 门 3.2s(成人);60 档只 prepare+告警,紧急交 AEB
  §3.3 TTC_entry: adult 4.0(单目3.2)/child 3.5/low 2.5(AEB 交接);D_check=D(v,T0=.70)
  §7.12 静止提前带: τ_potential=d_corr/1.6 只做 prepare 准入,step-off 后时钟归零
  §6.6.2/E 代价模型: p* thresholds 2.0e-5/9.99e-4/2.99e-3(gating 属 G13 融合概率,
      原型期以感知置信档位 proxy 并显式注明,不在本核拍 p_c)
  row17(修订25): 儿童实高 <1.09m 由 50 档回落 40 档处置
  修订24: 儿童类 (1.0,1.4];修订25: 成人 ≥1.45,1.40-1.45 归 50 档
"""
import math

# ---- 常量(已签) ----
T0_S = 0.70                # §7.15 执行响应(所有 D_check 以此)
J, A_CONF, TAU = 3.0, 3.0, 1.0   # §7.15 舒适 jerk/加速度/τ
F_PX_1280 = 1372.0
PX_GATE_STAND, PX_GATE_LOW = 30.0, 12.0
V_W = 1.6                  # §7.12 行走速度上界(τ_potential 分母)
STEP_OFF_V = 0.3           # §7.12: |v|≥0.3 连续3帧
STEP_OFF_N = 3
MONO_COMFORT_CAP_KMH = 45.0       # D1 单目舒适档上限
H_CHILD_BOUNDARY_M = 1.09        # row17 子带上沿;其上按 50 档

# cls: 0 adult 1 child 2 cyclist 3 motorcycle 4 animal 5 cone 6 debris
CLS_ENVELOPE = {           # (名义 enter km/h, 确认维持 km/h, TTC_entry s, px 门)
  0: (60.0, 65.0, 4.0, PX_GATE_STAND),
  1: (50.0, 55.0, 3.5, PX_GATE_STAND),
  2: (60.0, 65.0, 4.0, PX_GATE_STAND),
  3: (60.0, 65.0, 4.0, PX_GATE_STAND),
  4: (40.0, 45.0, 2.5, PX_GATE_LOW),
  5: (40.0, 45.0, 2.5, PX_GATE_LOW),
  6: (40.0, 45.0, 2.5, PX_GATE_LOW),
}

# 动作档(词义分层,修订19)——tier 只增不减(单调)
T_OBSERVE, T_ALERT_ONLY, T_PREPARE, T_COMFORT, T_EMERGENCY = 0, 1, 2, 3, 4
TIER_NAME = {0: "OBSERVE", 1: "ALERT_ONLY", 2: "PREPARE", 3: "COMFORT", 4: "EMERGENCY_AEB_HANDOFF"}


def D_check(v_kmh: float, t0: float = T0_S, a: float = A_CONF) -> float:
  """§7.15 完整停车/动作距离(与结构校验脚本同式同参)。"""
  v = v_kmh / 3.6
  return v * t0 + v * TAU - J * TAU ** 3 / 6 + max(0.0, v - J * TAU ** 2 / 2) ** 2 / (2 * a)


def est_height_m(detPxH: float, d_m: float) -> float:
  """由消息一手值反推实高: h = px·d/f_px(1280 域)。
  detPxH 上游 int 截断,取 (px+0.5) 中心估计,防 1.40/1.09 包络边界的系统性低估。"""
  if detPxH <= 0 or d_m <= 0:
    return 0.0
  return (detPxH + 0.5) * d_m / F_PX_1280


class TrackCtx:
  """决策侧每 track 状态(v_rel 时序窗 + step-off 计数 + tier 单调账)。"""
  __slots__ = ("tier", "d_hist", "stepoff_n", "seen_n", "tier_since_ns")

  def __init__(self):
    self.tier = T_OBSERVE
    self.d_hist = []          # (t_ns, d_m)
    self.stepoff_n = 0
    self.seen_n = 0
    self.tier_since_ns = 0


class AvoidanceDecider:
  def __init__(self, mono_profile: bool = True, hysteresis_floor_s: float = 1.0):
    self.mono = mono_profile
    self.hold_s = hysteresis_floor_s
    self.ctx: dict[int, TrackCtx] = {}
    self.last_now_ns = 0

  def decide(self, tracks, vEgo_kmh: float, now_ns: int):
    """tracks: 小轨道字段容器(需 trackId/cls/x/y/vx/confirmed/detPxH/scoreFused)。"""
    self.last_now_ns = now_ns
    # TTL 清理:5s 未见的 track 上下文退休(防 ctx 无限增长)
    live = {int(tr.trackId) for tr in tracks}
    for tid in list(self.ctx.keys()):
      if tid not in live and self.ctx[tid].d_hist:
        if now_ns - self.ctx[tid].d_hist[-1][0] > 5_000_000_000:
          del self.ctx[tid]
    v_cap = MONO_COMFORT_CAP_KMH if self.mono else 1e9
    out = []
    max_tier = T_OBSERVE
    for tr in tracks:
      tid = int(tr.trackId)
      ctx = self.ctx.setdefault(tid, TrackCtx())
      ctx.seen_n += 1
      d = max(0.05, float(tr.x))                  # x=前进距(消息一手)
      ctx.d_hist.append((now_ns, d))
      if len(ctx.d_hist) > 8:
        ctx.d_hist.pop(0)

      # 闭合速度 v_rel(近端时序窗斜率;静止→0)
      v_rel = 0.0
      if len(ctx.d_hist) >= 3:
        (t0_, d0), (t1_, d1) = ctx.d_hist[0], ctx.d_hist[-1]
        dt = (t1_ - t0_) / 1e9
        if dt >= 0.099:                              # 三帧恰好 0.1s 也算有效窗
          v_rel = max(0.0, (d0 - d1) / dt)        # m/s 正=接近
      moving = (abs(float(tr.vx)) > STEP_OFF_V) or (v_rel > STEP_OFF_V)
      if moving:
        ctx.stepoff_n += 1
      else:
        ctx.stepoff_n = 0                          # §7.12 计数语义:连续

      # 类别回退(修订24/25 + row17): 只换"处置包络",wire 类标签不动
      cls = int(tr.cls)
      h_est = est_height_m(float(tr.detPxH), d)
      env = CLS_ENVELOPE[cls]
      if int(tr.cls) == 0 and 1.40 <= h_est < 1.45:
        env = CLS_ENVELOPE[1]                       # 修订25: 1.40-1.45 归 50 档处置(类仍成人)
      elif int(tr.cls) == 1 and 0 < h_est < H_CHILD_BOUNDARY_M:
        env = CLS_ENVELOPE[6]                       # row17 [a] + D2: <1.09m 子带 40 档处置(类仍儿童)

      enter_kmh, maintain_kmh, ttc_entry, _px_gate = env

      # TTC / 静止提前带(§7.12: step-off 前不进 TTC)
      if ctx.stepoff_n >= STEP_OFF_N:
        ttc = d / max(v_rel, 0.05)
        tau_pot = None
        reason_pre = "stepoff"
      elif moving:
        ttc = d / max(v_rel, 0.05)
        tau_pot = None
        reason_pre = "moving(noscale)"
      else:
        ttc = None
        tau_pot = d / V_W
        reason_pre = "static_band"

      # 动作档判定
      in_gate = False
      if ttc is not None and ttc <= (3.2 if (self.mono and cls in (0, 2, 3)) else ttc_entry):
        in_gate = True
      if tau_pot is not None and tau_pot <= ttc_entry:
        in_gate = True                              # 提前带准入(只准 prepare)

      envelope_in = vEgo_kmh <= enter_kmh or (ctx.tier > T_OBSERVE and vEgo_kmh <= maintain_kmh)

      if not tr.confirmed:
        new = ctx.tier                              # 未确认:不升档(§7.13 三帧确认上游已管)
      elif in_gate and envelope_in and self.mono and vEgo_kmh > v_cap:
        new = T_ALERT_ONLY                          # 单目 >45: 只告警(D1)
      elif in_gate and envelope_in and not self.mono and vEgo_kmh > v_cap:
        new = T_ALERT_ONLY
      elif in_gate and envelope_in:
        # 升档判据锚已签物理式:comfort=d≤D(v,a=3.0) 舒适停;emergency=d≤D(v,a=6.0) 舒适已不够(AEB 交接)
        if ttc is None:
          new = T_PREPARE                           # 提前带只准 prepare
        elif d <= D_check(vEgo_kmh, a=6.0):
          new = T_EMERGENCY
        elif d <= D_check(vEgo_kmh, a=3.0):
          new = T_COMFORT if vEgo_kmh <= v_cap else T_ALERT_ONLY
        else:
          new = T_PREPARE
      elif in_gate and not envelope_in:
        new = T_ALERT_ONLY                          # vEgo 越名义包络: 只告警(§0.7 >60 行)
      else:
        new = ctx.tier if ctx.tier > T_OBSERVE else T_OBSERVE

      # 单调: tier 只升不降(窗口内);迟滞保持 hold_s
      if new > ctx.tier or (now_ns - ctx.tier_since_ns) > self.hold_s * 1e9:
        if new != ctx.tier:
          ctx.tier_since_ns = now_ns
        ctx.tier = max(ctx.tier, new) if new >= ctx.tier else new
        if new >= ctx.tier:
          ctx.tier = new
      out.append({
        "trackId": tid, "cls": cls, "clsRaw": int(tr.cls), "hEst": round(h_est, 2),
        "dM": round(d, 1), "vRel": round(v_rel, 2),
        "ttcS": None if ttc is None else round(ttc, 2),
        "tauPotS": None if tau_pot is None else round(tau_pot, 2),
        "mode": reason_pre, "tier": ctx.tier, "tierName": TIER_NAME[ctx.tier],
        "envelopeKmh": int(enter_kmh), "confirmed": bool(tr.confirmed),
      })
      max_tier = max(max_tier, ctx.tier)
    return out, max_tier, TIER_NAME[max_tier]
