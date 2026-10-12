#!/usr/bin/env python3
"""TensorRT execution for the STATEFUL (cinque-v3) driving policy.
Inputs: new_img, desire, traffic_convention, action_t, state_img_q, state_desire_q, state_feat_q
Outputs: outputs, next_state_img_q, next_state_desire_q, next_state_feat_q
next_state outputs feed back into the state inputs each frame (zero-copy via
separate device buffers + copy, since TRT needs stable binding addresses)."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

import numpy as np


class StatefulTensorRTPolicyRunner:
  INPUT_NAMES = ("new_img", "desire", "traffic_convention", "action_t",
                 "state_img_q", "state_desire_q", "state_feat_q")
  OUTPUT_NAMES = ("outputs", "next_state_img_q", "next_state_desire_q", "next_state_feat_q")
  STATE_PAIRS = {"next_state_img_q": "state_img_q",
                 "next_state_desire_q": "state_desire_q",
                 "next_state_feat_q": "state_feat_q"}

  def __init__(self, engine_path: str | Path, input_shapes: Mapping[str, tuple[int, ...]]):
    import sys
    for _p in ("/usr/lib/python3.12/dist-packages", "/home/nvidia/.local/lib/python3.12/site-packages",
               "/usr/lib/python3/dist-packages"):
      if _p not in sys.path:
        sys.path.insert(0, _p)
    import tensorrt as trt
    import torch

    self.torch = torch
    self.trt = trt
    self.input_shapes = {k: tuple(v) for k, v in input_shapes.items()}

    logger = trt.Logger(trt.Logger.WARNING)
    runtime = trt.Runtime(logger)
    engine = runtime.deserialize_cuda_engine(Path(engine_path).read_bytes())
    if engine is None:
      raise RuntimeError(f"failed to deserialize TensorRT engine: {engine_path}")
    context = engine.create_execution_context()
    if context is None:
      raise RuntimeError("failed to create TensorRT execution context")

    self._logger = logger
    self._runtime = runtime
    self.engine = engine
    self.context = context
    self.stream = torch.cuda.Stream()

    # All TRT bindings are float32 (ONNX was converted: uint8 img inputs -> float)
    self.bindings = {}
    for name in self.INPUT_NAMES:
      shape = self.input_shapes[name]
      self.bindings[name] = torch.empty(shape, dtype=torch.float32, device="cuda")
    # outputs
    self.outputs = {}
    for name in self.OUTPUT_NAMES:
      if name == "outputs":
        shape = (1, 18452)
      else:
        shape = self.input_shapes[self.STATE_PAIRS[name]] if name in self.STATE_PAIRS else (1, 18452)
      self.outputs[name] = torch.empty(shape, dtype=torch.float32, device="cuda")

    for name, tensor in self.bindings.items():
      expected = tuple(context.get_tensor_shape(name))
      if expected != tuple(tensor.shape):
        raise RuntimeError(f"TRT shape mismatch {name}: engine={expected} runner={tuple(tensor.shape)}")
      if not context.set_tensor_address(name, tensor.data_ptr()):
        raise RuntimeError(f"failed to bind input {name}")
    for name, tensor in self.outputs.items():
      expected = tuple(context.get_tensor_shape(name))
      if expected != tuple(tensor.shape):
        raise RuntimeError(f"TRT output shape mismatch {name}: engine={expected} runner={tuple(tensor.shape)}")
      if not context.set_tensor_address(name, tensor.data_ptr()):
        raise RuntimeError(f"failed to bind output {name}")

  def run(self, new_img: np.ndarray, desire: np.ndarray, traffic_convention: np.ndarray,
          action_t: np.ndarray, state_img_q: np.ndarray, state_desire_q: np.ndarray,
          state_feat_q: np.ndarray) -> np.ndarray:
    torch = self.torch
    with torch.cuda.stream(self.stream), torch.inference_mode():
      self.bindings["new_img"].copy_(torch.as_tensor(new_img, dtype=torch.float32, device="cuda"))
      self.bindings["desire"].copy_(torch.as_tensor(desire, dtype=torch.float32, device="cuda").reshape(-1))
      self.bindings["traffic_convention"].copy_(torch.as_tensor(traffic_convention, dtype=torch.float32, device="cuda").reshape(-1))
      self.bindings["action_t"].copy_(torch.as_tensor(action_t, dtype=torch.float32, device="cuda").reshape(-1))
      self.bindings["state_img_q"].copy_(torch.as_tensor(state_img_q, dtype=torch.float32, device="cuda"))
      self.bindings["state_desire_q"].copy_(torch.as_tensor(state_desire_q, dtype=torch.float32, device="cuda"))
      self.bindings["state_feat_q"].copy_(torch.as_tensor(state_feat_q, dtype=torch.float32, device="cuda"))

      if not self.context.execute_async_v3(self.stream.cuda_stream):
        raise RuntimeError("TensorRT execute_async_v3 failed")
      self.stream.synchronize()

      result = self.outputs["outputs"].cpu().numpy().astype(np.float32, copy=False)
      # feedback: next_state -> state inputs (values read on CPU, fed back next frame)
      self._state_img = self.outputs["next_state_img_q"].cpu().numpy()
      self._state_desire = self.outputs["next_state_desire_q"].cpu().numpy()
      self._state_feat = self.outputs["next_state_feat_q"].cpu().numpy()
    return result[0]

  @property
  def state_img(self) -> np.ndarray:
    return getattr(self, "_state_img", None)

  @property
  def state_desire(self) -> np.ndarray:
    return getattr(self, "_state_desire", None)

  @property
  def state_feat(self) -> np.ndarray:
    return getattr(self, "_state_feat", None)
