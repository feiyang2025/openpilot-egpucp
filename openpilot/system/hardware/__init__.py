import os
import platform
from typing import cast

from openpilot.system.hardware.base import HardwareBase
from openpilot.system.hardware.tici.hardware import Tici
from openpilot.system.hardware.pc.hardware import Pc

TICI = os.path.isfile('/TICI')
AGNOS = os.path.isfile('/AGNOS')

# Jetson AGX Orin: aarch64 + tegra SoC present
_JETSON = False
try:
    _model = open('/proc/device-tree/model').read().replace('\x00', '').strip().lower()
    _JETSON = (platform.machine() == 'aarch64') and ('jetson' in _model)
except Exception:
    pass
JETSON = _JETSON or os.path.exists('/sys/devices/soc0')

# PC=True only on generic desktops. Jetson (like TICI) is a real device.
PC = not (TICI or JETSON)

if TICI:
    HARDWARE = cast(HardwareBase, Tici())
elif JETSON:
    from openpilot.system.hardware.jetson.hardware import Jetson
    HARDWARE = cast(HardwareBase, Jetson())
else:
    HARDWARE = cast(HardwareBase, Pc())
