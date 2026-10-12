"""USB gadget owner and Jetlink client, isolated from modeld's frame deadline."""
import fcntl
import gc
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import numpy as np

from openpilot.selfdrive.modeld.jetlink import VENDOR
from openpilot.selfdrive.modeld.jetlink.link import (SPEC, SOCKET, STATUS, REQUEST, REPLY, PacketReader, send, send_parts)
from openpilot.selfdrive.modeld.jetlink.models import label
from openpilot.selfdrive.modeld.jetlink.phase import Publisher as PhasePublisher
from openpilot.selfdrive.modeld.jetlink.mac import prepare, PreparationDeferred
from openpilot.selfdrive.modeld.jetlink.usb_claim import capture_context, claimed_by_usbgpu
from jetlink.client import JetlinkClient
import jetlink.transport.ffs as ffs_module
from jetlink.transport.ffs import FfsTransport

# The app reloads its QNN engine after every re-enumeration and does not read
# the link while it does: measured on an SM8750 at 37-43 s. A write into that
# window is abandoned at WRITE_TIMEOUT, and protocol 3 answers an abandoned
# write by dropping the gadget, which re-enumerates and starts the reload over.
# Give a write longer than a host reload, so it waits instead of tearing down.
ffs_module.WRITE_TIMEOUT = 180.0


# The server drops every message at or below the high-water mark it keeps for
# the connection, and a fresh client starts at 0. Start every client past that
# mark so a retry is never read as a replay; relying on the caller assigning it
# was not enough - a client built anywhere else came back at seq 1 and had its
# engine request discarded, which is what left the app waiting.
def _client_with_base_seq(orig):
  def init(self, *args, **kwargs):
    orig(self, *args, **kwargs)
    self.seq = max(self.seq, int(time.monotonic()) & 0xFFFFFFFF)
  return init


JetlinkClient.__init__ = _client_with_base_seq(JetlinkClient.__init__)

GADGET = '/sys/kernel/config/usb_gadget/jetlink'
ROLE = Path('/sys/class/power_supply/usb/typec_mode')
log = logging.getLogger('carrot.jetlink')
# The manager captures nothing from this process, which has cost whole
# debugging sessions: keep a file that can just be read afterwards.
_file_log = logging.FileHandler('/data/jetlinkd.log')
_file_log.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
logging.getLogger().setLevel(logging.INFO)
logging.getLogger().addHandler(_file_log)
sys.path.insert(0, str(VENDOR.parents[1] / 'tools/jetlink'))
from hud_protocol import Publisher, HUD_CAPABILITY, HUD_MESSAGE
from hud_navi import CAPABILITY as NAVI_CAPABILITY, MESSAGE as NAVI_MESSAGE
from hud_navi import send_ready_after_reply, PUMP_CAPABILITY
from wifi_protocol import CAPABILITY as WIFI_CAPABILITY, Publisher as WifiPublisher


def update_affinity():
  from openpilot.common.params import Params
  onroad = Params().get_bool('IsOnroad') and Path('/sys/devices/system/cpu/cpu7/online').read_text().strip() == '1'
  # Keep USB completion and IPC work off modeld/DM's core7. Pinning the
  # reader there delayed runnable reads behind DM and blocked the host's
  # response write. Include the normal-priority watchdog in this placement.
  # Model/DM policies and the display children's separate policy are unchanged.
  cores = set(range(4))
  os.sched_setscheduler(0, os.SCHED_FIFO if onroad else os.SCHED_OTHER, os.sched_param(1 if onroad else 0))
  for thread in Path('/proc/self/task').iterdir():
    try:
      os.sched_setaffinity(int(thread.name), cores)
    except ProcessLookupError:
      pass


def publish_hud(client, publisher):
  if publisher is not None:
    try:
      packet = publisher.packet()
    except Exception:
      log.exception('display snapshot unavailable')
      return
    if packet:
      client.t.send(HUD_MESSAGE, client._next_seq(), [packet])
    # At most one small fragment per inference window. No video
    # decoding or unbounded stream draining occurs on the USB owner's thread.
    media = publisher.media_packet()
    if media:
      client.t.send(NAVI_MESSAGE, client._next_seq(), [media])


