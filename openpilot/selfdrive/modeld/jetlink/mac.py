"""Comma-side provisioning: hand whichever host is attached the pinned engine.

Every host gets the same treatment. A server that already has an engine for the
pinned model validates in place; one that does not is sent the ONNX, which the
comma keeps in CACHE or downloads from the selected model's URL first (which
model that is lives in models.py). The unmodified upstream Mac app is the
special case: it polls for cancellation while the app builds by itself.

Nothing here waits for offroad. A comma wired into a car powers up straight into
onroad, so gating on it only stranded those devices without a model; what really
invalidates a preparation is the host going away, which `connected` reports.
"""
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import time
import urllib.request

from openpilot.common.jetlink_peer import is_mac_peer
from openpilot.selfdrive.modeld.jetlink.link import SPEC, validate_spec
from openpilot.selfdrive.modeld.jetlink.models import (CACHE, cached_paths, download_target,
                                                      label, model_url, selected_entry)
from jetlink.client import EngineMissing
from jetlink.transport.base import LinkTimeout


class PreparationDeferred(RuntimeError):
  pass


def require_setup(offroad, connected):
  """Whether a preparation in flight may continue.

  `offroad` is still consulted, but the daemon hands in a permissive predicate:
  a comma that only ever powers up into onroad would otherwise never get a model.
  The check stays so a caller that does care - a bench run, a test - can still
  pass a real one.
  """
  if not connected():
    raise PreparationDeferred('Host disconnected; waiting for reconnection')
  if not offroad():
    raise PreparationDeferred('Model setup requires ignition off')


def model_file(offroad, connected, progress, cache=CACHE):
  require_setup(offroad, connected)
  deadline = time.monotonic() + 1800
  cache.mkdir(parents=True, exist_ok=True)
  target = download_target(selected_entry(), cache)
  # Every verified copy counts, including one the eGPU cache already holds: the
  # point is to hand the host the model, not to own a second copy of it.
  for existing in cached_paths(SPEC.sha256):
    if not existing.is_file() or existing.stat().st_size != SPEC.nbytes:
      continue
    value = hashlib.sha256()
    with existing.open('rb') as stream:
      for block in iter(lambda: stream.read(4 << 20), b''):
        require_setup(offroad, connected)
        value.update(block)
        progress('verify', 0., 'Checking cached host model')
    if value.hexdigest() == SPEC.sha256:
      return existing
  if shutil.disk_usage(cache).free < SPEC.nbytes + (64 << 20):
    raise OSError('Not enough free space for the model')
  fd, name = tempfile.mkstemp(dir=cache, prefix='download-', suffix='.part')
  temporary = Path(name)
  # Resolve both once: the loop below runs for minutes and the selection cannot
  # change under it without a reboot anyway.
  url = model_url()
  model_label = label()
  try:
    progress('download', 0., f'Downloading {model_label}')
    with os.fdopen(fd, 'wb') as output:
      with urllib.request.urlopen(url, timeout=10) as response:
        if response.geturl() != url:
          raise ValueError('Unexpected model download redirect')
        count, value = 0, hashlib.sha256()
        while True:
          require_setup(offroad, connected)
          if time.monotonic() >= deadline:
            raise TimeoutError('Model download exceeded 30 minutes')
          block = response.read(1 << 20)
          if not block:
            break
          count += len(block)
          if count > SPEC.nbytes:
            raise ValueError('Oversized model download')
          output.write(block)
          value.update(block)
          progress('download', count / SPEC.nbytes, f'Downloading {model_label}')
      if count != SPEC.nbytes or value.hexdigest() != SPEC.sha256:
        raise ValueError('Model checksum/size mismatch')
      require_setup(offroad, connected)
      output.flush()
      os.fsync(output.fileno())
    os.replace(temporary, target)
    return target
  finally:
    temporary.unlink(missing_ok=True)


class PreparationTransport:
  """Poll setup cancellation while existing client waits for engine responses.

  Installed only during Mac preparation; inference keeps the original transport
  and deadlines. The underlying transport retains partially received messages.
  """
  def __init__(self, transport, check):
    self.transport, self.check = transport, check

  def __getattr__(self, name):
    return getattr(self.transport, name)

  def send(self, *args, **kwargs):
    self.check()
    return self.transport.send(*args, **kwargs)

  def send_json(self, *args, **kwargs):
    self.check()
    return self.transport.send_json(*args, **kwargs)

  def recv(self, timeout=None):
    end = None if timeout is None else time.monotonic() + timeout
    while True:
      self.check()
      remaining = 1. if end is None else min(1., end - time.monotonic())
      if remaining <= 0:
        raise LinkTimeout('Mac preparation response timeout')
      try:
        return self.transport.recv(timeout=remaining)
      except LinkTimeout:
        pass


def provision(client, offroad, connected, progress, cache=CACHE):
  """Give the host the pinned engine, uploading our ONNX when it has none.

  The quick probe keeps a host that is already prepared (a Jetson, or a phone
  app that downloaded the model itself) on the fast path. A need_upload answer
  means the model comes from here: the cache, or the selected model's URL when
  it is missing. The host's build then takes minutes, so this stops the moment
  the host goes away.
  """
  try:
    validate_spec(client.ensure_engine(SPEC.sha256, SPEC.nbytes, frame_skip=SPEC.frame_skip, build_timeout=30))
    return
  except EngineMissing:
    pass

  def stopped():
    require_setup(offroad, connected)
    return False

  try:
    path = model_file(offroad, connected, progress, cache)
    validate_spec(client.ensure_engine(SPEC.sha256, SPEC.nbytes, onnx_path=path,
                                       frame_skip=SPEC.frame_skip, build_timeout=1800,
                                       should_stop=stopped, progress=progress))
  finally:
    client.progress_cb = None
    client._should_stop = lambda: False


def prepare(client, peer, offroad, connected, progress, cache=CACHE):
  """Provision every host; the unmodified upstream Mac app keeps its own path."""
  if not is_mac_peer(peer):
    provision(client, offroad, connected, progress, cache)
    return

  # HELLO resets the upstream session's requested model, so engine_state is
  # normally "none" even when loaded names a resident engine. ENGINE_REQ below
  # still verifies its full spec.
  preloaded = peer.get('loaded') == SPEC.sha256
  if not preloaded:
    require_setup(offroad, connected)

  def check():
    if not connected():
      raise PreparationDeferred('Mac disconnected; waiting for reconnection')
    if not preloaded:
      require_setup(offroad, connected)
    progress('prepare', None, 'Waiting for Mac model preparation')

  def stopped():
    # A ready response returns without building. Any pending build or upload
    # still stops when the host goes away, including a stale preloaded HELLO.
    require_setup(offroad, connected)
    return False

  def report(stage, fraction, message):
    require_setup(offroad, connected)
    progress(stage, fraction, message)

  original = client.t
  client.t = PreparationTransport(original, check)
  try:
    args = dict(frame_skip=SPEC.frame_skip, build_timeout=900, should_stop=stopped, progress=report)
    try:
      result = client.ensure_engine(SPEC.sha256, SPEC.nbytes, **args)
    except EngineMissing:
      require_setup(offroad, connected)
      path = model_file(offroad, connected, progress, cache)
      require_setup(offroad, connected)
      result = client.ensure_engine(SPEC.sha256, SPEC.nbytes, onnx_path=path, **args)
    validate_spec(result)
  finally:
    client.t = original
    client.progress_cb = None
    client._should_stop = lambda: False
