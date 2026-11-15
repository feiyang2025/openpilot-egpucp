# qcam NVENC 硬编迁移实施计划

> **For agentic workers:** 按任务逐项执行；完成代码后必须进行设备构建和运行验证。

**目标：** 将 `qRoadEncodeData` 从 FFmpeg/libx264 软编迁移到 Jetson NVENC H264 硬编，使用 VIC 将主路 NV12 缩放到 526x330，并保持 256 kbps、GOP 15、20 FPS 输出规格。

**架构：** 主路 H265 继续使用现有 MMAP NVENC 路径；qcam 使用同一个 `JetsonNvencEncoder` 的独立缩放路径。qcam 每帧将 VisionBuf 拷贝到 NVMM 源 dmabuf，经 `NvBufSurf::NvTransform` 由 VIC 缩放到目标 dmabuf，再通过 NVENC output plane 的 `V4L2_MEMORY_DMABUF` 直接编码，避免 CPU 缩放和二次小图拷贝。

**技术栈：** Jetson Multimedia API、`NvBufSurface`、`NvBufSurf::NvTransform`、V4L2 NVENC、C++、SCons。

## 全局约束

- 不改变主路 H265 的现有输出行为。
- qcam 输出必须为 H264、526x330、256000 bps CBR、GOP 15、MAIN_FPS。
- 输入尺寸始终使用 `VisionBuf` 的实际尺寸；qcam 输出尺寸来自 `VideoEncoder::out_width/out_height`。
- qcam 每帧不因 buffer 池暂时耗尽而静默丢帧；应阻塞等待 NVENC output buffer 回收。
- 不创建 git commit，除非用户明确要求。
- 设备构建环境：`nvidia@192.168.7.132`，源码工作树位于设备对应的 openpilot 目录。

## 文件职责

- `openpilot/system/loggerd/SConscript`：加入 `NvBufSurface.cpp` 和 `nvbufsurftransform` 链接。
- `openpilot/system/loggerd/encoder/jetson_nvenc_encoder.h`：声明 H264/缩放状态、VIC buffer 池和 qcam 编码辅助接口。
- `openpilot/system/loggerd/encoder/jetson_nvenc_encoder.cc`：初始化 NVENC/VIC、执行缩放、回收 dmabuf、分类 H264 NAL。
- `openpilot/system/loggerd/encoderd.cc`：将 `qRoadEncodeData` 分派给 Jetson NVENC。

### Task 1：更新 Jetson 构建依赖

**文件：** `openpilot/system/loggerd/SConscript`

- 在 aarch64 源文件列表加入 `/usr/src/jetson_multimedia_api/samples/common/classes/NvBufSurface.cpp`。
- 在 Jetson 库列表加入 `nvbufsurftransform`；现有 `nvbufsurface` 保留。
- 保持现有 `NvVideoEncoder.cpp` 等 Multimedia API 类源文件和 `JETSON_MAIN_ENCODER_NVENC` 宏不变。
- 用设备上的 `scons` 编译 `encoderd`，确认 `NvBufSurf::NvAllocate/NvTransform` 及 `NvBufSurface*` 符号均能链接。

### Task 2：扩展编码器状态接口

**文件：** `jetson_nvenc_encoder.h`

增加：

```cpp
#include <vector>
#include <NvBufSurface.h>

static int classify_h264_nals(const uint8_t *data, uint32_t len);
int qcam_encode_frame(VisionBuf *buf, VisionIpcBufExtra *extra);
int alloc_nv12_dmabuf(int width, int height);
```

增加成员：

```cpp
bool is_h264 = false;
bool needs_scale = false;
std::vector<int> src_fds;
std::vector<int> dst_fds;
SafeQueue<int> free_src;
```

`dst_fds[i]` 与 NVENC output plane index `i` 一一对应；`src_fds` 是 VIC 源池。保留现有 `free_out`，主路仍表示 MMAP 索引，qcam 表示映射的 DMABUF 槽位。

### Task 3：扩展构造和 qcam buffer 初始化

**文件：** `jetson_nvenc_encoder.cc`

- 引入 `<vector>`（头文件已声明）和 `NvBufSurface.h`。
- 删除 `assert(out_width == in_width && out_height == in_height)`。
- 根据 `encoder_info_.get_settings(in_width).encode_type` 设置 `is_h264`，根据尺寸差异设置 `needs_scale`。
- 编码格式：
  - H264：`V4L2_PIX_FMT_H264`、`V4L2_MPEG_VIDEO_H264_PROFILE_HIGH`。
  - 主路：原 H265 格式和 Main profile。
- `setCapturePlaneFormat` 使用输出尺寸；`setOutputPlaneFormat` 使用 NVENC 实际输入尺寸：qcam 为 `out_width/out_height`，主路为 `in_width/in_height`。
- 保留 CBR、two-pass CBR、IDR/I-frame interval、无 B 帧、SPS/PPS at IDR 和帧率设置。
- qcam 使用 `output_plane.setupPlane(V4L2_MEMORY_DMABUF, NUM_OUT_BUFFERS, true, false)`；主路仍使用 MMAP。
- qcam 目标池每项通过以下参数调用 `NvBufSurf::NvAllocate`：
  - `width=out_width`、`height=out_height`
  - `colorFormat=NVBUF_COLOR_FORMAT_NV12`
  - `layout=NVBUF_LAYOUT_PITCH`
  - `memType=NVBUF_MEM_SURFACE`
  - `memtag=NvBufSurfaceTag_VIDEO_ENC`
