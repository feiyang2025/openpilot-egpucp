#include "system/loggerd/encoder/jetson_nvenc_encoder.h"

#include <cstring>

#include <NvBufSurface.h>

#include "common/swaglog.h"

namespace {
constexpr int NUM_OUT_BUFFERS = 4;
constexpr int NUM_CAP_BUFFERS = 6;
constexpr int NUM_SRC_BUFFERS = 4;
constexpr uint32_t MAX_PLANES_LOCAL = 8;
}  // namespace

JetsonNvencEncoder::JetsonNvencEncoder(const EncoderInfo &encoder_info_, int in_width_, int in_height_)
    : VideoEncoder(encoder_info_, in_width_, in_height_) {
  EncoderSettings settings = encoder_info_.get_settings(in_width);
  is_h264 = settings.encode_type == cereal::EncodeIndex::Type::QCAMERA_H264;
  needs_scale = out_width != in_width || out_height != in_height;

  enc = NvVideoEncoder::createVideoEncoder(encoder_info_.publish_name);
  assert(enc && "NvVideoEncoder::createVideoEncoder 失败, 检查 /dev/nvhost-msenc 与 tegra 库");

  int ret;
  ret = enc->setCapturePlaneFormat(
      is_h264 ? V4L2_PIX_FMT_H264 : V4L2_PIX_FMT_H265,
      out_width, out_height, 2 * 1024 * 1024);
  assert(ret >= 0);

  const int enc_width = needs_scale ? out_width : in_width;
  const int enc_height = needs_scale ? out_height : in_height;
  ret = enc->setOutputPlaneFormat(V4L2_PIX_FMT_NV12M, enc_width, enc_height,
                                  V4L2_COLORSPACE_SMPTE170M);
  assert(ret >= 0);

  ret = enc->setBitrate(settings.bitrate);
  assert(ret >= 0);
  ret = enc->setRateControlMode(V4L2_MPEG_VIDEO_BITRATE_MODE_CBR);
  assert(ret >= 0);
  ret = enc->enableTwoPassCBR();
  assert(ret >= 0);
  const uint32_t enc_profile = is_h264
      ? (uint32_t)V4L2_MPEG_VIDEO_H264_PROFILE_HIGH
      : (uint32_t)V4L2_MPEG_VIDEO_H265_PROFILE_MAIN;
  ret = enc->setProfile(enc_profile);
  assert(ret >= 0);
  ret = enc->setIDRInterval(settings.gop_size);
  assert(ret >= 0);
  ret = enc->setIFrameInterval(settings.gop_size);
  assert(ret >= 0);
  ret = enc->setNumBFrames(0);
  assert(ret >= 0);
  ret = enc->setInsertSpsPpsAtIdrEnabled(true);
  assert(ret >= 0);
  ret = enc->setFrameRate(encoder_info_.fps, 1);
  assert(ret >= 0);

  ret = enc->output_plane.setupPlane(needs_scale ? V4L2_MEMORY_DMABUF : V4L2_MEMORY_MMAP,
                                     NUM_OUT_BUFFERS, true, false);
  assert(ret >= 0);

  if (needs_scale) {
    for (int i = 0; i < NUM_SRC_BUFFERS; i++) {
      int fd = alloc_nv12_dmabuf(in_width, in_height);
      assert(fd >= 0);
      src_fds.push_back(fd);
      free_src.push(i);
    }
    for (int i = 0; i < NUM_OUT_BUFFERS; i++) {
      int fd = alloc_nv12_dmabuf(out_width, out_height);
      assert(fd >= 0);
      dst_fds.push_back(fd);
    }
    for (int i = 0; i < NUM_OUT_BUFFERS; i++) {
      struct v4l2_buffer v4l2_buf;
      struct v4l2_plane planes[MAX_PLANES_LOCAL];
      memset(&v4l2_buf, 0, sizeof(v4l2_buf));
      memset(planes, 0, sizeof(planes));
      v4l2_buf.index = i;
      v4l2_buf.type = V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE;
      v4l2_buf.memory = V4L2_MEMORY_DMABUF;
      v4l2_buf.m.planes = planes;
      ret = enc->output_plane.mapOutputBuffers(v4l2_buf, dst_fds[i]);
      assert(ret >= 0);
    }
  }

  ret = enc->capture_plane.setupPlane(V4L2_MEMORY_MMAP, NUM_CAP_BUFFERS, true, false);
  assert(ret >= 0);

  ret = enc->subscribeEvent(V4L2_EVENT_EOS, 0, 0);
  assert(ret >= 0);
  ret = enc->output_plane.setStreamStatus(true);
  assert(ret >= 0);
  ret = enc->capture_plane.setStreamStatus(true);
  assert(ret >= 0);

  for (uint32_t i = 0; i < enc->capture_plane.getNumBuffers(); i++) {
    struct v4l2_buffer v4l2_buf;
    struct v4l2_plane planes[MAX_PLANES_LOCAL];
    memset(&v4l2_buf, 0, sizeof(v4l2_buf));
    memset(planes, 0, sizeof(planes));
    v4l2_buf.index = i;
    v4l2_buf.m.planes = planes;
    ret = enc->capture_plane.qBuffer(v4l2_buf, NULL);
    assert(ret >= 0);
  }

  enc->capture_plane.setDQThreadCallback(JetsonNvencEncoder::capture_dq_callback);
  ret = enc->capture_plane.startDQThread(this);
  assert(ret >= 0);

  for (int i = 0; i < NUM_OUT_BUFFERS; i++) {
    free_out.push(i);
  }

  LOGW("nvenc init %s: in=%dx%d out=%dx%d codec=%s bitrate=%d gop=%d fps=%d",
       encoder_info_.publish_name, in_width_, in_height_, out_width, out_height,
       is_h264 ? "H264" : "H265", settings.bitrate, settings.gop_size, encoder_info_.fps);
}

