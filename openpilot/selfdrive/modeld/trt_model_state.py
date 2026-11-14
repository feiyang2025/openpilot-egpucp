#!/usr/bin/env python3
"""TrtModelState: TensorRT backend for the big driving model on the on-board GPU.

tinygrad's CUDA path needs ~273 ms per frame for the 765 MB big model (5 Hz),
which is unusable while driving. TensorRT's FP16 engine does the same forward
pass in ~33 ms (24 Hz), so when a serialized plan is present we run it here and
keep the rest of modeld untouched.

Interface is deliberately identical to ModelState:
  __init__(cam_w, cam_h, usbgpu, pkl_path=None, plan_path=None, metadata_path=None)
  run(bufs, transforms, inputs, prepare_only) -> dict | None
  reset()
  .vision_input_names / .usbgpu / .frame_skip / .output_slices

Warp is done with OpenCV on the CPU (same approach the c3 tree proved out) so
nothing here touches tinygrad's CUDA context, which the TRT runner keeps
isolated in its own context.
"""
import json
import os

import cv2
import numpy as np

from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.modeld.compile_modeld import nv12_copy_size
from openpilot.selfdrive.modeld.constants import ModelConstants
from openpilot.selfdrive.modeld.parse_model_outputs import Parser
from openpilot.selfdrive.modeld.trt_runner import TrtRunner
from openpilot.system.camerad.cameras.nv12_info import get_nv12_info

MODEL_W, MODEL_H = 512, 256


def metadata_path_for(plan_path) -> str:
  return str(plan_path).rsplit('.', 1)[0] + '_meta.json'


def save_metadata(metadata: dict, path: str) -> None:
  """Persist input_shapes/output_slices so startup never has to load the pkl."""
  value = {
    'input_shapes': {k: list(v) for k, v in metadata['input_shapes'].items()},
    'output_slices': {k: [int(v.start), int(v.stop)] for k, v in metadata['output_slices'].items()},
  }
  with open(path, 'w', encoding='utf-8') as f:
    json.dump(value, f, sort_keys=True)


def load_metadata(path: str) -> dict:
  with open(path, encoding='utf-8') as f:
    raw = json.load(f)
  return {
    'input_shapes': {k: tuple(v) for k, v in raw['input_shapes'].items()},
    'output_slices': {k: slice(v[0], v[1]) for k, v in raw['output_slices'].items()},
  }


