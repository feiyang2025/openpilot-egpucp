#!/usr/bin/env python3
from __future__ import annotations

import math
from pathlib import Path
from typing import Mapping

import numpy as np


class TensorRTPolicyRunner:
  """TensorRT execution for the driving policy, preserving modeld queue semantics."""

  INPUT_DTYPES = {
    "img": "float32",
    "big_img": "float32",
    "desire_pulse": "float16",
    "traffic_convention": "float16",
    "action_t": "float16",
    "features_buffer": "float16",
  }

  def __init__(self, engine_path: str | Path, input_shapes: Mapping[str, tuple[int, ...]], frame_skip: int):
    import sys
    for _p in ("/usr/lib/python3.12/dist-packages", "/home/nvidia/.local/lib/python3.12/site-packages"):
      if _p not in sys.path:
        sys.path.insert(0, _p)
    import tensorrt as trt
    import torch

    self.torch = torch
    self.trt = trt
    self.frame_skip = frame_skip
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

    img = self.input_shapes["img"]
    n_frames = img[1] // 6
    image_queue_shape = (frame_skip * (n_frames - 1) + 1, 6, img[2], img[3])
    fb = self.input_shapes["features_buffer"]
    feat_dim = math.prod(fb[2:])
    dp = self.input_shapes["desire_pulse"]

    self.img_q = torch.zeros(image_queue_shape, dtype=torch.uint8, device="cuda")
    self.big_img_q = torch.zeros_like(self.img_q)
    self.desire_q = torch.zeros((frame_skip * dp[1], dp[0], dp[2]), dtype=torch.float16, device="cuda")
    self.feat_q = torch.zeros((frame_skip * fb[1], fb[0], feat_dim), dtype=torch.float16, device="cuda")
    self._heads = {"img": 0, "big_img": 0, "desire": 0, "feat": 0}

    self.bindings = {
      "img": torch.empty(self.input_shapes["img"], dtype=torch.float32, device="cuda"),
      "big_img": torch.empty(self.input_shapes["big_img"], dtype=torch.float32, device="cuda"),
      "desire_pulse": torch.empty(self.input_shapes["desire_pulse"], dtype=torch.float16, device="cuda"),
      "traffic_convention": torch.empty(self.input_shapes["traffic_convention"], dtype=torch.float16, device="cuda"),
      "action_t": torch.empty(self.input_shapes["action_t"], dtype=torch.float16, device="cuda"),
      "features_buffer": torch.empty(self.input_shapes["features_buffer"], dtype=torch.float16, device="cuda"),
    }

    output_names = [engine.get_tensor_name(i) for i in range(engine.num_io_tensors)
                    if engine.get_tensor_mode(engine.get_tensor_name(i)) == trt.TensorIOMode.OUTPUT]
    if output_names != ["outputs"]:
      raise RuntimeError(f"unexpected TensorRT outputs: {output_names}")
    out_shape = tuple(context.get_tensor_shape("outputs"))
    self.output = torch.empty(out_shape, dtype=torch.float16, device="cuda")

    for name, tensor in self.bindings.items():
      expected = tuple(context.get_tensor_shape(name))
      if expected != tuple(tensor.shape):
        raise RuntimeError(f"TensorRT shape mismatch for {name}: engine={expected}, runner={tuple(tensor.shape)}")
      if not context.set_tensor_address(name, tensor.data_ptr()):
        raise RuntimeError(f"failed to bind TensorRT input {name}")
    if not context.set_tensor_address("outputs", self.output.data_ptr()):
      raise RuntimeError("failed to bind TensorRT output")

  def _append(self, name, queue, value) -> None:
    head = self._heads[name]
    queue[head:head + 1].copy_(value)
    self._heads[name] = (head + 1) % queue.shape[0]

  def _ordered(self, name, queue):
    head = self._heads[name]
    if head == 0:
      return queue
    return self.torch.cat((queue[head:], queue[:head]), dim=0)

  def run(self, warped: np.ndarray, desire: np.ndarray, traffic_convention: np.ndarray,
          action_t: np.ndarray, prev_feat: np.ndarray) -> np.ndarray:
    torch = self.torch
    if warped.shape != (2, 6, self.input_shapes["img"][2], self.input_shapes["img"][3]):
      raise ValueError(f"unexpected warped shape: {warped.shape}")

    with torch.cuda.stream(self.stream), torch.inference_mode():
      warped_gpu = torch.as_tensor(warped, device="cuda")
      self._append("img", self.img_q, warped_gpu[0:1])
      self._append("big_img", self.big_img_q, warped_gpu[1:2])
      self._append("desire", self.desire_q, torch.as_tensor(desire, dtype=torch.float16, device="cuda").reshape(1, 1, -1))
      self._append("feat", self.feat_q, torch.as_tensor(prev_feat, dtype=torch.float16, device="cuda").reshape(1, 1, -1))

      img_q = self._ordered("img", self.img_q)
      big_img_q = self._ordered("big_img", self.big_img_q)
      desire_q = self._ordered("desire", self.desire_q)
      feat_q = self._ordered("feat", self.feat_q)
      self.bindings["img"].copy_(img_q[::self.frame_skip].flatten(0, 1).unsqueeze(0))
      self.bindings["big_img"].copy_(big_img_q[::self.frame_skip].flatten(0, 1).unsqueeze(0))
      desire_sampled = desire_q.reshape(-1, self.frame_skip, *desire_q.shape[1:]).amax(1).flatten(0, 1).unsqueeze(0)
      self.bindings["desire_pulse"].copy_(desire_sampled)
      self.bindings["features_buffer"].copy_(feat_q[::self.frame_skip].flatten(0, 1).reshape(self.input_shapes["features_buffer"]))
      self.bindings["traffic_convention"].copy_(torch.as_tensor(traffic_convention, dtype=torch.float16, device="cuda"))
      self.bindings["action_t"].copy_(torch.as_tensor(action_t, dtype=torch.float16, device="cuda"))

      if not self.context.execute_async_v3(self.stream.cuda_stream):
        raise RuntimeError("TensorRT execute_async_v3 failed")
      # Transfer compact FP16 output first, then widen on CPU; this avoids a
      # device-side cast and keeps the modeld critical path on the TRT stream.
      self.stream.synchronize()
      result = self.output.cpu().numpy().astype(np.float32, copy=False)
    return result[0]
