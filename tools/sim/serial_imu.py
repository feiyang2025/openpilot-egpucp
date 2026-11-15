#!/usr/bin/env python3
"""Yahboom 10-axis IMU on /dev/ttyTHS2 -> openpilot accelerometer/gyroscope.

Protocol (docs: yahboom imu serial protocol):
  frame: 0x55 TYPE D1L D1H D2L D2H D3L D3H D4L D4H SUM (11 bytes)
  TYPE 0x51: accel (16g) + temp; 0x52: gyro (2000dps) + voltage
  accel g  = int16 / 32768 * 16
  gyro dps = int16 / 32768 * 2000
Config: unlock (FF AA 69 88 B5), RSW=0x06 (accel|gyro), RRATE=0x09 (100Hz),
save (FF AA 00 00 00). 10s lockout after unlock.

Env: IMU_PORT (default /dev/ttyTHS2), IMU_BAUD (default 115200)
"""
import math
import os
import sys
import time

import serial

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
  sys.path.insert(0, ROOT)

from openpilot.cereal.messaging import PubMaster, new_message

PORT = os.getenv("IMU_PORT", "/dev/ttyTHS2")
BAUD = int(os.getenv("IMU_BAUD", "115200"))
RATE = 100.0

FRAME_HDR = 0x55
TYPE_ACCEL = 0x51
TYPE_GYRO = 0x52


def send_cmd(ser, cmd: bytes) -> None:
  ser.write(cmd)
  time.sleep(0.05)


def configure(ser) -> None:
  send_cmd(ser, bytes([0xFF, 0xAA, 0x69, 0x88, 0xB5]))  # unlock KEY=0xB588
  send_cmd(ser, bytes([0xFF, 0xAA, 0x02, 0x06, 0x00]))  # RSW: accel|gyro only
  send_cmd(ser, bytes([0xFF, 0xAA, 0x03, 0x09, 0x00]))  # RRATE: 100Hz
  send_cmd(ser, bytes([0xFF, 0xAA, 0x00, 0x00, 0x00]))  # SAVE


def parse_stream(ser, cb) -> None:
  buf = bytearray()
  while True:
    chunk = ser.read(256)
    if not chunk:
      continue
    buf += chunk
    while len(buf) >= 11:
      if buf[0] != FRAME_HDR:
        buf.pop(0)
        continue
      frame = bytes(buf[:11])
      if sum(frame[:10]) & 0xFF != frame[10]:
        buf.pop(0)
        continue
      buf = buf[11:]
      typ = frame[1]
      if typ == TYPE_ACCEL:
        ax = int.from_bytes(frame[2:4], "little", signed=True) / 32768.0 * 16.0 * 9.81
        ay = int.from_bytes(frame[4:6], "little", signed=True) / 32768.0 * 16.0 * 9.81
        az = int.from_bytes(frame[6:8], "little", signed=True) / 32768.0 * 16.0 * 9.81
        cb("accel", (ax, ay, az))
      elif typ == TYPE_GYRO:
        wx = int.from_bytes(frame[2:4], "little", signed=True) / 32768.0 * 2000.0 * math.pi / 180.0
        wy = int.from_bytes(frame[4:6], "little", signed=True) / 32768.0 * 2000.0 * math.pi / 180.0
        wz = int.from_bytes(frame[6:8], "little", signed=True) / 32768.0 * 2000.0 * math.pi / 180.0
        cb("gyro", (wx, wy, wz))


def main() -> None:
  pm = PubMaster(["accelerometer", "gyroscope"])

  def publish(which, v):
    # locationd compares SensorEventData.timestamp with Event.logMonoTime and
    # rejects empty or >100 ms divergent readings. Use one CLOCK_MONOTONIC
    # timestamp for both fields so serial IMU samples share openpilot's clock.
    timestamp = time.monotonic_ns()
    if which == "accel":
      dat = new_message("accelerometer", valid=True, logMonoTime=timestamp)
      dat.accelerometer.timestamp = timestamp
      dat.accelerometer.version = 1
      dat.accelerometer.sensor = 1   # SENSOR_ACCELEROMETER
      dat.accelerometer.type = 1     # SENSOR_TYPE_ACCELEROMETER
      dat.accelerometer.source = "bno055"
      dat.accelerometer.init("acceleration")
      dat.accelerometer.acceleration.v = list(v)
      dat.accelerometer.acceleration.status = 1
      pm.send("accelerometer", dat)
    else:
      dat = new_message("gyroscope", valid=True, logMonoTime=timestamp)
      dat.gyroscope.timestamp = timestamp
      dat.gyroscope.version = 2
      dat.gyroscope.sensor = 5       # SENSOR_GYRO_UNCALIBRATED
      dat.gyroscope.type = 16        # SENSOR_TYPE_GYROSCOPE_UNCALIBRATED
      dat.gyroscope.source = "bno055"
      dat.gyroscope.init("gyroUncalibrated")
      dat.gyroscope.gyroUncalibrated.v = list(v)
      dat.gyroscope.gyroUncalibrated.status = 1
      pm.send("gyroscope", dat)

  print(f"IMU: opening {PORT} @ {BAUD}", flush=True)
  ser = serial.Serial(PORT, BAUD, timeout=0.2)
  configure(ser)
  ser.reset_input_buffer()
  print(f"IMU: configured (accel+gyro @{RATE:.0f}Hz), parsing stream", flush=True)
  parse_stream(ser, publish)


if __name__ == "__main__":
  main()
