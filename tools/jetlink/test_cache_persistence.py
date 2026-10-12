from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'third_party/jetlink'))
# Jetlink 0.7.2 moved the server to Swift and deleted the Python package this
# exercised. Kept for the record until the Jetson host side is migrated.
pytest.importorskip('jetlink.server', reason='jetlink 0.7.2 has no Python server')
from jetlink.server import cache


def test_unchanged_preload_does_not_write(tmp_path, monkeypatch):
  engine = cache.EngineCache(tmp_path, SimpleNamespace(name='synthetic'))
  engine.remember_loaded('a' * 64, 2)
  def fail(*args, **kwargs):
    raise AssertionError('unchanged preload wrote storage')
  monkeypatch.setattr(cache.tempfile, 'NamedTemporaryFile', fail)
  engine.remember_loaded('a' * 64, 2)
  assert engine.last_loaded() == ('a' * 64, 2)


def test_interrupted_metadata_replacement_preserves_previous_preload(tmp_path, monkeypatch):
  engine = cache.EngineCache(tmp_path, SimpleNamespace(name='synthetic'))
  engine.remember_loaded('a' * 64, 2)
  def fail(*args):
    raise OSError('simulated power cut before rename')
  monkeypatch.setattr(cache.os, 'replace', fail)
  engine.remember_loaded('b' * 64, 3)
  assert engine.last_loaded() == ('a' * 64, 2)
  assert not list(tmp_path.glob('.last-loaded-*'))
