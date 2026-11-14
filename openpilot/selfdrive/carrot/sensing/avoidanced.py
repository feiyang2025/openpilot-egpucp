# 受管避让决策守护(P0 台架,P0=只出决策状态面,不碰控制链)
# 订阅 smallObjectTracks + carState → AvoidanceDecider(已签判据) → avoidanceState 20Hz
import argparse
import json
import sys
import time

import openpilot.cereal.messaging as messaging
from openpilot.selfdrive.carrot.sensing.avoidance_decider import AvoidanceDecider

HB_PATH = "/tmp/avoidanced.json"
PERIOD_S = 0.05


def main(argv=None):
  ap = argparse.ArgumentParser()
  ap.add_argument("--mono", type=int, default=1, help="1=单目车型(45 档/3.2s,D1)")
  ap.add_argument("--hb-every", type=float, default=0.5)
  args, _ = ap.parse_known_args(argv if argv is not None else sys.argv[1:])

  dec = AvoidanceDecider(mono_profile=bool(args.mono))
  sub = messaging.sub_sock("smallObjectTracks", timeout=100, conflate=True)
  cs_sock = messaging.sub_sock("carState", timeout=100, conflate=True)
  pm = messaging.PubMaster(["avoidanceState"])
  hb_t = 0.0
  t0 = time.monotonic()
  n_pub = 0
  last = None
  print("avoidanced: mono=%d up" % args.mono)
  while True:
    ts = messaging.recv_sock(sub, wait=True)
    if ts is None:
      time.sleep(0.005)
      continue
    vEgo = 0.0
    csm = messaging.recv_sock(cs_sock)
    if csm is not None:
      try:
        vEgo = float(csm.carState.vEgo) * 3.6
      except Exception:
        vEgo = 0.0
    now_ns = time.monotonic_ns()
    trs = ts.smallObjectTracks
    out, max_tier, tier_name = dec.decide(trs.tracks, vEgo, now_ns)
    msg = messaging.new_message("avoidanceState")
    st = msg.avoidanceState
    st.vEgoKmh = vEgo
    st.activeTier = max_tier
    st.monoProfile = bool(args.mono)
    lst = st.init("targets", len(out))
    for j, r in enumerate(out):
      lst[j].trackId = r["trackId"]
      lst[j].tier = r["tier"]
      lst[j].cls = r["cls"]
      lst[j].clsRaw = r["clsRaw"]
      lst[j].dM = r["dM"]
      lst[j].ttcS = -1.0 if r["ttcS"] is None else float(r["ttcS"])
      lst[j].tauPotS = -1.0 if r["tauPotS"] is None else float(r["tauPotS"])
      lst[j].vRel = r["vRel"]
      lst[j].hEstM = r["hEst"]
      lst[j].envelopeKmh = r["envelopeKmh"]
    pm.send("avoidanceState", msg)
    n_pub += 1
    last = (len(out), max_tier, tier_name)
    now = time.monotonic()
    if now - hb_t >= args.hb_every:
      hb_t = now
      try:
        with open(HB_PATH, "w") as f:
          json.dump({"t": time.time(), "pub": n_pub,
                      "hz_avg": round(n_pub / max(0.1, now - t0), 1),
                     "n": last[0] if last else 0, "activeTier": last[1] if last else 0,
                      "tier": last[2] if last else "-" , "vEgoKmh": round(vEgo, 1)}, f)
      except Exception:
        pass
    target = t0 + n_pub * PERIOD_S
    sl = target - time.monotonic()
    if sl > 0:
      time.sleep(sl)


if __name__ == "__main__":
  main()