def host_attached():
  try:
    # CC orientation alone also detects eGPU/hub cables. Require the peer to
    # be a source/host: never seize the existing eGPU's USB role.
    return ROLE.read_text().strip().startswith('Source attached')
  except OSError:
    return False


def publish(status, **extra):
  record = dict(state=status, updated=time.monotonic(), model=label(), sha256=SPEC.sha256, **extra)
  temporary = STATUS.with_suffix('.tmp')
  temporary.write_text(json.dumps(record))
  os.replace(temporary, STATUS)


def close_transport(transport):
  """Give the gadget up on purpose, tolerating a transport that already failed."""
  try:
    transport.close()
  except Exception:
    log.exception('Jetlink transport close failed')


def rebind_transport(transport) -> bool:
  """Put a gadget back on the bus after protocol 3 took it off.

  A write nobody read is answered by unbinding the gadget, so the host sees the
  cable leave; leaving it off until the next session rebuilds the endpoint set
  from scratch. The host is still attached, so reattach the controller here.

  Returns whether the gadget is back on the bus. A failure used to exist in the
  log file only, so the link could be stuck with nothing on screen saying so.
  """
  if not transport.bound_udc:
    return False
  if claimed_by_usbgpu(transport.bound_udc):
    # Binding the UDC is the one action here that can drop a running USB-eGPU
    # (they share the controller; see usb_claim): leave the port to the GPU.
    log.warning('not rebinding the gadget: a USB-eGPU is using %s', transport.bound_udc)
    publish('retrying', error='USB eGPU is using the port; jetlink gadget held off')
    return False
  try:
    transport.bind(transport.bound_udc)
    return True
  except Exception as exc:
    log.exception('Jetlink gadget rebind failed')
    publish('retrying', error=f'gadget rebind failed: {exc}'[:300])
    return False


def transport_needs_rebuild(exc):
  """Whether a failed session left the transport itself unusable.

  A desynced byte stream is the only such case: a timed-out frame, a write with
  no reader or a server error all recover on the same gadget, and rebuilding
  takes the USB link off the bus, which an Android host answers by re-opening
  the device.
  """
  text = str(exc)
  return 'desynced' in text or 'must be reopened' in text


def _first_udc() -> str | None:
  """The device controller the gadget would be bound to, if any."""
  try:
    return next(Path('/sys/class/udc').iterdir()).name
  except (OSError, StopIteration):
    return None


_usbgpu_diagnostic_seen: str | None = None
_usb_hold_logged = False


def _note_usb_hold(active: bool) -> None:
  """Log entering and leaving the USB-eGPU hold, once per change."""
  global _usb_hold_logged
  if active == _usb_hold_logged:
    return
  _usb_hold_logged = active
  if active:
    log.warning('holding the gadget off: a USB-eGPU is using %s', _first_udc())
  else:
    log.info('the USB-eGPU released the controller; the gadget may bind again')


def _pending_usbgpu_diagnostic() -> str | None:
  """The eGPU reason modeld queued, returned once while this process is idle.

  Upstream modeld.py sets CarrotException="egpu_error" when the eGPU fails and
  leaves the USB-level evidence to whoever notices; on the 2026-10-02 drive
  nothing did, so a 30 s loss of the model could not be explained afterwards.
  This process owns the USB gadget and sits idle in exactly that state, so it
  records the context once per queued reason (usb_claim.capture_context).
  """
  global _usbgpu_diagnostic_seen
  try:
    from openpilot.common.params import Params
    reason = Params().get('CarrotException')
    if isinstance(reason, bytes):
      reason = reason.decode('utf-8', errors='ignore')
  except Exception:
    return None
  if reason in (None, '') or reason == _usbgpu_diagnostic_seen:
    return None
  _usbgpu_diagnostic_seen = reason
  return f'eGPU diagnostic queued by modeld (CarrotException={reason})'


