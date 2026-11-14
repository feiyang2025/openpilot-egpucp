#!/usr/bin/env python3
# smalldetTracks 台架注入器 v2 — §7.16 观察面证据源。
# v2: bbox 从占位改为与投影几何自洽的归一化 [x0,y0,x1,y1](与目标 3D 位置一致),
#     UI 直接画消息 bbox —— 与真实检测数据同通道。
# 14 个脚本航迹: 成人×6(含 66m 低门演示)/儿童×2/两轮×2/锥×1/Coast 演示×1/tentative 闪烁×2;20Hz。
import math
import time

from openpilot.cereal import messaging

F_PX = 1372.0
PERIOD_NS = 50_000_000
H = {0: 1.7, 1: 1.1, 2: 1.6, 3: 1.4, 4: 0.5, 5: 0.75, 6: 0.3}
AR = {0: 0.45, 1: 0.45, 2: 0.6, 3: 0.95, 4: 0.9, 5: 0.55, 6: 0.9}
# 与 UI 渲染窗一致的几何常量(内容区 [30,30,2100,1020], 2160x1080 画布)
CX, F_CAM, V_HORIZON, CAM_H = 1080.0, 1129.29, 540.0, 1.2
RX, RY, RW, RH = 30.0, 30.0, 2100.0, 1020.0


def bbox_for(cls, d, y):
  v_b = V_HORIZON + F_CAM * CAM_H / d
  v_t = v_b - F_CAM * H.get(cls, 1.0) / d
  u = CX - F_CAM * y / d
  bh = max(8.0, v_b - v_t)
  bw = max(6.0, bh * AR.get(cls, 0.6))
  x0 = max(0.0, min(1.0, (u - bw / 2 - RX) / RW))
  x1 = max(0.0, min(1.0, (u + bw / 2 - RX) / RW))
  y0 = max(0.0, min(1.0, (v_t - RY) / RH))
  y1 = max(0.0, min(1.0, (v_b - RY) / RH))
  return (x0, y0, x1, y1)


def mk(tid, cls, x, y, vx=0.0, vy=0.0, conf=True, assoc=8, heading=0.0, pstep=0.0):
  d = math.hypot(x, y)
  return dict(tid=tid, cls=cls, x=x, y=y, vx=vx, vy=vy, conf=conf, assoc=assoc,
              heading=heading, pstep=pstep, px=max(4, int(H.get(cls, 1.5) * F_PX / max(d, 1.0))))


def script(now):
  t = now % 60.0
  out = [
    mk(1001, 0, 30.0, 0.3, vx=1.2),
    mk(1002, 0, 45.2, -2.6),
    mk(1003, 0, 55.0, 2.8, vx=0.6),
    mk(1005, 1, 28.0, 1.6, vy=-0.4, pstep=0.8, heading=0.7),
    mk(1006, 1, 41.0, -1.8),
    mk(1007, 2, 22.0, -1.9, vx=2.0, vy=0.35),
    mk(1008, 3, 63.0, 2.2),
    mk(1009, 5, 18.0, 0.9),
    mk(1012, 0, 36.0 + math.sin(t * 0.2) * 2.0, -3.6),
    mk(1004, 0, 66.2, 1.4),              # 30px 低门演示(1.4m、29px)
  ]
  if (t % 2.0) < 0.6:
    out += [mk(1020, 0, 34.0, 3.1, conf=False, assoc=1),
            mk(1021, 6, 52.0, -3.3, conf=False, assoc=1)]
  return out


def main():
  pm = messaging.PubMaster(["smallObjectTracks"])
  i = 0
  t0 = time.monotonic()
  print("publishing smallObjectTracks @20Hz (v2, self-consistent bbox) … Ctrl-C to stop")
  try:
    while True:
      now = time.monotonic()
      tracks = script(now)
      coast_demo = (int(now) % 14) >= 12
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
        lst[j].tExposureNs = time.monotonic_ns() - (2_500_000_000 if (coast_demo and False) else 0)
        d = math.hypot(r["x"], r["y"])
        b = lst[j].init("bbox", 4)
        x0, y0, x1, y1 = bbox_for(r["cls"], d, r["y"])
        b[0], b[1], b[2], b[3] = x0, y0, x1, y1
        lst[j].headingRad = r["heading"]
        lst[j].pStep = r["pstep"]
        lst[j].tFirstSeenNs = time.monotonic_ns() - 4_000_000_000
        lst[j].validAssocCount = r["assoc"]
        lst[j].actualPeriodNs = PERIOD_NS
        lst[j].detPxH = r["px"]
      pm.send("smallObjectTracks", msg)
      i += 1
      if i % 200 == 0:
        print(f"{i} msgs, {len(tracks)} tracks")
      target = t0 + i * 0.05
      sleep = target - time.monotonic()
      if sleep > 0:
        time.sleep(sleep)
  except KeyboardInterrupt:
    print("stopped")


if __name__ == "__main__":
  main()
