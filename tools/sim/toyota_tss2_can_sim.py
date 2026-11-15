#!/usr/bin/env python3
"""TOYOTA_COROLLA_TSS2 台架输入仿真：D 档、30 km/h、ACC 开启、无雷达目标。"""

import argparse
import platform
import time
from pathlib import Path

import openpilot.cereal.messaging as messaging
from openpilot.cereal import car, log
from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper
from openpilot.selfdrive.pandad.pandad_api_impl import can_capnp_to_list, can_list_to_can_capnp
from opendbc.can import CANPacker
from opendbc.car.toyota.interface import CarInterface
from opendbc.car.toyota.radar_interface import RadarInterface
from opendbc.car.toyota.values import CAR, DBC

CAR_NAME = CAR.TOYOTA_COROLLA_TSS2
SPEED_KPH = 30.0
CAN_HZ = 100
PANDA_HZ = 10


def make_car_params():
  return CarInterface.get_params(CAR_NAME, {0: set(), 1: set(), 2: set()}, [], False, False, False)


def is_jetson():
  if platform.machine() != "aarch64":
    return False
  try:
    model = Path("/proc/device-tree/model").read_bytes().replace(b"\x00", b"").decode().lower()
    return "jetson" in model
  except OSError:
    return False


def validate_online_environment(jetson, fingerprint):
  if not jetson:
    raise RuntimeError("--online 仅允许在 Jetson 台架运行")
  if fingerprint != CAR_NAME:
    raise RuntimeError(f"车型必须是 {CAR_NAME}，当前为 {fingerprint}")


def reject_existing_input(received):
  active = [name for name in ("can", "pandaStates") if received.get(name)]
  if active:
    raise RuntimeError(f"检测到已有 {', '.join(active)} 输入；请先停止真实 panda/CAN 或其他仿真实例")


