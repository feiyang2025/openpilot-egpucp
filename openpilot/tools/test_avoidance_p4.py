#!/usr/bin/env python3
"""P4 信号灯决策断言套: 红1帧/绿3帧+0.3s+绑定/黄 dilemma/灯灭 MRM/停车带/计数单列。"""
import sys

sys.path.insert(0, "/data/openpilot")
from openpilot.selfdrive.carrot.sensing.signal_decider import SignalStopDecider

PASS, FAIL = 0, []
T0 = 1000.0


def ok(name, cond, detail=""):
  global PASS
  if cond:
    PASS += 1
    print(" [PASS]", name)
  else:
    FAIL.append(name)
    print(" [FAIL]", name, detail)


# 1. 参数默认 OFF → 恒等
d = SignalStopDecider(enabled=False)
r = d.update("red", 0.99, 50.0, 10.0, True, T0)
ok("默认 OFF→恒等", r["reason"] == "disabled" and r["state"] == "PROCEED")
# 2. 红 1 帧确认即刹
d = SignalStopDecider(enabled=True)
r = d.update("red", 0.99, 50.0, 10.0, True, T0)
ok("红 1 帧→STOPPING red_1f", r["state"] == "STOPPING" and r["reason"] == "red_1f", r)
ok("红 1 帧即出虚拟停车 floor", r["aFloor"] is not None and r["aFloor"] < 0)
# 3. floor 口径: v=10, d=50 → aim=48 → a=−100/96=−1.042,不越 −6
ok("a_floor=−1.042", abs(r["aFloor"] - (-10 * 10 / (2 * 48.0))) < 1e-9, r["aFloor"])
# 4. 近距大 v → floor 钳在 −6
r = d.update("red", 0.99, 8.0, 30.0, True, T0 + 0.1)
ok("floor 钳 −6(AEB 语义)", r["aFloor"] == -6.0, r["aFloor"])
# 5. 绿 1/2 帧不放行(保持既定 STOPPING)
r = d.update("green", 0.99, 5.0, 0.0, True, T0 + 0.2)
ok("绿 1 帧→不放行", r["state"] == "STOPPING" and r["reason"] == "green_counting", r)
r = d.update("green", 0.99, 5.0, 0.0, True, T0 + 0.3)
ok("绿 2 帧→仍不放行", r["reason"] == "green_counting", r)
# 6. 绿 3 帧 + ≥0.3s + 绑定 → GO
r = d.update("green", 0.99, 5.0, 0.0, True, T0 + 0.55)
ok("绿 3 帧+0.35s+绑定→GO", r["state"] == "PROCEED" and r["reason"] == "green_3f_hold_go", r)
# 7. 绿灯保持 <0.3s 不放行(3 帧但间隔过短)
d2 = SignalStopDecider(enabled=True)
for i, t in enumerate((0.0, 0.05, 0.10)):
  r = d2.update("green", 0.99, 50.0, 5.0, True, T0 + t)
ok("3 帧仅 0.10s→不放行(保持态不 GO)",
   r["reason"] == "green_counting" and r["counters"]["green_gos"] == 0, r)
# 8. 绑定失败 + 绿 → unknown 停车 MRM,单列计数
r = d2.update("green", 0.99, 50.0, 5.0, False, T0 + 0.2)
ok("绿+绑定失败→unknown MRM 停车", r["state"] == "STOPPING" and r["reason"] == "bind_fail_unknown_mrm", r)
ok("unknown_stops 单列=1", r["counters"]["unknown_stops"] == 1, r["counters"])
# 9. 黄灯 dilemma: v=8, d=30 → 需 a=64/59.4=1.08 ≤3 → 停
d3 = SignalStopDecider(enabled=True)
r = d3.update("yellow", 0.99, 30.0, 8.0, True, T0)
ok("黄灯可停(|a|=1.08≤3)→停", r["state"] == "STOPPING" and r["reason"] == "yellow_dilemma_stop", r)
# 10. 黄灯不可停: v=20, d=15 → 需 a=400/29.4=13.6 >3 → 通过
d4 = SignalStopDecider(enabled=True)
r = d4.update("yellow", 0.99, 15.0, 20.0, True, T0)
ok("黄灯不可停(|a|=13.6>3)→通过", r["state"] == "PROCEED" and r["reason"] == "yellow_dilemma_clear", r)
# 11. 灯灭 → MRM 停车(不自主通行)
r = d4.update(None, 0.0, 40.0, 10.0, True, T0 + 0.1)
ok("灯灭→light_off_mrm", r["state"] == "STOPPING" and r["reason"] == "light_off_mrm", r)
ok("mrm 计数", r["counters"]["mrm"] == 1, r["counters"])
# 12. 无灯路口(obs 从未出现+无线)→ 不在本单元域,恒等
d5 = SignalStopDecider(enabled=True)
r = d5.update(None, 0.0, None, 10.0, True, T0)
ok("无灯路口→no_signal 不动作", r["reason"] == "no_signal" and r["state"] == "PROCEED", r)
# 13. 停车带收敛: v≈0 且净距 ≤2.0 → STOPPED
d6 = SignalStopDecider(enabled=True)
r = d6.update("red", 0.99, 1.5, 0.05, True, T0)
ok("带内停稳→STOPPED", r["state"] == "STOPPED" and r["reason"] == "stopped_in_band", r)
# 14. 未知灯色(占位)→ unknown MRM
d7 = SignalStopDecider(enabled=True)
r = d7.update("flash_red", 0.2, 50.0, 10.0, True, T0)
ok("未知灯色→unknown_mrm", r["reason"] == "unknown_mrm" and r["counters"]["unknown_stops"] == 1, r)
# 15. unknown_stops 不混入红/绿计数
ok("红绿计数为 0(unknown 单列)", r["counters"]["red_stops"] == 0 and r["counters"]["green_gos"] == 0,
   r["counters"])
# 16. 优先级语义占位: aFloor 由调用链 min-only 并入(AEB>信号>小目标),本核只给 floor
ok("floor 均为 min-only 标量", all(r.get("aFloor") is None or r["aFloor"] <= 0 for r in [r]))

print("\n%d PASS / %d FAIL" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