int JetsonNvencEncoder::alloc_nv12_dmabuf(int width, int height) {
  NvBufSurf::NvCommonAllocateParams params = {};
  params.width = width;
  params.height = height;
  params.colorFormat = NVBUF_COLOR_FORMAT_NV12;
  params.layout = NVBUF_LAYOUT_PITCH;
  params.memType = NVBUF_MEM_SURFACE;
  params.memtag = NvBufSurfaceTag_VIDEO_ENC;

  int fd = -1;
  if (NvBufSurf::NvAllocate(&params, 1, &fd) < 0) {
    LOGE("nvenc NvAllocate failed: %dx%d", width, height);
    return -1;
  }
  return fd;
}

JetsonNvencEncoder::~JetsonNvencEncoder() {
  encoder_close();

  bool eos_sent = false;
  if (enc && !enc->isInError()) {
    struct v4l2_buffer v4l2_buf;
    struct v4l2_plane planes[MAX_PLANES_LOCAL];
    memset(&v4l2_buf, 0, sizeof(v4l2_buf));
    memset(planes, 0, sizeof(planes));
    v4l2_buf.m.planes = planes;

    int idx = -1;
    NvBuffer *buffer = nullptr;
    if (!free_out.empty()) {
      idx = free_out.pop();
    } else if (enc->output_plane.dqBuffer(v4l2_buf, &buffer, NULL, 50) == 0) {
      idx = v4l2_buf.index;
    }

    if (idx >= 0) {
      v4l2_buf.index = idx;
      if (needs_scale) {
        v4l2_buf.type = V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE;
        v4l2_buf.memory = V4L2_MEMORY_DMABUF;
        for (uint32_t i = 0; i < 2; i++) {
          planes[i].bytesused = 0;
          planes[i].m.fd = dst_fds[idx];
        }
      } else {
        buffer = enc->output_plane.getNthBuffer(idx);
        for (uint32_t i = 0; i < buffer->n_planes; i++) {
          buffer->planes[i].bytesused = 0;
          planes[i].bytesused = 0;
        }
      }
      eos_sent = enc->output_plane.qBuffer(v4l2_buf, NULL) == 0;
    }
    if (eos_sent) {
      enc->capture_plane.waitForDQThread(3000);
    }
  }

  if (enc && needs_scale) {
    for (size_t i = 0; i < dst_fds.size(); i++) {
      if (dst_fds[i] >= 0) {
        enc->output_plane.unmapOutputBuffers(i, dst_fds[i]);
      }
    }
  }

  for (int fd : src_fds) {
    if (fd >= 0) NvBufSurf::NvDestroy(fd);
  }
  for (int fd : dst_fds) {
    if (fd >= 0) NvBufSurf::NvDestroy(fd);
  }

  if (enc) {
    enc->abort();
    enc->capture_plane.waitForDQThread(1000);
    delete enc;
  }
}

