"""Which pinned engine the comma hands the host, and where it comes from.

A model here *is* its SPEC. The sha256 inside the SPEC names the cache file on
both sides, the host builds its engine for it, and link.py validates every reply
against it - so switching models re-downloads the ONNX and re-builds the host
engine. There is nothing cheaper to switch, and this module is the single place
that decides which SPEC the rest of the jetlink code loads.

The built-in list holds the checkpoint this branch ships. A server-side catalog
(CATALOG_PATH, next to MODEL_BASE) can add more, the same way the eGPU picker
does in selfdrive/modeld/model_source.py; the picked sha256 is remembered in
INDEX so every process reads the same choice.

This module must not import link.py or mac.py: both import it, at module level,
before they can do anything.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import urllib.request

SPEC_DIR = Path(__file__).resolve().parent
BUILTIN_SPEC = 'cinque_v2.json'
DEFAULT_LABEL = 'Cinque v2'

# Where the ONNX handed to the host is kept, keyed by SPEC.sha256. LEGACY_CACHE
# holds the copy from when only the Mac app could be provisioned.
CACHE = Path('/data/models/carrot-jetlink-host')
LEGACY_CACHE = Path('/data/models/carrot-jetlink-mac')
# The choice itself. Deliberately next to the models rather than in the Params
# database, so a device with no manager running still resolves it.
INDEX = Path('/data/models/carrot-jetlink/index.json')

# The eGPU picker's own catalog, not a second one of ours: it already lists every
# checkpoint the device can fetch, and its parser reads only the five fields it
# knows, so a jetlink SPEC rides along in the same entry. One file on the server,
# two consumers.
CATALOG_PATH = 'models/catalog.json'
REMOTE_TIMEOUT = 6.0

# The eGPU picker keeps big models in its own cache and decides a model is
# downloaded purely from the file name it finds there
# (big_driving_supercombo-<sha16>.onnx). So the same checkpoint is written there,
# under that name, whichever picker asked for it first: one download, one copy on
# disk. A file jetlink did not write is only ever read - remove() leaves it alone.
SHARED_CACHE_FALLBACK = Path('/data/media/0/carrot/models')

# sha256s the eGPU catalog lists, filled by remote_catalog(). Tells
# download_target whether the eGPU page will recognise a downloaded file.
_EGPU_SHAS: set[str] = set()

# Resolved on first use; see selected_entry().
_RESOLVED: dict | None = None


def _builtin_url(sha256: str) -> str:
  # The layout the pinned Cinque v2 has always been published under. Kept as a
  # function so a catalog entry can override it per model.
  return ('https://upload.shind0.synology.me/models/carrot-jetlink-cinque-v2/'
          'big_driving_supercombo.onnx')


def _read_json(path: Path):
  try:
    return json.loads(path.read_text())
  except (OSError, ValueError):
    return None


def _builtin_spec() -> dict:
  spec = _read_json(SPEC_DIR / BUILTIN_SPEC)
  return spec if isinstance(spec, dict) else {}


def _builtin() -> list[dict]:
  """The checkpoint this branch ships, described from its own SPEC."""
  spec = _builtin_spec()
  sha = spec.get('sha256')
  if not isinstance(sha, str) or len(sha) != 64:
    return []
  return [{'sha256': sha, 'label': DEFAULT_LABEL, 'spec_file': BUILTIN_SPEC,
           'spec': spec, 'url': _builtin_url(sha), 'nbytes': spec.get('nbytes'),
           'builtin': True}]


def _base_url() -> str | None:
  """MODEL_BASE, imported lazily: it lives with the eGPU model plumbing."""
  try:
    from openpilot.selfdrive.modeld.model_source import MODEL_BASE
  except Exception:
    return None
  return MODEL_BASE or None


def remote_catalog() -> list[dict] | None:
  """The eGPU catalog, narrowed to the models jetlink can actually drive.

  It is the same file the eGPU picker reads (<MODEL_BASE>/models/catalog.json), so
  the server keeps one list for both. An entry is usable here only when it carries
  a SPEC whose sha256 matches: the eGPU simply ignores that field, but a model
  without a contract could never be agreed on with the host. Every listed sha256 is
  remembered, usable or not, so download_target can tell which files the eGPU page
  will recognise.
  """
  global _EGPU_SHAS
  base = _base_url()
  if not base:
    return None
  url = base if base.endswith('/') else base + '/'
  url = url + CATALOG_PATH
  try:
    request = urllib.request.Request(url, headers={'User-Agent': 'carrot-jetlink/1'})
    with urllib.request.urlopen(request, timeout=REMOTE_TIMEOUT) as response:
      if response.status != 200:
        return None
      value = json.loads(response.read().decode('utf-8'))
  except Exception:
    return None
  if not isinstance(value, dict):
    return None
  entries = value.get('models')
  if not isinstance(entries, list):
    return None
  listed: set[str] = set()
  result: list[dict] = []
  for entry in entries:
    if not isinstance(entry, dict):
      continue
    sha = entry.get('sha256')
    if not isinstance(sha, str) or len(sha) != 64:
      continue
    listed.add(sha)
    spec = entry.get('spec')
    spec_file = entry.get('spec_file')
    if not isinstance(spec, dict) and isinstance(spec_file, str):
      spec = _read_json(SPEC_DIR / Path(spec_file).name)
    if not isinstance(spec, dict) or spec.get('sha256') != sha:
      # Without a matching contract the host could never agree with us.
      continue
    result.append({'sha256': sha, 'label': entry.get('label') or sha[:12],
                   'spec': spec, 'spec_file': spec_file if isinstance(spec_file, str) else None,
                   'url': entry.get('url'), 'filename': entry.get('filename'),
                   'nbytes': entry.get('nbytes') or entry.get('size') or spec.get('nbytes'),
                   'builtin': False})
  _EGPU_SHAS = listed
  return result


def read_index() -> dict:
  value = _read_json(INDEX)
  return value if isinstance(value, dict) else {}


def _write_json(path: Path, value) -> bool:
  """Atomic write: a half-written SPEC or index reads back as garbage."""
  temporary = path.with_suffix('.tmp')
  try:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(json.dumps(value, indent=2))
    os.replace(temporary, path)
  except OSError:
    try:
      temporary.unlink(missing_ok=True)
    except OSError:
      pass
    return False
  return True


def write_index(selected: str | None, entry: dict | None = None) -> bool:
  """Record the choice, and enough about it to survive an unreachable catalog.

  The label and URL travel with the sha256: this device may boot somewhere the
  catalog cannot be reached, and it still has to be able to name the model it is
  running and fetch it if the cache is gone.
  """
  value: dict = {'selected': selected}
  if isinstance(entry, dict):
    for key in ('label', 'url', 'nbytes'):
      if entry.get(key) is not None:
        value[key] = entry[key]
  return _write_json(INDEX, value)


def entries(refresh: bool = True) -> list[dict]:
  """Built-in models first, then anything the catalog adds."""
  result = _builtin()
  known = {item['sha256'] for item in result}
  if refresh:
    for item in remote_catalog() or []:
      if item['sha256'] not in known:
        result.append(item)
        known.add(item['sha256'])
  return result


def entry_for(sha256: str | None, refresh: bool = True) -> dict | None:
  for item in entries(refresh):
    if item['sha256'] == sha256:
      return item
  return None


def selected_entry(refresh: bool = True) -> dict:
  """The model in use, resolved once per process.

  Switching models needs a reboot - the host has to rebuild its engine for the
  new sha256 - so a process that is already running never has to notice a
  change. Resolve on first use and keep it: daemon.publish() runs every second
  and must not touch the index each time.

  Falls back to the built-in model, never returns None.
  """
  global _RESOLVED
  if _RESOLVED is None:
    _RESOLVED = _resolve_selected(refresh)
  return _RESOLVED


def _resolve_selected(refresh: bool) -> dict:
  builtin = _builtin()
  fallback = builtin[0] if builtin else None
  index = read_index()
  sha = index.get('selected')
  if not isinstance(sha, str) or len(sha) != 64:
    return fallback or {}
  found = entry_for(sha, refresh)
  if found is not None:
    return found
  # Nothing describes this sha right now - the catalog is unreachable, or the
  # entry was withdrawn - but the device was switched to it, and must not
  # silently become a different model. Rebuild the entry from the index and the
  # SPEC on disk; if even that is gone, falling back is the only honest option.
  materialised = spec_dir() / f'{sha}.json'
  if materialised.is_file():
    return {'sha256': sha, 'label': index.get('label') or sha[:12],
            'spec_file': materialised.name, 'spec': _read_json(materialised),
            'url': index.get('url'), 'nbytes': index.get('nbytes'), 'builtin': False}
  return fallback or {}


def selected_sha(refresh: bool = True) -> str | None:
  return selected_entry(refresh).get('sha256')


def label(refresh: bool = True) -> str:
  """What the UI and the logs call the current model."""
  entry = selected_entry(refresh)
  return entry.get('label') or DEFAULT_LABEL


def spec_dir() -> Path:
  """Where a SPEC the device was switched to is kept (next to the index).

  link.py reads the SPEC at import time, so a catalog entry that carries its
  contract inline has to exist as a file before the next boot can use it. Keeping
  those copies beside the index also means an unreachable catalog cannot strand a
  device on the wrong contract.
  """
  return INDEX.parent


def _materialise(entry: dict) -> Path | None:
  """Make sure this entry's SPEC exists on disk; return its path, or None."""
  sha = entry.get('sha256')
  if isinstance(sha, str) and len(sha) == 64:
    materialised = spec_dir() / f'{sha}.json'
    if materialised.is_file():
      return materialised
  name = entry.get('spec_file')
  if isinstance(name, str):
    candidate = SPEC_DIR / Path(name).name
    if candidate.is_file():
      return candidate
  spec = entry.get('spec')
  if isinstance(spec, dict) and isinstance(sha, str) and spec.get('sha256') == sha:
    path = spec_dir() / f'{sha}.json'
    if _write_json(path, spec):
      return path
  return None