class ToyotaTss2CanSimulator:
  def __init__(self, cp=None):
    self.CP = make_car_params() if cp is None else cp
    if self.CP.carFingerprint != CAR_NAME:
      raise ValueError(f"仅支持 {CAR_NAME}")
    self.pt_packer = CANPacker(DBC[CAR_NAME]["pt"])
    self.radar_packer = CANPacker(DBC[CAR_NAME]["radar"])

  def _pt_frame(self, name, values):
    return self.pt_packer.make_can_msg(name, 0, values)

  def _cam_frame(self, name, values):
    return self.pt_packer.make_can_msg(name, 2, values)

  def can_frames(self, frame):
    speed = SPEED_KPH
    frames = [
      self._pt_frame("WHEEL_SPEEDS", {
        "WHEEL_SPEED_FL": speed, "WHEEL_SPEED_FR": speed,
        "WHEEL_SPEED_RL": speed, "WHEEL_SPEED_RR": speed,
      }),
      self._pt_frame("GEAR_PACKET", {"GEAR": 0, "DRIVE_ENGAGED": 1}),
      self._pt_frame("PCM_CRUISE", {
        "GAS_RELEASED": 1, "CRUISE_ACTIVE": 1, "CRUISE_STATE": 8, "ACC_BRAKING": 0,
      }),
      self._pt_frame("PCM_CRUISE_2", {
        "MAIN_ON": 1, "SET_SPEED": speed, "LOW_SPEED_LOCKOUT": 1,
        "ACC_FAULTED": 0, "PCM_FOLLOW_DISTANCE": 2,
      }),
      self._pt_frame("PCM_CRUISE_SM", {
        "MAIN_ON": 1, "CRUISE_CONTROL_STATE": 6, "UI_SET_SPEED": speed,
      }),
      self._pt_frame("BODY_CONTROL_STATE", {
        "DOOR_OPEN_FL": 0, "DOOR_OPEN_FR": 0, "DOOR_OPEN_RL": 0, "DOOR_OPEN_RR": 0,
        "SEATBELT_DRIVER_UNLATCHED": 0, "PARKING_BRAKE": 0,
      }),
      self._pt_frame("BODY_CONTROL_STATE_2", {"UNITS": 1, "UI_SPEED": speed}),
      self._pt_frame("BRAKE_MODULE", {"BRAKE_PRESSED": 0}),
      self._pt_frame("ESP_CONTROL", {"TC_DISABLED": 0, "BRAKE_HOLD_ACTIVE": 0}),
      self._pt_frame("STEER_ANGLE_SENSOR", {"STEER_ANGLE": 0, "STEER_FRACTION": 0, "STEER_RATE": 0}),
      self._pt_frame("STEER_TORQUE_SENSOR", {
        "STEER_ANGLE": 0, "STEER_TORQUE_DRIVER": 0,
        "STEER_TORQUE_EPS": 0, "STEER_ANGLE_INITIALIZING": 0,
      }),
      self._pt_frame("EPS_STATUS", {"LKA_STATE": 1, "LTA_STATE": 1}),
      self._pt_frame("BLINKERS_STATE", {"TURN_SIGNALS": 3}),
      self._pt_frame("LIGHT_STALK", {"AUTO_HIGH_BEAM": 0}),
      self._pt_frame("ENGINE_RPM", {"RPM": 1200, "ENGINE_RUNNING": 1}),
      self._pt_frame("VSC1S07", {"GVC": 0}),
      self._cam_frame("ACC_CONTROL", {"ACC_TYPE": 1, "ACC_MALFUNCTION": 0}),
      self._cam_frame("PCS_HUD", {"FCW": 0}),
      self._cam_frame("LKAS_HUD", {"LDA_MALFUNCTION": 0, "LDA_UNAVAILABLE": 0}),
      self._cam_frame("PRE_COLLISION", {"PRECOLLISION_ACTIVE": 0, "FORCE": 0}),
    ]

    # Toyota TSS2 雷达周期为 20 ms；0x19f 是 RadarInterface 的触发帧。
    if frame % 2 == 0:
      for address in range(0x180, 0x190):
        frames.append(self.radar_packer.make_can_msg(address, 1, {
          "LONG_DIST": 255, "VALID": 0, "NEW_TRACK": 0,
        }))
      for address in range(0x190, 0x1a0):
        frames.append(self.radar_packer.make_can_msg(address, 1, {"SCORE": 0}))
    return frames

  def panda_states_bytes(self, controls_allowed=False):
    msg = messaging.new_message("pandaStates", 1, valid=True)
    ps = msg.pandaStates[0]
    safety = self.CP.safetyConfigs[0]
    ps.pandaType = log.PandaState.PandaType.blackPanda
    ps.ignitionLine = True
    ps.ignitionCan = True
    ps.controlsAllowed = controls_allowed
    ps.safetyModel = safety.safetyModel
    ps.safetyParam = safety.safetyParam
    ps.alternativeExperience = self.CP.alternativeExperience
    ps.safetyRxChecksInvalid = False
    ps.heartbeatLost = False
    ps.faultStatus = log.PandaState.FaultStatus.none
    ps.harnessStatus = log.PandaState.HarnessStatus.normal
    for can_state in (ps.canState0, ps.canState1, ps.canState2):
      can_state.busOff = False
      can_state.errorWarning = False
      can_state.errorPassive = False
      can_state.canSpeed = 500
      can_state.canDataSpeed = 500
    return msg.to_bytes()


def _require(condition, message):
  if not condition:
    raise RuntimeError(f"自测失败：{message}")


