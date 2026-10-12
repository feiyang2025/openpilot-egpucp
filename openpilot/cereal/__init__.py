import os
import capnp
from importlib.resources import as_file, files
from pathlib import Path

from openpilot.common.capnp_compat import capnp_import_paths

capnp.remove_import_hook()

with as_file(files("openpilot.cereal")) as fspath:
  CEREAL_PATH = fspath.as_posix()
  REPO_ROOT = Path(CEREAL_PATH).parents[1]
  opendbc_import_path = REPO_ROOT / "opendbc_repo" / "opendbc" / "car"
  if not (opendbc_import_path / "car.capnp").exists():
    with as_file(files("opendbc")) as opendbc_path:
      opendbc_import_path = Path(opendbc_path.as_posix()).resolve() / "car"

  # pycapnp passes import paths as UTF-8 bytes but measures them by character
  # count, truncating any non-ASCII path (e.g. a tree under 公共/) and aborting
  # with "Import failed: /include/c++.capnp". capnp_import_paths() wraps those.
  imports = capnp_import_paths(
    CEREAL_PATH,
    os.path.join(CEREAL_PATH, "include"),
    opendbc_import_path.as_posix(),
    (opendbc_import_path / "include").as_posix(),
  )
  parser = capnp.SchemaParser()
  car = parser.load((opendbc_import_path / "car.capnp").as_posix(), "/car.capnp", imports=imports)
  log = parser.load(os.path.join(CEREAL_PATH, "log.capnp"), "/log.capnp", imports=imports)
  custom = parser.load(os.path.join(CEREAL_PATH, "custom.capnp"), "/custom.capnp", imports=imports)
