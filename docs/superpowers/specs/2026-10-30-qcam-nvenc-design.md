# qcam 迁移 NVENC 硬编（方案 B：VIC 硬缩放 + 第二路 NVENC H264）设计

日期：2026-10-30
状态：已批准（方案 B）

## 1. 背景与目标

qcam（`qRoadEncodeData`，输出 `qcamera.ts`）目前由 `FfmpegEncoder` 软编：
CPU 侧 NV12→I420 + I420Scale（libyuv）→ x264 (ultrafast, ABR+VBV)。设备实测
encoderd 内 qcam worker 线程池约 **24.2% CPU**（encoderd 总 ~52.28%），是当前
剩余的主要 CPU 大头。主路（road/wide/driver）已迁移到 `JetsonNvencEncoder`
（H265 NVENC，<10% CPU）。

**目标**：将 qcam 迁移到 Jetson NVENC 硬编，去除 libyuv 缩放与 x264 软编，
使 qcam 编码占用降到接近硬件开销；输出规格保持不变。

**qcam 规格**（[loggerd.h](file:///data/openpilot_egpucp/openpilot/system/loggerd/loggerd.h#L138-L146) 与会话实测）：

| 项 | 值 |
|---|---|
| 发布名 | `qRoadEncodeData` |
| 编码 | QCAMERA_H264（AVC） |
| 输出分辨率 | 526x330 |
| 码率 | 256 kbps（CBR） |
| GOP | 15 |
| 帧率 | MAIN_FPS（20） |
| 输入 | 主路 VisionBuf NV12（设备实测 ~1920x1200，以 buf 实尺寸为准，必须从 buf 尺寸工作） |

## 2. 现状梳理

- [encoderd.cc](file:///data/openpilot_egpucp/openpilot/system/loggerd/encoderd.cc#L18-L31)
  的 `make_encoder` 仅将 road/wide/driver 三个主路发布名分派到
  `JetsonNvencEncoder`，qcam 仍落 `FfmpegEncoder`。
- 现有 [jetson_nvenc_encoder.cc](file:///data/openpilot_egpucp/openpilot/system/loggerd/encoder/jetson_nvenc_encoder.cc)
  构造器限制 `out_width == in_width && out_height == in_height`（约 20-27 行），
  固定 H265，output plane 为 `V4L2_MEMORY_MMAP`。
- 设备（192.168.7.132，SSH 用户 `nvidia`）已确认：
  - VIC API：`NvBufSurf::NvAllocate` + `NvBufSurf::NvTransform`（
    `/usr/src/jetson_multimedia_api/samples/common/classes/NvBufSurface.cpp`），
    头文件 `NvBufSurface.h` 在 `/usr/src/jetson_multimedia_api/include`。
  - 库：`/usr/lib/aarch64-linux-gnu/tegra/libnvbufsurface.so`、
    `libnvbufsurftransform.so`（`NvTransform` 在此库）。
  - 01_video_encode 样例确认 NVENC output plane 支持 `V4L2_MEMORY_DMABUF`。

## 3. 方案对比（已决策）

| 方案 | 做法 | 结论 |
|---|---|---|
| A | libyuv 缩放 + 第二路 NVENC | 低复杂度但仍有 ~1 次 CPU 缩放拷贝 |
| **B（已选）** | **VIC 硬缩放 + 第二路 NVENC，DMABUF 直连** | 零 CPU 缩放；内存映射多一次但为硬件 |
| C | 单 NVENC 输出 qcam 替代主路 | 改变主路架构，风险大，否决 |

## 4. 架构设计

### 4.1 组件

扩展现有 `JetsonNvencEncoder`，用两个成员开关区分两条通路，**主路 H265 通路零改动**：

- `is_h264`：`encoder_info.get_settings(in_width).encode_type == QCAMERA_H264` 时启用
  （capture plane 用 `V4L2_PIX_FMT_H264` + H264 profile High）。
- `needs_scale`：`out_width != in_width || out_height != in_height` 时启用 VIC 通路
  （即 qcam 场景；主路恒为 false，走现有 MMAP 路径）。

### 4.2 Buffer 池与数据流（qcam 通路，每帧）

```
VisionBuf(NV12, 主路尺寸, CPU 内存)
  │  copy_plane ×2 (+NvBufSurfaceSyncForDevice)   ← 唯一的 CPU 拷贝
  ▼
src_pool[i]  NvBuffer ×4  (主路尺寸 NV12M, NVBUF_MEM_SURFACE, PITCH)
  │  NvBufSurf::NvTransform(src_fd, dst_fd)        ← VIC 硬缩放, 同步
  ▼
dst_pool[j]  NvBuffer ×NUM_OUT_BUFFERS (526x330 NV12M, 由 NvAllocate 分配; 兼作 NVENC DMABUF 输入)
  │  v4l2 plane m.fd = dst_pool[j]->planes[k].fd   ← DMABUF qBuffer, 无再拷贝
  ▼
NVENC output plane (526x330, V4L2_MEMORY_DMABUF)
  │  硬件编码 H264 CBR 256kbps
  ▼
NVENC capture plane (V4L2_MEMORY_MMAP)  ← 内部 DQ 线程回调发布, 与主路同机制
```

要点：

- **src_pool**：4 个源 NvBuffer，每帧轮换；`arrayPtr` 忙标志用 `SafeQueue<int> free_src`。
  同步 NvTransform 完成后立刻归还，池深 4 仅为避免覆盖在途 DMA。
- **dst_pool 与 free_out 统一**：`free_out` 语义从"MMAP 索引"扩展为二者兼容——
  qcam 通路存索引 `j`，`dst_pool[j]` 即该输入 buffer；qBuffer 时填
  `dst_pool[j]` 的 fd。驱动编码结束后 `output_plane.dqBuffer` 回收索引放回
  `free_out`（DMABUF 模式下 qBuffer/dqBuffer 的 index 由用户自定维护，不使用
  驱动侧 `getNthBuffer` 的 MMAP planes）。
- **capture plane 处理**：与主路完全一致——MMAP、`NUM_CAP_BUFFERS`、入队、
  `capture_dq_callback` + 内部 DQ 线程、`extras` 队列配对。唯一差异是 NAL 分类。

### 4.3 NAC 分类（新增 `classify_h264_nals`）

复用主路 classify 的骨架，NAL type 语义：

- type 7 (SPS) / 8 (PPS) → 参数集位 bit0；
- type 1-5 → VCL 位 bit1，其中 type 5 (IDR) → IDR 位 bit2；
- 其余（SEI 6、AUD 9 等）忽略。

capture 回调仅在“含 VCL”时消费 `extras` 并发布；纯参数集帧直接回收入队。
SPS/PPS 由 `setInsertSpsPpsAtIdrEnabled(true)` 内联进每个 IDR，流自包含，
header 传空（与主路一致，`qcamera.ts` 可独立解码）。

### 4.4 构造/析构扩展

- 构造：qcam 通路额外执行
  1. `setOutputPlaneFormat(V4L2_PIX_FMT_NV12M, 526, 330, V4L2_COLORSPACE_SMPTE170M)`
     （即 out 尺寸，非 in 尺寸）；
  2. `setCapturePlaneFormat(V4L2_PIX_FMT_H264, 526, 330, 256KB)`；
  3. 码控：CBR + `enableTwoPassCBR()` + bitrate=256000 + `setIDRInterval(15)`
     + `setIFrameInterval(15)` + `setNumBFrames(0)` + `setFrameRate(fps,1)`
     + H264 High profile；
  4. `output_plane.setupPlane(V4L2_MEMORY_DMABUF, NUM_OUT_BUFFERS, ...)`；
  5. `NvAllocate` 分配 src_pool（主路尺寸）与 dst_pool（526x330）。
- 析构：先 `dqBuffer` 清空在途 dst 缓冲并归还池，再 `NvBufSurfaceNvDestroy`
  释放 src/dst pool，最后沿用现有 EOS/abort 清理。
- `encode_frame` 入口断言 `buf->width == in_width && buf->height == in_height`
  保持不变；qcam 通路在 `in_width` 传入主路缓冲尺寸（encoderd 处传
  `buf_info.width/height` 已天然满足）。

### 4.5 边界细节（实现时在设备确认）

1. **stride 一致性**：`NvAllocate` 的 pitch（自动对齐）与 NVENC output plane
   的 `fmt.stride` 必须一致。实现时先 `setOutputPlaneFormat` 后读取
   `output_plane.getFormat()`，若与 `NvBufSurfaceFromFd(dst_fd)` 的 pitch 不符，
   需要在 qBuffer 前对齐（首选：提前按 driver stride 配置，若 NvAllocate 无法
   指定 stride，则以 VIC 输出 buffer 的 pitch 为准校准 driver 期望，或加
   `V4L2_BUF_FLAG_USE_SYNC` / crop 处理）。
2. **DMABUF qBuffer 填法**：`v4l2_buf.m.planes[k].m.fd = dst_pool[j]->planes[k].fd`，
   参考设备 01_video_encode_main.cpp（约 1104、1382-1406、1614-1617、1729-1752）。
3. **VIC transform 参数**：`NvCommonTransformParams{ src_rect=全帧, dst_rect=526x330,
   flag=NVBUFSURF_TRANSFORM_FILTER, filter=NvBufSurfTransformInter_Bilinear }`；
   `NvBufSurf::NvTransform(&params, src_fd, dst_fd)` 同步执行，无需 V4L2 converter
   线程。
4. **526x330 奇偶性**：均为偶数，NVENC/VIC 无对齐问题。

## 5. SConscript 变更

[SConscript](file:///data/openpilot_egpucp/openpilot/system/loggerd/SConscript#L16-L34)
aarch64 分支追加：

- `libs += ['nvbufsurftransform']`（NvTransform 符号）；
- 若使用 `NvVideoConverter` 类则追加其 .cpp；当前设计直用 `NvBufSurf::NvTransform`，
  无需引入 converter 类文件。

## 6. encoderd 变更

`make_encoder` 增加 `qRoadEncodeData` 分派到 `JetsonNvencEncoder`；同时保留
stream 编码器（`livestream*EncodeData`）走 ffmpeg（按需场景，不在本次范围）。

## 7. 错误处理

- `NvAllocate` / `NvTransform` / 任一 ioctl 失败：`LOGE` + `assert`（与现有编码器
  一致性错误策略一致，宁挂勿坏日志）；释放已分配资源后退出。
- `free_out` 空：阻塞 `output_plane.dqBuffer`（带 timeout）回收一帧再继续，
  保证不丢帧（与主路现逻辑一致，见 [jetson_nvenc_encoder.cc](file:///data/openpilot_egpucp/openpilot/system/loggerd/encoder/jetson_nvenc_encoder.cc) encode_frame）。
- capture 回调 DQ 失败：返回 false 停 DQ 线程（与主路一致）。

## 8. 验证计划

1. 构建：设备上 `scons` 出 encoderd，无链接错误。
2. 单测启动：单独拉起 encoderd（或整机），观察日志 `nvenc init qRoadEncodeData: in=..x.. bitrate=256000 gop=15 fps=20`。
3. 功能：`qcam` 服务正常出 `qcamera.ts`；`ffprobe -i qcamera.ts` 确认
   H264、526x330、时长连续。
4. 码流：提取 qcam 码流，确认首帧含 SPS/PPS（可独立解码）、每 GOP IDR、
   码率 ~256kbps（CBR）。
5. CPU：encoderd 进程 CPU 从 ~52% 降到 ~10% 量级（主路占比不变 + qcam 近零）。
6. 回归：road/wide H265 码流与 keyframe 行为不变（主路未触碰的断言保证）。
7. 丢帧：`qcam` 无丢帧告警（`encoderd` 无 "lag" 日志）。

## 9. 风险与回滚

- **riskiest：stride 不匹配 / DMABUF 填法** → 见 4.5，先做最小 smoke test
  （单实例 526x330 DMABUF qBuffer + dq 回收），验证通过再全量。
- 回滚：encoderd 的 `make_encoder` 去掉 `qRoadEncodeData` 一行即恢复 ffmpeg 软编；
  SConscript 保留库链接无害。
- 主路不受影响：needs_scale/is_h264 均 false 时走原路径（构造器 assert、
  MMAP、H265 全部不变）。