class TrtModelState:
  prev_desire: np.ndarray

  def __init__(self, cam_w: int, cam_h: int, usbgpu: bool = False,
               pkl_path=None, plan_path=None, metadata_path=None, frame_skip=None,
               reverse_frames: bool = False):
    if plan_path is None:
      raise ValueError('TrtModelState requires plan_path')
    self.usbgpu = usbgpu
    # Some exports pack the vision input as [newest, oldest] instead of
    # [oldest, newest]; the wrong order reads as backward motion and makes the
    # model brake to a standstill while every shape stays valid.
    self.reverse_frames = reverse_frames
    self.cam_w, self.cam_h = cam_w, cam_h
    self.plan_path = str(plan_path)
    self.trt = TrtRunner(self.plan_path)

    md = load_metadata(metadata_path or metadata_path_for(plan_path))
    self.input_shapes = md['input_shapes']
    self.output_slices = md['output_slices']
    self.vision_input_names = [k for k in self.input_shapes if 'img' in k]

    self.parser = Parser()
    self.prev_desire = np.zeros(ModelConstants.DESIRE_LEN, dtype=np.float32)
    # frame_skip is overridable: the buffer/context convention must match the
    # model, and picking it wrong silently collapses the plan to ~0 m even
    # though every tensor shape stays valid.
    self.frame_skip = int(frame_skip or (ModelConstants.MODEL_RUN_FREQ // ModelConstants.MODEL_CONTEXT_FREQ))

    self.nv12 = get_nv12_info(cam_w, cam_h)
    self.stride, self.y_h, self.uv_h, self._size = self.nv12
    self.frame_copy_size = nv12_copy_size(self.stride, self.y_h, self.uv_h)

    img_shp = self.input_shapes['img']            # (1, 12, 128, 256) -> 2 frames
    n_frames = img_shp[1] // 6
    fb = self.input_shapes['features_buffer']
    self.feat_dim = int(np.prod(fb[2:]))
    dp = self.input_shapes['desire_pulse']

    self.img_buf_shape = (self.frame_skip * (n_frames - 1) + 1, 6, img_shp[2], img_shp[3])
    self.img_q = np.zeros(self.img_buf_shape, dtype=np.uint8)
    self.big_q = np.zeros(self.img_buf_shape, dtype=np.uint8)
    self.feat_q = np.zeros((self.frame_skip * fb[1], fb[0], self.feat_dim), dtype=np.float32)
    self.desire_q = np.zeros((self.frame_skip * dp[1], dp[0], dp[2]), dtype=np.float32)
    self.prev_feat = np.zeros((1, self.feat_dim), dtype=np.float32)
    self.model_dtypes = {n: self.trt.io[n]['npdt'] for n in self.trt.input_names}

    log = ('big model TRT backend ready: plan=%s skip=%d feat_dim=%d' %
           (os.path.basename(self.plan_path), self.frame_skip, self.feat_dim))
    try:
      cloudlog.warning(log)
    except Exception:
      print(log)

  # ------------------------------------------------------------------ helpers
  def slice_outputs(self, model_outputs: np.ndarray, output_slices: dict[str, slice]) -> dict[str, np.ndarray]:
    return {k: model_outputs[np.newaxis, v] for k, v in output_slices.items()}

  def _warp(self, frame_buf, M, src_stride=None, src_uv_offset=None):
    W, H = self.cam_w, self.cam_h
    src_stride = src_stride or self.stride
    src_uv_offset = src_uv_offset if src_uv_offset is not None else src_stride * self.y_h
    y_h = src_uv_offset // src_stride
    mw, mh = MODEL_W, MODEL_H
    y = frame_buf[:src_uv_offset].reshape(y_h, src_stride)
    uv_h = (len(frame_buf) - src_uv_offset) // src_stride
    uv = frame_buf[src_uv_offset:src_uv_offset + uv_h * src_stride].reshape(uv_h, src_stride)
    # transforms carry OUTPUT->INPUT (model->camera); cv2 wants the inverse.
    # Before extrinsics arrive the matrix is all-zero -> singular, so skip.
    if np.count_nonzero(M) == 0:
      return np.zeros((6, MODEL_H // 2, MODEL_W // 2), dtype=np.float32)
    M_inv = np.linalg.inv(M)
    M_uv = M_inv * np.array([[1.0, 1.0, 0.5], [1.0, 1.0, 0.5], [2.0, 2.0, 1.0]], dtype=np.float32)
    yw = cv2.warpPerspective(y[:H, :W], M_inv, (mw, mh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    uw = cv2.warpPerspective(uv[:y_h // 2, :W:2], M_uv, (mw // 2, mh // 2), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    vw = cv2.warpPerspective(uv[:y_h // 2, 1:W:2], M_uv, (mw // 2, mh // 2), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    yuv = np.concatenate([yw.reshape(-1), uw.reshape(-1), vw.reshape(-1)]).reshape(mh * 3 // 2, mw)
    Hh, Ww = mh // 2, mw // 2
    return np.stack([
      yuv[0:mh:2, 0::2], yuv[1:mh:2, 0::2], yuv[0:mh:2, 1::2], yuv[1:mh:2, 1::2],
      yuv[mh:mh + mh // 4].reshape(Hh, Ww), yuv[mh + mh // 4:mh + mh // 2].reshape(Hh, Ww),
    ])

  def _sample_skip(self, buf):
    return buf[::self.frame_skip].reshape(1, -1)

  def _sample_desire(self, buf):
    b = buf.reshape(-1, self.frame_skip, *buf.shape[1:])
    return b.max(1).reshape(1, -1)

  # --------------------------------------------------------------------- API
  def reset(self):
    self.prev_desire[:] = 0
    self.img_q[:] = 0
    self.big_q[:] = 0
    self.feat_q[:] = 0
    self.desire_q[:] = 0
    self.prev_feat[:] = 0

  def run(self, bufs, transforms, inputs, prepare_only=False):
    _frame_n = len(bufs['img'].data)
    frame_buf = np.frombuffer(bufs['img'].data, dtype=np.uint8, count=_frame_n)
    big_frame_buf = np.frombuffer(bufs['big_img'].data, dtype=np.uint8, count=len(bufs['big_img'].data))

    inputs['desire_pulse'][0] = 0
    desire = np.where(inputs['desire_pulse'] - self.prev_desire > .99, inputs['desire_pulse'], 0)
    self.prev_desire[:] = inputs['desire_pulse']

    self.img_q[:-1] = self.img_q[1:]
    self.img_q[-1] = self._warp(frame_buf, transforms['img'], getattr(bufs['img'], 'stride', None), getattr(bufs['img'], 'uv_offset', None))
    self.big_q[:-1] = self.big_q[1:]
    self.big_q[-1] = self._warp(big_frame_buf, transforms['big_img'], getattr(bufs['big_img'], 'stride', None), getattr(bufs['big_img'], 'uv_offset', None))
    self.feat_q[:-1] = self.feat_q[1:]
    self.feat_q[-1] = self.prev_feat.reshape(1, 1, -1)
    self.desire_q[:-1] = self.desire_q[1:]
    self.desire_q[-1] = desire.reshape(1, 1, -1)

    if prepare_only:
      return None

    d = self.model_dtypes
    img_frames = self._sample_skip(self.img_q)
    big_frames = self._sample_skip(self.big_q)
    if self.reverse_frames:
      img_frames = img_frames[::-1]
      big_frames = big_frames[::-1]
    trt_inputs = {
      # this plan embeds the /255 normalization internally: raw 0..255 values
      # cast straight to fp16. Feeding /255-squashed values makes every frame
      # look identical to the model -> trajectory never reacts to the camera.
      'img': img_frames.reshape(self.input_shapes['img']).astype(d['img']),
      'big_img': big_frames.reshape(self.input_shapes['big_img']).astype(d['big_img']),
      'desire_pulse': self._sample_desire(self.desire_q).reshape(self.input_shapes['desire_pulse']).astype(d['desire_pulse']),
      'features_buffer': self._sample_skip(self.feat_q).reshape(self.input_shapes['features_buffer']).astype(d['features_buffer']),
      'traffic_convention': np.asarray(inputs['traffic_convention'], dtype=d['traffic_convention']).reshape(1, 2),
      'action_t': np.asarray(inputs['action_t'], dtype=d['action_t']).reshape(1, 2),
    }
    model_output = self.trt.run_np(trt_inputs)

    if not np.all(np.isfinite(model_output)):
      raise RuntimeError('TRT model output is not finite')
    outputs_dict = self.parser.parse_outputs(self.slice_outputs(model_output, self.output_slices))
    self.prev_feat[:] = model_output[self.output_slices['hidden_state']]
    if os.environ.get('SEND_RAW_PRED'):
      outputs_dict['raw_pred'] = model_output.copy()
    return outputs_dict

  def warmup(self) -> None:
    # Random frames, never zeros: the model emits inf/NaN on all-zero input and
    # prev_feat feeds back into features_buffer, poisoning every later frame.
    dummy = {k: np.random.randint(0, 255, self.frame_copy_size, dtype=np.uint8)
             for k in self.vision_input_names}
    eye = np.eye(3, dtype=np.float32)
    dims = {'desire_pulse': ModelConstants.DESIRE_LEN, 'traffic_convention': 2, 'action_t': 2}
    self.run(dummy, {k: eye for k in self.vision_input_names},
             {k: np.zeros(v, dtype=np.float32) for k, v in dims.items()})
    self.reset()
