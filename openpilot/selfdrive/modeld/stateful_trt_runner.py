#!/usr/bin/env python3
"""TensorRT execution for the STATEFUL (cinque-v3) driving policy.

ctypes/libcudart port of the stateful TRT runner (the original imported torch,
which is not available on the Jetson JetPack 7 / CUDA 13 image). Keeps the same
public interface so modeld does not need changes:

  inputs : new_img, desire, traffic_convention, action_t,
           state_img_q, state_desire_q, state_feat_q
  outputs: outputs, next_state_img_q, next_state_desire_q, next_state_feat_q

next_state outputs are copied back to host each frame and exposed via
state_img / state_desire / state_feat so the caller can feed them into the next
frame's state inputs.
"""
from __future__ import annotations

import ctypes
from pathlib import Path
from typing import Mapping

import numpy as np

from openpilot.selfdrive.modeld.tensorrt_policy_runner import CudaRuntime

_TRT_TO_NUMPY = {
  "FLOAT": np.float32,
  "HALF": np.float16,
  "INT32": np.int32,
  "INT8": np.int8,
  "BOOL": np.bool_,
}


def _import_tensorrt():
  import importlib
  import sys
  for _p in ("/usr/lib/python3.12/dist-packages", "/home/nvidia/.local/lib/python3.12/site-packages",
             "/usr/lib/python3/dist-packages"):
    if _p not in sys.path:
      sys.path.insert(0, _p)
  return importlib.import_module("tensorrt")


class StatefulTensorRTPolicyRunner:
  INPUT_NAMES = ("new_img", "desire", "traffic_convention", "action_t",
                 "state_img_q", "state_desire_q", "state_feat_q")
  OUTPUT_NAMES = ("outputs", "next_state_img_q", "next_state_desire_q", "next_state_feat_q")
  STATE_PAIRS = {"next_state_img_q": "state_img_q",
                 "next_state_desire_q": "state_desire_q",
                 "next_state_feat_q": "state_feat_q"}

  def __init__(self, engine_path: str | Path, input_shapes: Mapping[str, tuple[int, ...]]):
    trt = _import_tensorrt()
    self.trt = trt
    self.input_shapes = {k: tuple(v) for k, v in input_shapes.items()}
    self.cuda = CudaRuntime()
    self.stream = self.cuda.create_stream()

    runtime = trt.Runtime(trt.Logger(trt.Logger.WARNING))
    engine = runtime.deserialize_cuda_engine(Path(engine_path).read_bytes())
    if engine is None:
      raise RuntimeError(f"failed to deserialize TensorRT engine: {engine_path}")
    context = engine.create_execution_context()
    if context is None:
      raise RuntimeError("failed to create TensorRT execution context")
    self._runtime, self.engine, self.context = runtime, engine, context

    self._host: dict[str, np.ndarray] = {}
    self._dev: dict[str, ctypes.c_void_p] = {}
    self.input_names: list[str] = []
    self.output_names: list[str] = []
    for i in range(engine.num_io_tensors):
      name = engine.get_tensor_name(i)
      shape = tuple(context.get_tensor_shape(name))
      dtype = _TRT_TO_NUMPY[engine.get_tensor_dtype(name).name]
      self._host[name] = np.zeros(shape, dtype=dtype)
      self._dev[name] = self.cuda.malloc(self._host[name].nbytes)
      if not context.set_tensor_address(name, self._dev[name].value):
        raise RuntimeError(f"failed to bind TensorRT tensor {name}")
      (self.input_names if engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT
       else self.output_names).append(name)

    self._state_img: np.ndarray | None = None
    self._state_desire: np.ndarray | None = None
    self._state_feat: np.ndarray | None = None

  def _to(self, name: str, value: np.ndarray) -> None:
    self._host[name][...] = np.asarray(value).reshape(self._host[name].shape)

  def run(self, new_img: np.ndarray, desire: np.ndarray, traffic_convention: np.ndarray,
          action_t: np.ndarray, state_img_q: np.ndarray, state_desire_q: np.ndarray,
          state_feat_q: np.ndarray) -> np.ndarray:
    self._to("new_img", new_img)
    self._to("desire", desire)
    self._to("traffic_convention", traffic_convention)
    self._to("action_t", action_t)
    self._to("state_img_q", state_img_q)
    self._to("state_desire_q", state_desire_q)
    self._to("state_feat_q", state_feat_q)

    for name in self.input_names:
      self.cuda.upload(self._dev[name], self._host[name])
    if not self.context.execute_async_v3(int(self.stream.value or 0)):
      raise RuntimeError("TensorRT execute_async_v3 failed")
    self.cuda.sync(self.stream)
    for name in self.output_names:
      self.cuda.download(self._dev[name], self._host[name])

    self._state_img = self._host["next_state_img_q"].copy()
    self._state_desire = self._host["next_state_desire_q"].copy()
    self._state_feat = self._host["next_state_feat_q"].copy()
    return self._host["outputs"].astype(np.float32, copy=False)[0]

  @property
  def state_img(self):
    return self._state_img

  @property
  def state_desire(self):
    return self._state_desire

  @property
  def state_feat(self):
    return self._state_feat

  def __del__(self):
    cuda = getattr(self, "cuda", None)
    if cuda is None:
      return
    stream = getattr(self, "stream", None)
    if stream:
      cuda.destroy_stream(stream)
    for ptr in getattr(self, "_dev", {}).values():
      cuda.free(ptr)