void JetsonNvencEncoder::encoder_open() {
  segment_num++;
  counter = 0;
  publish_idx = 0;
  enc->forceIDR();
  is_open = true;
}

void JetsonNvencEncoder::encoder_close() {
  is_open = false;
}

int JetsonNvencEncoder::classify_h265_nals(const uint8_t *data, uint32_t len) {
  uint32_t i = 0;
  int flags = 0;
  while (i + 3 < len) {
    if (data[i] != 0 || data[i + 1] != 0) { i++; continue; }
    uint32_t sc_len;
    if (data[i + 2] == 1) {
      sc_len = 3;
    } else if (i + 3 < len && data[i + 2] == 0 && data[i + 3] == 1) {
      sc_len = 4;
    } else {
      i++;
      continue;
    }
    if (i + sc_len + 2 > len) break;
    int nal_type = (data[i + sc_len] >> 1) & 0x3f;
    if (nal_type == 32 || nal_type == 33 || nal_type == 34) flags |= 1;
    else if (nal_type <= 31) {
      flags |= 2;
      if (nal_type == 19 || nal_type == 20) flags |= 4;
    }
    i += sc_len + 2;
  }
  return flags;
}

int JetsonNvencEncoder::classify_h264_nals(const uint8_t *data, uint32_t len) {
  uint32_t i = 0;
  int flags = 0;
  while (i + 3 < len) {
    if (data[i] != 0 || data[i + 1] != 0) { i++; continue; }
    uint32_t sc_len;
    if (data[i + 2] == 1) {
      sc_len = 3;
    } else if (i + 3 < len && data[i + 2] == 0 && data[i + 3] == 1) {
      sc_len = 4;
    } else {
      i++;
      continue;
    }
    if (i + sc_len + 1 > len) break;
    const int nal_type = data[i + sc_len] & 0x1f;
    if (nal_type == 7 || nal_type == 8) flags |= 1;
    else if (nal_type >= 1 && nal_type <= 5) {
      flags |= 2;
      if (nal_type == 5) flags |= 4;
    }
    i += sc_len + 1;
  }
  return flags;
}

void JetsonNvencEncoder::copy_plane(uint8_t *dst, int dst_stride, const uint8_t *src,
                                    int src_stride, int width, int height) {
  if (dst_stride == src_stride) {
    memcpy(dst, src, (size_t)src_stride * height);
  } else {
    for (int r = 0; r < height; r++) {
      memcpy(dst + (size_t)r * dst_stride, src + (size_t)r * src_stride, width);
    }
  }
}

