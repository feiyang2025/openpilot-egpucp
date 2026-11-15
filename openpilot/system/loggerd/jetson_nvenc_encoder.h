#pragma once

// Jetson NVENC 硬件编码器（NvMmlite / libnvmmlite_video, /dev/nvhost-msenc）。
// 替换主路 FFV1 无损软编（实测 282% CPU, ~1.16MB/帧）:
// H265 CBR 硬编占用 <10% CPU, 码流 ~62KB/帧 (10M@20fps)。
// 输入 NV12 (VisionBuf), memcpy 进 V4L2 MMAP 缓冲。
// SPS/PPS 由 setInsertSpsPpsAtIdrEnabled 内联在 IDR 帧, header 传空。
// qcam 次级通路 (H264 526x330): VIC 硬缩放 + output plane DMABUF 直连,
// 仅一次 CPU 拷贝 (VisionBuf -> VIC 源 NvBuffer)。
#include <atomic>
#include <vector>

// 必须先于 encoder.h 包含: NvMmlite 头链引入系统 v4l2-controls.h (含
// v4l2_h264_weight_factors 等新类型), 其 guard 与 openpilot vendored
// 副本相同, 先到者生效, 避免 v4l2_nv_extensions.h 编译错误。
#include <NvVideoEncoder.h>

#include "common/queue.h"
#include "system/loggerd/encoder/encoder.h"

class JetsonNvencEncoder : public VideoEncoder {
public:
  JetsonNvencEncoder(const EncoderInfo &encoder_info, int in_width, int in_height);
  ~JetsonNvencEncoder() override;
  int encode_frame(VisionBuf* buf, VisionIpcBufExtra *extra) override;
  void encoder_open() override;
  void encoder_close() override;

private:
  // capture plane 内部 DQ 线程回调: 取码流 -> 发布 -> 回收入队; 返回 false 停线程
  static bool capture_dq_callback(struct v4l2_buffer *v4l2_buf, NvBuffer *buffer,
                                  NvBuffer * /*shared_buffer*/, void *data);
  // 扫描 H265 NAL: 判断是否含 VCL slice (可发布帧) 以及是否 IDR
  // 返回: -1 无法解析; bit0: 含参数集(VPS/SPS/PPS); bit1: 含 VCL; bit2: IDR
  static int classify_h265_nals(const uint8_t *data, uint32_t len);
  // 扫描 H264 NAL: 与 H265 同骨架但单字节 NAL header; bit2: IDR (type 5)
  static int classify_h264_nals(const uint8_t *data, uint32_t len);
  static void copy_plane(uint8_t *dst, int dst_stride, const uint8_t *src, int src_stride,
                         int width, int height);

  // qcam 缩放通路: VIC 缩放 + DMABUF qBuffer; 返回 frame counter, 失败 -1
  int qcam_encode_frame(VisionBuf *buf, VisionIpcBufExtra *extra);
  // 分配 NV12 pitch dmabuf (NvBufSurf::NvAllocate), 返回 fd 或 -1
  int alloc_nv12_dmabuf(int width, int height);

  NvVideoEncoder *enc = nullptr;
  bool is_open = false;
  bool is_h264 = false;       // qcam H264 通路 (QCAMERA_H264 encode_type)
  bool needs_scale = false;   // out != in, 走 VIC 缩放
  std::atomic<int> segment_num{-1};
  std::atomic<int> publish_idx{0};
  int counter = 0;
  SafeQueue<VisionIpcBufExtra> extras;
  SafeQueue<int> free_out;   // 主路: MMAP output 索引; qcam: DMABUF 槽位 (对应 dst_fds[i])
  // qcam VIC 源池 (主路尺寸 dmabuf); free_src 存放空闲槽位
  std::vector<int> src_fds;
  SafeQueue<int> free_src;
  // qcam VIC 目标池 (out 尺寸 dmabuf), 兼作 NVENC output plane 输入
  std::vector<int> dst_fds;
};