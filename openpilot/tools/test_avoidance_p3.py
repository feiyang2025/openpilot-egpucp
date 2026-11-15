#!/usr/bin/env python3
"""P3 横向避让断言套: §9.8 剖面夹具 + 门控语义(G8/G9/G10 台架层)。"""
import sys

sys.path.insert(0, "/data/openpilot")
from openpilot.selfdrive.carrot.sensing.avoidance_lateral import (
    LateralAvoidance, plan_profile, t_out, a_lat_peak)

PASS, FAIL = 0, []
NOW = 1000.0


def ok(name, cond, detail=""):
  global PASS
  if cond:
    PASS += 1
    print(" [PASS]", name)
  else:
    FAIL.append(name)
    print(" [FAIL]", name, detail)


# ===== §9.8 剖面夹具(同式复算,不按表反推) =====
p = plan_profile(0.75, 40.0)
ok("δ0.75 T_out=2.4662", abs(p["T_out"] - 2.4662) < 1e-3, p["T_out"])
ok("δ0.75 T_full=4.9324", abs(p["T_full"] - 4.9324) < 1e-3, p["T_full"])
ok("δ0.75 a_lat_peak=0.7119", abs(a_lat_peak(0.75) - 0.7119) < 1e-3, a_lat_peak(0.75))
ok("纯S L=65.005", abs(plan_profile(0.75, 40.0, a=0.0)["L"] - 65.005) < 0.01,
   plan_profile(0.75, 40.0, a=0.0)["L"])
pj = plan_profile(0.75, 40.0, a=1.5)
ok("联合 a1.5 L=46.758 v_end=3.712", abs(pj["L"] - 46.758) < 0.01 and abs(pj["v_end"] - 3.712) < 1e-3,
   (pj["L"], pj["v_end"]))
pc = plan_profile(1.6, 40.0, a=0.0)
ok("中心纯S L=80.751(>77.8 拒绝域)", abs(pc["L"] - 80.751) < 0.02, pc["L"])
pc2 = plan_profile(1.6, 40.0, a=1.5)
ok("中心 a1.5 L=50.513 v_end=1.587", abs(pc2["L"] - 50.513) < 0.02 and abs(pc2["v_end"] - 1.587) < 1e-3,
   (pc2["L"], pc2["v_end"]))
pk = plan_profile(1.4, 40.0, a=1.5)
ok("儿童中心 a1.5 L=50.017 v_end=2.001", abs(pk["L"] - 50.017) < 0.02 and abs(pk["v_end"] - 2.001) < 1e-3,
   (pk["L"], pk["v_end"]))
pk2 = plan_profile(1.4, 40.0, a=2.0)
ok("儿童中心 a2 恒减速 L=40.796 但 v_end=−1.035 拒绝",
   abs(pk2["L"] - 40.796) < 0.01 and abs(pk2["v_end"] - (-1.035)) < 1e-3 and not pk2["feasible"],
   (pk2["L"], pk2["v_end"], pk2["feasible"]))
pk3 = plan_profile(1.4, 40.0, a=2.0, a_peak=2.0)
ok("儿童中心分段 a_peak=2 → L=41.832 v_end=1.0",
   pk3["feasible"] and abs(pk3["L"] - 41.832) < 0.01 and abs(pk3["v_end"] - 1.0) < 1e-9,
   (pk3["L"], pk3["v_end"]))
pk4 = plan_profile(1.4, 40.0, a=2.0, a_peak=2.0, T_p=0.5)
ok("+T_p=0.5 → L=42.332(禁跨 Tp 复用)", abs(pk4["L"] - 42.332) < 0.01, pk4["L"])
pl = plan_profile(0.525, 40.0, a=1.5)
ok("低矮 δ0.525 L=44.48 > 34.3 门 → 非 L0/L1", abs(pl["L"] - 44.476) < 0.02 and pl["L"] > 34.3, pl["L"])

# ===== 门控语义 =====
def tgt(x, y, cls=0, hEst=1.70, tier=3):
  return {"x": x, "y": y, "cls": cls, "hEst": hEst, "tier": tier}


# 1. v>40 → 不新增横向
la = LateralAvoidance()
r = la.update([tgt(60, 0.9)], 50.0, NOW)
ok("50kmh >40 → 拒绝", r["level"] == 0 and r["reason"] == "v_over_40", r["reason"])
# 2. 成人压线纯 S → L0
la = LateralAvoidance()
r = la.update([tgt(66.0, 0.9)], 40.0, NOW)
ok("成人压线 66m ≥L_S(65.0) → L0 纯 S", r["level"] == 1 and "pure" in r["reason"], (r["level"], r["reason"]))
ok("纯 S 无联合 floor", r["aJointFloor"] is None)
# 3. lead 不足 → 退制动
la = LateralAvoidance()
r = la.update([tgt(60.0, 0.9)], 40.0, NOW)
ok("成人压线 60m <65 → lead 不足退制动", r["level"] == 0 and r["reason"] == "lead_insufficient_brake",
   r["reason"])
