#!/usr/bin/env python3
"""Offline camera-calibration pipeline (spec §10.5).

Replays a route's rlog segments through the same observers the car runs live:
  - cameraSyncState statistics (CameraSyncMonitor): per-route phase health;
    segments failing the sync check are marked unusable (§16.6);
  - the vanishing-point + robust-LSQ mounting-pitch estimator (StreamCalib),
    fed video frames from fcamera.hevc / ecamera.hevc when present;
  - the L3 lane-geometry focal fitter (LaneGeomFitter) on road frames;
  - §6.5 merge limits identical to calibrationd, output = CameraCalibSet JSON
    (the only effective runtime store stays Params["CalibrationParams"]).

Usage:
  python tools/camcalib_offline.py <route> [--seg 0-5] [--video] [--json out.json]
"""
import argparse
import json
from pathlib import Path

import numpy as np

from openpilot.common.transformations.camera_calib import (
  Cam, CalibSource, from_live_calibration, to_json)
from openpilot.selfdrive.locationd.camcalibd import (
  CameraSyncMonitor, LaneGeomFitter, StreamCalib, compute_vanishing_point)

CANDIDATE_FOCAL_LIMIT = 0.08
CANDIDATE_PITCH_LIMIT = 0.15


def from_json_file(d, device_type="pc", sensor="imx390"):
  """to_json 逆投影: 工厂默认集 + 全字段覆写(to_json 不含 identity,身份由 --device/--sensor 兜底)。"""
  import numpy as _np
  from openpilot.cereal import messaging as _messaging
  base = from_live_calibration(_messaging.new_message("liveCalibration").liveCalibration,
                               device_type=device_type, sensor=sensor)
  base.seq = int(d.get("seq", base.seq))
  base.schema_version = int(d.get("schemaVersion", base.schema_version))
  base.height = float(d.get("height", base.height))
  if "bodyFromCalib" in d:
    base.body_from_calib = _np.asarray(d["bodyFromCalib"], dtype=float)
  for c in d.get("cams", []):
    cam = Cam(int(c["id"]))
    if cam not in base.cams:
      continue
    t = base.cams[cam]
    t.width, t.height = int(c.get("width", t.width)), int(c.get("height", t.height))
    t.fx, t.fy = float(c.get("fx", t.fx)), float(c.get("fy", t.fy))
    t.cx, t.cy = float(c.get("cx", t.cx)), float(c.get("cy", t.cy))
    if "dist" in c:
      t.dist = _np.asarray(c["dist"], dtype=float)
    if c.get("rpy") is not None:
      t.rpy = _np.asarray(c["rpy"], dtype=float)
    if c.get("mountHeight") is not None:
      t.mount_height = float(c["mountHeight"])
    t.extrinsic_valid = bool(c.get("extrinsicValid", t.extrinsic_valid))
    t.valid = bool(c.get("valid", t.valid))
    if "source" in c:
      try:
        t.source = CalibSource[c["source"].upper()]
      except KeyError:
        pass
    t.blocks = int(c.get("blocks", t.blocks))
    t.rms_reproj = float(c.get("rmsReproj", t.rms_reproj))
    if "spread" in c:
      t.spread = _np.asarray(c["spread"], dtype=float)
  return base


def merge_candidate(calib_set, road_f=None, road_pitch=None,
                    wide_f=None, wide_pitch=None):
  """§6.5 merge — same limits as calibrationd.apply_calib_candidate."""
  changed = False
  for cam, f, pitch in ((Cam.ROAD, road_f, road_pitch), (Cam.WIDE, wide_f, wide_pitch)):
    c = calib_set.cams.get(cam)
    if c is None or (f is None and pitch is None):
      continue
    if f is not None:
      if abs(f / c.fx - 1.0) > CANDIDATE_FOCAL_LIMIT:
        print(f"  [gate] {cam.name} focal {f:.1f} exceeds ±8%, dropped")
        continue
      c.fx = c.fy = float(f)
    if pitch is not None and abs(pitch) <= CANDIDATE_PITCH_LIMIT:
      c.rpy = np.array([0.0, float(pitch), 0.0])
    c.source = CalibSource.AUTO
    changed = True
  if changed:
    calib_set.seq += 1
  return changed


