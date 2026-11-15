#!/usr/bin/env python3
"""P2 影子层断言套:反事实幽灵计数(G2 口径)+ 充分性 + 分档单列。
注意: G2 语义复核——COMFORT floor −3.0 本身即 >1.5 m/s²,幽灵 COMFORT 同时计
ghost 与 ghost_1p5(逐次阻断语义);充分性反事实在单目 45 帽下由 EMERGENCY 档承载。
"""
import sys

sys.path.insert(0, "/data/openpilot")
from openpilot.selfdrive.carrot.sensing.avoidance_shadow import AvoidanceShadow
from openpilot.selfdrive.carrot.sensing.avoidance_decider import D_check

PASS, FAIL = 0, []
NOW = 1794707000.0
MONO_NS = int(NOW * 1e9) - 10_000_000


def ok(name, cond, detail=""):
  global PASS
  if cond:
    PASS += 1
    print(" [PASS]", name)
  else:
    FAIL.append(name)
    print(" [FAIL]", name, detail)


class T:
  def __init__(self, tier, dM=0.0):
    self.tier, self.dM = tier, dM


def fresh():
  s = AvoidanceShadow(mono_profile=True)
  return s, lambda tgt, a, gen=True, v=8.33: s.update(tgt, v, a, True, True, NOW, MONO_NS,
                                                      genuine=gen, hb=False)

# 1. 总闸关 → 不计数不动作
s, _ = fresh()
w, f, r = s.update([T(4)], 8.33, 0.0, False, True, NOW, MONO_NS, genuine=False, hb=False)
ok("disabled→恒等不计数", (not w) and s.n_ghost == 0)

# 2. 幽灵 COMFORT: ghost=1 且 ghost_1p5=1(−3.0 即 >1.5 误减速)
s, UPD = fresh()
w, f, r = UPD([T(3)], 0.0, False)
ok("幽灵 COMFORT→ghost=1", w and s.n_ghost == 1 and abs(f - (-3.0)) < 1e-9, (w, f, r))
ok("幽灵 COMFORT→ghost_1p5=1(G2 >1.5)", s.n_ghost_1p5 == 1, s.n_ghost_1p5)

# 3. 幽灵 EMERGENCY → 单列计数
s, UPD = fresh()
w, f, r = UPD([T(4)], 0.0, False)
ok("幽灵 EMERGENCY→emerg_req 单列", w and s.n_emerg_req == 1 and s.n_ghost == 1)

# 4. 真实冲突 → 不计 ghost,进 comfort 档计数
s, UPD = fresh()
w, f, r = UPD([T(3)], 0.0, True)
ok("真实冲突→ghost=0 且 comfort=1", w and s.n_ghost == 0 and s.n_comfort == 1)

# 5. 空目标 floor 不触发 → 无事件
s, UPD = fresh()
w, f, r = UPD(None, 0.0, True)
ok("无目标→不动作", not w)

# 6. 充分性(EMERGENCY 档承载,不受单目 45 帽): 60m@60 < D=66.18 → insuff
s, UPD = fresh()
w, f, r = UPD([T(4, dM=60.0)], 0.0, True, v=60 / 3.6)
ok("60m@60 <D(66.18)→insuff", w and s.n_insuff == 1 and s.n_suff == 0, (s.n_suff, s.n_insuff))
# 7. 充分: 70m → suff
w, f, r = UPD([T(4, dM=70.0)], 0.0, True, v=60 / 3.6)
ok("70m@60 ≥D→suff", s.n_suff == 1 and s.n_insuff == 1, (s.n_suff, s.n_insuff))

# 8. D_check 锚值复核(与结构校验同式)
ok("D(60)=66.18", abs(D_check(60.0) - 66.18) < 0.02, D_check(60.0))

# 9. G2 频次: 2 km 内 1 ghost(≤1.5)→ 0.5/1000km 边界;>1.5 → 逐次阻断不过
s, UPD = fresh()
s.km = 2000.0
w, f, r = s.update([T(2)], 8.33, 0.0, True, True, NOW, MONO_NS, genuine=False, hb=False)
ok("PREPARE(−0.2<1.0)不进 ghost", not s.n_ghost)
s.n_ghost = 1  # 注入 1 个 ≤1.5 ghost 以验频次公式(1 次/2000 km = 0.5/1000km)
ok("ghost 率=0.5/1000km", abs(s.ghost_per_1000km() - 0.5) < 1e-9, s.ghost_per_1000km())
ok("无 1p5 且率 0.5(边界内)→ G2 过", s.g2_pass())

# 10. reset 清零
s, _ = fresh()
s.n_ghost, s.n_ghost_1p5, s.km = 3, 2, 5.0
s.reset()
ok("reset 清零", s.n_ghost == 0 and s.n_ghost_1p5 == 0 and s.km == 0.0)

# 11. 真值默认 True(生产不供真值不虚增)
s, UPD = fresh()
w, f, r = UPD([T(3)], 0.0)
ok("genuine 默认 True→不虚增 ghost", w and s.n_ghost == 0)

print("\n%d PASS / %d FAIL" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