class CarrotTransport(FfsTransport):
  # A frame is 393 KB and the vendored default writes up to 512 KB at once,
  # which needs a host to have that many reads in flight at that instant. The
  # Android app keeps a fixed pool of posted reads and a write that has to wait
  # for them is abandoned after WRITE_TIMEOUT, and protocol 3 answers an
  # abandoned write by unbinding the gadget, i.e. unplugging the cable. Small
  # writes need one posted read at a time and carry exactly the same bytes.
  write_chunk = 16 * 1024

  def _widen_affinity(self):
    os.sched_setaffinity(0, set(range(min(4, os.cpu_count() or 1))))

  def _raise_reader_priority(self):
    # The short USB receive/copy worker is realtime, below modeld/DM.
    # Display workers remain normal priority. Existing camera/control/sensor
    # placements and priorities are untouched.
    os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(1))


def serve_local(listener, client, peer, wifi=None):
  publisher = Publisher(navi=bool(peer.get(NAVI_CAPABILITY))) if peer.get(HUD_CAPABILITY) else None
  phase = PhasePublisher()
  try:
    _serve_local(listener, client, peer, publisher, phase, wifi)
  finally:
    phase.close()
    if publisher is not None:
      publisher.close()


def _serve_local(listener, client, peer, publisher, phase, wifi=None):
  from openpilot.common.params import Params
  from openpilot.common.runtime_diagnostics import RuntimeDiagnostics
  from openpilot.common.swaglog import cloudlog
  params = Params()
  diagnostics = RuntimeDiagnostics('jetlinkd', cloudlog.event)
  last_status = 0.
  last_ping = time.monotonic()
  telemetry_updated = 0.
  while host_attached():
    if time.monotonic() - last_status >= 1:
      update_affinity()
      publish('ready', peer=peer, telemetry=client.last_state, telemetry_updated=telemetry_updated)
      last_status = time.monotonic()
    try:
      connection, _ = listener.accept()
    except TimeoutError:
      if wifi is not None:
        wifi.send(client)
      publish_hud(client, publisher)
      if time.monotonic() - last_ping > 2:
        client.last_state = client.state()
        telemetry_updated = time.monotonic()
        last_ping = time.monotonic()
      continue
    with connection:
      connection.settimeout(.5)
      reader = PacketReader(REQUEST.size + SPEC.warped_nbytes + SPEC.packed_nbytes)
      try:
        send(connection, json.dumps({'spec': SPEC.to_dict(), 'peer': peer}).encode())
        # The app loads its engine on the frames right after a join: measured at
        # ~50 s for this model here. Serving keeps a strict frame budget so a
        # slow frame is only a dropped camera frame, but that budget also
        # abandons the link in the middle of that load, and the app drops the
        # engine with it, so every retry restarted the load and no frame ever
        # completed. Give the first frames the preparation budget; a settled
        # link keeps the strict one.
        served = 0
        while host_attached():
          client.deadline = 300.0 if served < 3 else 3.0
          loop_started, cpu_started = time.monotonic(), time.thread_time()
          if time.monotonic() - last_status >= 1:
            update_affinity()
            if publisher is not None:
              params.put_bool_nonblocking('ClusterHudConnected', bool((client.last_state or {}).get('carrot_hud_connected')))
            publish('ready', peer=peer, timings=list(client.last_timings),
                    telemetry=client.last_state, telemetry_updated=telemetry_updated,
                    navigation_tail=getattr(publisher, 'tail_stats', {}))
            last_status = time.monotonic()
          receive_started = time.monotonic()
          try:
            request = reader.receive(connection)
          except TimeoutError:
            if wifi is not None:
              wifi.send(client)
            publish_hud(client, publisher)
            client.last_state = client.state()
            telemetry_updated = time.monotonic()
            continue
          received = time.monotonic()
          if len(request) != REQUEST.size + SPEC.warped_nbytes + SPEC.packed_nbytes:
            raise ValueError('invalid local inference request')
          frame, reset, source_sof = REQUEST.unpack_from(request)
          if reset not in (0, 1):
            raise ValueError('invalid reset flag')
          images = np.frombuffer(request, np.uint8, SPEC.warped_nbytes, REQUEST.size).reshape(SPEC.warped_shape)
          packed = np.frombuffer(request, np.float32, SPEC.packed_nelem, REQUEST.size + SPEC.warped_nbytes)
          if not np.all(np.isfinite(packed)):
            raise ValueError('invalid local model context')
          started = time.monotonic()
          seq = client.infer_begin(images, packed, frame, reset=bool(reset), want_state=(frame % 20 == 0))
          sent = time.monotonic()
          if peer.get('carrot_host') == 'jetson':
            phase.sent(source_sof)
          phase_done = time.monotonic()
          if peer.get(NAVI_CAPABILITY):
            publish_hud(client, publisher)
          hud_done = time.monotonic()
          previous_state = client.last_state
          output = client.infer_end(seq)
          served += 1
          if client.last_state is not previous_state:
            telemetry_updated = time.monotonic()
          completed = time.monotonic()
          try:
            send_parts(connection, REPLY.pack(frame, *client.last_timings), output)
          finally:
            # Preserve the send/response split even when modeld already timed
            # out and the local reply raises BrokenPipeError.
            if completed - started > .05:
              log.warning('USB frame %d: send %.1f response %.1f IPC %.1f ms', frame,
                          (sent-started)*1000, (completed-sent)*1000, (time.monotonic()-completed)*1000)
          replied = time.monotonic()
          if not peer.get(NAVI_CAPABILITY):
            publish_hud(client, publisher)
          else:
            # modeld already has its reply. Drain only a bounded ready tail;
            # never add these fragments before infer_end or delay its reply.
            send_ready_after_reply(client, publisher, fast_receiver=peer.get(PUMP_CAPABILITY) is True)
          tail_done = time.monotonic()
          if wifi is not None:
            wifi.send(client)
          finished = time.monotonic()
          # Record in rlog as well as stderr. Receive time includes normal idle
          # waiting; the reply tail may delay admission of the NEXT request.
          diagnostics.record(
            context={'frame_id': frame, 'usb_seq': seq},
            housekeeping_ms=(receive_started-loop_started)*1000,
            ipc_receive_ms=(received-receive_started)*1000,
            request_parse_ms=(started-received)*1000,
            usb_send_ms=(sent-started)*1000,
            phase_ms=(phase_done-sent)*1000,
            hud_ms=(hud_done-phase_done)*1000,
            usb_response_ms=(completed-hud_done)*1000,
            ipc_reply_ms=(replied-completed)*1000,
            display_tail_ms=(tail_done-replied)*1000,
            wifi_tail_ms=(finished-tail_done)*1000,
            server_gpu_ms=client.last_timings[0]/1000,
            server_queue_ms=client.last_timings[1]/1000,
            server_total_ms=client.last_timings[2]/1000,
            loop_ms=(finished-loop_started)*1000,
            thread_cpu_ms=(time.thread_time()-cpu_started)*1000,
          )
      except (ConnectionError, BrokenPipeError, ValueError) as exc:
        log.info('local client ended: %s', exc)
    last_ping = time.monotonic()


