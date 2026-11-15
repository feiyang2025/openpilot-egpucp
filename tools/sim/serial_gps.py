#!/usr/bin/env python3
"""4G-module GPS (NMEA on /dev/ttyUSB1) -> openpilot gpsLocationExternal.

The Qualcomm SimTech 4G modem exposes NMEA sentences on a USB-CDC serial port.
Parse GGA (lat/lon/alt/fix) and RMC (speed/bearing) and publish
gpsLocationExternal (only with a valid fix, flags=1).

Env: GPS_PORT (default /dev/ttyUSB1), GPS_BAUD (default 115200)
"""
import math
import os
import sys
import time

import serial

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
  sys.path.insert(0, ROOT)

from openpilot.cereal import log
from openpilot.cereal.messaging import PubMaster, new_message

PORT = os.getenv("GPS_PORT", "/dev/ttyUSB1")
BAUD = int(os.getenv("GPS_BAUD", "115200"))


def nmea_to_deg(raw: str) -> float | None:
  """ddmm.mmmm -> decimal degrees; '' -> None."""
  if not raw:
    return None
  try:
    d = float(raw)
  except ValueError:
    return None
  deg = int(d / 100)
  minutes = d - deg * 100
  return deg + minutes / 60.0


def main() -> None:
  pm = PubMaster(["gpsLocationExternal"])
  print(f"GPS: opening {PORT} @ {BAUD} (NMEA)", flush=True)
  ser = serial.Serial(PORT, BAUD, timeout=1.0)

  fix = False
  lat = lon = alt = 0.0
  speed_kts = 0.0
  bearing = 0.0
  utc = None
  last_pub = 0.0

  while True:
    try:
      line = ser.readline().decode("ascii", "ignore").strip()
      receive_mono_ns = time.monotonic_ns()
      receive_realtime_ns = time.time_ns()
    except Exception as e:
      print(f"GPS: read err {e}", flush=True)
      time.sleep(1)
      continue
    if not line.startswith("$"):
      continue
    parts = line.split(",")
    if parts[0] in ("$GPGGA", "$GNGGA") and len(parts) >= 10:
      lat = nmea_to_deg(parts[2])
      lon = nmea_to_deg(parts[4])
      if parts[2] and parts[2].endswith("S"):
        lat = -lat
      if parts[4] and parts[4].endswith("W"):
        lon = -lon
      try:
        alt = float(parts[9])
      except ValueError:
        alt = 0.0
      fix = parts[6] not in ("", "0")
    elif parts[0] in ("$GPRMC", "$GNRMC") and len(parts) >= 9:
      try:
        speed_kts = float(parts[7]) if parts[7] else 0.0
      except ValueError:
        speed_kts = 0.0
      try:
        bearing = float(parts[8]) if parts[8] else 0.0
      except ValueError:
        bearing = 0.0

    now = receive_mono_ns * 1e-9
    if fix and lat is not None and lon is not None and (now - last_pub) >= 1.0:
      last_pub = now
      dat = new_message("gpsLocationExternal", valid=True, logMonoTime=receive_mono_ns)
      dat.gpsLocationExternal = {
        "unixTimestampMillis": receive_realtime_ns // 1_000_000,
        "flags": 1,
        "horizontalAccuracy": 5.0,
        "verticalAccuracy": 10.0,
        "speedAccuracy": 0.5,
        "bearingAccuracyDeg": 1.0,
        "vNED": [0.0, 0.0, 0.0],
        "bearingDeg": bearing,
        "latitude": lat,
        "longitude": lon,
        "altitude": alt,
        "speed": speed_kts * 0.514444,  # kt -> m/s
        "source": log.GpsLocationData.SensorSource.ublox,
      }
      pm.send("gpsLocationExternal", dat)


if __name__ == "__main__":
  main()