int JetsonNvencEncoder::qcam_encode_frame(VisionBuf *buf, VisionIpcBufExtra *extra) {
  const int src_idx = free_src.pop();
  const int src_fd = src_fds[src_idx];

  NvBufSurface *src_surf = nullptr;
  if (NvBufSurfaceFromFd(src_fd, (void **)&src_surf) != 0 || src_surf == nullptr) {
    LOGE("nvenc source surface lookup failed: %s", encoder_info.publish_name);
    free_src.push(src_idx);
    return -1;
  }
  const NvBufSurfacePlaneParams &src_params = src_surf->surfaceList[0].planeParams;
  for (uint32_t p = 0; p < src_params.num_planes; p++) {
    if (NvBufSurfaceMap(src_surf, 0, p, NVBUF_MAP_WRITE) != 0) {
      LOGE("nvenc source map failed: %s plane %d", encoder_info.publish_name, p);
      free_src.push(src_idx);
      return -1;
    }
    uint8_t *dst = (uint8_t *)src_surf->surfaceList[0].mappedAddr.addr[p];
    const uint8_t *src = p == 0 ? buf->y : buf->uv;
    const int height = p == 0 ? in_height : in_height / 2;
    copy_plane(dst, src_params.pitch[p], src, buf->stride, in_width, height);
    if (NvBufSurfaceSyncForDevice(src_surf, 0, p) != 0 ||
        NvBufSurfaceUnMap(src_surf, 0, p) != 0) {
      LOGE("nvenc source sync failed: %s plane %d", encoder_info.publish_name, p);
      free_src.push(src_idx);
      return -1;
    }
  }

  if (free_out.empty()) {
    struct v4l2_buffer v4l2_buf;
    struct v4l2_plane planes[MAX_PLANES_LOCAL];
    memset(&v4l2_buf, 0, sizeof(v4l2_buf));
    memset(planes, 0, sizeof(planes));
    v4l2_buf.m.planes = planes;
    if (enc->output_plane.dqBuffer(v4l2_buf, NULL, NULL, 50) < 0) {
      LOGE("nvenc output dq failed: %s", encoder_info.publish_name);
      free_src.push(src_idx);
      return -1;
    }
    free_out.push(v4l2_buf.index);
  }

  const int out_idx = free_out.pop();
  NvBufSurf::NvCommonTransformParams transform = {};
  transform.src_width = in_width;
  transform.src_height = in_height;
  transform.dst_width = out_width;
  transform.dst_height = out_height;
  transform.flag = NVBUFSURF_TRANSFORM_FILTER;
  transform.filter = NvBufSurfTransformInter_Bilinear;
  if (NvBufSurf::NvTransform(&transform, src_fd, dst_fds[out_idx]) != 0) {
    LOGE("nvenc VIC transform failed: %s", encoder_info.publish_name);
    free_src.push(src_idx);
    free_out.push(out_idx);
    return -1;
  }
  free_src.push(src_idx);

  NvBufSurface *dst_surf = nullptr;
  if (NvBufSurfaceFromFd(dst_fds[out_idx], (void **)&dst_surf) != 0 || dst_surf == nullptr) {
    LOGE("nvenc destination surface lookup failed: %s", encoder_info.publish_name);
    free_out.push(out_idx);
    return -1;
  }
  const NvBufSurfacePlaneParams &dst_params = dst_surf->surfaceList[0].planeParams;

  struct v4l2_buffer v4l2_buf;
  struct v4l2_plane planes[MAX_PLANES_LOCAL];
  memset(&v4l2_buf, 0, sizeof(v4l2_buf));
  memset(planes, 0, sizeof(planes));
  v4l2_buf.index = out_idx;
  v4l2_buf.type = V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE;
  v4l2_buf.memory = V4L2_MEMORY_DMABUF;
  v4l2_buf.m.planes = planes;
  for (uint32_t p = 0; p < dst_params.num_planes; p++) {
    planes[p].bytesused = dst_params.pitch[p] * dst_params.height[p];
    planes[p].m.fd = dst_fds[out_idx];
  }
  v4l2_buf.flags |= V4L2_BUF_FLAG_TIMESTAMP_COPY;
  v4l2_buf.timestamp.tv_sec = extra->timestamp_eof / 1000000000ULL;
  v4l2_buf.timestamp.tv_usec = (extra->timestamp_eof / 1000ULL) % 1000000ULL;

  if (enc->output_plane.qBuffer(v4l2_buf, NULL) < 0) {
    LOGE("nvenc output qBuffer failed: %s", encoder_info.publish_name);
    free_out.push(out_idx);
    return -1;
  }
  extras.push(*extra);
  return counter++;
}