def self_test():
  cp = make_car_params()
  source = ToyotaTss2CanSimulator(cp)
  car_interface = CarInterface(cp)
  radar_interface = RadarInterface(cp)
  cs = None
  radar = None

  for frame in range(8):
    frames = source.can_frames(frame)
    radar_frames = [msg for msg in frames if msg[2] == 1]
    _require(len(radar_frames) == (32 if frame % 2 == 0 else 0), "雷达帧数或周期错误")
    packets = can_capnp_to_list([can_list_to_can_capnp(frames)])
    cs = car_interface.update(packets)
    parsed_radar = radar_interface.update(packets)
    if parsed_radar is not None:
      radar = parsed_radar

  _require(cs.canValid and not cs.canTimeout, "车身 CAN 无效或超时")
  _require(abs(cs.vEgoRaw - SPEED_KPH / 3.6) < 0.02, "原始车速不是 30 km/h")
  _require(abs(cs.vEgo - SPEED_KPH / 3.6) < 0.1, "滤波车速不是 30 km/h")
  _require(cs.gearShifter == "drive", "档位不是 D")
  _require(abs(cs.steeringAngleDeg) < 0.01, "方向盘未居中")
  _require(cs.cruiseState.available and cs.cruiseState.enabled, "ACC 不可用或未开启")
  _require(abs(cs.cruiseState.speed - SPEED_KPH / 3.6) < 0.01, "ACC 设定车速错误")
  _require(not cs.accFaulted and not cs.steerFaultTemporary and not cs.steerFaultPermanent, "车辆存在故障状态")
  _require(radar is not None and not radar.errors.canError, "雷达 CAN 错误")
  _require(len(radar.points) == 0, "空雷达场景出现了目标")

  with log.Event.from_bytes(source.panda_states_bytes(controls_allowed=True)) as event:
    _require(event.valid and event.which() == "pandaStates" and len(event.pandaStates) == 1, "pandaStates 格式错误")
    ps = event.pandaStates[0]
    _require(ps.ignitionLine and ps.ignitionCan and ps.controlsAllowed, "pandaStates 点火或 controlsAllowed 错误")
    _require(ps.safetyModel == cp.safetyConfigs[0].safetyModel and
             ps.safetyParam == cp.safetyConfigs[0].safetyParam and
             ps.alternativeExperience == cp.alternativeExperience, "pandaStates 安全参数不匹配")
    _require(not ps.safetyRxChecksInvalid and not ps.heartbeatLost, "pandaStates 存在通信故障")
    _require(ps.faultStatus == "none" and ps.harnessStatus == "normal", "pandaStates 硬件状态异常")

  validate_online_environment(True, CAR_NAME)
  for args in ((False, CAR_NAME), (True, CAR.TOYOTA_RAV4_TSS2)):
    try:
      validate_online_environment(*args)
      raise RuntimeError("自测失败：在线环境保护未拒绝非法环境")
    except RuntimeError as exc:
      _require("自测失败" not in str(exc), "在线环境保护未拒绝非法环境")
  reject_existing_input({"can": [], "pandaStates": []})
  for received in ({"can": [b"frame"], "pandaStates": []}, {"can": [], "pandaStates": [b"state"]}):
    try:
      reject_existing_input(received)
      raise RuntimeError("自测失败：已有输入保护未生效")
    except RuntimeError as exc:
      _require("自测失败" not in str(exc), "已有输入保护未生效")

  print(f"PASS: {CAR_NAME}, D 档, {SPEED_KPH:.0f} km/h, ACC 开启, 方向盘居中")
  print("PASS: 车身/摄像头/TSS2 雷达 CAN 解析正常，雷达无目标")
  print("PASS: pandaStates 格式及安全参数正常，在线保护规则正常")


def _load_online_car_params():
  params = Params()
  raw = params.get("CarParams") or params.get("CarParamsPersistent")
  if raw is None:
    raise RuntimeError("未找到 CarParams；请先启动系统并完成车型选择")
  with car.CarParams.from_bytes(raw) as cp:
    return cp.as_builder()


def _check_existing_input():
  socks = {name: messaging.sub_sock(name, conflate=False, timeout=100) for name in ("can", "pandaStates")}
  time.sleep(0.25)
  received = {name: messaging.drain_sock_raw(sock, wait_for_one=False) for name, sock in socks.items()}
  reject_existing_input(received)


def run_online():
  cp = _load_online_car_params()
  validate_online_environment(is_jetson(), cp.carFingerprint)
  _check_existing_input()

  source = ToyotaTss2CanSimulator(cp)
  pm = messaging.PubMaster(["can", "pandaStates"])
  sm = messaging.SubMaster(["selfdriveState"])
  rk = Ratekeeper(CAN_HZ, print_delay_threshold=None)
  frame = 0
  print(f"开始仿真：{CAR_NAME}，D 档，{SPEED_KPH:.0f} km/h，ACC 开启，无雷达目标。Ctrl-C 停止。")
  try:
    while True:
      sm.update(0)
      pm.send("can", can_list_to_can_capnp(source.can_frames(frame)))
      if frame % (CAN_HZ // PANDA_HZ) == 0:
        active = sm.valid["selfdriveState"] and sm["selfdriveState"].active
        pm.send("pandaStates", source.panda_states_bytes(controls_allowed=active))
      frame += 1
      rk.keep_time()
  except KeyboardInterrupt:
    print("\n仿真已停止")


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  mode = parser.add_mutually_exclusive_group(required=True)
  mode.add_argument("--self-test", action="store_true", help="离线验证 CAN 解析和 pandaStates，不发布消息")
  mode.add_argument("--online", action="store_true", help="在 Jetson 台架发布 can 和 pandaStates")
  args = parser.parse_args()
  if args.self_test:
    self_test()
  else:
    run_online()


if __name__ == "__main__":
  main()
