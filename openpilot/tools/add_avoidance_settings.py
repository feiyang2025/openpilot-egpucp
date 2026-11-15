#!/usr/bin/env python3
"""向 carrot_settings.json 注入"避让"设置组(5 个开关,全部热重载):
  SmalldetEnabled / TlDetEnabled / AvoidanceEnabled → manager 轮询门控(拨开关即起停 daemon)
  AvoidanceExecEnabled → plannerd 20Hz 循环内热读
  AvoidanceShadowEnabled → avoidanced 循环内热读
幂等: 已存在则跳过。indent=2 round-trip,格式与原文件一致。"""
import json
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "openpilot/selfdrive/carrot_settings.json"

D = {
  "SmalldetEnabled": {
    "title": "小目标检测守护", "etitle": "Small-Object Detector",
    "descr": "smalldetd 守护进程总开关。关闭即停止小目标(锥桶/动物/儿童低矮类)检测推理与轨迹发布。\n热生效: 拨动开关即起/停,无需重启。",
    "edescr": "smalldetd daemon gate. Toggling starts/stops the daemon live — no restart needed.",
  },
  "TlDetEnabled": {
    "title": "信号灯观测守护", "etitle": "Traffic-Light Observer",
    "descr": "tl_detd 守护进程总开关(只观测,不含 P4 停车决策)。\n热生效: 拨动开关即起/停,无需重启。",
    "edescr": "tl_detd observer daemon gate (observation only). Toggling starts/stops the daemon live.",
  },
  "AvoidanceEnabled": {
    "title": "避让决策总开关(P0)", "etitle": "Avoidance Decider (P0)",
    "descr": "avoidanced 决策守护: 小目标→分级(tier)→avoidanceState 状态面。只出决策,不碰控制链。\n热生效: 拨动开关即起/停,无需重启。",
    "edescr": "avoidanced decider daemon: publishes tiered avoidanceState. Decision surface only. Live toggle.",
  },
  "AvoidanceExecEnabled": {
    "title": "避让执行闸(P1 台架)", "etitle": "Avoidance Executor (P1 BENCH)",
    "descr": "tier→纵向加速度 floor(PREPARE −0.2 / COMFORT −3.0 / EMERGENCY −6.0 m/s²),min() 只加深不放松。\n台架层,实车放量被 G15 卡住。默认关。热生效(plannerd 每周期读取),无需重启。",
    "edescr": "tier->longitudinal accel floor, min-only. Bench level, gated by G15. Default OFF. Hot-read each planner cycle.",
  },
  "AvoidanceShadowEnabled": {
    "title": "纵向影子反事实(P2 台架)", "etitle": "Longitudinal Shadow (P2 BENCH)",
    "descr": "\"若生效会怎样\"反事实: 幽灵刹车计数(G2 ≤0.5/1000km)、>1.5 m/s² 误减速、充分性 d≥D(v,T0)。\n只计数不控制,心跳 /tmp/avoidance_shadow.json。需同时开启避让决策总开关。默认关。热生效。",
    "edescr": "Counterfactual counters (ghost braking G2, sufficiency). Counting only, no control. Requires P0 gate on. Default OFF. Hot-read.",
  },
  "AvoidanceLateralEnabled": {
    "title": "横向影子(P3 台架)", "etitle": "Lateral Shadow (P3 BENCH)",
    "descr": "横向状态机影子: 仅 L0 压线 S 型可演练(δ=0.75,lead≥L_S);L1 跨线需虚线双源+安全窗,当前无源恒拒。\n只出状态面,不接 EPS。心跳 /tmp/avoidanced.json lateral 节。需同时开启避让决策总开关。默认关。热生效。",
    "edescr": "Lateral state machine shadow: L0 edge-S only (line/gap sources missing, L1 stays denied). No EPS. Default OFF. Hot-read.",
  },
  "SignalStopEnabled": {
    "title": "信号灯停车影子(P4 台架)", "etitle": "Signal-Stop Shadow (P4 BENCH)",
    "descr": "灯色→动作映射影子: 红1帧刹/绿3帧+0.3s+绑定放行/黄dilemma/灯灭MRM。\n当前灯色取自 tl_detd 台架通道,停止线距离无源 → aFloor 恒空,只记录决策面。\n心跳 /tmp/avoidanced.json signal 节。默认关。热生效。",
    "edescr": "Light-to-action mapping shadow via tl_detd bench channel; no stopline source yet (aFloor empty). Default OFF. Hot-read.",
  },
}
MENU = {
  "id": "AVOIDANCE", "ko": "회피", "en": "Avoidance", "zh": "避让",
  "groups": [{
    "id": "AVOID_BENCH", "ko": "회피 스위치", "en": "Avoidance Switches", "zh": "避让开关",
    "params": list(D.keys()),
  }],
}

with open(PATH, encoding="utf-8") as f:
  d = json.load(f)

changed = False
names = {p["name"] for p in d["params"]}
for name, meta in D.items():
  if name in names:
    continue
  d["params"].append({
    "group": "회피", "name": name, "title": meta["title"], "descr": meta["descr"],
    "egroup": "AVOIDANCE", "etitle": meta["etitle"], "edescr": meta["edescr"],
    "cgroup": "避让", "ctitle": meta["title"], "cdescr": meta["descr"],
    "min": 0, "max": 1, "default": 0, "unit": 1, "control": "toggle", "risk": "high",
  })
  changed = True

menu_ids = [m["id"] for m in d["menu"]]
if "AVOIDANCE" not in menu_ids:
  d["menu"].insert(1, MENU)   # DRIVING 之后
  changed = True

if not changed:
  print("already present, skip")
  sys.exit(0)

with open(PATH, "w", encoding="utf-8") as f:
  json.dump(d, f, ensure_ascii=False, indent=2)
  f.write("\n")
print("injected: %s" % ", ".join(D))
