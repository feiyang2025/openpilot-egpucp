import os
import capnp
from opendbc.car.common.basedir import BASEDIR

try:
  from openpilot.cereal import car
except ImportError:
  capnp.remove_import_hook()
  try:
    # pycapnp truncates non-ASCII import paths (see openpilot/common/capnp_compat.py)
    from openpilot.common.capnp_compat import capnp_import_paths
  except ImportError:  # standalone opendbc checkout without the openpilot tree
    def capnp_import_paths(*paths):
      return [str(p) for p in paths]
  car = capnp.load(os.path.join(BASEDIR, "car.capnp"), "/car.capnp",
                   imports=capnp_import_paths(BASEDIR, os.path.join(BASEDIR, "include")))

CarState = car.CarState
RadarData = car.RadarData
CarControl = car.CarControl
CarParams = car.CarParams

CarStateT = capnp.lib.capnp._StructModule
RadarDataT = capnp.lib.capnp._StructModule
CarControlT = capnp.lib.capnp._StructModule
CarParamsT = capnp.lib.capnp._StructModule
