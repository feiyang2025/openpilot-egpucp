"""The USB ownership split between the jetlink gadget and a USB-eGPU.

Both hang off the same controller (a600000.ssusb / a600000.dwc3), so the daemon
must refuse to bind its gadget while a GPU is using the port, and it must record
the USB state modeld's tmux capture leaves out. See modeld/jetlink/usb_claim.py.
"""
from pathlib import Path

from openpilot.selfdrive.modeld.jetlink import usb_claim

EGPU_ID = ((0x3801, 0x0001),)


def _sysfs(root: Path, controller: str = 'a600000.ssusb', bus: str = 'usb4') -> Path:
  """A fake /sys/bus/usb/devices tree inside `controller`."""
  devices = root / controller / bus / 'devices'
  devices.mkdir(parents=True, exist_ok=True)
  return devices


def _add_device(devices: Path, name: str, vendor: str, product: str, speed: str = '5000') -> Path:
  device = devices / name
  device.mkdir(parents=True, exist_ok=True)
  (device / 'idVendor').write_text(vendor)
  (device / 'idProduct').write_text(product)
  (device / 'speed').write_text(speed)
  (device / 'product').write_text('custom ed4e39b7-CLEAN')
  return device


def test_udc_prefix_names_the_controller():
  assert usb_claim.udc_prefix('a600000.dwc3') == 'a600000'
  assert usb_claim.udc_prefix('') is None
  assert usb_claim.udc_prefix(None) is None


def test_egpu_on_our_controller_holds_the_link(monkeypatch, tmp_path: Path):
  monkeypatch.setattr(usb_claim, 'usbgpu_ids', lambda: EGPU_ID)
  devices = _sysfs(tmp_path)
  _add_device(devices, '4-1', '3801', '0001')
  monkeypatch.setattr(usb_claim, 'USB_DEVICES', devices)

  assert usb_claim.claimed_by_usbgpu('a600000.dwc3')
  # Another controller is free even while the eGPU is on ours.
  assert not usb_claim.claimed_by_usbgpu('a800000.dwc3')
  assert usb_claim.usbgpu_controllers() == {'a600000'}


def test_a_different_product_or_controller_never_holds_the_link(monkeypatch, tmp_path: Path):
  monkeypatch.setattr(usb_claim, 'usbgpu_ids', lambda: EGPU_ID)
  # The panda shares the vendor id but not the product id.
  devices = _sysfs(tmp_path)
  _add_device(devices, '1-1', '3801', 'ddcc', speed='12')
  monkeypatch.setattr(usb_claim, 'USB_DEVICES', devices)
  assert not usb_claim.claimed_by_usbgpu('a600000.dwc3')

  # An eGPU on the other controller holds that one, not ours. In /sys/bus/usb/devices
  # every controller's devices are listed together, so the scan is pointed at that
  # controller's own directory to keep this hermetic.
  other = _sysfs(tmp_path, controller='a800000.ssusb', bus='usb2')
  _add_device(other, '2-1', '3801', '0001')
  monkeypatch.setattr(usb_claim, 'USB_DEVICES', other)
  assert usb_claim.claimed_by_usbgpu('a800000.dwc3')
  assert not usb_claim.claimed_by_usbgpu('a600000.dwc3')


def test_unreadable_sysfs_never_blocks_the_link(monkeypatch, tmp_path: Path):
  monkeypatch.setattr(usb_claim, 'usbgpu_ids', lambda: EGPU_ID)
  monkeypatch.setattr(usb_claim, 'USB_DEVICES', tmp_path / 'missing')
  assert not usb_claim.claimed_by_usbgpu('a600000.dwc3')
  assert usb_claim.usbgpu_controllers() == set()


def test_capture_context_appends_evidence(monkeypatch, tmp_path: Path):
  log = tmp_path / 'usbgpu_diag.log'
  monkeypatch.setattr(usb_claim, 'LOG', log)
  monkeypatch.setattr(usb_claim, 'USB_DEVICES', tmp_path / 'missing')
  monkeypatch.setattr(usb_claim, '_run', lambda args, timeout=6.0: 'stub output')

  assert usb_claim.capture_context('eGPU failed', extra={'link': 'jetlink idle'}) == log
  text = log.read_text(encoding='utf-8')
  assert 'eGPU failed' in text
  assert 'typec_mode=' in text and 'udc=' in text
  assert 'link=jetlink idle' in text
  assert 'stub output' in text

  # A second failure appends: the first one is still the evidence.
  assert usb_claim.capture_context('second failure') == log
  text = log.read_text(encoding='utf-8')
  assert 'second failure' in text and 'eGPU failed' in text


def test_capture_context_keeps_the_previous_log_when_it_grows(monkeypatch, tmp_path: Path):
  log = tmp_path / 'usbgpu_diag.log'
  log.write_text('x' * (usb_claim.LOG_LIMIT_BYTES + 1), encoding='utf-8')
  monkeypatch.setattr(usb_claim, 'LOG', log)
  monkeypatch.setattr(usb_claim, 'USB_DEVICES', tmp_path / 'missing')
  monkeypatch.setattr(usb_claim, '_run', lambda args, timeout=6.0: 'stub')

  usb_claim.capture_context('after rotation')
  assert log.with_suffix(log.suffix + '.1').is_file()
  assert 'after rotation' in log.read_text(encoding='utf-8')


def test_capture_context_survives_a_broken_environment(monkeypatch, tmp_path: Path):
  # Even a log path that cannot be created must not raise into the daemon loop.
  monkeypatch.setattr(usb_claim, 'LOG', tmp_path / 'no-such-dir' / 'diag.log')
  monkeypatch.setattr(usb_claim, 'USB_DEVICES', tmp_path / 'missing')
  monkeypatch.setattr(usb_claim, '_run', lambda args, timeout=6.0: 'stub')
  assert usb_claim.capture_context('unwritable') is None
