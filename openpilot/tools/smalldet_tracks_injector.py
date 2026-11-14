#!/usr/bin/env python3
# smalldetTracks 台架注入器 — §7.16 观察面 v0 证据源(smalldetd 未落地前的仿真源)。
# 14 个脚本航迹: 成人×6(含 1 个 28px 低门演示)/儿童×2/两轮×2/锥×1/Coast 演示×1/
# tentative 闪烁×2;20 Hz;Ctrl-C 退出。用法:
#   PYTHONPATH=/data/openpilot /data/openpilot/.venv/bin/python smalldet_tracks_injector.py
import math
import time

from openpilot.cereal import messaging

F_PX = 1372.0
H = {0: 1.7, 1: 1.1, 2: 1.6, 3: 1.6, 4: 0.5, 5: 0.6, 6: 0.2}
PERIOD_NS = 50_000_000


def mk(tid, cls, x, y, vx=0.0, vy=0.0, conf=True, assoc=8, heading=0.0, pstep=0.0):
  d = math.hypot(x, y)
  return dict(tid=tid, cls=cls, x=x, y=y, vx=vx, vy=vy, conf=conf, assoc=assoc,
              heading=heading, pstep=pstep, px=max(4, int(H.get(cls, 1.5) * F_PX / max(d, 1.0))))


def script(now):
  t = now % 60.0
  out = [
    mk(1001, 0, 30.0, 0.3, vx=1.2),                       # 正前成人 接近中
    mk(1002, 0, 45.2, -2.6),                              # 压线成人
    mk(1003, 0, 55.0, 2.8, vx=0.6),                        # 右远
    mk(1004, 0, 68.4, -1.2),                              # 28px 低门演示(1.7m@68.4→34px 故意取 2.06m 无效…用 1.4m 等效:直接给 px)
    mk(1005, 1, 28.0, 1.6, vy=-0.4, pstep=0.8, heading=0.7),   # 儿童 step-off 演示
    mk(1006, 1, 41.0, -1.8),
    mk(1007, 2, 22.0, -1.9, vx=2.0, vy=0.35),              # 两轮横穿
    mk(1008, 3, 63.0, 2.2),
    mk(1009, 5, 18.0, 0.9),                                # 锥
    mk(1012, 0, 36.0 + math.sin(t * 0.2) * 2.0, -3.6),     # 邻道巡航
  ]
  # 28px 低门: 1.4m 成人 @ 66.2m
  out.append(mk(1004, 0, 66.2, 1.4))
  # tentative 闪烁两枚(约 2s 周期出现 0.6s) — 验证虚框语义与"禁 1 帧闪没"靠 coast 端
  if (t % 2.0) < 0.6:
    out += [mk(1020, 0, 34.0, 3.1, conf=False, assoc=1),
            mk(1021, 6, 52.0, -3.3, conf=False, assoc=1)]
  return out


def main():
  pm = messaging.PubMaster(["smallObjectTracks"])
  i = 0
  t0 = time.monotonic()
  print("publishing smallObjectTracks @20Hz … Ctrl-C to stop")
  try:
    while True:
      now = time.monotonic()
      tracks = script(now)
      coast_demo = (int(now) % 14) >= 12          # 每 14s 里 2s 让 1003 断流 → 演示 COAST
      if coast_demo:
        tracks = [r for r in tracks if r["tid"] != 1003]
      msg = messaging.new_message("smallObjectTracks")
      st = msg.smallObjectTracks
      st.frameId = i
      st.modelLatencyMs = 12.0
      lst = st.init("tracks", len(tracks))
      for j, r in enumerate(tracks):
        lst[j].trackId = r["tid"]
        lst[j].cls = r["cls"]
        lst[j].x = r["x"]
        lst[j].y = r["y"]
        lst[j].vx = r["vx"]
        lst[j].vy = r["vy"]
        lst[j].sigmaX = 0.3
        lst[j].sigmaY = 0.2
        lst[j].score = 0.88 if r["conf"] else 0.35
        lst[j].scoreFused = 0.92 if r["conf"] else 0.4
        lst[j].ageFrames = r["assoc"]
        lst[j].confirmed = r["conf"]
        lst[j].source = 0
        lst[j].tExposureNs = time.monotonic_ns() if not coast_demo or r["tid"] != 1003 else time.monotonic_ns() - 2_500_000_000
        b = lst[j].init("bbox", 4)
        for k in range(4):
          b[k] = 0.1 * k
        lst[j].headingRad = r["heading"]
        lst[j].pStep = r["pstep"]
        lst[j].tFirstSeenNs = time.monotonic_ns() - 4_000_000_000
        lst[j].validAssocCount = r["assoc"]
        lst[j].actualPeriodNs = PERIOD_NS
        lst[j].detPxH = r["px"]
      pm.send("smallObjectTracks", msg)
      i += 1
      if i % 100 == 0:
        print(f"{i} msgs, {len(tracks)} tracks last")
      target = t0 + i * 0.05
      sleep = target - time.monotonic()
      if sleep > 0:
        time.sleep(sleep)
  except KeyboardInterrupt:
    print("stopped")


if __name__ == "__main__":
  main()
