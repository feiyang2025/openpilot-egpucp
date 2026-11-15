#!/usr/bin/env python3
"""v4l2 mmap reader replacing cv.VideoCapture for tegra GMSL.
Standard V4L2: S_FMT UYVY -> REQBUFS 4 -> QUERYBUF+mmap -> STREAMON -> DQBUF/QBUF.
27fps verified with v4l2-ctl; OpenCV only achieves 10fps on tegra GMSL."""
import ctypes
import fcntl
import mmap
import os
import struct

# ---- v4l2 ioctls (linux/videodev2.h) ----
VIDIOC_QUERYCAP = 0x80685600
VIDIOC_S_FMT = 0xc0d05605
VIDIOC_REQBUFS = 0xC0145608  # _IOWR('V', 8, v4l2_requestbuffers[20B])
VIDIOC_QUERYBUF = 0xc0585609
VIDIOC_QBUF = 0xc058560f
VIDIOC_DQBUF = 0xc0585611
VIDIOC_STREAMON = 0x40045612
VIDIOC_STREAMOFF = 0x40045613

V4L2_BUF_TYPE_VIDEO_CAPTURE = 1
V4L2_MEMORY_MMAP = 1
V4L2_PIX_FMT_UYVY = 0x59565955  # 'UYVY'
V4L2_BUF_FLAG_ERROR = 0x40
V4L2_FMT_FLAG_COMPRESSED = 0x1


class V4L2PixFormat(ctypes.Structure):
  _fields_ = [
    ("width", ctypes.c_uint32),
    ("height", ctypes.c_uint32),
    ("pixelformat", ctypes.c_uint32),
    ("field", ctypes.c_uint32),
    ("bytesperline", ctypes.c_uint32),
    ("sizeimage", ctypes.c_uint32),
    ("colorspace", ctypes.c_uint32),
    ("priv", ctypes.c_uint32),
    ("flags", ctypes.c_uint32),
    ("ycbcr_enc", ctypes.c_uint32),
    ("quantization", ctypes.c_uint32),
    ("xfer_func", ctypes.c_uint32),
    ("reserved", ctypes.c_uint32 * 4),
  ]

class V4L2FmtUnion(ctypes.Union):
  _fields_ = [
    ("pix", V4L2PixFormat),
    ("raw", ctypes.c_uint8 * 204),
  ]

class V4L2Format(ctypes.Structure):
  _fields_ = [
    ("type", ctypes.c_uint32),
    ("fmt", V4L2FmtUnion),
  ]


class V4L2RequestBuffers(ctypes.Structure):
  _fields_ = [
    ("count", ctypes.c_uint32),
    ("type", ctypes.c_uint32),
    ("memory", ctypes.c_uint32),
    ("capabilities", ctypes.c_uint32),
    ("flags", ctypes.c_uint8),
    ("reserved", ctypes.c_uint8 * 3),
  ]


class V4L2Buffer(ctypes.Structure):
  # arm64: 88 bytes; union m aligned to 8
  _fields_ = [
    ("index", ctypes.c_uint32),
    ("type", ctypes.c_uint32),
    ("bytesused", ctypes.c_uint32),
    ("flags", ctypes.c_uint32),
    ("field", ctypes.c_uint32),
    ("_pad0", ctypes.c_uint32),
    ("timestamp", ctypes.c_int64 * 2),
    ("timecode", ctypes.c_uint32 * 4),
    ("sequence", ctypes.c_uint32),
    ("memory", ctypes.c_uint32),
    ("m_offset", ctypes.c_uint64),
    ("length", ctypes.c_uint32),
    ("_pad1", ctypes.c_uint32),
    ("reserved", ctypes.c_uint32 * 2),
  ]


class V4L2Plane(ctypes.Structure):
  _fields_ = [("bytesused", ctypes.c_uint32), ("length", ctypes.c_uint32)]


class V4L2BufferMulti(ctypes.Structure):
  _fields_ = [
    ("index", ctypes.c_uint32),
    ("type", ctypes.c_uint32),
    ("bytesused", ctypes.c_uint32),
    ("flags", ctypes.c_uint32),
    ("field", ctypes.c_uint32),
    ("timestamp", ctypes.c_int64 * 2),
    ("timecode", ctypes.c_uint32 * 4),
    ("sequence", ctypes.c_uint32),
    ("memory", ctypes.c_uint32),
    ("planes", ctypes.POINTER(V4L2Plane)),
    ("length", ctypes.c_uint32),
    ("reserved", ctypes.c_uint32 * 2),
  ]