# 4. 儿童: 压线也联合(有 floor −2.0)
la = LateralAvoidance()
r = la.update([tgt(50.0, 0.9, cls=1, hEst=1.2)], 40.0, NOW)
ok("儿童压线 50m ≥L(46.76) → L0 联合", r["level"] == 1 and r["aJointFloor"] == -2.0,
   (r["level"], r["aJointFloor"], r["reason"]))
# 5. 中心档儿童 → 双门拒绝(实线)退制动
la = LateralAvoidance()
r = la.update([tgt(45.0, 0.3, cls=1, hEst=1.2)], 40.0, NOW, line_vis="solid", line_map="solid")
ok("儿童中心+实线 → cross 拒绝退制动", r["level"] == 0 and "brake" in r["reason"], r["reason"])
# 6. 中心档儿童 + 虚线双源 + 窗足 → L1
la = LateralAvoidance()
r = la.update([tgt(45.0, 0.3, cls=1, hEst=1.2)], 40.0, NOW, line_vis="dashed", line_map="dashed",
              line_conf=0.95, gap_s=9.0)
ok("儿童中心+虚线+9s 窗 → L1 跨线", r["level"] == 2, (r["level"], r["reason"]))
ok("L1 深度 ≤0.75", abs(r["offsetCmd"]) <= 0.751, r["offsetCmd"])
# 7. 窗不足 6s → 拒绝
la = LateralAvoidance()
r = la.update([tgt(45.0, 0.3, cls=1, hEst=1.2)], 40.0, NOW, line_vis="dashed", line_map="dashed",
              line_conf=0.95, gap_s=6.0)
ok("6s 窗不足 → 退制动", r["level"] == 0, (r["level"], r["reason"]))
# 8. 双源不一致 → 拒绝
la = LateralAvoidance()
r = la.update([tgt(45.0, 0.3, cls=1, hEst=1.2)], 40.0, NOW, line_vis="dashed", line_map="solid",
              line_conf=0.95, gap_s=12.0)
ok("线型双源不一致 → 退制动", r["level"] == 0, r["reason"])
# 9. AEB 激活 → offset 命令首 tick 归零
la = LateralAvoidance()
la.update([tgt(66.0, 0.9)], 40.0, NOW)
r = la.update([tgt(60.0, 0.9)], 40.0, NOW + 0.1, aeb_active=True)
ok("AEB → offset 首 tick 归零", r["offsetCmd"] == 0.0 and r["reason"] == "aeb_offset_zero", r)
# 10. degraded → 抑制
la = LateralAvoidance()
la.update([tgt(66.0, 0.9)], 40.0, NOW)
r = la.update([tgt(66.0, 0.9)], 40.0, NOW + 0.1, degraded=True)
ok("degraded → 抑制横向", r["reason"] == "degraded_suppressed", r["reason"])
# 11. 低矮类 → 一律不横向
la = LateralAvoidance()
r = la.update([tgt(20.0, 0.9, cls=5, hEst=0.5)], 40.0, NOW)
ok("锥桶 → brake_only", r["reason"] == "low_class_brake_only", r["reason"])
# 12. offset 限速 ≤0.3 m/s(0.1s 内从 0 起步 ≤0.03)
la = LateralAvoidance()
la.update([tgt(66.0, 0.9)], 40.0, NOW)
r = la.update([tgt(66.0, 0.9)], 40.0, NOW + 0.1)
ok("offset 0.1s ≤0.03 m", abs(r["offsetCmd"]) <= 0.031, r["offsetCmd"])
# 13. 出段→驻段推进;驻段>2s → L2 不自动回原道
la = LateralAvoidance()
la.update([tgt(66.0, 0.9)], 40.0, NOW)
r = la.update([tgt(66.0, 0.9)], 40.0, NOW + 2.5)   # T_out=2.466 → 转 HOLD
ok("T_out 后转 HOLD", r["phase"] == 2, (r["phase"], r["reason"]))
r = la.update([tgt(66.0, 0.9)], 40.0, NOW + 2.5 + 2.1)
ok("驻段>2s → L2", r["level"] == 3, (r["level"], r["reason"]))
# 14. 出段前撤目标 → 中止退 L0 制动并收敛归零
la = LateralAvoidance()
la.update([tgt(66.0, 0.9)], 40.0, NOW)
r = la.update([], 40.0, NOW + 0.1)
ok("出段前撤目标→中止制动", r["reason"] == "abort_before_out_brake", r["reason"])
r = la.update([], 40.0, NOW + 0.2)
ok("中止后收敛 offset=0", r["offsetCmd"] == 0.0, r)
# 15. 驻位中撤目标 → 回摆收敛(残余 ≤0.15 归零)
la = LateralAvoidance()
la.update([tgt(66.0, 0.9)], 40.0, NOW)
la.update([tgt(66.0, 0.9)], 40.0, NOW + 2.5)          # 进 HOLD
seen_returned, r_last = False, None
for i in range(60):
  r = la.update([], 40.0, NOW + 2.5 + 0.1 * (i + 1))
  if r["reason"] == "returned":
    seen_returned = True
  r_last = r
ok("HOLD 撤目标→出现 returned", seen_returned and r_last["offsetCmd"] == 0.0, (r_last, seen_returned))

print("\n%d PASS / %d FAIL" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
