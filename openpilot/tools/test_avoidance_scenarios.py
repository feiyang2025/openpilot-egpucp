#!/usr/bin/env python3
"""避让决策核台架断言套——每条断言锚已签判据;渐近喂帧(恒 v_rel)驱动时序窗。"""
import sys

sys.path.insert(0, "/data/openpilot")
sys.path.insert(0, "/data/openpilot/openpilot/selfdrive/carrot/sensing")
from avoidance_decider import (  # noqa: E402
  AvoidanceDecider, D_check, T_ALERT_ONLY, T_COMFORT, T_EMERGENCY,
  T_OBSERVE, T_PREPARE, est_height_m)

PASS = 0
FAIL = []
NS = 50_000_000


def ok(name, cond, detail=""):
  global PASS
  if cond:
    PASS += 1
    print(" [PASS]", name)
  else:
    FAIL.append(name)
    print(" [FAIL]", name, detail)


class Tr:
  def __init__(self, tid, cls, x, h_m, confirmed=True, vx=0.0):
    self.trackId, self.cls, self.x = tid, cls, x
    self.confirmed, self.vx = confirmed, vx
    self.detPxH = max(1, int(1372.0 * h_m / max(0.05, x)))


class Sim:
  """每步 d -= v_rel·dt,真实驱动 v_rel 时序窗。"""

  def __init__(self, dec, tid, cls, h, vEgo, v_rel):
    self.dec, self.tid, self.cls, self.h = dec, tid, cls, h
    self.vEgo, self.v_rel = vEgo, v_rel
    self.t = 0

  def run(self, d_start, n_steps):
    last = None
    d = d_start
    for _ in range(n_steps):
      self.t += NS
      tr = Tr(self.tid, self.cls, d, self.h, vx=self.v_rel)
      out, mt, mtn = self.dec.decide([tr], self.vEgo, self.t)
      last = out[0]
      d = max(0.1, d - self.v_rel * (NS / 1e9))
    return last


A = 0
ok("D_check(60)=66.18", abs(D_check(60) - 66.18) < 0.02, D_check(60))
ok("D_check(50)=48.69", abs(D_check(50) - 48.69) < 0.02, D_check(50))
ok("D_check(40)=33.78", abs(D_check(40) - 33.78) < 0.02, D_check(40))

# 2. 单目 D1:41kmh 成人 v_rel=12 温渐近 → 带内 TTC≤3.2 ∧ d>D(a3) → PREPARE
dec = AvoidanceDecider(mono_profile=True)
s = Sim(dec, 1, A, 1.70, 41.0, 12.0)
r = s.run(45.0, 14)   # 45→~36.6m,v_rel=12 → TTC 3.05..3.75
ok("41kmh 渐近 TTC≤3.2|d>D(3)→PREPARE", r["tier"] == T_PREPARE, r)

# 3. 继续渐近过 D(a=3.0)=32.96 → COMFORT 只升不降
r = s.run(max(0.1, r["dM"] - 0.001), 8)
ok("d≤D(41,a=3)→COMFORT", r["tier"] == T_COMFORT, r)

# 4. 再近 cross D(a=6.0)=25.5 → EMERGENCY(隔离 dec 防上下文混窗)
decE = AvoidanceDecider(mono_profile=True)
r = Sim(decE, 21, A, 1.70, 41.0, 12.0).run(25.0, 3)
ok("d≤D(41,a=6)→EMERGENCY(AEB 交接)", r["tier"] == T_EMERGENCY, r)

# 5. 单目 >45(50kmh) 舒适禁止 → 带内只告警
dec3 = AvoidanceDecider(mono_profile=True)
r = Sim(dec3, 2, A, 1.70, 50.0, 12.0).run(40.0, 8)   # 40→~35.2 TTC≤3.2 入带
ok("单目 50kmh 带内→ALERT_ONLY(D1)", r["tier"] == T_ALERT_ONLY, r)

# 6. 静止 τ_potential 提前带:d≤TTC_entry·1.6 才入带;锻 PREPARE 不越级
dec4 = AvoidanceDecider(mono_profile=True)
r = Sim(dec4, 3, A, 1.70, 40.0, 0.0).run(5.5, 4)     # τ_pot=5.5/1.6=3.44≤4.0
ok("静止 5.5m τ_pot=3.4→PREPARE(提前带)", r["tier"] == T_PREPARE and r["mode"] == "static_band", r)
r = Sim(dec4, 4, A, 1.70, 40.0, 0.0).run(30.0, 4)    # τ_pot=18.75 出带
ok("静止 30m 出带→OBSERVE", r["tier"] == T_OBSERVE, r)

# 7. 修订25:1.42m"矮成人"→50 档处置(cls 标签仍 adult)
dec5 = AvoidanceDecider(mono_profile=True)
r = Sim(dec5, 5, A, 1.42, 47.0, 0.0).run(30.0, 3)
ok("adult 1.42m→envelope=50(修订25)", r["envelopeKmh"] == 50 and r["clsRaw"] == 0, r)

# 8. row17:1.05m 儿童子带→40 档处置(类仍 child),40 档门=2.5s → τ_pot≤2.5 → d≤4.0
dec6 = AvoidanceDecider(mono_profile=True)
r = Sim(dec6, 6, 1, 1.05, 38.0, 0.0).run(3.5, 4)      # τ_pot=3.5/1.6=2.19≤2.5 入带∧38≤40
ok("child 1.05m→envelope=40 且 PREPARE(row17,40档门2.5s)", r["envelopeKmh"] == 40 and r["tier"] == T_PREPARE, r)

# 9. 儿童越名义包络:55kmh>50 → 静止带内只告警
dec7 = AvoidanceDecider(mono_profile=True)
r = Sim(dec7, 7, 1, 1.20, 55.0, 0.0).run(5.0, 4)
ok("child@55kmh 带内→ALERT_ONLY", r["tier"] == T_ALERT_ONLY, r)

# 10. 未确认不升档
dec8 = AvoidanceDecider(mono_profile=True)
s8 = Sim(dec8, 8, A, 1.70, 40.0, 12.0)
r = None
for d in (36.0,):
  for _ in range(4):
    s8.t += NS
    tr = Tr(8, A, d, 1.70, confirmed=False, vx=12.0)
    r = dec8.decide([tr], 40.0, s8.t)[0][0]
    d = max(0.1, d - 12.0 * (NS / 1e9))
ok("未确认(track=False)带内不升档", r["tier"] == T_OBSERVE, r)

# 11. est_height 往返(detPxH 截断 → px+0.5 中心估计,容差=半像素)
ok("est_height 往返(px+0.5 中心)", abs(est_height_m(1372 * 1.7 / 30, 30) - 1.7) < 0.02,
   est_height_m(1372 * 1.7 / 30, 30))

# 12. 迟滞:确认目标 vEgo 走带内→升档后 42(≤维持? adult 65;child 无关)——成人 65 维持
dec9 = AvoidanceDecider(mono_profile=True)
s9 = Sim(dec9, 9, A, 1.70, 41.0, 12.0)
r = s9.run(45.0, 14)                  # PREPARE
s9.vEgo = 62.0                        # 落回名义上限以下?(62>60 入带维持 65)
r = Sim(dec9, 9, A, 1.70, 62.0, 12.0).run(45.0, 6)
ok("确认后 62≤维持65 band 仍 in_envelope(不退化告警)", r["tier"] >= T_PREPARE, r)

print("\n%d PASS / %d FAIL" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