- 每个目标 fd 通过 `mapOutputBuffers` 映射到对应 output index。映射用 `v4l2_buffer.index=i` 和 `v4l2_buffer.m.planes`；DMABUF 模式下 NVIDIA API 将所有 NV12M planes 关联到同一个 fd。
- qcam 源池按同样的 NV12 pitch 参数分配 `NUM_SRC_BUFFERS=4` 个主路尺寸 fd，并加入 `free_src`。
- 初始化 capture plane、capture buffer 入队、DQ 线程和 `free_out` 的现有逻辑保持不变。
- 日志同时打印输入、输出、codec、bitrate 和 gop。

### Task 4：实现 VIC 缩放和 DMABUF 编码输入

**文件：** `jetson_nvenc_encoder.cc`

在 `encode_frame` 开头保留输入尺寸断言；当 `needs_scale` 为真时调用 `qcam_encode_frame`，否则执行现有主路路径。

`qcam_encode_frame` 的顺序：

1. 从 `free_src` 取得源槽位。通过 `NvBufSurfaceFromFd` 获取 `NvBufSurface*`，对每个 plane 调用 `NvBufSurfaceMap(..., NVBUF_MAP_WRITE)`，使用 `surfaceList[0].mappedAddr.addr[p]` 和 `planeParams.pitch[p]` 将 `buf->y/buf->uv` 拷贝到 NV12 源表面；每个 plane 调用 `NvBufSurfaceSyncForDevice` 后 `NvBufSurfaceUnMap`。
2. 若 `free_out` 为空，调用 `output_plane.dqBuffer` 等待一个完成的 output buffer，将返回的 `v4l2_buf.index` 放回 `free_out`；不得丢弃当前帧。
3. 取 `free_out` 中的目标槽位，构造 `NvBufSurf::NvCommonTransformParams`：源矩形为 `in_width x in_height`，目标矩形为 `out_width x out_height`，`flag=NVBUFSURF_TRANSFORM_FILTER`，`filter=NvBufSurfTransformInter_Bilinear`。调用 `NvBufSurf::NvTransform(&params, src_fds[src_idx], dst_fds[out_idx])`。
4. 将源槽位立即放回 `free_src`（`NvTransform` 是同步调用）。
5. 构造 DMABUF `v4l2_buffer`，设置 index、`memory=V4L2_MEMORY_DMABUF`、timestamp；对 `getNthBuffer(out_idx)` 的每个 plane 设置 `bytesused = fmt.stride * fmt.height` 和 `m.fd = plane.fd`。按 NVIDIA `01_video_encode` 样例填充后调用 `output_plane.qBuffer`。
6. 将 `VisionIpcBufExtra` 入 `extras`，返回当前 frame counter；失败时归还槽位并返回 -1。

### Task 5：H264 NAL 分类与回调

**文件：** `jetson_nvenc_encoder.h/.cc`

实现 `classify_h264_nals`，扫描 3/4 字节起始码，读取一个字节 NAL header：

- type 7、8：参数集 bit0；
- type 1-5：VCL bit1；
- type 5：IDR bit2。

在 capture DQ 回调中根据 `is_h264` 选择 H264 或 H265 分类器。保持现有行为：无 VCL 的 buffer 只重新入队，不消费 `extras`；含 VCL 的 buffer 使用对应 extra 发布，并以 IDR 或 V4L2 keyframe 标志发布。发布后重新入队 capture buffer。

### Task 6：清理 DMABUF 资源

**文件：** `jetson_nvenc_encoder.cc`

- 沿用现有 EOS、abort、capture DQ 线程停止逻辑。
- qcam output fd 清理前，对每个 index 调 `output_plane.unmapOutputBuffers(index, dst_fds[index])`，然后调用 `NvBufSurf::NvDestroy`。
- 对 `src_fds` 调 `NvBufSurf::NvDestroy`。
- 清理应放在 encoder 对象删除前，且避免对负 fd 或已清理项重复释放。
- 主路析构路径保持原有行为。

### Task 7：切换 qcam 分派

**文件：** `openpilot/system/loggerd/encoderd.cc`

在 `make_encoder` 的 Jetson 分支中，将 `qRoadEncodeData` 与 road/wide/driver 三个主路发布名一起分派给 `JetsonNvencEncoder`；`livestream*EncodeData` 等其余编码器继续使用 `FfmpegEncoder`。

### Task 8：设备构建与功能验证

按以下顺序执行：

1. 设备构建 `encoderd`，确认无头文件、链接或 V4L2 类型错误。
2. 启动 encoderd/整机，确认同时出现主路 H265 和 `qRoadEncodeData` 的 NVENC 初始化日志。
3. 观察 `qRoadEncodeData` 发布：确认 H264 码流、宽高 526x330、CBR 约 256 kbps、GOP 15、每个 IDR 含 SPS/PPS。
4. 使用现有 qcamera.ts 消费链路或 ffprobe 检查码流可解码、时间戳连续、无 `encoderd lag` 日志。
5. 检查 road/wide 主路 H265 码流和 keyframe 行为未改变。
6. 对比 encoderd CPU 占用，确认 qcam 软编线程消失且总 CPU 明显下降。
7. 若 DMABUF 或 VIC 初始化失败，保留日志和完整错误，优先修正 stride、plane fd 或 map/unmap 顺序；不要静默回退到 FFmpeg。
