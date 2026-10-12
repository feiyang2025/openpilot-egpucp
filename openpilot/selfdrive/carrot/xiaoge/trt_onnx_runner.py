#!/usr/bin/env python3
"""Minimal TensorRT runner for the small XIAOGE ONNX models.

The XIAOGE VASM/lane models used to run through OpenCV's DNN on the CPU
(``DNN_TARGET_CPU``), which costs ~60-170 ms per frame on the Orin. This builds a
TensorRT engine (fp16 by default) from the committed ONNX on first use, caches
the serialized plan, and runs the model on the Orin GPU in a few milliseconds.

The engine is bound against plain host numpy buffers per tensor, so callers keep
their existing pre/post-processing and only the ``forward`` moves to the GPU.
"""
from __future__ import annotations

import ctypes
import hashlib
from pathlib import Path
import tempfile

import numpy as np


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

  for path in ("/usr/lib/python3.12/dist-packages", "/home/nvidia/.local/lib/python3.12/site-packages"):
    if path not in sys.path:
      sys.path.insert(0, path)
  return importlib.import_module("tensorrt")


def _cache_path(model_path: Path, trt_version: str, fp16: bool) -> Path:
  try:
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()[:16]
  except OSError:
    digest = "unknown"
  tag = f"{digest}.{trt_version}.{'fp16' if fp16 else 'fp32'}.plan"
  beside = model_path.with_suffix(model_path.suffix + f".{tag}")
  # Prefer caching next to the model; fall back to a writable temp dir when the
  # model assets are on a read-only mount (AGNOS).
  try:
    beside.parent.mkdir(parents=True, exist_ok=True)
    if beside.parent.stat().st_mode & 0o200:
      return beside
  except OSError:
    pass
  tmp_dir = Path(tempfile.gettempdir()) / "carrot_xiaoge_trt"
  tmp_dir.mkdir(parents=True, exist_ok=True)
  return tmp_dir / f"{model_path.stem}.{tag}"


class TrtOnnxRunner:
  """Run a single-input/single-or-multi-output ONNX model on TensorRT."""

  @staticmethod
  def cached_plan_path(model_path: str | Path, fp16: bool = True) -> Path | None:
    """Return the cached plan path if a built engine already exists (either precision)."""
    try:
      trt = _import_tensorrt()
    except Exception:
      return None
    model = Path(model_path)
    for use_fp16 in ((True, False) if fp16 else (False,)):
      path = _cache_path(model, trt.__version__, use_fp16)
      if path.is_file():
        return path
    return None

  def __init__(self, model_path: str | Path, fp16: bool = True):
    from openpilot.selfdrive.modeld.tensorrt_policy_runner import CudaRuntime

    self.trt = _import_tensorrt()
    self.model_path = Path(model_path)
    self.cuda = CudaRuntime()
    self.stream = self.cuda.create_stream()

    engine, self.fp16 = self._load_or_build(fp16)
    self.engine = engine
    self.context = engine.create_execution_context()
    if self.context is None:
      raise RuntimeError("failed to create TensorRT execution context")

    self.input_names: list[str] = []
    self.output_names: list[str] = []
    self._host: dict[str, np.ndarray] = {}
    self._dev: dict[str, ctypes.c_void_p] = {}
    for i in range(engine.num_io_tensors):
      name = engine.get_tensor_name(i)
      shape = tuple(self.context.get_tensor_shape(name))
      dtype = _TRT_TO_NUMPY[engine.get_tensor_dtype(name).name]
      self._host[name] = np.zeros(shape, dtype=dtype)
      self._dev[name] = self.cuda.malloc(self._host[name].nbytes)
      if not self.context.set_tensor_address(name, self._dev[name].value):
        raise RuntimeError(f"failed to bind TensorRT tensor {name}")
      if engine.get_tensor_mode(name) == self.trt.TensorIOMode.INPUT:
        self.input_names.append(name)
      else:
        self.output_names.append(name)

  def _build(self, fp16: bool):
    trt = self.trt
    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    parser = trt.OnnxParser(network, logger)
    if not parser.parse_from_file(str(self.model_path)):
      raise RuntimeError(f"TensorRT failed to parse {self.model_path}")
    config = builder.create_builder_config()
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 1 << 29)
    # These models run in a few ms; cap the builder at level 2 so the one-time
    # engine build is not spent exhaustively timing every tactic.
    config.builder_optimization_level = 2
    if fp16 and builder.platform_has_fast_fp16:
      config.set_flag(trt.BuilderFlag.FP16)
    # Returns None (rather than raising) when the build fails, so the caller can
    # retry at the other precision.
    return builder.build_serialized_network(network, config)

  def _load_or_build(self, fp16: bool):
    trt = self.trt
    runtime = trt.Runtime(trt.Logger(trt.Logger.WARNING))
    precisions = (True, False) if fp16 else (False,)
    # 1) Any cached plan (either precision). Checking both before building avoids
    #    re-attempting a precision whose tactic already failed to compile.
    for use_fp16 in precisions:
      cache = _cache_path(self.model_path, trt.__version__, use_fp16)
      if cache.is_file():
        engine = runtime.deserialize_cuda_engine(cache.read_bytes())
        if engine is not None:
          return engine, use_fp16
    # 2) Build, falling back to fp32 if an fp16 tactic fails to compile on Orin.
    for use_fp16 in precisions:
      plan = self._build(use_fp16)
      if plan is None:
        continue
      cache = _cache_path(self.model_path, trt.__version__, use_fp16)
      try:
        cache.write_bytes(bytes(plan))
      except OSError:
        pass
      engine = runtime.deserialize_cuda_engine(bytes(plan))
      if engine is not None:
        return engine, use_fp16
    raise RuntimeError(f"TensorRT failed to build {self.model_path} (fp16 and fp32)")

  def infer(self, feeds: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    for name in self.input_names:
      self._host[name][...] = feeds[name]
    for name in self.input_names:
      self.cuda.upload(self._dev[name], self._host[name])
    if not self.context.execute_async_v3(int(self.stream.value or 0)):
      raise RuntimeError("TensorRT execute_async_v3 failed")
    self.cuda.sync(self.stream)
    for name in self.output_names:
      self.cuda.download(self._dev[name], self._host[name])
    return {name: self._host[name] for name in self.output_names}

  def __del__(self):
    cuda = getattr(self, "cuda", None)
    if cuda is None:
      return
    stream = getattr(self, "stream", None)
    if stream:
      cuda.destroy_stream(stream)
    for ptr in getattr(self, "_dev", {}).values():
      cuda.free(ptr)


class AsyncTrtRunner:
  """Build/load the engine without blocking the caller.

  A cached plan loads synchronously (fast). Otherwise the engine is built on a
  background thread; callers keep using their CPU fallback until ``ready``.
  """

  def __init__(self, model_path: str | Path, fp16: bool = True):
    import threading

    self.model_path = Path(model_path)
    self._runner: TrtOnnxRunner | None = None
    self._failed = False
    cached = TrtOnnxRunner.cached_plan_path(self.model_path, fp16)
    if cached is not None:
      try:
        self._runner = TrtOnnxRunner(self.model_path, fp16)
        return
      except Exception:
        self._failed = True
        return
    self._thread = threading.Thread(target=self._build, args=(fp16,), daemon=True, name="trt-build")
    self._thread.start()

  def _build(self, fp16: bool) -> None:
    try:
      self._runner = TrtOnnxRunner(self.model_path, fp16)
    except Exception:
      self._failed = True

  @property
  def ready(self) -> bool:
    return self._runner is not None

  def infer(self, feeds: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    assert self._runner is not None
    return self._runner.infer(feeds)