class V4L2Reader:
  """mmap streaming reader. read() returns (frame_id, bytes_uyvy, ts)."""

  def __init__(self, device, width=1920, height=1080, pixelformat=V4L2_PIX_FMT_UYVY, nbufs=4):
    self.fd = os.open(device, os.O_RDWR)
    self.width = width
    self.height = height
    self.nbufs = nbufs
    self.buffers = []
    self.sizes = []

    # S_FMT
    fmt = V4L2Format()
    fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE
    fmt.fmt.pix.width = width
    fmt.fmt.pix.height = height
    fmt.fmt.pix.pixelformat = pixelformat
    fmt.fmt.pix.field = 0
    try:
      fcntl.ioctl(self.fd, VIDIOC_S_FMT, fmt)
    except OSError as e:
      os.close(self.fd)
      raise RuntimeError(f"S_FMT failed: {e}")
    self.bytesperline = fmt.fmt.pix.bytesperline or width * 2
    self.sizeimage = fmt.fmt.pix.sizeimage or width * height * 2

    # REQBUFS
    rb = V4L2RequestBuffers()
    rb.count = nbufs
    rb.type = V4L2_BUF_TYPE_VIDEO_CAPTURE
    rb.memory = V4L2_MEMORY_MMAP
    fcntl.ioctl(self.fd, VIDIOC_REQBUFS, rb)

    # QUERYBUF + mmap each
    for i in range(nbufs):
      qb = V4L2Buffer()
      qb.index = i
      qb.type = V4L2_BUF_TYPE_VIDEO_CAPTURE
      qb.memory = V4L2_MEMORY_MMAP
      fcntl.ioctl(self.fd, VIDIOC_QUERYBUF, qb)
      buf = mmap.mmap(self.fd, qb.length, mmap.MAP_SHARED, mmap.PROT_READ, offset=qb.m_offset)
      self.buffers.append(buf)
      self.sizes.append(qb.length)
      # QBUF to enqueue
      fcntl.ioctl(self.fd, VIDIOC_QBUF, qb)

    # STREAMON
    on = ctypes.c_uint32(V4L2_BUF_TYPE_VIDEO_CAPTURE)
    fcntl.ioctl(self.fd, VIDIOC_STREAMON, on)
    self.frame_id = 0

  def read(self):
    dq = V4L2Buffer()
    dq.type = V4L2_BUF_TYPE_VIDEO_CAPTURE
    dq.memory = V4L2_MEMORY_MMAP
    fcntl.ioctl(self.fd, VIDIOC_DQBUF, dq)
    idx = dq.index
    data = bytes(self.buffers[idx][:dq.bytesused])
    # requeue
    qb = V4L2Buffer()
    qb.index = idx
    qb.type = V4L2_BUF_TYPE_VIDEO_CAPTURE
    qb.memory = V4L2_MEMORY_MMAP
    fcntl.ioctl(self.fd, VIDIOC_QBUF, qb)
    self.frame_id += 1
    return self.frame_id, data, dq.sequence

  def close(self):
    try:
      off = ctypes.c_uint32(V4L2_BUF_TYPE_VIDEO_CAPTURE)
      fcntl.ioctl(self.fd, VIDIOC_STREAMOFF, off)
    except OSError:
      pass
    for b in self.buffers:
      b.close()
    os.close(self.fd)


if __name__ == "__main__":
  import sys
  import time
  dev = sys.argv[1] if len(sys.argv) > 1 else "/dev/video0"
  r = V4L2Reader(dev)
  print(f"opened {dev}: {r.width}x{r.height} bpl={r.bytesperline} size={r.sizeimage}")
  t0 = time.monotonic()
  n = 0
  while time.monotonic() - t0 < 5 and n < 100:
    fid, data, seq = r.read()
    n += 1
  print(f"v4l2 direct: {n/5:.1f} fps, frame {len(data)} bytes")
  r.close()