def segment_paths(route, seg_range):
  # accept a local realdata directory (e.g. .../realdata/0000029d--dongle--5)
  # or a canonical dongle|route name
  p = Path(route)
  is_seg_dir = p.is_dir() and any(q.name.startswith("rlog") or q.name.startswith("qlog") for q in p.iterdir())
  if is_seg_dir or p.is_file():
    if p.is_file():
      yield 0, str(p), p.parent
    else:
      yield 0, str(p / "rlog.zst"), p
    return
  from openpilot.tools.lib.route import Route
  segs = sorted(Route(route).log_paths(), key=lambda x: str(x))
  if segs and segs[0] is None:
    raise SystemExit("route logs are not downloaded")
  lo, hi = 0, len(segs) - 1
  if seg_range:
    a, b = seg_range.split("-")
    lo, hi = int(a), int(b)
  for i in range(lo, min(hi, len(segs) - 1) + 1):
    seg_dir = Path(segs[i]).parent if segs[i] else None
    yield i, segs[i], seg_dir


def open_frames(seg_dir, name):
  """FrameReader over <seg_dir>/<name>; None when the video is absent."""
  if seg_dir is None:
    return None
  video = seg_dir / name
  if not video.exists():
    return None
  from openpilot.tools.lib.framereader import FrameReader
  return FrameReader(str(video))


