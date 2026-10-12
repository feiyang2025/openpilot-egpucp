#!/usr/bin/env python3
"""Pre-build the XIAOGE TensorRT engines (recommended at deploy time).

The XIAOGE VASM/lane models run far faster on the Orin GPU via TensorRT than on
OpenCV's CPU DNN backend, but the first engine build can take minutes. Run this
once after deploy (or in the image build) so on-vehicle startup just deserializes
the cached plans instead of building them.

    python tools/build_xiaoge_engines.py
"""
from __future__ import annotations

from pathlib import Path

from openpilot.selfdrive.carrot.xiaoge.trt_onnx_runner import TrtOnnxRunner

ASSETS = Path(__file__).resolve().parents[1] / "selfdrive" / "carrot" / "xiaoge" / "assets"
MODELS = ("v_asm_model.onnx", "lane.onnx")


def main() -> None:
  for name in MODELS:
    model = ASSETS / name
    if not model.is_file():
      print(f"skip {name}: not found")
      continue
    if TrtOnnxRunner.cached_plan_path(model) is not None:
      print(f"cached {name}")
      continue
    print(f"building {name} ...")
    runner = TrtOnnxRunner(model)
    print(f"built {name}: {runner.input_names} -> {runner.output_names}")


if __name__ == "__main__":
  main()
