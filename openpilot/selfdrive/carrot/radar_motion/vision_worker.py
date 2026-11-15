#!/usr/bin/env python3
"""视觉推理独立进程: VIPC 取彩色帧 -> OIV7(障碍/车辆) + 信号灯 -> 写 JSON。

为什么独立进程: TRT 执行上下文与线程/CUDA 状态绑定, 放在 carrot_man 的后台线程里
实测跑约 600 次后静默卡死(线程不再出结果, 主循环只能读到旧值)。独立进程可被主
循环按"结果超时"判死并重启, 不影响 20Hz 主循环。

输出 /dev/shm/carrot_vision.json(原子替换):
  {"ts": <epoch>, "n": <帧计数>, "vru": [[cls,d,y,conf], ...],
   "veh": [[cls,d,y,conf], ...], "sig": [[cls,cx,cy,conf], ...]}
"""
import json
import os
import sys
import time

import cv2
import numpy as np

ROOT = "/data/openpilot_egpucp"
sys.path.insert(0, ROOT)
sys.path.insert(0, ROOT + "/openpilot")

from msgq.visionipc import VisionIpcClient                     # noqa: E402
from openpilot.selfdrive.carrot.radar_motion import obstacle_vision as ov  # noqa: E402
try:
  from openpilot.selfdrive.carrot.radar_motion.vision_tracker import (
    PRED_HORIZONS_S, VisionTracker,
  )
except Exception:
  VisionTracker = None
  PRED_HORIZONS_S = (0.5, 1.0, 1.5, 2.0)


MODELS = ROOT + "/openpilot/selfdrive/carrot/radar_motion/models"

# 信号灯距离估计常量(见 red_light_stop.py 头注释)。
# fx=2637 是本机 1920x1080 road 相机的实测焦距; 灯箱高 0.95m(竖三灯标准);
# 灯中心离地 5.5m(市区悬臂/立柱灯典型); 相机高取标定值 1.35m。
# fx / 相机高度改为从唯一标定数据源读取（obstacle_vision.road_calib，5s 缓存），
# 常量仅作标定值缺失时的回退。
SIG_FX = 2637.0
SIG_CY0 = 540.0
SIG_BOX_H_M = 0.95
SIG_LAMP_H_M = 5.5
SIG_CAM_H_M = 1.35


def sig_distance(bbox, frame_w, frame_h):
  """由信号灯 bbox 反推距离(m)。两法交叉, 取较小(保守); 差异过大返回 None。

  返回 None = 不可靠, 调用方不应据此刹车。
  """
  try:
    x1, y1, x2, y2 = [float(v) for v in bbox]
    box_h = max(y2 - y1, 1.0)
    from openpilot.selfdrive.carrot.radar_motion.obstacle_vision import road_calib
    fx, cam_h = road_calib()
    fx = fx * (frame_w / 1920.0)
    fy = fx
    cy0 = frame_h * (SIG_CY0 / 1080.0)
    d_box = fx * SIG_BOX_H_M / box_h
    denom = max(cy0 - y2, 1.0)
    d_geom = fy * (SIG_LAMP_H_M - cam_h) / denom
    if not (1.0 < d_box < 300.0 and 1.0 < d_geom < 300.0):
      return None
    lo, hi = min(d_box, d_geom), max(d_box, d_geom)
    if hi / max(lo, 0.1) > 1.35:   # 两法差 >35% -> 不可靠
      return None
    return lo
  except Exception:
    return None
OUT = "/dev/shm/carrot_vision.json"
# 推理频率: 固定 5Hz, 不做"空闲降频"。
# 背景: Orin 上 modeld(BMV4 TRT 30Hz) 与 OIV7 抢同一 GPU 上下文。实测(清理完
# loggerd.deleter 孤儿后) 5Hz 时 modelV2=24.8Hz、2Hz 时 26.2Hz —— 差距只有
# 1.4Hz, 而 2Hz(500ms 间隔)会整段漏掉行人那种仅 0.2-0.4s 的检出窗口, 正是
# FAST_SINGLE 单帧快速通道要覆盖的场景。安全优先: 不降频。
# (之前 modelV2 掉到 13.5Hz 的真凶是 7 个 loggerd.deleter 孤儿各吃 40% CPU)
RATE_IDLE_HZ = 5.0     # 保留结构便于日后调参, 与 ACTIVE 相同 = 固定 5Hz
RATE_ACTIVE_HZ = 5.0
ACTIVE_KEEP_S = 2.0
# TRT 引擎静默退化自愈: 连续这么久零检出就退出, 让 carrot_serv 重启进程。
# (实测退化时心跳正常、n 正常增长, 只有 detect() 恒空, 无法从内部区分)
NO_HIT_EXIT_S = 240.0
HEARTBEAT_S = 2.0      # 无论有没有结果都刷新一次 ts, 供主循环判断进程是否活着