int JetsonNvencEncoder::encode_frame(VisionBuf* buf, VisionIpcBufExtra *extra) {
  assert(buf->width == this->in_width);
  assert(buf->height == this->in_height);

  if (needs_scale) {
    return qcam_encode_frame(buf, extra);
  }

  if (free_out.empty()) {
    struct v4l2_buffer v4l2_buf;
    struct v4l2_plane planes[MAX_PLANES_LOCAL];
    memset(&v4l2_buf, 0, sizeof(v4l2_buf));
    memset(planes, 0, sizeof(planes));
    v4l2_buf.m.planes = planes;
    if (enc->output_plane.dqBuffer(v4l2_buf, NULL, NULL, 50) < 0) {
      LOGE("nvenc output dq failed: %s", encoder_info.publish_name);
      return -1;
    }
    free_out.push(v4l2_buf.index);
  }

  int idx = free_out.pop();
  NvBuffer *buffer = enc->output_plane.getNthBuffer(idx);
  assert(buffer->n_planes == 2);

  copy_plane((uint8_t *)buffer->planes[0].data, buffer->planes[0].fmt.stride,
             (const uint8_t *)buf->y, buf->stride, in_width, in_height);
  copy_plane((uint8_t *)buffer->planes[1].data, buffer->planes[1].fmt.stride,
             (const uint8_t *)buf->uv, buf->stride, in_width, in_height / 2);
  for (uint32_t i = 0; i < buffer->n_planes; i++) {
    buffer->planes[i].bytesused = buffer->planes[i].fmt.stride * buffer->planes[i].fmt.height;
    NvBufSurface *surf = nullptr;
    if (NvBufSurfaceFromFd(buffer->planes[i].fd, (void **)&surf) != 0 ||
        NvBufSurfaceSyncForDevice(surf, 0, i) != 0) {
      LOGE("nvenc buf sync failed: %s plane %d", encoder_info.publish_name, i);
      free_out.push(idx);
      return -1;
    }
  }

  struct v4l2_buffer v4l2_buf;
  struct v4l2_plane planes[MAX_PLANES_LOCAL];
  memset(&v4l2_buf, 0, sizeof(v4l2_buf));
  memset(planes, 0, sizeof(planes));
  v4l2_buf.index = idx;
  v4l2_buf.m.planes = planes;
  v4l2_buf.flags |= V4L2_BUF_FLAG_TIMESTAMP_COPY;
  v4l2_buf.timestamp.tv_sec = extra->timestamp_eof / 1000000000ULL;
  v4l2_buf.timestamp.tv_usec = (extra->timestamp_eof / 1000ULL) % 1000000ULL;

  if (enc->output_plane.qBuffer(v4l2_buf, NULL) < 0) {
    LOGE("nvenc output qBuffer failed: %s", encoder_info.publish_name);
    free_out.push(idx);
    return -1;
  }
  extras.push(*extra);
  return counter++;
}

bool JetsonNvencEncoder::capture_dq_callback(struct v4l2_buffer *v4l2_buf, NvBuffer *buffer,
                                              NvBuffer * /*shared_buffer*/, void *data) {
  JetsonNvencEncoder *e = static_cast<JetsonNvencEncoder *>(data);
  if (v4l2_buf == NULL || buffer == NULL) {
    return false;
  }
  if (buffer->planes[0].bytesused == 0) {
    return false;
  }

  int nal_flags = e->is_h264
      ? classify_h264_nals((const uint8_t *)buffer->planes[0].data, buffer->planes[0].bytesused)
      : classify_h265_nals((const uint8_t *)buffer->planes[0].data, buffer->planes[0].bytesused);
  if (nal_flags < 0 || !(nal_flags & 2)) {
    if (e->enc->capture_plane.qBuffer(*v4l2_buf, NULL) < 0) {
      LOGE("nvenc capture qBuffer(header) failed");
      return false;
    }
    return true;
  }

  VisionIpcBufExtra extra = e->extras.pop();
  unsigned int flags = ((nal_flags & 4) || (v4l2_buf->flags & V4L2_BUF_FLAG_KEYFRAME))
                           ? V4L2_BUF_FLAG_KEYFRAME : 0;
  e->publisher_publish(e->segment_num, e->publish_idx++, extra, flags,
                       kj::ArrayPtr<capnp::byte>(),
                       kj::arrayPtr<capnp::byte>((capnp::byte *)buffer->planes[0].data,
                                                 buffer->planes[0].bytesused));

  if (e->enc->capture_plane.qBuffer(*v4l2_buf, NULL) < 0) {
    LOGE("nvenc capture qBuffer failed");
    return false;
  }
  return true;
}