def spec_path(refresh: bool = True) -> Path:
  """Path of the SPEC the jetlink code must load.

  Always returns an existing file: a selection whose SPEC cannot be found would
  otherwise leave the device describing a different contract than the one the
  host validated.
  """
  sha = read_index().get('selected')
  if isinstance(sha, str) and len(sha) == 64:
    materialised = spec_dir() / f'{sha}.json'
    if materialised.is_file():
      return materialised
  path = _materialise(selected_entry(refresh))
  return path if path is not None else SPEC_DIR / BUILTIN_SPEC


def model_url(refresh: bool = True) -> str:
  entry = selected_entry(refresh)
  url = entry.get('url')
  return url if isinstance(url, str) and url else _builtin_url(entry.get('sha256') or '')


def model_nbytes(refresh: bool = True) -> int | None:
  entry = selected_entry(refresh)
  size = entry.get('nbytes')
  return size if isinstance(size, int) and size > 0 else None


def _shared_cache() -> Path:
  """Where the eGPU picker keeps its models; imported lazily (heavy module)."""
  try:
    from openpilot.selfdrive.modeld.big_model import model_cache_dir
    return Path(model_cache_dir())
  except Exception:
    return SHARED_CACHE_FALLBACK


def owned_paths(sha256: str) -> list[Path]:
  """Copies this module may create, and may therefore delete."""
  return [root / f'{sha256}.onnx' for root in (CACHE, LEGACY_CACHE)]


