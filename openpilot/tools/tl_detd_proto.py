#!/usr/bin/env python3
# tl_detd 原型(D4 §7.11 垫片): 相机帧 → 用户自训红绿灯头(6类) → 门控 → /tmp/tl_detd.json
# 素材: yolov8n_weights/best.pt (mAP50 .983, P .987, R .962); 引擎 tl_yolov8n_fp16.plan
# (同头,2026-11-04 建) — tl_own_best_fp16.plan 溯源重建中,建好 --plan 切换。
# 状态面: 只报观察(类/置信/几何/持续性),不做决策——决策属 D4 规划阶段。
import argparse
import json
import time

import cv2
import numpy as np

from openpilot.selfdrive.modeld.trt_runner import TrtRunner
from msgq.visionipc import VisionIpcClient, VisionStreamType

H = 640
CONF_TH = 0.50
IOU_TH = 0.45
TL_NAMES = {0: "traffic_light", 1: "green", 2: "left", 3: "red", 4: "right", 5: "yellow"}
STATE_COLOR = {"red": "red", "yellow": "yellow", "green": "green",
               "left": "green_left", "right": "green_right"}
PERIOD_S = 0.05
HB_PATH = "/tmp/tl_detd.json"
HB_EVERY = 0.5
MAX_AREA_RATIO = 0.05   # 灯=远处小目标;>5% 全帧的大块必是幻觉


def sigmoid(x):
  return 1.0 / (1.0 + np.exp(-x))


def decode_nms(out, nc=6):
  o = out.reshape(4 + nc, -1)
  boxes = o[:4, :].T
  scores = sigmoid(o[4:, :].T)
  cls_ids = scores.argmax(axis=1)
  confs = scores.max(axis=1)
  keep = np.where(confs > CONF_TH)[0]
  if len(keep) == 0:
    return []
  boxes, confs, cls_ids = boxes[keep], confs[keep], cls_ids[keep]
  x0 = boxes[:, 0] - boxes[:, 2] / 2
  y0 = boxes[:, 1] - boxes[:, 3] / 2
  x1 = boxes[:, 0] + boxes[:, 2] / 2
  y1 = boxes[:, 1] + boxes[:, 3] / 2
  order = confs.argsort()[::-1][:40]
  picked = []
  for i in order:
    sup = False
    for j in picked:
      if cls_ids[j] != cls_ids[i]:
        continue
      ix = max(0.0, min(x1[i], x1[j]) - max(x0[i], x0[j]))
      iy = max(0.0, min(y1[i], y1[j]) - max(y0[i], y0[j]))
      inter = ix * iy
      union = boxes[i, 2] * boxes[i, 3] + boxes[j, 2] * boxes[j, 3] - inter
      if union > 0 and inter / union > IOU_TH:
        sup = True
        break
    if not sup:
      picked.append(i)
  return [(float(x0[i]), float(y0[i]), float(x1[i] - x0[i]), float(y1[i] - y0[i]),
           float(confs[i]), int(cls_ids[i])) for i in picked[:16]]


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--plan", default="/data/trt_build/tl_yolov8n_fp16.plan")
  args = ap.parse_args()
  run = TrtRunner(args.plan)
  in_name = run.input_names[0]
  vic = VisionIpcClient("camerad", VisionStreamType.VISION_STREAM_ROAD, conflate=True)
  assert vic.connect(True)
  print("tl_detd proto: plan=%s" % args.plan)
  hist = {}          # 灯体签名 -> 最近命中序列(灯态持续性门)
  last_hb = 0.0
  n_pub = 0
  t0 = time.monotonic()
  while True:
    buf = vic.recv()
    if buf is None:
      time.sleep(0.002)
      continue
    fh, fw, stride = buf.height, buf.width, buf.stride
    uv_off = buf.uv_offset
    raw = bytes(buf.data)
    y = np.frombuffer(raw[:fh * stride], dtype=np.uint8).reshape(fh, stride)[:fh, :fw]
    uv = np.frombuffer(raw[uv_off: uv_off + (fh // 2) * stride],
                       dtype=np.uint8).reshape(fh // 2, stride)[:, :fw]
    nv12 = np.ascontiguousarray(np.vstack([y, uv]))
    bgr = cv2.cvtColor(nv12, cv2.COLOR_YUV2BGR_NV12)
    s = H / float(fh)
    nw_full = int(round(fw * s))
    res = cv2.resize(bgr, (nw_full, H), interpolation=cv2.INTER_LINEAR)
    ox = (nw_full - H) // 2
    canvas = np.ascontiguousarray(res[:, ox:ox + H])
    k = fh / float(H)
    x = canvas.astype(np.float32).transpose(2, 0, 1)[None] / 255.0
    out = run.run_np({in_name: x})
    dets = decode_nms(out)
    n_pub += 1
    # 灯体归并:traffic_light(0)=灯体;1-5=状态
    items = []
    for (bx, by, bw, bh, conf, cid) in dets:
      gx = (bx + ox) * k
      gby = by * k
      gw, gh = bw * k, bh * k
      if (gw * gh) / (fw * fh) > MAX_AREA_RATIO:
        continue
      sig = (int(gx / 40), int(gby / 40)) if cid in (1, 2, 3, 4, 5) else (int(gx / 80), int(gby / 80))
      h = hist.setdefault(sig, [])
      h.append(1)
      if len(h) > 20:
        h.pop(0)
      perm = sum(h) / float(len(h))
      items.append({"cls": cid, "name": TL_NAMES[cid], "conf": round(conf, 3),
                    "bbox": [round(max(0.0, gx / fw), 3), round(max(0.0, gby / fh), 3),
                             round(min(1.0, (gx + gw) / fw), 3), round(min(1.0, (gby + gh) / fh), 3)],
                    "persist": round(perm, 2)})
    for sig in list(hist.keys()):
      if n_pub % 8 == 0:
        hist[sig] = [v for v in hist[sig][-4:]]  # 缓慢衰减窗口
    items.sort(key=lambda d: -d["conf"])
    now = time.monotonic()
    if now - last_hb >= HB_EVERY:
      last_hb = now
      state = None
      conf_sum = {}
      for it in items:
        if it["cls"] in (1, 2, 3, 4, 5) and it["persist"] >= 0.6:
          nm = TL_NAMES[it["cls"]]
          if nm in STATE_COLOR:
            conf_sum[nm] = max(conf_sum.get(nm, 0), it["conf"])
      if conf_sum:
        best = max(conf_sum.items(), key=lambda kv: kv[1])
        state = STATE_COLOR[best[0]]
      try:
        with open(HB_PATH, "w") as f:
          json.dump({"t": time.time(), "hz_avg": round(n_pub / max(0.1, now - t0), 1),
                     "n": len(items), "state": state,
                     "state_conf": round(max(conf_sum.values()), 2) if conf_sum else 0.0,
                     "items": items[:8]}, f)
      except Exception:
        pass
    target = t0 + n_pub * PERIOD_S
    sl = target - time.monotonic()
    if sl > 0:
      time.sleep(sl)


if __name__ == "__main__":
  try:
    main()
  except KeyboardInterrupt:
    print("stopped")
