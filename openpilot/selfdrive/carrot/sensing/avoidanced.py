# 受管避让决策守护(P0 台架,P0=只出决策状态面,不碰控制链)
# 订阅 smallObjectTracks + carState → AvoidanceDecider(已签判据) → avoidanceState 20Hz
# 热重载: daemon 生死由 manager 按 AvoidanceEnabled 轮询门控(拨开关即起停,免重启);
# P2 影子在本循环内按 AvoidanceShadowEnabled 每周期热读,写 /tmp/avoidance_shadow.json
import argparse
import json
import sys
import time

import openpilot.cereal.messaging as messaging
from openpilot.common.params import Params
from openpilot.selfdrive.carrot.sensing.avoidance_decider import AvoidanceDecider
from openpilot.selfdrive.carrot.sensing.avoidance_shadow import AvoidanceShadow

HB_PATH = "/tmp/avoidanced.json"
PERIOD_S = 0.05


def main(argv=None):
  ap = argparse.ArgumentParser()
  ap.add_argument("--mono", type=int, default=1, help="1=单目车型(45 档/3.2s,D1)")
  ap.add_argument("--hb-every", type=float, default=0.5)
  args, _ = ap.parse_known_args(argv if argv is not None else sys.argv[1:])

  dec = AvoidanceDecider(mono_profile=bool(args.mono))
  shadow = AvoidanceShadow(mono_profile=bool(args.mono))
  params = Params()
  sub = messaging.sub_sock("smallObjectTracks", timeout=100, conflate=True)
  cs_sock = messaging.sub_sock("carState", timeout=100, conflate=True)
  pm = messaging.PubMaster(["avoidanceState"])
  hb_t = 0.0
  t0 = time.monotonic()
  last_t = t0
  km = 0.0
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
    now = time.monotonic()
    km += (vEgo / 3.6) * max(0.0, min(0.5, now - last_t))
    last_t = now
    trs = ts.smallObjectTracks
    out, max_tier, tier_name = dec.decide(trs.tracks, vEgo, now_ns)
    # P2 影子(台架): 反事实计数,不碰控制链;开关每周期热读,默认 OFF
    shadow_on = params.get_bool("AvoidanceShadowEnabled")
    w_apply, w_floor, w_reason = shadow.update(
      out, vEgo / 3.6, 0.0, shadow_on, True, now, now_ns,
      genuine=True, dist_km=km, hb=True)
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
    if now - hb_t >= args.hb_every:
      hb_t = now
      try:
        with open(HB_PATH, "w") as f:
          json.dump({"t": time.time(), "pub": n_pub,
                      "hz_avg": round(n_pub / max(0.1, now - t0), 1),
                     "n": last[0] if last else 0, "activeTier": last[1] if last else 0,
                      "tier": last[2] if last else "-" , "vEgoKmh": round(vEgo, 1),
                      "shadowOn": shadow_on,
                      "shadow": {"km": round(shadow.km, 2), "ghost": shadow.n_ghost,
                                  "ghost1p5": shadow.n_ghost_1p5,
                                  "suff": shadow.n_suff, "insuff": shadow.n_insuff,
                                  "g2Pass": shadow.g2_pass()}}, f)
      except Exception:
        pass
    target = t0 + n_pub * PERIOD_S
    sl = target - time.monotonic()
    if sl > 0:
      time.sleep(sl)


if __name__ == "__main__":
  main()
