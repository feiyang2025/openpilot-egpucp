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
  """Auto-derive output slices from the final Concat of a full driving model.

  Handles both legacy (18452, hidden_state 16384) and point-policy (2580,
  hidden_state 512) architectures. Segment order is inferred from the Concat
  node feeding 'outputs', with shapes from shape inference (Mul/scale outputs
  included: pose/plan/lead/action come through Mul nodes, not Gemm).
  """
  import onnx
  from onnx import shape_inference
  m = onnx.load(str(onnx_path), load_external_data=False)
  mi = shape_inference.infer_shapes(m)
  g = mi.graph

  concat_node = None
  for n in g.node:
    if n.op_type == "Concat" and "outputs" in n.output:
      concat_node = n
      break
  if concat_node is None:
    raise ValueError(f"no final Concat in {onnx_path}")

  vi = {}
  for v in g.value_info:
    vi[v.name] = v

  segs = []
  offset = 0
  for inp in concat_node.input:
    if inp not in vi:
      continue
    dims = [d.dim_value if d.HasField("dim_value") else 0 for d in vi[inp].type.tensor_type.shape.dim]
    if len(dims) != 2:
      continue
    n = int(dims[1])
    segs.append((inp, offset, offset + n))
    offset += n

  # sanity: total must equal the model output width (allow pad tail)
  if offset > output_count:
    raise ValueError(f"concat width {offset} exceeds output {output_count}")
  if offset + 2 < output_count:
    raise ValueError(f"concat width {offset} far below output {output_count}")

  # semantic names by known segment order (both architectures share this)
  names = [
    "lane_lines", "lane_lines_prob", "road_edges", "meta", "desire_pred",
    "pose", "wide_from_device_euler", "road_transform",
    "plan", "lead", "lead_prob", "desire_state", "action",
    "hidden_state",
  ]
  if len(segs) != len(names):
    # BRH has only 13 segments (no separate pad); drop names accordingly
    names = names[:len(segs)]
  slices = {}
  for (name, seg) in zip(names, segs):
    _, s, e = seg
    slices[name] = [s, e]
  return slices


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
  sig = {}
  for k, v in input_shapes.items():
    sig[k] = tuple(v)

  # determine output width from the onnx graph output
  import onnx
  m = onnx.load(str(args.onnx), load_external_data=False)
  out_count = 0
  for o in m.graph.output:
    dims = [d.dim_value if d.HasField("dim_value") else 0 for d in o.type.tensor_type.shape.dim]
    if dims:
      out_count = int(dims[-1])
  if out_count == 0:
    out_count = 18452
  slices = onnx_output_slices(args.onnx, out_count)
  print(f"output width: {out_count}, slices: {len(slices)}")

  shell = {
    "metadata": {
      "model_checkpoint": args.model_id,
      "input_shapes": sig,
      "output_shapes": {"outputs": (1, out_count)},
      "output_slices": {k: slice(*v) for k, v in slices.items()},
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

  # register in the model_catalog index so the web UI (models.html) lists it
  from openpilot.selfdrive.modeld.big_model import BigModelManifest
  from openpilot.selfdrive.modeld.model_catalog import register as catalog_register
  m = BigModelManifest.from_dict({
    "model_id": args.model_id, "filename": "big_driving_supercombo.onnx",
    "size": args.size, "sha256": args.sha256, "url": args.url,
  }, args.url)
  catalog_register(m, selected=True)
  print(f"models.json registered -> {args.model_id}")
  print("next: Params().remove('UsbGpuStartupFailed'); pkill -f '[s]elfdrive.modeld.modeld'")


if __name__ == "__main__":
  main()
