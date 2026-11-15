#pragma once

// Jetson NVENC 硬件编码器（NvMmlite / libnvmmlite_video, /dev/nvhost-msenc）。
// 替换主路 FFV1 无损软编（实测 282% CPU, ~1.16MB/帧）:
// H265 CBR 硬编占用 <10% CPU, 码流 ~62KB/帧 (10M@20fps)。
// 输入: camerad perfD 零拷贝通路直接分发 NVMM dmabuf (VisionBuf::fd),
// 编码器 output plane 用 DMABUF 直连, 全程无 CPU 拷贝。
// SPS/PPS 由 setInsertSpsPpsAtIdrEnabled 内联在 IDR 帧, header 传空。
// qcam 次级通路 (H264 526x330): VIC 硬缩放 (NVMM->NVMM) + DMABUF 直连,
// 同样零 CPU 拷贝。
#include <atomic>
#include <vector>

// 必须先于 encoder.h 包含: NvMmlite 头链引入系统 v4l2-controls.h (含
// v4l2_h264_weight_factors 等新类型), 其 guard 与 openpilot vendored
// 副本相同, 先到者生效, 避免 v4l2_nv_extensions.h 编译错误。
#include <NvVideoEncoder.h>

#include "common/queue.h"
#include "system/loggerd/encoder/encoder.h"

// 前置声明: 仅缓存句柄指针用, 实现在 .cc 中 include <NvBufSurface.h>
struct NvBufSurface;

class JetsonNvencEncoder : public VideoEncoder {
public:
  // encode_frame 返回码: -1 编码失败 (encoderd 记 LOGE);
  // -2 按设计采样丢帧 (P3: qcam 30fps 输入采样到 20fps), 不计错误不刷日志
  static constexpr int FRAME_DROPPED = -2;

  // stream_type (VisionStreamType 整数) 用于定位 camerad 导出的跨进程
  // NvBufSurfaceImport 参数文件 (/tmp/egpucp_nvbuf_s<type>.bin)。
  JetsonNvencEncoder(const EncoderInfo &encoder_info, int in_width, int in_height, int stream_type);
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

  // qcam 缩放通路: VIC 缩放 + DMABUF qBuffer; 返回 frame counter, 失败 -1
  int qcam_encode_frame(VisionBuf *buf, VisionIpcBufExtra *extra);
  // O1: camerad perfD 的 NVMM dmabuf 经 Unix socket 跨进程传到本进程后,
  // 必须先 NvBufSurfaceImport 注册才能被 NvBufSurfaceFromFd / NvTransform 解析。
  // 参数取自 camerad 每流导出的权威 map params 文件; 缓存按 (stream, fd) (thread_local) 复用,
  // 同一 dmabuf 只 import 一次, 避免主路与 qcam 编码器重复 import 同一 fd 被 NVRM 拒绝。
  // 返回 import 后的 surface 句柄 (含真实 planeParams), 失败返回 nullptr。
  NvBufSurface *ensure_import(VisionBuf *buf);
  // 分配 NV12 pitch dmabuf (NvBufSurf::NvAllocate), 返回 fd 或 -1
  int alloc_nv12_dmabuf(int width, int height);

  // output plane 缓冲数 (DMABUF 通路共用)
  static constexpr int NUM_OUT_BUFFERS = 4;

  NvVideoEncoder *enc = nullptr;
  bool is_open = false;
  bool is_h264 = false;       // qcam H264 通路 (QCAMERA_H264 encode_type)
  bool needs_scale = false;   // out != in, 走 VIC 缩放
  int stream_type = 0;        // VisionStreamType 整数, 定位 camerad 导出的 import 参数文件
  std::atomic<int> segment_num{-1};
  std::atomic<int> publish_idx{0};
  int counter = 0;
  SafeQueue<VisionIpcBufExtra> extras;
  SafeQueue<int> free_out;   // DMABUF output 槽位 (对应 dst_fds[i])
  // qcam VIC 目标池 (out 尺寸 dmabuf), 兼作 NVENC output plane 输入
  std::vector<int> dst_fds;
  std::vector<NvBufSurface *> dst_surfs;
};