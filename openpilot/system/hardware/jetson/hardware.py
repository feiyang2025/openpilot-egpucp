"""Jetson AGX Orin / Orin Nano hardware support."""
from openpilot.cereal import log
from openpilot.system.hardware.base import ThermalConfig, ThermalZone
from openpilot.system.hardware.pc.hardware import Pc

NetworkType = log.DeviceState.NetworkType


class Jetson(Pc):
  """Jetson-series device (AGX Orin, Orin Nano, etc.).

  Mostly shares behavior with a PC (no internal panda, no modem).
  DeviceType reports as "pc" since the capnp DeviceType enum doesn't
  have a "jetson" entry; the hardware IS correctly detected as non-PC
  (JETSON=True, PC=False) at module level.
  """

  def get_device_type(self) -> str:
    # Capnp DeviceType enum: unknown, neo, chffrAndroid, chffrIos, tici, pc, tizi, mici
    # No "jetson" yet — use "pc" as closest match.
    return "pc"

  def get_thermal_config(self):
    # AGX Orin /sys/class/thermal zone types: cpu-thermal gpu-thermal
    # soc0-2-thermal cv0-2-thermal tj-thermal (ThermalZone matches by type, scale 1e-3)
    return ThermalConfig(
      cpu=[ThermalZone("cpu-thermal")],
      gpu=[ThermalZone("gpu-thermal")],
      memory=ThermalZone("soc0-thermal"),
      pmic=[ThermalZone("tj-thermal")],
    )

  _vin_5v_path: str | None = None

  def get_battery_voltage(self) -> int:
    # 台架供电为外部电源经载板整流稳压; 原始输入(插头/USB-C VBUS) 无监控芯片, sysfs 不可读。
    # 此处读 INA3221 的 VIN_SYS_5V0 系统轨(mV) — 载板上唯一真实可读的电源电压。
    import glob
    if self._vin_5v_path is None:
      self._vin_5v_path = ""
      for label in glob.glob("/sys/class/hwmon/hwmon*/in*_label"):
        try:
          with open(label) as f:
            if f.read().strip() != "VIN_SYS_5V0":
              continue
          self._vin_5v_path = label.replace("_label", "_input")
          break
        except OSError:
          continue
    if not self._vin_5v_path:
      return 0
    try:
      with open(self._vin_5v_path) as f:
        return int(f.read().strip())
    except (OSError, ValueError):
      return 0

  def get_fan_rpm(self) -> int:
    # pwm_tach fan tachometer (AGX Orin 载板风扇转速)
    try:
      with open("/sys/class/hwmon/hwmon3/rpm") as f:
        return int(f.read().strip())
    except (OSError, ValueError):
      return 0
