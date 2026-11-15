#include "system/loggerd/encoder/jetson_nvenc_encoder.h"

#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <unistd.h>

#include <NvBufSurface.h>

#include "common/swaglog.h"

namespace {
// NUM_OUT_BUFFERS 定义于头文件 (类静态常量)
constexpr int NUM_CAP_BUFFERS = 6;
constexpr uint32_t MAX_PLANES_LOCAL = 8;

// O1: 跨进程 dmabuf import 缓存 (thread_local -> 每 encoder_thread 一份, 隔离不同 stream)。
// 主路与 qcam 编码器在同一 stream 线程内共享缓存, 同一 fd 只 import 一次
// (NvBufSurfaceImport 对同一 fd 重复调用会被 NVRM 拒绝)。
struct NvImportEntry {
  int fd = -1;
  NvBufSurface *surf = nullptr;
};
struct NvImportCache {
  NvBufSurfaceMapParams params = {};  // camerad 导出的权威 map params
  bool params_loaded = false;
  std::vector<NvImportEntry> entries;
};
NvImportCache &nvbuf_import_cache() {
  static thread_local NvImportCache cache;
  return cache;
}
}  // namespace

JetsonNvencEncoder::JetsonNvencEncoder(const EncoderInfo &encoder_info_, int in_width_, int in_height_,
                                       int stream_type_)
    : VideoEncoder(encoder_info_, in_width_, in_height_), stream_type(stream_type_) {
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
  // camerad 已统一以 20fps 发布 (含 qcam 所用的 road 流), rate-control 一律按
  // encoder_info_.fps(20) 校准; 之前主路写死 30 是配合 30fps 灌入的旧设定。
  const int rc_fps = encoder_info_.fps;
  ret = enc->setFrameRate(rc_fps, 1);
  assert(ret >= 0);

  // O1: 统一 DMABUF 通路。主路直接交付 camerad perfD 的 NVMM dmabuf
  // (VisionBuf::fd), qcam 经 VIC 缩放到 dst 池后交付; 全程无 CPU 拷贝。
  ret = enc->output_plane.setupPlane(V4L2_MEMORY_DMABUF, NUM_OUT_BUFFERS, true, false);
  assert(ret >= 0);

  // qcam: VIC 目标池 (out 尺寸 dmabuf) 兼作 NVENC output plane 输入
  if (needs_scale) {
    for (int i = 0; i < NUM_OUT_BUFFERS; i++) {
      int fd = alloc_nv12_dmabuf(out_width, out_height);
      assert(fd >= 0);
      dst_fds.push_back(fd);
      NvBufSurface *surf = nullptr;
      assert(NvBufSurfaceFromFd(fd, (void **)&surf) == 0 && surf != nullptr);
      dst_surfs.push_back(surf);
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
  params.memType = NVBUF_MEM_SURFACE_ARRAY;
  params.memtag = NvBufSurfaceTag_VIDEO_ENC;

  int fd = -1;
  if (NvBufSurf::NvAllocate(&params, 1, &fd) < 0) {
    LOGE("nvenc NvAllocate failed: %dx%d", width, height);
    return -1;
  }
  return fd;
}

NvBufSurface *JetsonNvencEncoder::ensure_import(VisionBuf *buf) {
  NvImportCache &cache = nvbuf_import_cache();
  if (!cache.params_loaded) {
    // 从 camerad 导出的权威 map params 文件加载 (perfD 分配成功后按流写一份)
    char path[96];
    snprintf(path, sizeof(path), "/tmp/egpucp_nvbuf_s%d.bin", stream_type);
    int rfd = open(path, O_RDONLY);
    if (rfd < 0) {
      LOGE("nvenc open %s failed (errno=%d): %s", path, errno, encoder_info.publish_name);
      return nullptr;
    }
    ssize_t n = read(rfd, &cache.params, sizeof(cache.params));
    close(rfd);
    if (n != (ssize_t)sizeof(cache.params)) {
      LOGE("nvenc read %s failed (n=%zd): %s", path, n, encoder_info.publish_name);
      return nullptr;
    }
    cache.params_loaded = true;
  }

  // 同一 fd 已 import 过 (同 frame 主路与 qcam 编码器共享) 直接复用
  for (const auto &e : cache.entries) {
    if (e.fd == buf->fd && e.surf != nullptr) {
      return e.surf;
    }
  }

  // 首次见到该 fd: 以 camerad 导出的几何 + 本进程收到的 dup fd 做 import 并缓存
  NvBufSurfaceMapParams mp = cache.params;
  mp.fd = (uint64_t)buf->fd;
  NvBufSurface *surf = nullptr;
  if (NvBufSurfaceImport(&surf, &mp) != 0 || surf == nullptr) {
    LOGE("nvenc NvBufSurfaceImport failed (fd=%d): %s", buf->fd, encoder_info.publish_name);
    return nullptr;
  }
  surf->numFilled = 1;  // 与 jetson_multimedia_api 跨进程样例 (13_argus_multi_camera) 一致
  cache.entries.push_back({buf->fd, surf});
  return surf;
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
      v4l2_buf.type = V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE;
      v4l2_buf.memory = V4L2_MEMORY_DMABUF;
      if (needs_scale) {
        for (uint32_t i = 0; i < 2; i++) {
          planes[i].bytesused = 0;
          planes[i].m.fd = dst_fds[idx];
        }
      } else {
        // O1: 主路输入来自 camerad 的 NVMM dmabuf (buf->fd), EOS 帧取当前
        // 空闲槽位即可, 无需填充 fd (仅触发编码器 drain)。
        for (uint32_t i = 0; i < 2; i++) {
          planes[i].bytesused = 0;
          planes[i].m.fd = -1;
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
  counter = 1;  // A: 从 1 起始, 保证段首帧 (forceIDR 后) 不被 P3 的 counter%3==0 采样丢弃
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
    if (nal_type == 32 || nal_type == 33 || nal_type == 34) {
      flags |= 1;
    } else if (nal_type <= 31) {
      // O2: 首个 VCL slice 即可定论 (bit1=可发布, bit2=IDR),
      // 后续 NAL 不改变判定, 提前终止免扫整帧
      flags |= 2;
      if (nal_type == 19 || nal_type == 20) flags |= 4;
      return flags;
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
    if (nal_type == 7 || nal_type == 8) {
      flags |= 1;
    } else if (nal_type >= 1 && nal_type <= 5) {
      // O2: 同 H265, 首个 VCL slice 即可定论并提前终止
      flags |= 2;
      if (nal_type == 5) flags |= 4;
      return flags;
    }
    i += sc_len + 1;
  }
  return flags;
}

int JetsonNvencEncoder::qcam_encode_frame(VisionBuf *buf, VisionIpcBufExtra *extra) {
  // 抽帧已上移到 camerad (camera_jetson.cc, sensor 30fps -> 发布 20fps)。
  // 这里再按 3:2 采一次会变成 13.3fps (实测 qRoadEncodeData 13.2Hz), 与
  // encoder_info_.fps=20 / srt 时间戳全对不上, 故此处逐帧编码。

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

  int out_idx = -1;
  if (!free_out.try_pop(out_idx, 500)) {
    LOGE("nvenc out pool timeout: %s", encoder_info.publish_name);
    return -1;
  }

  // O1: camerad perfD 已将 VisionBuf::fd 直接指向 NVMM dmabuf, VIC 直接缩放到
  // 编码器 output 池, 不再经过 CPU 映射、拷贝或独立 source 池。
  // VIC src 是跨进程 dmabuf, 必须先 import 注册 (NvTransform 内部对 src fd 调
  // NvBufSurfaceFromFd), 否则报 "dmabuf_fd N mapped entry NOT found"。
  if (ensure_import(buf) == nullptr) {
    free_out.push(out_idx);
    return -1;
  }

  NvBufSurf::NvCommonTransformParams transform = {};
  transform.src_width = in_width;
  transform.src_height = in_height;
  transform.dst_width = out_width;
  transform.dst_height = out_height;
  transform.flag = NVBUFSURF_TRANSFORM_FILTER;
  transform.filter = NvBufSurfTransformInter_Bilinear;
  if (NvBufSurf::NvTransform(&transform, buf->fd, dst_fds[out_idx]) != 0) {
    LOGE("nvenc VIC transform failed: %s", encoder_info.publish_name);
    free_out.push(out_idx);
    return -1;
  }

  const NvBufSurfacePlaneParams &dst_params = dst_surfs[out_idx]->surfaceList[0].planeParams;
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

  int idx = -1;
  if (!free_out.try_pop(idx, 500)) {
    LOGE("nvenc out pool timeout: %s", encoder_info.publish_name);
    return -1;
  }

  // O1: camerad perfD 的 NVMM dmabuf 先在本进程 import 注册, 才能取其真实
  // planeParams 构造 DMABUF qBuffer; 否则 NvBufSurfaceFromFd 必然失败。
  NvBufSurface *src_surf = ensure_import(buf);
  if (src_surf == nullptr) {
    free_out.push(idx);
    return -1;
  }
  const NvBufSurfacePlaneParams &src_params = src_surf->surfaceList[0].planeParams;

  struct v4l2_buffer v4l2_buf;
  struct v4l2_plane planes[MAX_PLANES_LOCAL];
  memset(&v4l2_buf, 0, sizeof(v4l2_buf));
  memset(planes, 0, sizeof(planes));
  v4l2_buf.index = idx;
  v4l2_buf.type = V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE;
  v4l2_buf.memory = V4L2_MEMORY_DMABUF;
  v4l2_buf.m.planes = planes;
  for (uint32_t p = 0; p < src_params.num_planes; p++) {
    // bytesused 按可视高度裁剪: camerad surface 含 2 行 padding 且尾部 8 字节
    // 是 frame_id (行 1081 末 8B), 不能交给 NVENC 读写, 故 Y 只送 in_height 行、
    // UV 只送 in_height/2 行 (实际 surface 行数恰多 1 行, 与头部 Y 对齐一致)。
    planes[p].bytesused = src_params.pitch[p] *
        (p == 0 ? (uint32_t)in_height : (uint32_t)(in_height / 2));
    planes[p].m.fd = buf->fd;
  }
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

  // P1: extras 与已入队的每个带 VCL 帧 1:1 FIFO 匹配(每帧 qBuffer 成功后才 push,
  // 每发布一帧 pop 一次)。为避免极端情况下 DQ 线程无限阻塞, 先超时探测;
  // 若异常为空(理论上仅发生在 EOS/错误边沿), 告警后阻塞兜底等待——
  // 不能直接放弃该 extra, 否则会破坏后续帧 timestamp/frame_id 的错位。
  VisionIpcBufExtra extra;
  if (!e->extras.try_pop(extra, 100)) {
    LOGW("nvenc extras empty on publish, waiting for matching extra: %s",
         e->encoder_info.publish_name);
    extra = e->extras.pop();
  }
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