def vipc_to_bgr(buf):
  raw = np.frombuffer(buf.data, dtype=np.uint8)
  w, h, stride = buf.width, buf.height, buf.stride
  yv = raw[:h * stride].reshape(h, stride)[:, :w]
  try:
    uvv = raw[buf.uv_offset:buf.uv_offset + (h // 2) * stride].reshape(h // 2, stride)[:, :w]
    return cv2.cvtColorTwoPlane(yv, uvv.reshape(h // 2, w // 2, 2), cv2.COLOR_YUV2BGR_NV12)
  except Exception:
    return cv2.cvtColor(yv, cv2.COLOR_GRAY2BGR)


def write_atomic(payload):
  tmp = OUT + ".tmp"
  with open(tmp, "w") as f:
    json.dump(payload, f)
  os.replace(tmp, OUT)


def main():
  # 专用车载检测模型: YOLO11m, COCO 80 类(车/人/骑行者/摩托/交通设施), 1280 输入
  det_obs = ov.VisionObstacleDetector(MODELS + "/yolo11m_1280.onnx")
  light = None
  p = MODELS + "/tl_traffic_light.onnx"
  # 诊断: CARROT_NO_LIGHT=1 时禁用信号灯模型, 用于验证双 engine 是否互相污染
  if os.path.exists(p) and os.environ.get("CARROT_NO_LIGHT") != "1":
    light = ov.VisionObstacleDetector(p)
  try:
    from openpilot.selfdrive.carrot.radar_motion.obstacle_vision import VEHICLE_NAMES
  except Exception:
    VEHICLE_NAMES = frozenset()
  VEHICLE_NAMES_LOCAL = VEHICLE_NAMES

  # 多目标跟踪 + 运动预测: 给相邻车道目标身份/速度/轨迹预测。
  # 跟踪失败不能影响原有检测输出 -> 整体 try 包裹, None 时跳过。
  tracker = VisionTracker() if VisionTracker is not None else None
  write_atomic({"ts": time.time(), "n": 0, "boot": True, "vru": [], "veh": [], "sig": []})
  client = None
  n = 0
  last_hb = 0.0
  _none = 0
  last_hit = time.time()   # 最近一次检出(vru/veh 非空)的时刻
  while True:
    try:
      if client is None:
        c = VisionIpcClient("camerad", 0, False)
        if not c.connect(False):
          if time.time() - last_hb > HEARTBEAT_S:
            write_atomic({"ts": time.time(), "n": n, "connected": False, "vru": [], "veh": [], "sig": []})
            last_hb = time.time()
          time.sleep(0.5)
          continue
        client = c
      t0 = time.monotonic()
      buf = client.recv(200)
      if buf is None:
        # camerad 重启(或回放器换源)后旧 client 会永久返回 None, 必须重连;
        # 不重连就表现为"进程活着、n 不涨、JSON 不更新"的空转。
        _none += 1
        if _none >= 10:
          client = None
          _none = 0
          time.sleep(0.2)
        continue
      _none = 0
      bgr = vipc_to_bgr(buf)
      # FORCE_DETECT_EACH_CYCLE: worker 本身已 5Hz 节流, 不能再叠加
      # obstacle_vision.DETECT_EVERY_N(=3) 的跳帧, 否则 2/3 轮写入空结果,
      # 表现为 UI 目标闪烁 + 避让断续。把计数对齐, 保证每轮都真推理。
      try:
        _den = getattr(det_obs, "_detect_every_n", None)
        if _den is None:
          from openpilot.selfdrive.carrot.radar_motion.obstacle_vision import (
            DETECT_EVERY_N as _DEN_CONST,
          )
          _den = _DEN_CONST
        det_obs._frame_count = int(_den) - 1 if int(_den) > 1 else 0
      except Exception:
        pass
      obs = det_obs.detect(bgr) or []
      # 跟踪/预测: 在车/人分流前做, 车辆类也能拿到横向速度(判断是否在切入)。
      trk_tracks, trk_warns, trk_adj = [], [], []
      in_lane_veh = []
      if tracker is not None:
        try:
          _trks = tracker.update(obs, now=time.time())
          for _t in _trks:
            trk_tracks.append({
              "id": int(_t.tid), "cls": str(_t.cls),
              "d": round(float(_t.d_rel), 2), "y": round(float(_t.y_rel), 2),
              "conf": round(float(_t.conf), 3),
              "v_close": round(float(_t.v_closing), 2),
              "v_lat": round(float(_t.v_lat), 2),
              "pred": [[round(float(h), 1)] + [round(float(v), 2) for v in _t.predict(h)]
                       for h in PRED_HORIZONS_S],
            })
          _raw_warns = tracker.intrusion_warnings()
          for _w in _raw_warns:
            trk_warns.append({
              "id": int(_w.tid), "cls": str(_w.cls),
              "d": round(float(_w.d_rel), 2), "y": round(float(_w.y_rel), 2),
              "v_lat": round(float(_w.v_lat), 2),
              "ttc": (None if _w.ttc_s is None else round(float(_w.ttc_s), 2)),
              "clr_now": round(float(_w.clearance_now), 2),
              "clr_pred": round(float(_w.clearance_pred), 2),
            })
          for _a in tracker.adjacent_tracks():
            trk_adj.append({"id": int(_a.tid), "cls": str(_a.cls),
                            "d": round(float(_a.d_rel), 2),
                            "y": round(float(_a.y_rel), 2)})
          # 本车道内"快速接近"的车辆: 车类默认不进避让链路, 导致切入车隐形。
          # 这里只捞 v_close 明显(>=3 m/s)的, 避免同向同速前车触发无谓减速。
          for _t in _trks:
            if str(_t.cls).lower() not in VEHICLE_NAMES_LOCAL:
              continue
            # 门槛 3.5m 与 avoidance.MAX_TRIGGER_DPATH_M 对齐: 目标一旦
            # 离开侵入预警窗口(当前 |y| < 3.5) 就由这里接管, 边界无缝,
            # 不会出现 2.0~3.5m 的覆盖空窗。
            if abs(float(_t.y_rel)) >= 3.5:
              continue
            # 1.5 m/s = 5.4km/h 持续接近才算危险: 同向同速前车 v_close≈0
            # 不误触; 前车停下或切入车收窄速度会明显超过。
            if not _t.fast_closing():
              continue
            if not (2.0 <= float(_t.d_rel) <= 80.0):
              continue
            in_lane_veh.append([str(_t.cls), round(float(_t.d_rel), 2),
                                round(float(_t.y_rel), 2), round(float(_t.conf), 3)])
        except Exception as _e:
          try:
            with open("/tmp/carrot_tracker_err.txt", "a") as _ef:
              _ef.write("%.1f %s\n" % (time.time(), str(_e)[:200]))
          except Exception:
            pass
      sig = (light.detect_signals(bgr) or []) if light is not None else []
      # 方案2: 存在性单独推理(5Hz 节流下多 13ms 可接受)。只报"有灯",
      # 颜色不可靠, 不写 traffic_state, 不参与刹车/转向/起步。
      lit = light.detect_light_presence(bgr) if light is not None else (False, 0.0, "", None)
      n += 1
      # 红绿灯/交通标志不是障碍物: 混进 vru 会被当静止目标触发避让
      # (实测 Traffic light y_rel=0.30 在车道内)。信号灯另由 tl 模型处理。
      _IGNORE = ("traffic light", "traffic sign", "stop sign")
      vru = [[o.cls, float(o.d_rel), float(o.y_rel), float(o.conf)]
             for o in obs if str(o.cls).lower() not in VEHICLE_NAMES
             and str(o.cls).lower() not in _IGNORE]
      veh = [[o.cls, float(o.d_rel), float(o.y_rel), float(o.conf)]
             for o in obs if str(o.cls).lower() in VEHICLE_NAMES]
      if vru or veh:
        last_hit = time.time()
      # 诊断注入(仅当 /tmp/carrot_inject_sig.txt 存在且非空):
      # 台架素材无真红绿灯, 用注入走真实链路验证红灯刹停。
      # 格式: red_light,cx,cy,conf,dist   例: red_light,960,400,0.9,40.0
      try:
        if os.path.exists("/tmp/carrot_inject_sig.txt"):
          _sj = open("/tmp/carrot_inject_sig.txt").read().strip()
          if _sj:
            _q = [x.strip() for x in _sj.split(",")]
            _dd = float(_q[4]) if len(_q) > 4 and _q[4] else None
            sig = [[_q[0], float(_q[1]), float(_q[2]), float(_q[3]), _dd]]
            # 注入也要能验证存在性通道
            lit = (True, float(_q[3]), _q[0], None)
      except Exception:
        pass
      # 诊断注入(仅当 /tmp/carrot_inject_vru.txt 存在且非空): 台架无真雷达,
      # 车道内近距障碍无法自然出现, 用注入让真实 carrot_serv 链路可验证。
      try:
        if os.path.exists("/tmp/carrot_inject_vru.txt"):
          _inj = open("/tmp/carrot_inject_vru.txt").read().strip()
          if _inj:
            # 多行注入: 每行 person,d,y,conf; 支持一次注入多个目标(验证/调试)
            vru = []
            for _ln in _inj.splitlines():
              _ln = _ln.strip()
              if not _ln or _ln.startswith("#"):
                continue
              _p = [x.strip() for x in _ln.split(",")]
              if len(_p) >= 4:
                try:
                  vru.append([_p[0], float(_p[1]), float(_p[2]), float(_p[3])])
                except ValueError:
                  continue
      except Exception:
        pass
      write_atomic({
        "ts": time.time(), "n": n, "connected": True, "frame": [int(bgr.shape[1]), int(bgr.shape[0])],
        "vru": vru, "veh": veh,
        # sig 第 5 位 = 距离估计(None 表示不可靠)。向后兼容: 旧消费端只读 0..3。
        # 方案2: 存在性(供 UI/诊断), 与 sig 的颜色分开
        "light_present": bool(lit[0]), "light_conf": float(lit[1]), "light_cls": str(lit[2]),
        # 跟踪与运动预测(相邻车道侵入预警); 无跟踪器时为空列表
        "tracks": trk_tracks, "lane_intrusion": trk_warns, "adjacent": trk_adj,
        # 本车道内快速接近的车辆(格式同 vru), 供避让链路消费
        "in_lane_veh": in_lane_veh,
        "trk": (tracker.summary() if tracker is not None else {}),
        "sig": [[s[0], float(s[1]), float(s[2]), float(s[3]),
                 (float(s[4])
                  if len(s) > 4 and isinstance(s[4], (int, float)) and not isinstance(s[4], bool)
                  else (sig_distance(s[4], bgr.shape[1], bgr.shape[0])
                        if len(s) > 4 else None))]
                for s in sig],
      })
      # 退化自愈: 已在稳定运行(n>200)却长时间零检出 -> 主动退出等重启
      if n > 200 and time.time() - last_hit > NO_HIT_EXIT_S:
        try:
          write_atomic({"ts": time.time(), "n": n, "connected": True, "exit": "no-hit-timeout",
                        "vru": [], "veh": [], "sig": []})
        except Exception:
          pass
        sys.exit(0)
      last_hb = time.time()
      dt = time.monotonic() - t0
      _rate = RATE_ACTIVE_HZ if (time.time() - last_hit) < ACTIVE_KEEP_S else RATE_IDLE_HZ
      if dt < 1.0 / _rate:
        time.sleep(1.0 / _rate - dt)
    except Exception as e:
      try:
        write_atomic({"ts": time.time(), "n": n, "error": str(e)[:200], "vru": [], "veh": [], "sig": []})
      except Exception:
        pass
      client = None
      time.sleep(0.5)


if __name__ == "__main__":
  main()
