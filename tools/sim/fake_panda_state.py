#!/usr/bin/env python3
"""Fake panda state + realistic Toyota TSS2 CAN for dev/test without hardware.

Publishes:
- pandaStates (ignition) -> hardwared marks device onroad
- CAN frames packed with the SAME DBC the card parser uses
  (toyota_nodsu_pt_generated for TOYOTA_COROLLA_TSS2), so carState becomes
  valid and UI renders lane lines / path overlays.

Env:
  FAKE_PANDA_IGNITION=1 (default) -> onroad; =0 -> offroad
  FAKE_PANDA_SPEED_MPS  -> cruise speed in m/s (default 8.0)
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
  sys.path.insert(0, ROOT)

from openpilot.cereal import log
from openpilot.cereal.messaging import PubMaster, new_message

IGNITION = os.getenv("FAKE_PANDA_IGNITION", "1") != "0"
SPEED_MPH = float(os.getenv("FAKE_PANDA_SPEED_MPS", "8.0")) * 2.23694  # to mph (DBC unit)
RATE = 20.0

PACKER = None


def get_packer():
  global PACKER
  if PACKER is None:
    from opendbc.can.packer import CANPacker
    PACKER = CANPacker("toyota_nodsu_pt_generated")
  return PACKER


def frame(name, values, bus=0):
  addr, dat, b = get_packer().make_can_msg(name, bus, values)
  return addr, b, dat


def panda_state_msg():
  msg = new_message("pandaStates", size=1, valid=True)
  ps = msg.pandaStates[0]
  ps.ignitionLine = IGNITION
  ps.ignitionCan = IGNITION
  ps.pandaType = log.PandaState.PandaType.uno
  return msg


def can_msg(frames):
  """One 'can' Event carrying all frames (like a real panda burst)."""
  msg = new_message("can", size=len(frames), valid=True)
  for i, (addr, bus, dat) in enumerate(frames):
    msg.can[i].address = addr
    msg.can[i].src = bus
    msg.can[i].dat = dat
  return msg


def main() -> None:
  pm = PubMaster(["pandaStates", "can"])
  print(f"fake panda: ignition={IGNITION}, speed={SPEED_MPH:.0f}mph, publishing @{RATE:.0f}Hz", flush=True)

  # Build the full CAN set once: every DBC message (zero values) plus
  # hand-set frames (gear/cruise/gas). Parser needs checksummed + cam frames.
  from opendbc.can.dbc import DBC
  dbc = DBC("toyota_nodsu_pt_generated")
  base_frames = []
  for addr, msg in sorted(dbc.addr_to_msg.items()):
    base_frames.append((msg.name, addr, 0))
  # cam-bus frames (parser Bus.cam uses src=2): PCS_HUD/LKAS_HUD are cam-native;
  # ACC_CONTROL/PRE_COLLISION are read via cp_acc (=cam parser on TSS2).
  cam_frames = {n for n, a in [("LKAS_HUD", 0x412), ("PCS_HUD", 0x411), ("ACC_CONTROL", 0x343), ("PRE_COLLISION", 0x283)]}

  tick = 0
  while True:
    ps_msg = panda_state_msg()
    speed = SPEED_MPH

    frames = []
    for name, addr, bus in base_frames:
      bus = 2 if name in cam_frames else bus
      frames.append(frame(name, {}, bus=bus))
    # override hand-set frames (sent again after the zero versions)
    frames.append(frame("KINEMATICS", {"ACCEL_X": 0.0, "ACCEL_Y": 0.0, "YAW_RATE": 0.0}))
    frames.append(frame("WHEEL_SPEEDS", {
      "WHEEL_SPEED_FL": speed, "WHEEL_SPEED_FR": speed,
      "WHEEL_SPEED_RL": speed, "WHEEL_SPEED_RR": speed}))
    frames.append(frame("GEAR_PACKET", {"GEAR": 0, "DRIVE_ENGAGED": 1, "B_GEAR_ENGAGED": 0}))
    frames.append(frame("BRAKE_MODULE", {"BRAKE_PRESSED": 0, "BRAKE_POSITION": 0.0, "BRAKE_PRESSURE": 0.0}))
    frames.append(frame("PCM_CRUISE", {"GAS_RELEASED": 1, "CRUISE_ACTIVE": 1, "CRUISE_STATE": 0, "ACCEL_NET": 0.0}))
    frames.append(frame("PCM_CRUISE_2", {"MAIN_ON": 1, "SET_SPEED": 8.0 * 3.6, "ACC_FAULTED": 0, "BRAKE_PRESSED": 0, "LOW_SPEED_LOCKOUT": 0}))
    frames.append(frame("PCM_CRUISE_SM", {"MAIN_ON": 1, "CRUISE_CONTROL_STATE": 0, "UI_SET_SPEED": 0.0}))
    frames.append(frame("GAS_PEDAL", {"GAS_PEDAL": 0.0, "GAS_RELEASED": 1, "ETQISC": 0.0}))
    frames.append(frame("BODY_CONTROL_STATE", {
      "DOOR_OPEN_FL": 0, "DOOR_OPEN_FR": 0, "DOOR_OPEN_RL": 0, "DOOR_OPEN_RR": 0,
      "SEATBELT_DRIVER_UNLATCHED": 0, "PARKING_BRAKE": 0}))
    frames.append(frame("LKAS_HUD", {"LKAS_STATUS": 0, "LTA_STATUS": 0, "LTA_MSG": 0, "LKA_MSG": 0, "STEER_REQUIRED": 0}, bus=2))
    frames.append(frame("PCS_HUD", {"PCS_ACTIVE": 0, "PCS_OFF": 0}, bus=2))

    pm.send("can", can_msg(frames))
    pm.send("pandaStates", ps_msg)
    tick += 1
    time.sleep(1.0 / RATE)


if __name__ == "__main__":
  main()
