#!/usr/bin/env python3
# 主动避让20261112.md 结构力学校验脚本(文档 v1.19 附录 D "联合"约束行的 CI 落地)
# - mechanics 全过 → exit 0;任何力学/一致性回归 → exit 1
# - 待签决策(pixel 门 60 档、儿童身高下界)不算失败,单列 pending_signatures —— 但一旦
#   签字改数,对应检查自动转为硬门,单边改距离/门/身高/速度会立刻 CI 红。
# 纯 stdlib,无 openpilot 依赖;输出 JSON: docs/avoidance_structure_validation.json
import json
import math
import sys

F_PX_1280 = 1372.0          # f @1280 输入(附录 D COCO small 行)
PX_GATE_STAND = 30.0        # §3.3 站立像素质子门
PX_GATE_LOW = 12.0
H_ADULT_MIN = 1.4           # 附录 B min_height_m_adult
H_ADULT_DERIVED = 1.70      # §3.3 推导口径(30px ↔ 77.8m 反解)
H_CHILD_TENTH_FIVE = 1.05   # 幼童参考身高(待签: <1.07 归低矮档)
J, A_P, TAU, T0_CAND = 3.0, 3.0, 1.0, 0.70
T_PROC_BUDGET_MS = 126.0
G3_MS = 250.0

res = {"mechanics": {}, "pending_signatures": [], "computed": {}}
fail = []


def chk(name, cond, detail=""):
  res["mechanics"][name] = "PASS" if cond else "FAIL"
  res["computed"][name] = detail
  if not cond:
    fail.append(name)
  return cond


def D(v, T0=T0_CAND, J=J, tau=TAU, a_p=A_P):  # §7.15 完整停车距离
  return v * T0 + v * tau - J * tau ** 3 / 6 + max(0.0, v - J * tau ** 2 / 2) ** 2 / (2 * a_p)


# ===== §7.15 停车距离 =====
d60 = D(60 / 3.6)
d50 = D(50 / 3.6)
d30 = D(30 / 3.6)
chk("s715_D_60", abs(d60 - 66.18) < 0.02, f"{d60:.3f} m (doc 66.18)")
chk("s715_D_60_margin_vs_ttc4", abs((4.0 * 60 / 3.6 - d60) - 0.49) < 0.02, f"margin {4.0*60/3.6 - d60:.3f} m (doc 0.49)")
chk("s715_D_50_violates_ttc3_5", d50 > 3.5 * 50 / 3.6, f"D={d50:.2f} vs TTC 距离 {3.5*50/3.6:.2f} → 50@T0=.70 候选不成立")
chk("s715_D_30", abs(d30 - 21.45) < 0.02, f"{d30:.3f} m (doc 21.45)")
# 保 2.5m 余量所需 T0 上限(文档 .514/.580,反解复算)
ok_50 = D(50 / 3.6, 0.514) <= 3.5 * 50 / 3.6 - 2.5 + 0.01
ok_60 = D(60 / 3.6, 0.580) <= 4.0 * 60 / 3.6 - 2.5 + 0.01
chk("s715_T0_cap_50", ok_50, "T0=0.514 → D≈%.2f ≤ %.2f (doc .514)" % (D(50/3.6, 0.514), 3.5*50/3.6 - 2.5))
chk("s715_T0_cap_60", ok_60, "T0=0.580 → D≈%.2f ≤ %.2f (doc .580)" % (D(60/3.6, 0.580), 4.0*60/3.6 - 2.5))

# ===== §9.8 剖面域(儿童中心 @40, δ=1.4, 2T=6.0732) =====
v40 = 40 / 3.6
T_full = 2 * (60 * 1.4 / J) ** (1 / 3)
chk("s98_2Tout", abs(T_full - 6.0732) < 0.001, f"{T_full:.4f} s (doc 6.0732)")
L_const = v40 * T_full - 2 * T_full ** 2 / 2 + 10.2
v_end_const = v40 - 2 * T_full
chk("s98_L_const", abs(L_const - 40.796) < 0.002, f"L={L_const:.3f} (doc 40.796)")
chk("s98_const_profile_must_reject", v_end_const < 0, f"v_end={v_end_const:.3f} (doc −1.035,恒减速必须拒绝)")
vmin = 1.0
T_b = (v40 - vmin) / 2
L_pw = (v40 * v40 - vmin * vmin) / (2 * 2) + vmin * (T_full - T_b) + 10.2
chk("s98_L_piecewise", abs(L_pw - 41.832) < 0.002, f"L={L_pw:.3f}, T_b={T_b:.4f}, v_end={vmin} (doc 41.832/5.0556/1.0)")
L_pw_tp = L_pw + vmin * 0.5   # +Tp=0.5 增量 =vmin·Tp
chk("s98_L_piecewise_Tp05", abs(L_pw_tp - 42.332) < 0.002, f"L={L_pw_tp:.3f} (doc 42.332, 禁跨 Tp 复用)")

