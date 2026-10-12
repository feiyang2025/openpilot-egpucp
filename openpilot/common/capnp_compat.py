"""Work around pycapnp truncating non-ASCII schema import paths.

pycapnp builds the capnp import-path array with
``StringPtr(import_path, len(import_path))``. ``len()`` on a ``str`` counts
characters, but ``StringPtr`` holds the UTF-8 bytes, so any non-ASCII byte in a
schema search path truncates the path and the schema import aborts the process
with ``Import failed: /include/<schema>.capnp``.

Wrapping the path in a ``str`` subclass whose ``__len__`` returns the UTF-8 byte
count keeps the full string intact. ASCII paths are returned unchanged so the
common case stays allocation-free.
"""


class _Utf8Path(str):
  __slots__ = ()

  def __len__(self) -> int:
    return len(str.encode(self))


def capnp_path(path) -> str:
  """Return *path* as a string pycapnp can pass to capnp intact."""
  path = str(path)
  return path if path.isascii() else _Utf8Path(path)


def capnp_import_paths(*paths) -> list[str]:
  """Return schema search paths safe to pass as ``SchemaParser.load(imports=...)``."""
  return [capnp_path(p) for p in paths]