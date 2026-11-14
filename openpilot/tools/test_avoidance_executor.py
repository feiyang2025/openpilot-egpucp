#!/usr/bin/env python3
"""P1 执行器断言套:tier→纵向 floor 语义,含未接驾闸/陈旧闸/单目否决/单调 min。"""
import sys

sys.path.insert(0, "/data/openpilot")
from openpilot.selfdrive.controls.lib.longitudinal_avoidance import AvoidanceExecutor

PASS, FAIL = 0, []
NOW = 1794665000.0
MONO_NS = int(NOW * 1e9) - 10_000_000  # 10ms 前,新鲜


def ok(name, cond, detail=""):
  global PASS
  if cond:
    PASS += 1
    print(" [PASS]", name)
  else:
    FAIL.append(name)
    print(" [FAIL]", name, detail)


class T:
  def __init__(self, tier):
    self.tier = tier


ex = AvoidanceExecutor(mono_profile=True)
A = lambda t, tgt: ex.apply(t, [T(tgt)] if tgt is not None else [], 8.33, NOW,
                            MONO_NS, enabled=True, engaged=True, hb=False)

# 1. 总闸关 → 恒等
ok("disabled→恒等", ex.apply(-0.0, [T(4)], 8.33, NOW, MONO_NS, enabled=False, engaged=True, hb=False) == 0.0)
# 2. 未接驾 → 恒等(安全闸)
ok("未接驾→恒等", ex.apply(-0.0, [T(4)], 8.33, NOW, MONO_NS, enabled=True, engaged=False, hb=False) == 0.0)
# 3. 陈旧 → 恒等
ok("stale→恒等", ex.apply(-0.0, [T(4)], 8.33, NOW, MONO_NS - 400_000_000, enabled=True, engaged=True, hb=False) == 0.0)
# 4. 空目标 → 恒等
ok("无目标→恒等", A(-0.0, None) == 0.0)
# 5. ALERT_ONLY(1) → 恒等
ok("ALERT_ONLY→恒等", A(-0.0, 1) == 0.0)
# 6. PREPARE(2) → floor -0.2
ok("PREPARE→-0.2", abs(A(-0.0, 2) - (-0.2)) < 1e-9, A(-0.0, 2))
# 7. COMFORT(3) → floor -3.0
ok("COMFORT→-3.0", abs(A(-0.0, 3) - (-3.0)) < 1e-9, A(-0.0, 3))
# 8. EMERGENCY(4) → floor -6.0
ok("EMERGENCY→-6.0", abs(A(-0.0, 4) - (-6.0)) < 1e-9, A(-0.0, 4))
# 9. 单目 COMFORT @50kmh(13.9m/s)>45 帽 → 否决恒等
ok("单目>45kmh COMFORT→否决", ex.apply(-0.0, [T(3)], 50 / 3.6, NOW, MONO_NS,
                                        enabled=True, engaged=True, hb=False) == 0.0)
# 10. 单目 EMERGENCY @50kmh → 仍 -6.0(AEB 语义不受舒适帽)
ok("单目 EMERGENCY>45→仍-6", abs(ex.apply(-0.0, [T(4)], 50 / 3.6, NOW, MONO_NS,
                                          enabled=True, engaged=True, hb=False) - (-6.0)) < 1e-9)
# 11. MPC 已更深制动 → 不放松(min 保持更深值)
ok("更深制动保留(-7 保 -7)", A(-7.0, 3) == -7.0, A(-7.0, 3))
# 12. 多目标取 maxTier
ok("多目标 maxTier 驱动", abs(ex.apply(-0.0, [T(2), T(3)], 8.33, NOW, MONO_NS,
                                        enabled=True, engaged=True, hb=False) - (-3.0)) < 1e-9)

print("\n%d PASS / %d FAIL" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