def shared_paths(sha256: str) -> list[Path]:
  """Copies the eGPU picker happens to hold. Read-only: not ours to delete."""
  try:
    return [path for path in _shared_cache().glob(f'*-{sha256[:16]}.onnx') if path.is_file()]
  except OSError:
    return []


def download_target(entry: dict, cache: Path = CACHE) -> Path:
  """Where a fresh download of this entry lands.

  A checkpoint the eGPU catalog also lists is written into the eGPU cache, under
  the name its page looks for, so the device fetches it once and neither picker
  then offers a download that is already on disk. A model only jetlink knows stays
  in our own cache, instead of putting a file in that directory which the eGPU
  page would never list.
  """
  sha = entry.get('sha256') or ''
  name = entry.get('filename') or 'big_driving_supercombo.onnx'
  if sha in _EGPU_SHAS and name.endswith('.onnx'):
    stem, suffix = os.path.splitext(Path(name).name)
    return _shared_cache() / f'{stem}-{sha[:16]}{suffix}'
  return cache / f'{sha}.onnx'


def cached_paths(sha256: str | None = None, refresh: bool = True) -> list[Path]:
  """Every place this model may already be: ours first, then the shared cache."""
  sha = sha256 or selected_sha(refresh)
  if not isinstance(sha, str):
    return []
  return owned_paths(sha) + shared_paths(sha)


def downloaded(sha256: str | None = None, refresh: bool = True) -> bool:
  return any(path.is_file() for path in cached_paths(sha256, refresh))


def shared_only(sha256: str | None = None, refresh: bool = True) -> bool:
  """True when the model is here only because the eGPU cache holds it."""
  sha = sha256 or selected_sha(refresh)
  if not isinstance(sha, str):
    return False
  return not any(path.is_file() for path in owned_paths(sha)) and bool(shared_paths(sha))


def select(sha256: str) -> bool:
  entry = entry_for(sha256)
  if entry is None:
    return False
  # Write the contract and the entry down now: the next boot reads them from
  # disk, and by then the catalog may well be unreachable.
  _materialise(entry)
  return write_index(sha256, entry)


def remove(sha256: str) -> bool:
  """Drop our own cached ONNX; a shared eGPU copy is left where it is.

  Refuses the model in use, whose SPEC names the file this would delete.
  """
  if sha256 == selected_sha():
    return False
  removed = False
  for path in owned_paths(sha256):
    try:
      path.unlink()
      removed = True
    except OSError:
      pass
  return removed


def free_bytes() -> int:
  try:
    return shutil.disk_usage(CACHE.parent if not CACHE.exists() else CACHE).free
  except OSError:
    return 0