def main():
  logging.basicConfig(level=logging.INFO)
  # Like modeld, do not let cyclic GC scan the manager's inherited object graph
  # while an inference reply is due. Collect between USB sessions instead.
  gc.disable()
  os.sched_setscheduler(0, os.SCHED_OTHER, os.sched_param(0))
  os.sched_setaffinity(0, set(range(min(4, os.cpu_count() or 1))))
  lock = open('/dev/shm/carrot-jetlink.lock', 'w')
  fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
  Path(SOCKET).unlink(missing_ok=True)
  listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
  listener.bind(SOCKET)
  os.chmod(SOCKET, 0o600)
  listener.listen(1)
  listener.settimeout(.05)
  setup = VENDOR.parents[1] / 'tools/jetlink/setup_gadget.sh'
  peer = None
  # The gadget stays bound across session retries. An Android host re-opens the
  # device on every USB disconnect and takes seconds over it, so a link that
  # leaves the bus whenever a frame times out is never served at all; the Mac
  # and the Jetson tolerate that pattern, which is why carrot's loop survived
  # it. A transport is rebuilt only when the stream desynced, or after repeated
  # failures that point at this end rather than at the host.
  transport = None
  greeted = False
  failures = 0
  # Sequence number to continue from on this transport; see the client below.
  next_seq = 0
  try:
    while True:
      update_affinity()
      if not host_attached():
        # The typec role flickers while a write timeout is being recovered, so
        # this branch only idles: the gadget is kept. Dropping it here is what
        # made every retry rebuild the endpoints and re-enumerate the device.
        # A USB-eGPU reads as a powered cable here, so name that case: without it
        # "idle" cannot be told apart from "the port belongs to the GPU".
        hold = transport is None and claimed_by_usbgpu(_first_udc())
        _note_usb_hold(hold)
        publish('waiting', peer=peer, **({'usb_hold': 'usbgpu'} if hold else {}))
        failures = 0
        if (pending := _pending_usbgpu_diagnostic()) is not None:
          # One USB-level dump per queued eGPU diagnostic: modeld's tmux capture
          # carries none of it (see usb_claim).
          capture_context(pending, extra={'link': 'jetlink idle'})
        time.sleep(1)
        continue
      if transport is None and claimed_by_usbgpu(_first_udc()):
        # A USB-eGPU is on this controller (they share a600000.ssusb / a600000.dwc3):
        # binding the gadget would flip the port to device mode and take the GPU off
        # the bus mid-inference - modeld then burns its whole 30 s HCQ wait and the
        # camera drops hundreds of frames. Idle exactly as when no host is attached,
        # and say why (this branch is reached when typec reports a host while the
        # GPU is on the port, i.e. a hub or a debug cable).
        _note_usb_hold(True)
        publish('waiting', peer=peer, usb_hold='usbgpu')
        time.sleep(2)
        continue
      client = None
      wifi = None
      try:
        publish('connecting', peer=peer)
        # After a re-enumeration the app reloads its QNN engine and rebuilds
        # its USB read ring, and it does not read the link while it does. A
        # message written into that window is abandoned at WRITE_TIMEOUT (15 s)
        # and protocol 3 answers an abandoned write by dropping the gadget,
        # which starts the enumeration over: measured against this app, the
        # reload takes about 40 s, so the first write always lost the race.
        # Wait the host out rather than writing into the dark.
        if failures:
          time.sleep(45)
        gc.collect()
        if transport is None:
          subprocess.run(['sudo', '-n', 'bash', str(setup)], check=True, timeout=15, capture_output=True)
          udc = next(Path('/sys/class/udc').iterdir()).name
          transport = CarrotTransport('/dev/ffs-jetlink', gadget=GADGET, udc=udc)
          greeted = False
          next_seq = 0
        # Preparation budget, not a frame budget. The app's first inference
        # after an engine load is a QNN graph build on the NPU: measured at
        # 37.2 s here, where the 3 s frame budget only ever abandoned the link.
        # Serving restores the strict budget, since only preparation pays this.
        client = JetlinkClient(transport, deadline=300.0, name='carrot-jetlink')
        # The server drops every sequence at or below the high-water mark it
        # keeps for this connection ("dropping replayed message type=3 seq=1"),
        # and a fresh client starts at 0. Continue past the mark, and keep the
        # base monotonic so a rebuilt transport or a restarted daemon cannot
        # fall back under it either: being read as a replay is what made the
        # app discard every retry, time the wait out and reload its engine.
        client.seq = max(next_seq, int(time.monotonic()) & 0xFFFFFFFF)
        publish('connecting', peer=peer, seq=client.seq, src=__file__)
        if not greeted:
          # Hello once per gadget, not once per session. The app rebuilds its
          # USB read ring and reloads its engine on a hello and does not read
          # the link while it does; that window outlasts this end's write
          # budget, and protocol 3 answers a write nobody read by unbinding the
          # gadget - the unplug the app then reports. The server keeps its
          # session, so a later client on the same transport needs no hello.
          peer = client.hello()
          greeted = True
        speed = (Path('/sys/class/udc') / transport.bound_udc / 'current_speed').read_text().strip()
        if speed not in ('super-speed', 'super-speed-plus'):
          raise RuntimeError(f'USB 5Gbps or faster required; negotiated {speed}')
        if peer.get(WIFI_CAPABILITY) is True:
          wifi = WifiPublisher()
          # Provision before ensure_engine: a new host may need Internet to
          # fetch its first model. This is outside every model frame deadline.
          wifi.send(client, initial=True)
        publish('loading', peer=peer, seq=client.seq, src=__file__)
        last_progress = 0.

        def progress(stage, fraction, message):
          nonlocal last_progress
          if time.monotonic() - last_progress >= 1:
            publish('loading', peer=peer, preparation={'stage': stage, 'fraction': fraction, 'message': str(message)[:160]})
            last_progress = time.monotonic()

        # Provisioning is deliberately not gated on offroad. A comma wired into a
        # car powers up straight into onroad and may never see offroad, so the gate
        # left those devices permanently without a model; and it bought nothing.
        # The engine probe only reads, and while the ONNX uploads and the host
        # builds, this link serves no frames at all - the built-in model drives the
        # car meanwhile. host_attached() still tears preparation down with the
        # cable, which is the interruption that actually invalidates it.
        prepare(client, peer, lambda: True, host_attached, progress)
        # The app posts its USB read ring as it opens the device, and a frame
        # written before that ring is up is abandoned at the frame deadline;
        # protocol 3 answers an abandoned write by dropping the gadget, which
        # the phone sees as an unplug. Settle, then prove the host is reading
        # with one small round trip before a 393 KB frame goes into the dark.
        # The outcome is published because jetlinkd's log is not captured.
        time.sleep(2)
        ping = None
        for attempt in range(4):
          try:
            ping = client.ping(timeout=2.0)
            break
          except Exception as exc:
            publish('loading', peer=peer, preparation={'stage': 'ping',
                    'message': f'attempt {attempt + 1} failed: {str(exc)[:90]}'})
            time.sleep(1)
        if ping is None:
          raise RuntimeError('host stopped reading USB after its engine came up')
        publish('loading', peer=peer, preparation={'stage': 'ping', 'message': f'ok {ping * 1000:.1f} ms'})
        # One warm frame, not ten: warming is independent of camera/modeld and
        # every real session resets state, but a host that is not reading yet
        # turns each attempt into a write timeout, and protocol 3 drops the
        # gadget - a cable unplug on the phone's side - on the first one.
        for frame in range(1):
          client.infer(np.zeros(SPEC.warped_shape, np.uint8), np.zeros(SPEC.packed_nelem, np.float32), frame, reset=True)
        # Serving keeps the real frame budget: a slow frame is a dropped camera
        # frame, and modeld tolerates it exactly as it does on a chestnut.
        client.deadline = 3.0
        log.info('Jetlink ready: %s', peer)
        serve_local(listener, client, peer, wifi)
        failures = 0
      except PreparationDeferred as exc:
        log.info('%s', exc)
        publish('loading', peer=peer, preparation={'stage': 'waiting', 'message': str(exc)})
      except Exception as exc:
        log.exception('Jetlink connection failed')
        publish('retrying', peer=peer, error=str(exc)[:300], seq=client.seq if client else None, src=__file__)
        failures += 1
        if 'hello' in str(exc).lower():
          # The server has no session for us any more (it restarted, or the
          # link reopened): introduce ourselves again on the next attempt.
          greeted = False
        if transport is not None and transport_needs_rebuild(exc):
          close_transport(transport)
          transport = None
          greeted = False
          failures = 0
        elif transport is not None:
          # An abandoned write leaves the gadget off the bus. The host is still
          # attached, so put it straight back instead of waiting for a session
          # that would rebuild the endpoints and make the app start over.
          if not rebind_transport(transport):
            # Could not put it back (a USB-eGPU owns the controller, or the UDC
            # write failed): back off like any other failure instead of retrying
            # every 2 s against a port this process does not own right now.
            failures += 1
      finally:
        if wifi is not None:
          wifi.close()
        if client is not None and client.last_state is not None and 'carrot_hud_connected' in client.last_state:
          from openpilot.common.params import Params
          Params().put_bool_nonblocking('ClusterHudConnected', False)
        if client is not None:
          # Continue this transport's sequence numbering across sessions: the
          # server reads anything at or below its high-water mark as a replay.
          next_seq = client.seq
        # The client is dropped, never closed: closing it unbinds the gadget and
        # takes the link off the bus, and an Android host pays a re-enumeration
        # plus a fresh open for that. The transport outlives every session.
      # A host that is not answering yet (an app still building its engine, or
      # one that just re-opened the device) must not be hammered with hellos:
      # every hello restarts the server's session. Back off instead.
      time.sleep(2 if failures == 0 else 15)
  finally:
    listener.close()
    Path(SOCKET).unlink(missing_ok=True)
    publish('stopped')


if __name__ == '__main__':
  main()
