#!/usr/bin/env python3
"""camera.py for Tegra twgmsl (UYVY-tagged, YUYV-layout) GMSL cameras and
UVC (USB /dev/video*) cameras, unified to NV12 output.

The tegra VI driver swaps the 4:2:2 byte order: requesting UYVY returns
YUYV-layout data and vice versa, so OpenCV's built-in conversion always
produces green/purple garbage for GMSL. We bypass it: read raw frames with
CAP_PROP_CONVERT_RGB=0, convert UYVY->NV12 ourselves (numpy), then resize the
Y/UV planes separately to the target WxH.

USB UVC cameras (e.g. IMX678 4K MJPG stick) decode to a 2-channel YUYV frame
in OpenCV when CONVERT_RGB=0; we convert that standard YUYV layout to NV12.
Device type is detected from the v4l2 driver name (uvcvideo vs tegra-capture-vi).
"""
import os
import numpy as np
import cv2 as cv

CAM_WIDTH = int(os.getenv("CAM_WIDTH", "1920"))
CAM_HEIGHT = int(os.getenv("CAM_HEIGHT", "1080"))
# Brightness gain for dark GMSL scenes (IMX390 default exposure is dim).
BRIGHTNESS_GAIN = float(os.getenv("CAM_BRIGHTNESS", "2.0"))
# 180-degree flip for GMSL (mount orientation). USB cameras default to no flip
# unless CAM_USB_FLIP=1.
CAM_FLIP = os.getenv("CAM_FLIP", "1") == "1"
CAM_USB_FLIP = os.getenv("CAM_USB_FLIP", "0") == "1"


def _v4l_driver(camera_id) -> str:
  """Return the v4l2 driver name (uvcvideo / tegra-camrtc-capture-vi / ...) or ''.
  Uses readlink (not realpath): realpath can silently fail on some kernels and
  return the unresolved 'driver' basename."""
  try:
    dev = f"/dev/video{camera_id}" if isinstance(camera_id, int) else camera_id
    v4l_name = os.path.basename(os.path.realpath(dev))
    drv = os.readlink(f"/sys/class/video4linux/{v4l_name}/device/driver")
    return os.path.basename(drv)
  except Exception:
    return ""


class Camera:
  def __init__(self, cam_type_state, stream_type, camera_id):
    try:
      camera_id = int(camera_id)
    except ValueError:  # allow strings, ex: /dev/video0
      pass
    self.cam_type_state = cam_type_state
    self.stream_type = stream_type
    self.cur_frame_id = 0
    self.camera_id = camera_id
    self.is_uvc = _v4l_driver(camera_id) == "uvcvideo"

    print(f"Opening {cam_type_state} at {camera_id} (driver: {_v4l_driver(camera_id) or 'n/a'}, uvc={self.is_uvc})", flush=True)

    self.cap = cv.VideoCapture(camera_id)
    # Request the sensor's native mode; tegra VI exposes discrete sizes.
    self.cap.set(cv.CAP_PROP_FRAME_WIDTH, 1920.0)
    self.cap.set(cv.CAP_PROP_FRAME_HEIGHT, 1080.0)
    # Raw capture: no OpenCV YUV->BGR conversion (it mis-decodes GMSL driver).
    self.cap.set(cv.CAP_PROP_CONVERT_RGB, 0)

    self.src_w = int(self.cap.get(cv.CAP_PROP_FRAME_WIDTH))
    self.src_h = int(self.cap.get(cv.CAP_PROP_FRAME_HEIGHT))

    self.W = CAM_WIDTH
    self.H = CAM_HEIGHT

  def reopen(self):
    """Reopen the device after a stream loss (keep config)."""
    try:
      self.cap.release()
    except Exception:
      pass
    self.cap = cv.VideoCapture(self.camera_id)
    self.cap.set(cv.CAP_PROP_FRAME_WIDTH, 1920.0)
    self.cap.set(cv.CAP_PROP_FRAME_HEIGHT, 1080.0)
    self.cap.set(cv.CAP_PROP_CONVERT_RGB, 0)

  @staticmethod
  def _assemble_nv12(y, u, v, dst_w, dst_h):
    y = cv.resize(y, (dst_w, dst_h), interpolation=cv.INTER_LINEAR)
    u = cv.resize(u, (dst_w // 2, dst_h // 2), interpolation=cv.INTER_AREA)
    v = cv.resize(v, (dst_w // 2, dst_h // 2), interpolation=cv.INTER_AREA)
    uv = np.empty((dst_h // 2, dst_w), dtype=np.uint8)
    uv[:, 0::2] = u
    uv[:, 1::2] = v
    return np.concatenate([y.reshape(-1), uv.reshape(-1)]).tobytes()

  def uyvy_to_nv12(self, frame, dst_w, dst_h):
    """GMSL path: frame is (h, w, 2) uint8 UYVY-labeled, YUYV-physical."""
    h, w = frame.shape[:2]
    a = frame.reshape(-1)
    # Tegra twgmsl: stream labeled UYVY but chroma lanes are reversed
    # (V0 Y0 U0 Y1). Decode physical order -> standards-compliant NV12.
    y = a[1::2].reshape(h, w)
    u = a[2::4].reshape(h, w // 2)
    v = a[0::4].reshape(h, w // 2)
    # Brightness gain (dark GMSL scene compensation)
    y = np.clip(y.astype(np.float32) * BRIGHTNESS_GAIN, 0, 255).astype(np.uint8)
    return Camera._assemble_nv12(y, u, v, dst_w, dst_h)

  def yuyv_to_nv12(self, frame, dst_w, dst_h):
    """USB UVC path: OpenCV with CONVERT_RGB=0 yields standard YUYV
    (Y0 U0 Y1 V0 ...), 2 channels."""
    h, w = frame.shape[:2]
    a = frame.reshape(-1)
    y = a[0::2].reshape(h, w)
    u = a[1::4].reshape(h, w // 2)
    v = a[3::4].reshape(h, w // 2)
    return Camera._assemble_nv12(y, u, v, dst_w, dst_h)

  def read_frames(self):
    while True:
      ret, frame = self.cap.read()
      if not ret:
        break
      if self.is_uvc:
        if CAM_USB_FLIP:
          frame = cv.flip(frame, -1)
        nv12 = self.yuyv_to_nv12(frame, self.W, self.H)
      else:
        if CAM_FLIP:
          frame = cv.flip(frame, -1)
        nv12 = self.uyvy_to_nv12(frame, self.W, self.H)
      yield nv12
    self.cap.release()