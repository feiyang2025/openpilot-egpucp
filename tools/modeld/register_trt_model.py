#!/usr/bin/env python3
"""Register a big-driving ONNX + TRT plan for modeld on Local-GPU (CUDA) mode.

Unified path for new big models on this Jetson box:
  onnx -> trtexec plan -> shell pkl (signature + warp) -> state.json active.

The shell pkl reuses the pinned chunked model's warp and run_policy as a
placeholder; with a TRT plan present, modeld executes ONLY the plan
(TensorRTPolicyRunner), so the placeholder is never run.

Usage:
  python3 register_trt_model.py <onnx> <plan> <model_id> <sha256> <size> <url> \
      [--input-shapes-json file.json]

The input-shapes JSON (optional) overrides signature discovery from onnx for
models whose graph inputs need manual mapping (e.g. uint8 img -> float).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import pickle
import shutil
import subprocess
import sys

REPO = Path("/data/openpilot")
MODELS_DIR = REPO / "openpilot" / "selfdrive" / "modeld" / "models"
CACHE_DIR = Path("/home/nvidia/.comma/models")
PINNED = MODELS_DIR / "big_driving_1791d5940b2c048d_tinygrad.pkl"  # warp + run_policy source

sys.path.insert(0, "/usr/lib/python3.12/dist-packages")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "openpilot"))


def load_pinned():
  from openpilot.selfdrive.modeld.helpers import load_oob
  from openpilot.common.file_chunker import open_file_chunked
  return load_oob(open_file_chunked(PINNED))


def onnx_input_shapes(onnx_path: Path) -> dict[str, tuple[int, ...]]:
  import onnx
  m = onnx.load(str(onnx_path), load_external_data=False)
  shapes = {}
  for i in m.graph.input:
    dims = [d.dim_value if d.HasField("dim_value") else 0 for d in i.type.tensor_type.shape.dim]
    shapes[i.name] = tuple(int(d) for d in dims)
  return shapes


def onnx_output_slices(onnx_path: Path, output_count: int) -> dict[str, list[int]]:
  """Best-effort slices for full driving models (18452 outputs); vision-only
  models (2580) cannot drive and are rejected here."""
  if output_count == 18452:
    return {
      "lane_lines": [0, 528], "lane_lines_prob": [528, 536], "road_edges": [536, 800],
      "meta": [800, 855], "desire_pred": [855, 887], "pose": [887, 899],
      "wide_from_device_euler": [899, 905], "road_transform": [905, 917],
      "plan": [917, 1907], "lead": [1907, 2051], "lead_prob": [2051, 2054],
      "desire_state": [2054, 2062], "action": [2062, 2066],
      "hidden_state": [2066, 18450], "pad": [18450, 18452],
    }
  raise ValueError(f"unsupported output size {output_count}: only full driving models (18452) can drive")


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("onnx", type=Path)
  ap.add_argument("plan", type=Path)
  ap.add_argument("model_id")
  ap.add_argument("sha256")
  ap.add_argument("size", type=int)
  ap.add_argument("url")
  ap.add_argument("--input-shapes-json", type=Path)
  args = ap.parse_args()

  sha16 = args.sha256[:16]
  plan16 = MODELS_DIR / f"big_driving_{sha16}.plan"
  if not plan16.is_file():
    shutil.copyfile(args.plan, plan16)
  print(f"plan ready: {plan16}")

  pinned = load_pinned()
  input_shapes = json.loads(args.input_shapes_json.read_text()) if args.input_shapes_json else onnx_input_shapes(args.onnx)
  # modeld expects img/big_img/etc keys; map onnx names (uint8) -> float signature used by TRT runner
  sig = {}
  for k, v in input_shapes.items():
    sig[k] = tuple(v)
  out_count = 18452  # full driving model contract

  shell = {
    "metadata": {
      "model_checkpoint": args.model_id,
      "input_shapes": sig,
      "output_shapes": {"outputs": (1, out_count)},
      "output_slices": {k: slice(*v) for k, v in onnx_output_slices(args.onnx, out_count).items()},
    },
    "run_policy": pinned["run_policy"],
    (1344, 760): pinned[(1344, 760)],
    (1928, 1208): pinned[(1928, 1208)],
  }
  pkl = MODELS_DIR / f"big_driving_{sha16}_tinygrad.pkl"
  with pkl.open("wb") as f:
    pickle.dump(shell, f, protocol=5)
  print(f"shell pkl: {pkl} ({pkl.stat().st_size} bytes)")

  # cache placeholder so active_manifest() passes
  placeholder = CACHE_DIR / f"big_driving_supercombo-{sha16}.onnx"
  if not placeholder.is_file():
    with placeholder.open("wb") as f:
      f.truncate(args.size)
  print(f"cache placeholder: {placeholder}")

  # update state.json (active -> this model, previous -> old active)
  state = json.loads((CACHE_DIR / "state.json").read_text())
  state["previous"] = state["active"]
  state["active"] = {
    "filename": "big_driving_supercombo.onnx",
    "model_id": args.model_id,
    "sha256": args.sha256,
    "size": args.size,
    "url": args.url,
  }
  (CACHE_DIR / "state.json").write_text(json.dumps(state, indent=2) + "\n")
  print(f"state.json active -> {args.model_id}")
  print("next: Params().remove('UsbGpuStartupFailed'); pkill -f '[s]elfdrive.modeld.modeld'")


if __name__ == "__main__":
  main()