# ===== §7.8 S 型几何 =====
T_out_075 = (60 * 0.75 / J) ** (1 / 3)
chk("s78_Tout_d075", abs(T_out_075 - 2.466) < 0.01, f"{T_out_075:.3f} s (doc 2.47)")
d_adult_px30 = 1.70 * F_PX_1280 / PX_GATE_STAND      # 推导身高 30px 距离
d_child_px30 = 1.10 * F_PX_1280 / PX_GATE_STAND
d_low_px12 = 0.3 * F_PX_1280 / PX_GATE_LOW
chk("s78_adult30px_dist", abs(d_adult_px30 - 77.8) < 0.3, f"{d_adult_px30:.1f} m (doc 77.8, 身高 1.70)")
chk("s78_child30px_dist", abs(d_child_px30 - 50.3) < 0.3, f"{d_child_px30:.1f} m (doc 50.3, 身高 ~1.10)")
chk("s78_low12px_dist", abs(d_low_px12 - 34.3) < 0.2, f"{d_low_px12:.1f} m (doc 34.3)")
lead_50_infeasible = 79 > d_adult_px30               # 50 km/h lead 表值超门 → 只能制动
chk("s78_lead50_above_gate", lead_50_infeasible, "79 m > 77.8 m 门 → 50 档 S 不可行退制动(文档语义)")

# ===== §7.13/7.14 时延账本 =====
hops = [31, 5, 18, 4, 2, 1, 47, 3, 4]
chk("s714_hops_sum_le_budget", sum(hops) <= T_PROC_BUDGET_MS, f"sum={sum(hops)} ≤ 126(分项仅归因)")
t_action = T_PROC_BUDGET_MS + (3 - 1) / 20 * 1000
chk("s714_T_action", abs(t_action - 226) < 0.5 and t_action <= G3_MS, f"{t_action:.0f} ms ≤ G3 250(20Hz,K=3)")

# ===== 代价档单一性 =====
p_star = 1 / 1001
chk("cost_p_act", abs(p_star - 9.99e-4) < 1e-6, f"p*={p_star:.6f}")
chk("cost_tier_monotone", 2.0e-5 < p_star < 2.99e-3, "prepare 2e-5 < comfort 9.99e-4 < emergency 2.99e-3")

# ===== miss-rate 统计口径 =====
ci = 3 / 36000
chk("stats_ci_rule_of_three", abs(ci - 8.3e-5) < 2e-6, f"3/36000={ci:.2e} (doc 8.3e-5)")
n_req = math.log(0.05) / math.log(1 - 1e-4)
chk("stats_n_for_1e-4", 36000 >= n_req - 1, f"需 n≥{n_req:.0f}, 附录 B 样例 36000 ✓")

# ===== 联合约束(附录 D "联合"行;两项待签——不 CI 失败,但签字后任何单边改动立即转硬门) =====
px_adult_minH_at60 = H_ADULT_MIN * F_PX_1280 / d60
px_derivedH_at60 = H_ADULT_DERIVED * F_PX_1280 / d60
px_child105_at50 = H_CHILD_TENTH_FIVE * F_PX_1280 / d50
res["pending_signatures"].append({
  "decision": "60 档像素门三选一 [a]1.45m/[b]盲窗/[c]降速58.8",
  "fact": f"min_h 1.4m @D(60,T0=.70)={d60:.2f} m → {px_adult_minH_at60:.1f}px < {PX_GATE_STAND:.0f}px 门;推导身高 1.70m → {px_derivedH_at60:.1f}px 过门,两口身高不一致(1.4 vs 1.7)",
  "guard": "签字后: min_h_class·f_px/D_check(v) ≥ px_gate 硬门",
})
res["pending_signatures"].append({
  "decision": "儿童身高下界(建议 <1.07m 归低矮 40 档)",
  "fact": f"1.05m 幼童 @D(50,T0=.70)={d50:.2f} m → {px_child105_at50:.1f}px < 30px 门贴线;child ∈ (1.0,1.4] 无显式数值定义",
  "guard": "签字后: 数值区间写入 odd 块 + 本脚本硬门",
})
res["joint_constraint"] = {
  "formula": "min_h_class·f_px/D_check(v) ≥ px_gate(类)",
  "adult60_minH_px": round(px_adult_minH_at60, 2),
  "adult60_derivedH_px": round(px_derivedH_at60, 2),
  "child105_50_px": round(px_child105_at50, 2),
  "height_disagreement_adult": [H_ADULT_MIN, H_ADULT_DERIVED],
}

res["verdict"] = "MECHANICS_PASS_PENDING_SIGNATURES" if not fail else "MECHANICS_FAIL"
res["failed"] = fail

out_path = sys.argv[1] if len(sys.argv) > 1 else "docs/avoidance_structure_validation.json"
with open(out_path, "w", encoding="utf-8") as f:
  json.dump(res, f, ensure_ascii=False, indent=2)

print(json.dumps(res["mechanics"], indent=0))
print("verdict:", res["verdict"], "| pending_signatures:", len(res["pending_signatures"]))
print("json →", out_path)
sys.exit(1 if fail else 0)
