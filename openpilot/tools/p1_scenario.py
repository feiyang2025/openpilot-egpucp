#!/usr/bin/env python3
"""P1 台架闭环剧情源:虚拟成人静止站车道正中(d0=60m,y=0)。
d(t) 由真实 carState.vEgo 积分驱动 —— 刹得住,d 就慢下来,价格降档,
指令缓和:整链自调,真物理一致性。20Hz,同一消息契约,置信 0.92 已确认。
"""
import math
import time

import openpilot.cereal.messaging as messaging

F_PX = 1372.0
PERIOD_NS = 50_000_000
TID = 2001
D0 = 60.0
H_M = 1.70          # 成人,不触 1.40/1.09 回落包络


def main():
  pm = messaging.PubMaster(["smallObjectTracks"])
  sm = messaging.SubMaster(["carState"], poll="carState")
  d = D0
  t0 = time.monotonic()
  i = 0
  last_v = 0.0
  print("p1_scenario: virtual adult @60m dead-center, d driven by true vEgo")
  while True:
    sm.update(0)
    if sm.updated["carState"]:
      last_v = float(sm["carState"].vEgo)
    d = max(0.15, d - last_v * 0.05)
    now = time.monotonic()
    msg = messaging.new_message("smallObjectTracks")
    st = msg.smallObjectTracks
    st.frameId = i
    lst = st.init("tracks", 1)
    lst[0].trackId = TID
    lst[0].cls = 0
    lst[0].x = d
    lst[0].y = 0.0
    lst[0].vx = 0.0
    lst[0].vy = 0.0
    lst[0].sigmaX = 0.3
    lst[0].sigmaY = 0.2
    lst[0].score = 0.88
    lst[0].scoreFused = 0.92
    lst[0].ageFrames = 9
    lst[0].confirmed = True
    lst[0].source = 0
    lst[0].tExposureNs = time.monotonic_ns()
    b = lst[0].init("bbox", 4)
    cx = min(1.0, 0.5)
    bw = max(0.006, 0.45 * H_M * F_PX / d / 2100.0)
    v_b = min(1.0, (540.0 + 1129.29 * 1.2 / d - 30.0) / 1020.0)
    v_t = max(0.0, v_b - H_M * F_PX / d / 1020.0)
    b[0], b[1], b[2], b[3] = 0.5 - bw / 2, v_t, 0.5 + bw / 2, v_b
    lst[0].headingRad = 0.0
    lst[0].pStep = 0.0
    lst[0].tFirstSeenNs = time.monotonic_ns() - 4_000_000_000
    lst[0].validAssocCount = 9
    lst[0].actualPeriodNs = PERIOD_NS
    lst[0].detPxH = max(4, int(H_M * F_PX / max(d, 1.0)))
    pm.send("smallObjectTracks", msg)
    i += 1
    if i % 40 == 0:
      print(f"i={i} d={d:.1f} vEgo={last_v * 3.6:.1f}kmh px={lst[0].detPxH}")
    target = t0 + i * 0.05
    sl = target - time.monotonic()
    if sl > 0:
      time.sleep(sl)


if __name__ == "__main__":
  main()