def run_segment(idx, log_path, seg_dir, args, state):
  from openpilot.tools.lib.logreader import LogReader
  road_frames = open_frames(seg_dir, "fcamera.hevc") if args.video else None
  wide_frames = open_frames(seg_dir, "ecamera.hevc") if args.video else None
  lr = LogReader(log_path) if log_path else iter([])
  frame_idx = 0
  for msg in lr:
    which = msg.which()
    if which == "liveCalibration":
      try:
        s = from_live_calibration(msg, device_type="pc", sensor="imx390")
        if state["calib_set"] is None:
          state["calib_set"] = s
          state["lane_fitter"] = LaneGeomFitter(s)
        else:
          state["lane_fitter"].update_set(s)
        state["pitch"] = float(s.body_from_calib[1])
        for st in state["streams"].values():
          st.set_cy_from_set(s)
      except Exception as e:
        print(f"  seg{idx}: bad liveCalibration: {e}")

    elif which == "roadCameraState" and state["calib_set"] is not None:
      ts = msg.roadCameraState.timestampSof
      if ts > 0:
        state["sync"].on_stream(Cam.ROAD, ts)
        if state.get("seg_probe") is not None:
          state["seg_probe"].on_stream(Cam.ROAD, ts)
      if road_frames is not None and frame_idx < road_frames.frame_count and state["sync"].synced:
        gray = np.asarray(road_frames.get(frame_idx, pix_fmt="rgb24"))[:, :, 0]
        st = state["streams"][Cam.ROAD]
        v0, n = compute_vanishing_point(gray)
        st.last_lines = n
        if v0 is not None and state["pitch"] is not None:
          st.add_sample(v0, state["pitch"], st.cy or 540.0)
        if state["lane_fitter"] is not None:
          if state["model_v2"] is not None:
            state["lane_fitter"].add_sample(state["model_v2"], gray)
        frame_idx += 1

    elif which == "wideRoadCameraState" and state["calib_set"] is not None:
      ts = msg.wideRoadCameraState.timestampSof
      if ts > 0:
        state["sync"].on_stream(Cam.WIDE, ts)
        if state.get("seg_probe") is not None:
          state["seg_probe"].on_stream(Cam.WIDE, ts)

    elif which == "modelV2":
      state["model_v2"] = msg.modelV2


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("route", nargs="?", default=None,
                      help="realdata 段目录 / dongle|route;不给则需 --import(纯转换)")
  parser.add_argument("--seg", default=None, help="segment range, e.g. 0-5")
  parser.add_argument("--json", default=None, help="output CameraCalibSet JSON")
  parser.add_argument("--video", action="store_true", help="run image-side estimators")
  parser.add_argument("--import", dest="import_path", default=None,
                      help="source CameraCalibSet JSON (to_json 投影逆回;作为回放初值或纯转换)")
  parser.add_argument("--device", default="pc", help="identity 兜底(默认 pc)")
  parser.add_argument("--sensor", default="imx390", help="identity 兜底(默认 imx390)")
  parser.add_argument("--sync-report", dest="sync_report", default=None,
                      help="输出 §16.6 逐段+路由级同步健康 JSON")
  args = parser.parse_args()
  if args.route is None and args.import_path is None:
    raise SystemExit("需要 <route> 或 --import(至少一项)")

  imported = None
  if args.import_path:
    imported = from_json_file(json.loads(Path(args.import_path).read_text()),
                             device_type=args.device, sensor=args.sensor)
    print(f"imported: seq={imported.seq} cams={sorted(c.name for c in imported.cams)}")

  state = {
    "calib_set": imported, "sync": CameraSyncMonitor(), "pitch": None,
    "model_v2": None, "lane_fitter": None, "seg_probe": None, "seg_stats": [],
    "streams": {
      Cam.ROAD: StreamCalib(Cam.ROAD, None, "road", "roadCameraState", 2637.0),
      Cam.WIDE: StreamCalib(Cam.WIDE, None, "wide", "wideRoadCameraState", 564.6),
    },
  }

  for idx, log_path, seg_dir in segment_paths(args.route, args.seg) if args.route else []:
    print(f"=== segment {idx} ===")
    state["seg_probe"] = CameraSyncMonitor()
    run_segment(idx, log_path, seg_dir, args, state)
    ps = state["seg_probe"].stats()
    if ps:
      seg_ok = ps["synced"] and ps["p99"] <= 2_000_000
      print(f"  seg{idx} sync: deltaRef {ps['deltaRef']/1e6:.2f} ms | P99.9 {ps['p99']/1e3:.0f} us "
            f"| {'可用于标定' if seg_ok else 'UNUSABLE — 不可用于标定(§16.6 逐段标记)'}")
      state["seg_stats"].append({"seg": idx, "usable": seg_ok,
                                 "deltaRefMs": round(ps["deltaRef"] / 1e6, 3),
                                 "p50Us": round(ps["p50"] / 1e3, 1),
                                 "p999Us": round(ps["p99"] / 1e3, 1),
                                 "skewPpm": round(ps["skewPpm"], 1),
                                 "synced": ps["synced"]})
    state["seg_probe"] = None

  print("\n==== sync health (§16.6 T0) ====")
  stats = state["sync"].stats()
  if stats:
    print(f"deltaRef {stats['deltaRef']/1e6:.2f} ms | P50 {stats['p50']/1e3:.0f} us | "
          f"P99.9 {stats['p99']/1e3:.0f} us | jitter {stats['jitter']/1e3:.0f} us | "
          f"skew {stats['skewPpm']:.1f} ppm | synced={stats['synced']} | "
          f"missing={stats['missing']} epochs={stats['epoch']}")
    ok = stats["synced"] and stats["p99"] <= 2_000_000
    print("VERDICT:", "usable for calibration" if ok else "UNUSABLE — fix sync first")
  else:
    print("no frame pairs observed")

  print("\n==== calibration result ====")
  if state["calib_set"] is None:
    raise SystemExit("no liveCalibration in log")
  calib_set = state["calib_set"]
  if state["seg_stats"]:
    usable_n = sum(1 for s in state["seg_stats"] if s["usable"])
    print(f"segments: {len(state['seg_stats'])}, usable {usable_n} "
          f"(其余标记'不可用于标定',§16.6)")
  for cam in (Cam.ROAD, Cam.WIDE):
    info = state["streams"][cam].estimate()
    print(f"{cam.name} vp estimate:", info)
    if info and info["converged"]:
      merge_candidate(calib_set, **{f"{cam.name.lower()}_pitch": info["pitch_offset"]})
  l3 = state["lane_fitter"].fit() if state["lane_fitter"] is not None else None
  print("L3 lane-geometry:", l3)
  if l3 and l3["converged"]:
    merge_candidate(calib_set, road_f=l3["f"])

  if args.sync_report:
    rep = {"route": args.route or "(pure-import)",
           "segments": state["seg_stats"], "route_level": None}
    if stats:
      rep["route_level"] = {"deltaRefMs": round(stats["deltaRef"] / 1e6, 3),
                             "p50Us": round(stats["p50"] / 1e3, 1),
                             "p999Us": round(stats["p99"] / 1e3, 1),
                             "jitterUs": round(stats["jitter"] / 1e3, 1),
                             "skewPpm": round(stats["skewPpm"], 1),
                             "synced": stats["synced"],
                             "usable": bool(stats["synced"] and stats["p99"] <= 2_000_000)}
    Path(args.sync_report).write_text(json.dumps(rep, ensure_ascii=False, indent=2))
    print(f"written: {args.sync_report}")

  out = to_json(calib_set)
  print(json.dumps(out, indent=2))
  if args.json:
    Path(args.json).write_text(json.dumps(out, indent=2))
    print(f"\nwritten: {args.json}")


if __name__ == "__main__":
  main()
