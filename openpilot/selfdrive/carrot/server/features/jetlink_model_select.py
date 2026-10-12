"""Web API: list and switch the engine the comma hands the jetlink host.

Companion to features/egpu_model_select.py, which manages the big models that
run *on* the device. This one manages the pinned engine jetlink pushes over USB
into whichever host is attached (phone app, Jetson, Mac), so the plumbing
differs where the models do:

  - A jetlink model IS its SPEC. The sha256 inside it names the cache file on
    both ends and the host builds its engine for it, so switching re-downloads
    the ONNX (766 MB) and rebuilds on the host. That is offroad-only, and then
    the device has to reboot for the new SPEC to be loaded.
  - The choice lives in models.INDEX, which every jetlink process reads once at
    startup (models.selected_entry does the caching for exactly that reason).
  - Nothing here runs or stops a download: the daemon fetches the ONNX itself
    the first time a host answers need_upload, using the selected model's URL.

Routes:
  GET  /api/jetlink/models         list (built-in + remote catalog + cache state)
  POST /api/jetlink/models/select  choose one; optional reboot to activate
  POST /api/jetlink/models/remove  delete a downloaded ONNX from disk
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aiohttp import web

from openpilot.common.jetlink_status import LINK_STATUS
from openpilot.selfdrive.modeld.jetlink import models

from ..services.params import HAS_PARAMS, Params


def _status() -> dict[str, Any]:
  """The daemon's own view: which sha256 it loaded, and the live link state."""
  try:
    value = json.loads(Path(LINK_STATUS).read_text())
  except (OSError, ValueError):
    return {}
  return value if isinstance(value, dict) else {}


def _running_sha() -> str | None:
  sha = _status().get('sha256')
  return sha if isinstance(sha, str) and len(sha) == 64 else None


def _entries() -> tuple[list[dict], bool]:
  """Built-in models first, then whatever the server catalog adds."""
  result = models.entries(refresh=False)
  known = {item['sha256'] for item in result}
  remote = models.remote_catalog()
  for item in remote or []:
    if item['sha256'] not in known:
      result.append(item)
      known.add(item['sha256'])
  return result, remote is not None


def build_payload() -> dict[str, Any]:
  selected = models.selected_sha()
  running = _running_sha()
  items, remote_ok = _entries()

  models_payload: list[dict[str, Any]] = []
  for item in items:
    sha = item['sha256']
    spec = item.get('spec') or {}
    models_payload.append({
      'sha256': sha,
      'label': item.get('label') or sha[:12],
      'size': item.get('nbytes') or spec.get('nbytes'),
      'url': item.get('url'),
      'spec_file': item.get('spec_file'),
      'builtin': bool(item.get('builtin')),
      'frame_skip': spec.get('frame_skip'),
      'downloaded': models.downloaded(sha, refresh=False),
      # Present, but only because the eGPU cache holds the same file. Worth
      # saying out loud: there is nothing here for the user to delete.
      'shared': models.shared_only(sha, refresh=False),
      'selected': sha == selected,
      # What the running daemon actually loaded, which differs from `selected`
      # until the reboot that a switch needs.
      'running': sha == running,
    })

  return {
    'ok': True,
    'selected': selected,
    'running': running,
    'remote_catalog': remote_ok,
    'index': str(models.INDEX),
    'cache_dir': str(models.CACHE),
    'free_bytes': models.free_bytes(),
    'link': _status().get('state'),
    'models': models_payload,
  }


async def api_models(_request: web.Request) -> web.Response:
  return web.json_response(build_payload())


async def api_select(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    return web.json_response({'ok': False, 'error': 'invalid JSON body'}, status=400)
  if not isinstance(body, dict):
    return web.json_response({'ok': False, 'error': 'invalid body'}, status=400)

  sha = body.get('sha256')
  if not isinstance(sha, str) or len(sha) != 64:
    return web.json_response({'ok': False, 'error': 'sha256 required'}, status=400)
  if models.entry_for(sha, refresh=False) is None and models.entry_for(sha) is None:
    return web.json_response({'ok': False, 'error': 'unknown model'}, status=404)
  if not models.select(sha):
    return web.json_response({'ok': False, 'error': 'could not write the selection'}, status=500)

  reboot = bool(body.get('reboot'))
  if reboot and HAS_PARAMS and Params is not None:
    try:
      Params().put_bool('DoReboot', True)
    except Exception:
      reboot = False
  return web.json_response({'ok': True, 'selected': sha, 'reboot_requested': reboot,
                            'offroad_required': True})


async def api_remove(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    return web.json_response({'ok': False, 'error': 'invalid JSON body'}, status=400)
  sha = (body or {}).get('sha256') if isinstance(body, dict) else None
  if not isinstance(sha, str) or len(sha) != 64:
    return web.json_response({'ok': False, 'error': 'sha256 required'}, status=400)

  if HAS_PARAMS and Params is not None:
    try:
      if Params().get_bool('IsEngaged'):
        return web.json_response({'ok': False, 'error': 'disengage openpilot before removing a model'},
                                 status=409)
    except Exception:
      pass
  if sha == models.selected_sha():
    return web.json_response({'ok': False, 'error': 'cannot remove the model currently selected'},
                             status=409)
  if not models.remove(sha):
    return web.json_response({'ok': False, 'error': 'nothing to remove'}, status=404)
  return web.json_response({'ok': True, 'removed': sha})


def register(app: web.Application) -> None:
  app.router.add_get('/api/jetlink/models', api_models)
  app.router.add_post('/api/jetlink/models/select', api_select)
  app.router.add_post('/api/jetlink/models/remove', api_remove)
