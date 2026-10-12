"""Keep the jetlink gadget off the USB controller a USB-eGPU is using, and record
the USB-level state when the eGPU fails.

The USB-eGPU and the jetlink gadget hang off the same controller: the eGPU is
enumerated under ``a600000.ssusb`` (see openpilot/system/hardware/usbgpu.py) and
the gadget's UDC is ``a600000.dwc3``. Binding the gadget flips that port to device
mode, which takes the eGPU off the bus in the middle of an inference: modeld then
spends its 30 s HCQ wait (``tinygrad/runtime/support/hcq.py``) before falling back
to the internal model, and the camera pipeline drops hundreds of frames - the
2026-10-02 drive lost 677 of them and raised a "Communication Issue Between
Processes" alert.

The daemon's existing check is ``host_attached()``, which reads the typec partner
mode ("Source attached ..."). That covers a Jetson, a phone or a hub with power,
but it is a statement about the partner, not about this controller. This module
adds the hard check on the controller itself, so an eGPU that shows up as anything
else still keeps the gadget off.

It also owns the failure dump. Upstream's modeld.py only queues a tmux capture
(``CarrotException="egpu_error"``), so the 2026-10-02 investigation had no
USB-level evidence at all: whether the link dropped, the GPU hung or the port
renegotiated had to be guessed. The daemon calls :func:`capture_context` when it
sees that queue, which costs nothing on a healthy link.
"""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

USB_DEVICES = Path('/sys/bus/usb/devices')
LOG = Path('/data/usbgpu_diag.log')
LOG_LIMIT_BYTES = 1 << 20
DMESG_KEYWORDS = ('usb', 'xhci', 'dwc3', 'usbpd', 'ssusb', 'amdgpu', 'typec')
# 'a600000.ssusb' -> 'a600000'; the gadget's UDC is 'a600000.dwc3'.
_SSUSB = re.compile(r'^([0-9a-f]+)\.ssusb$')


def _text(path: Path) -> str:
  try:
    return path.read_text().strip()
  except OSError:
    return '?'


def _hex_int(path: Path) -> int:
  try:
    return int(path.read_text().strip(), 16)
  except (OSError, ValueError):
    return 0


def usbgpu_ids() -> tuple[tuple[int, int], ...]:
  """VID/PID pairs of the USB-eGPU boards, from upstream's own list when possible."""
  try:
    from openpilot.system.hardware.usbgpu import USBGPU_USB_IDS
    return tuple(USBGPU_USB_IDS)
  except Exception:
    return ((0xadd1, 0x0001), (0x3801, 0x0001))


def controller_prefix(device: Path) -> str | None:
  """Platform prefix ('a600000') of the controller `device` is attached to."""
  try:
    for parent in device.resolve().parents:
      if (match := _SSUSB.match(parent.name)) is not None:
        return match.group(1)
  except OSError:
    pass
  return None


def udc_prefix(udc: str | None) -> str | None:
  """'a600000.dwc3' -> 'a600000', the prefix the eGPU is enumerated under."""
  return udc.split('.', 1)[0] if udc else None


def usbgpu_controllers() -> set[str]:
  """Controller prefixes a USB-eGPU is attached to right now."""
  found: set[str] = set()
  ids = usbgpu_ids()
  try:
    devices = list(USB_DEVICES.iterdir())
  except OSError:
    return found
  for device in devices:
    vendor = _hex_int(device / 'idVendor')
    if vendor == 0 or (vendor, _hex_int(device / 'idProduct')) not in ids:
      continue
    if (prefix := controller_prefix(device)) is not None:
      found.add(prefix)
  return found


def claimed_by_usbgpu(udc: str | None) -> bool:
  """True when a USB-eGPU sits on the controller this UDC belongs to.

  Anything unreadable answers False: the link must never be held back on a guess,
  and the daemon's typec check stays the first line of defence.
  """
  prefix = udc_prefix(udc)
  return prefix is not None and prefix in usbgpu_controllers()


def _run(args: list[str], timeout: float = 6.0) -> str:
  try:
    done = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return (done.stdout or done.stderr or '').strip()
  except Exception as exc:  # diagnostics never raise into the caller
    return f'<{args[0]} unavailable: {exc}>'


def _usbgpu_lines() -> list[str]:
  lines: list[str] = []
  ids = usbgpu_ids()
  try:
    devices = sorted(USB_DEVICES.iterdir(), key=lambda path: path.name)
  except OSError:
    return lines
  for device in devices:
    vendor = _hex_int(device / 'idVendor')
    product = _hex_int(device / 'idProduct')
    if vendor == 0 or (vendor, product) not in ids:
      continue
    lines.append(f'  {device.name}: {vendor:04x}:{product:04x} speed={_text(device / "speed")} '
                 f'product={_text(device / "product")} controller={controller_prefix(device)}')
  return lines


def _dmesg_lines(limit: int = 40) -> list[str]:
  out = _run(['sudo', '-n', 'dmesg'], timeout=8.0)
  keep = [line for line in out.splitlines() if any(k in line.lower() for k in DMESG_KEYWORDS)]
  return keep[-limit:] or [f'  (no usb lines; raw {len(out)} bytes)']


def _rotate() -> None:
  try:
    if LOG.is_file() and LOG.stat().st_size > LOG_LIMIT_BYTES:
      LOG.replace(LOG.with_suffix(LOG.suffix + '.1'))
  except OSError:
    pass


def capture_context(tag: str, extra: dict | None = None) -> Path | None:
  """Append the USB state around an eGPU failure to LOG; returns LOG, or None.

  Called from the daemon when modeld queues an eGPU diagnostic. Never raises: a
  dump is worth less than the link it is describing.
  """
  try:
    report = [f'=== {time.strftime("%Y-%m-%d %H:%M:%S")} {tag} ===',
              f'  typec_mode={_text(Path("/sys/class/power_supply/usb/typec_mode"))} '
              f'orientation={_text(Path("/sys/class/power_supply/usb/typec_cc_orientation"))}']
    try:
      report.append(f'  udc={[entry.name for entry in Path("/sys/class/udc").iterdir()]} '
                    f'gadget_udc={_text(Path("/sys/kernel/config/usb_gadget/jetlink/UDC"))}')
    except OSError:
      report.append('  udc=<unavailable>')
    report.append('  usbgpu devices:')
    report.extend(_usbgpu_lines() or ['  (none)'])
    if extra:
      report.append('  caller:')
      report.extend(f'    {key}={value}' for key, value in extra.items())
    report.append('  lsusb:')
    report.extend('  ' + line for line in _run(['lsusb']).splitlines())
    report.append('  lsusb -t:')
    report.extend('  ' + line for line in _run(['lsusb', '-t']).splitlines())
    report.append('  dmesg (usb related, last 40):')
    report.extend(_dmesg_lines())
    report.append('')
    _rotate()
    with LOG.open('a', encoding='utf-8') as handle:
      handle.write('\n'.join(report) + '\n')
    return LOG
  except Exception:
    return None
