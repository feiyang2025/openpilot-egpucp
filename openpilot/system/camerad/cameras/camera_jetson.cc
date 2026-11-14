// Jetson (Tegra) GMSL IMX390 摄像头实现 —— 零拷贝采集链路
//
// 硬件链路: IMX390模组(内置ISP, 输出UYVY) -> MAX9295A -> MAX9296A -> Tegra VI (tegra-video/twgmsl)
// 设备节点: /dev/video0 = 45度(road)摄像头, /dev/video1 = 185度(wide)摄像头 (vi-output)
//
// 零拷贝数据流(每帧):
//   1. V4L2 MMAP 捕获: VI DMA 直接写入捕获缓冲区 (零CPU拷贝)
//   2. VIDIOC_EXPBUF 导出 dmabuf fd
//   3. NvBufSurfaceImport(SURFACE_ARRAY) 包装捕获 dmabuf (每个buffer缓存一次, 重复Import会被NVRM拒绝)
//   4. NvBufSurfTransform: VIC 2D硬件引擎 UYVY(4:2:2)->NV12(4:2:0) 色度降采样 (dmabuf->NVMM dmabuf, 零CPU)
//   5. perfD 零拷贝: VIC 直接写入 visionipc dmabuf (NV12 pitch 2048, CAM_H+2 行, 尾部 8 字节
//      存 frame_id), 经 Unix socket SCM_RIGHTS 传 fd 给消费端, 全程零 CPU 拷贝。
//      分配失败回退旧路径: NVMM 中间层 -> CUDA kernel (~366us) / CPU memcpy (~514us) 写 shm。
//
// 平台差异说明(相对 TICI/camera_qcom2.cc):
//   - Tegra 内核(6.8)无 /dev/ion、无 /dev/dma_heap, Qualcomm Spectra ISP/cam_req_mgr 均不存在,
//     因此本文件完全不依赖 spectra/cdm/高通内核头, 为独立实现。
//   - 曝光/增益通过标准 V4L2 ctrl (gain: 1-481 step3, exposure: 30-660001 us) 闭环控制。
//   - 分辨率 1920x1080@30 全链路统一 (modeld warp / 内参 / 编码): 优先模组原生 1080p 采集,
//     不支持则回退 1920x1200 采集 + VIC transform 中心裁剪到 1080 (上下各去 60 行, 与
//     色度转换同次完成, 零额外开销)。

#include "system/camerad/cameras/camera_common.h"

#include <poll.h>
#include <algorithm>
#include <cmath>
#include <cstring>

// === 相机断链自动恢复 (三级) ===
// L1: V4L2 层重建 (fd/buffer/src_surf), 覆盖 tegra-video 的"poll 有事件但 DQBUF EAGAIN"病态。
// L2: V4L2 重建连续失败 N 次后 -> 释放全部捕获层 + 重启 twgmsl bring (GMSL serdes 重新
//     lock, 物理拔插/重新上电后无需整机重启即可恢复)。带 60s 退避。
// L3: 仍不恢复 -> 永久释放该相机捕获层 (retired), 杜绝 uncorr_err 风暴引发整机看门狗重启,
//     以慢节奏 (5 min) 持续重试。
// L4: (可选, 默认关) CAMERA_AUTO_REBOOT=1 时, 持续 CAMERA_REBOOT_AFTER_MS 无帧 -> 受控重启。
static constexpr double CAMERA_STALL_RECOVER_MS = 3000.;
static constexpr double CAMERA_REINIT_BACKOFF_MS = 2000.;
static constexpr int    CAMERA_V4L2_RETRIES_BEFORE_BRING = 3;
static constexpr double CAMERA_BRING_BACKOFF_MS = 60000.;   // bring 重启的最小间隔
static constexpr double CAMERA_RETIRED_RETRY_MS = 300000.;  // retired 后慢速重试间隔
static constexpr double CAMERA_BRING_BOOT_MS = 30000.;      // bring 重启后等 GMSL lock 的时间
static constexpr double CAMERA_RETIRE_AFTER_MS = 90000.;    // bring 后 90s 仍无帧则 retired
static constexpr double CAMERA_REBOOT_AFTER_MS = 900000.;   // L4: 15 分钟无帧才受控重启
static bool camera_auto_reboot_enabled() {
  const char *v = getenv("CAMERA_AUTO_REBOOT");
  return v != nullptr && strcmp(v, "1") == 0;
}

// 跨相机的 bring 重启状态 (同一次 bring 重启只做一轮)
static double g_bring_restart_tms = 0.;
static int    g_bring_restarts = 0;      // 已完成的 bring 重启次数
static bool   g_bring_pending = false;   // 已下发 bring 重启, 等待 lock
static double g_bring_wait_until = 0.;
static double g_stall_epoch_tms = 0.;    // 首次出现任意相机断链的时刻, 用于 L4
#include <fcntl.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <linux/v4l2-controls.h>
#include <linux/videodev2.h>

#include <algorithm>
#include <cassert>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

#include "nvbufsurface.h"
#include "nvbufsurftransform.h"

#include "cereal/messaging/messaging.h"
#include "common/params.h"
#include "common/swaglog.h"
#include "common/timing.h"
#include "common/util.h"
#include "system/camerad/cameras/nv12_info.h"
#include "system/camerad/cameras/camera_jetson_cuda.h"

// Tegra VI 捕获缓冲区数量: VIC 转换 + 拷贝 + 发布总耗时 < 5ms << 33ms 帧间隔, 8 个保证不欠载
const int V4L2_BUF_COUNT = 8;
const int CAM_W = 1920;
const int CAM_H = 1080;  // 输出分辨率: 全链路统一 1080p (modeld warp / 内参 / 编码)
const int CAP_H_FALLBACK = 1200;  // 模组无原生 1080p 时的采集高度 (VIC 中心裁剪到 1080)

// 调试开关 (与 camera_qcom2.cc 保持一致语义)
const bool env_debug_frames = getenv("DEBUG_FRAMES") != nullptr;
// CUDA 零拷贝 A/B 对比调试:
//   CUDA_ZC_OFF  -> 强制 CPU 按行 memcpy 路径 (对比 GPU kernel 正确性)
//   CUDA_ZC_DUMP -> 导出前 2 帧 Y/UV 内容区到 /tmp/zc_<publish_name>_Y.bin / _UV.bin
const bool zc_force_cpu = getenv("CUDA_ZC_OFF") != nullptr;
const bool zc_dump_frames = getenv("CUDA_ZC_DUMP") != nullptr;
// CUDA_ZC_VERIFY: 前 2 帧用 CPU 映射源做同帧交叉验证 (memcmp kernel 输出 vs 期望紧凑结果),
//                 并统计前 60 帧 compact 耗时, 用于实机 A/B 正确性与性能验证。
const bool zc_verify = getenv("CUDA_ZC_VERIFY") != nullptr;
// CUDA_ZC_CE: perfB A/B 开关 —— compact 走 CE 引擎 (cudaMemcpy2DAsync, ~240us) 而非
//             SM kernel (~540us); CE 路径同 stream 追加独立 AE 直方图 kernel, AE 行为一致。
const bool zc_use_ce = getenv("CUDA_ZC_CE") != nullptr;

// 导出帧内容区 (仅已写入的行, 不含对齐 padding, 保证 CPU/GPU 输出字节一致)
static void zc_dump_frame(const VisionBuf *vb, const char *name) {
  char path[160];
  snprintf(path, sizeof(path), "/tmp/zc_%s_Y.bin", name);
  int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
  if (fd >= 0) {
    if (write(fd, vb->y, (size_t)CAM_H * vb->stride) < 0) {}
    close(fd);
  }
  snprintf(path, sizeof(path), "/tmp/zc_%s_UV.bin", name);
  fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
  if (fd >= 0) {
    if (write(fd, vb->uv, (size_t)(CAM_H / 2) * vb->stride) < 0) {}
    close(fd);
  }
}

// twgmsl 驱动注册的私有 ctrl ID (v4l2-ctl 实测: gain=0x009a2009, exposure=0x009a200a).
// 注意: 两者位于 V4L2_CTRL_CLASS_CAMERA(0x009a0000) 类内但超出标准 V4L2_CID_CAMERA_CLASS_BASE(0x009a0900)
// 分配区, 不能用 V4L2_CID_CAMERA_CLASS_BASE+N 计算得到, 否则 S_CTRL 返回 EINVAL.
// ctrl 类型为 int64: gain 范围 1-481 (合法序列 1+3k), exposure 范围 30-660001 us.
#define JETSON_CID_GAIN      0x009a2009
#define JETSON_CID_EXPOSURE  0x009a200a

ExitHandler do_exit;

struct JetsonCameraConfig {
  const char *device_path;
  const char *publish_name;
  VisionStreamType stream_type;
};

// 45度(road)摄像头 = /dev/video0 (twgmsl 9-0028), 185度(wide)摄像头 = /dev/video1 (twgmsl 9-002a)
static const JetsonCameraConfig ALL_JETSON_CAMERA_CONFIGS[] = {
  {"/dev/video0", "roadCameraState", VISION_STREAM_ROAD},
  {"/dev/video1", "wideRoadCameraState", VISION_STREAM_WIDE_ROAD},
};

class JetsonCameraState {
public:
  JetsonCameraConfig cc;
  unique_fd fd;
  bool enabled = false;
  bool streaming = false;

  // V4L2 捕获缓冲区 (MMAP + dmabuf)
  void *mm[V4L2_BUF_COUNT] = {};
  size_t mm_len[V4L2_BUF_COUNT] = {};
  int dmabuf_fd[V4L2_BUF_COUNT] = {};
  uint32_t cap_sizeimage = 0, cap_pitch = 0;
  int cap_h = CAM_H;  // 实际采集高度: 原生 1080p 时 = CAM_H, 回退 1200 采集时 = CAP_H_FALLBACK

  // VIC 转换: src = 捕获 dmabuf 的缓存 Import
  NvBufSurface *src_surf[V4L2_BUF_COUNT] = {};
  // perfD: VIC 直写 visionipc dmabuf (零拷贝)。每个 visionipc buffer 对应一个 NvBufSurface。
  // 分配 CAM_H+2 行 (预留 2 行给 frame_id 尾部), stride 由 NvBufSurface 分配器决定 (实测 2048)。
  // vic_surfs[i] 为 nullptr 表示 perfD 不可用, 回退旧路径 (nvmm_dst + GPU kernel / CPU memcpy)。
  NvBufSurface *vic_surfs[VIPC_BUFFER_COUNT] = {};
  int vic_fds[VIPC_BUFFER_COUNT] = {};  // 每个 surface 的 dmabuf fd (传给 visionipc)
  bool perfd_enabled = false;            // perfD 零拷贝是否激活

  // 旧路径: 单一 NVMM NV12 中间层 + GPU kernel / CPU memcpy 到 visionipc shm
  NvBufSurface *nvmm_dst = nullptr;
  NvBufSurfTransformParams transform_params = {};
  NvBufSurfTransformRect src_rect = {}, dst_rect = {};

  // NVMM NV12 CPU 映射地址 (pitch 2048, 硬件256对齐)
  uint8_t *nvmm_y = nullptr, *nvmm_uv = nullptr;
  uint32_t nvmm_pitch = 0, nvmm_y_height = 0, nvmm_uv_height = 0;
  // UV plane 在 dmabuf 内的真实偏移 (planeParams.offset[1])。
  // 注意: CUDA kernel 必须用此偏移, 不能用 CPU 映射指针差 (nvmm_uv - nvmm_y),
  //       NvBufSurfaceMap 对两个 plane 独立 mmap 时指针差与 buffer 内偏移无关。
  uint32_t nvmm_uv_offset = 0;

  // visionipc Venus 布局
  VisionIpcServer *vipc_server = nullptr;
  uint32_t stride = 0, y_height = 0, uv_height = 0, yuv_size = 0, uv_offset = 0;
  Rect ae_rect = {};

  // CUDA 零拷贝: GPU kernel 直写 visionipc shm, 替代 CPU 按行 memcpy (见 camera_jetson_cuda.cu)
  bool cuda_enabled = false;
  void *cuda_src_dev = nullptr;  // VIC 输出 dmabuf 的设备指针 (cudaImportExternalMemory)
  struct CudaBufMap {
    VisionBuf *vb = nullptr;
    void *dev_y = nullptr, *dev_uv = nullptr;  // 每 buffer 一次 hostRegister 的映射缓存
  };
  CudaBufMap cuda_bufs[VIPC_BUFFER_COUNT];
  // verify 模式的简易耗时统计
  uint32_t cuda_time_n = 0;
  double cuda_time_sum_us = 0;

  std::unique_ptr<PubMaster> pm;
  uint32_t frame_id = 0;

  // 自动曝光 (v4l2 ctrl 闭环)
  int64_t exposure_us = 33334;  // 默认 1/30s 满积分
  int64_t gain = 1;
  float measured_grey_fraction = 0.125f, target_grey_fraction = 0.125f;

  int camera_open(VisionIpcServer *v);
  void start_stream();
  bool process_frame();

  // === 断链自动恢复 ===
  // 相机线松动/GMSL 链路抖动时, tegra-video 可能进入 "poll 说有事件但 DQBUF 返回
  // EAGAIN" 的病态状态, 帧永不恢复, 只能重启整栈。这里按"连续 N 秒无帧"做相机级
  // 看门狗: 只重建该相机的 V4L2 层 (fd/buffer/src_surf), 保留 visionipc 的
  // vic_surfs 与 vipc_server 不变, 因此 modeld/encoderd 的客户端连接不受影响。
  double last_frame_tms = 0.;      // 上次成功 DQBUF 的时刻 (millis_since_boot)
  double stream_epoch_tms = 0.;    // 本次开流时刻, 用于"从未出过帧"的情形
  double last_reinit_tms = 0.;     // 上次重初始化时刻, 做退避
  int reinit_attempts = 0;
  int v4l2_setup();                // S_FMT + REQBUFS + mmap/EXPBUF + import src_surf
  void v4l2_teardown();            // STREAMOFF + 释放 capture 层 (不动 vic_surfs)
  bool v4l2_reinit();              // 关闭重开设备并重新配置, 失败返回 false
  bool released = false;           // capture 层已释放 (停止轮询/DQBUF, 避免 VI 错误风暴)
  void release_capture();          // 长期失败: 停流+关闭, 由看门狗周期性尝试恢复

  void send_state(const struct v4l2_buffer &buf);
  void set_camera_exposure(float grey_frac);
  float measure_grey_fraction(const VisionBuf *vb) const;
  void camera_close();
};

int JetsonCameraState::camera_open(VisionIpcServer *v) {
  vipc_server = v;

  fd = HANDLE_EINTR(open(cc.device_path, O_RDWR | O_NONBLOCK));
  if (fd < 0) {
    LOGE("failed to open camera device %s (errno=%d: %s)", cc.device_path, errno, strerror(errno));
    return -1;
  }

  struct v4l2_capability cap = {};
  if (HANDLE_EINTR(ioctl(fd, VIDIOC_QUERYCAP, &cap)) != 0) {
    LOGE("VIDIOC_QUERYCAP failed on %s (errno=%d)", cc.device_path, errno);
    return -1;
  }
  LOGD("camera %s: driver=%s card=%s", cc.device_path, cap.driver, cap.card);

  if (v4l2_setup() != 0) return -1;
  transform_params.dst_rect = &dst_rect;

  // === perfD: VIC 直写 visionipc dmabuf (零拷贝) ===
  // 为每个 visionipc buffer 分配 NvBufSurface (NV12, CAM_H+2 行, 预留 2 行给 frame_id 尾部)。
  // SURFACE_ARRAY 的 dmabuf fd 可按 dataSize 长度原生 mmap (probe 实测: mmap 长度必须
  // <= dmabuf 大小, 故 len = dataSize - 8, frame_id 在尾部 8 字节), client 端 import()
  // 同样原生 mmap, 无需任何改动。VIC transform 直接写这些 dmabuf, 消除 NVMM→shm 拷贝;
  // 分配失败则回退旧路径 (单一 nvmm_dst + GPU kernel / CPU memcpy)。
  {
    NvBufSurfaceAllocateParams ap = {};
    ap.params.width = CAM_W;
    ap.params.height = CAM_H + 2;  // 预留 2 行给 frame_id
    ap.params.colorFormat = NVBUF_COLOR_FORMAT_NV12;
    ap.params.layout = NVBUF_LAYOUT_PITCH;
    ap.params.memType = NVBUF_MEM_SURFACE_ARRAY;

    bool alloc_ok = true;
    int vipc_fds[VIPC_BUFFER_COUNT] = {};
    for (int i = 0; i < VIPC_BUFFER_COUNT; i++) {
      vipc_fds[i] = -1;
      if (NvBufSurfaceAllocate(&vic_surfs[i], 1, &ap) != 0) {
        LOGE("NvBufSurfaceAllocate(perfD buf %d) failed for %s", i, cc.device_path);
        alloc_ok = false;
        break;
      }
      const NvBufSurfaceParams *sp = &vic_surfs[i]->surfaceList[0];
      vic_fds[i] = (int)sp->bufferDesc;
      if (vic_fds[i] < 0) {
        LOGE("perfD buf %d: invalid dmabuf fd %d for %s", i, vic_fds[i], cc.device_path);
        alloc_ok = false;
        break;
      }
      // dup 给 visionipc: fd 所有权分离 (VisionBuf::free 关 dup, NvBufSurfaceDestroy 关原始 fd)
      vipc_fds[i] = dup(vic_fds[i]);
      if (vipc_fds[i] < 0) {
        LOGE("perfD buf %d: dup fd failed for %s (errno=%d)", i, cc.device_path, errno);
        alloc_ok = false;
        break;
      }
      // 记录几何参数 (所有 buffer 同参数分配, 取第一个即可)
      if (i == 0) {
        stride = sp->planeParams.pitch[0];
        uv_offset = sp->planeParams.offset[1];
        // perfD: len = dataSize - 8, 预留尾部 8 字节给 frame_id;
        // adopt/import 的 mmap 总长 = len + 8 = dataSize, 恰为 dmabuf 大小 (超长会 MAP_FAILED)
        yuv_size = sp->dataSize - sizeof(uint64_t);
        fprintf(stderr, "camera %s: perfD surface pitch=%u uv_offset=%u dataSize=%u yuv_size=%u\n",
                cc.device_path, stride, uv_offset, sp->dataSize, yuv_size);
      }
    }

    if (alloc_ok) {
      // 用 dmabuf fd 创建 visionipc 缓冲区 (adopt 原生 mmap; stride=2048, uv_offset 从 NvBufSurface 获取)
      vipc_server->create_buffers_from_fds(cc.stream_type, vipc_fds, VIPC_BUFFER_COUNT,
                                           CAM_W, CAM_H, yuv_size, stride, uv_offset);
      perfd_enabled = true;
      // O1: 向 encoderd (独立进程) 导出本流 perfD surface 的权威 map params。
      // 跨进程传的 dup fd 在本进程 nvbuf_utils 映射表中不存在, NvBufSurfaceFromFd /
      // NvTransform 前必须先 NvBufSurfaceImport; import 参数含 psize/blockheightlog2/
      // scanformat 等高成本字段, 手工推导易错, 直接用 NvBufSurfaceGetMapParams 拿
      // 分配器真实参数最稳。所有 buffer 同参分配, 写一份即可 (encoderd 侧按 stream+fd 缓存)。
      {
        NvBufSurfaceMapParams mp = {};
        if (NvBufSurfaceGetMapParams(vic_surfs[0], 0, &mp) != 0) {
          LOGE("NvBufSurfaceGetMapParams(perfD) failed for %s", cc.device_path);
        } else {
          char path[96];
          snprintf(path, sizeof(path), "/tmp/egpucp_nvbuf_s%d.bin", (int)cc.stream_type);
          int wfd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
          if (wfd >= 0) {
            if (write(wfd, &mp, sizeof(mp)) != (ssize_t)sizeof(mp)) {
              LOGE("write %s failed (errno=%d)", path, errno);
            }
            close(wfd);
          } else {
            LOGE("open %s failed (errno=%d)", path, errno);
          }
        }
      }
      fprintf(stderr, "camera %s: perfD 零拷贝启用 (stride=%u uv_offset=%u yuv_size=%u)\n",
              cc.device_path, stride, uv_offset, yuv_size);
    } else {
      // 清理已分配的 surfaces 和 dup fd, 回退旧路径
      for (int i = 0; i < VIPC_BUFFER_COUNT; i++) {
        if (vic_surfs[i] != nullptr) {
          NvBufSurfaceDestroy(vic_surfs[i]);
          vic_surfs[i] = nullptr;
        }
        if (vipc_fds[i] >= 0) close(vipc_fds[i]);
      }
      fprintf(stderr, "camera %s: perfD 分配失败, 回退旧路径\n", cc.device_path);
    }
  }

  // === 旧路径: NVMM 中间层 + GPU kernel / CPU memcpy 到 visionipc shm ===
  if (!perfd_enabled) {
    // 分配 VIC 输出: NVMM NV12 1920x1080 pitch (实际 stride 2048, 硬件 256 对齐)
    NvBufSurfaceAllocateParams ap = {};
    ap.params.width = CAM_W;
    ap.params.height = CAM_H;
    ap.params.colorFormat = NVBUF_COLOR_FORMAT_NV12;
    ap.params.layout = NVBUF_LAYOUT_PITCH;
    ap.params.memType = NVBUF_MEM_SURFACE_ARRAY;
    if (NvBufSurfaceAllocate(&nvmm_dst, 1, &ap) != 0) {
      LOGE("NvBufSurfaceAllocate(NVMM NV12 %dx%d) failed for %s", CAM_W, CAM_H, cc.device_path);
      return -1;
    }
    const NvBufSurfaceParams *dp = &nvmm_dst->surfaceList[0];
    nvmm_pitch = dp->planeParams.pitch[0];
    nvmm_y_height = dp->planeParams.height[0];
    nvmm_uv_height = dp->planeParams.height[1];
    nvmm_uv_offset = dp->planeParams.offset[1];
    LOGD("camera %s: VIC dst NV12 pitch=%u y_height=%u uv_height=%u uv_offset=%u dataSize=%u", cc.device_path,
         nvmm_pitch, nvmm_y_height, nvmm_uv_height, nvmm_uv_offset, dp->dataSize);
    if (nvmm_pitch < CAM_W || nvmm_y_height < CAM_H || nvmm_uv_height < CAM_H / 2) {
      LOGE("VIC dst NV12 geometry too small: pitch=%u y_h=%u uv_h=%u", nvmm_pitch, nvmm_y_height, nvmm_uv_height);
      return -1;
    }

    // 一次性 CPU 映射 NVMM dst (只读), 每帧仅需 SyncForCpu 刷 cache
    if (NvBufSurfaceMap(nvmm_dst, 0, -1, NVBUF_MAP_READ) != 0) {
      LOGE("NvBufSurfaceMap(VIC dst) failed for %s", cc.device_path);
      return -1;
    }
    nvmm_y = (uint8_t *)dp->mappedAddr.addr[0];
    nvmm_uv = (uint8_t *)dp->mappedAddr.addr[1];
    if (nvmm_y == nullptr || nvmm_uv == nullptr) {
      LOGE("VIC dst NV12 CPU map returned null (y=%p uv=%p)", nvmm_y, nvmm_uv);
      return -1;
    }

    // CUDA 零拷贝: 导入 VIC 输出 dmabuf (GPU kernel 直写 visionipc shm)。
    // bufferDesc 实为 dmabuf fd (zc_probe 验证); 失败不影响功能, process_frame 自动降级 CPU 路径。
    {
      int vic_fd = (int)dp->bufferDesc;
      struct stat st = {};
      bool fstat_ok = vic_fd >= 0 && fstat(vic_fd, &st) == 0 && st.st_size > 0;
      // UV 偏移解析: 优先 planeParams.offset[1]; SURFACE_ARRAY 分配器可能不填 (为0),
      // 此时回退 CPU 映射指针差, 仅当其落在 dmabuf 范围内才可信 (kernel 读取上限校验)。
      ptrdiff_t cpu_diff = (ptrdiff_t)(nvmm_uv - nvmm_y);
      if (fstat_ok && nvmm_uv_offset == 0 && cpu_diff > 0 &&
          (size_t)cpu_diff + (size_t)nvmm_pitch * (CAM_H / 2) <= (size_t)st.st_size) {
        nvmm_uv_offset = (uint32_t)cpu_diff;
      }
      bool bounds_ok = fstat_ok && nvmm_uv_offset > 0 &&
          (size_t)nvmm_uv_offset + (size_t)nvmm_pitch * (CAM_H / 2) <= (size_t)st.st_size;
      // 显性打印关键几何参数, 便于独立运行 (stderr) 时核对 dmabuf 布局
      fprintf(stderr, "camera %s: CUDA ZC probe fd=%d size=%llu pitch=%u offset1=%u cpu_diff=%td uv_offset=%u dataSize=%u bounds=%d\n",
              cc.device_path, vic_fd, fstat_ok ? (unsigned long long)st.st_size : 0ULL,
              nvmm_pitch, dp->planeParams.offset[1], cpu_diff, nvmm_uv_offset, dp->dataSize, (int)bounds_ok);
      if (fstat_ok && bounds_ok) {
        cuda_enabled = zc_cuda_init(vic_fd, st.st_size, &cuda_src_dev);
        fprintf(stderr, "camera %s: CUDA ZC init -> %s\n", cc.device_path, cuda_enabled ? "ok" : "failed");
        if (cuda_enabled) {
          LOGD("camera %s: CUDA kernel 直写启用 (dmabuf fd=%d size=%zu)", cc.device_path, vic_fd, st.st_size);
        } else {
          LOGW("camera %s: CUDA init 失败, 降级 CPU 按行 memcpy", cc.device_path);
        }
      } else {
        LOGW("camera %s: 无法获取 VIC dst dmabuf (fd=%d size=%llu uv_offset=%u), 降级 CPU 路径",
             cc.device_path, vic_fd, fstat_ok ? (unsigned long long)st.st_size : 0ULL, nvmm_uv_offset);
      }
    }

    // visionipc Venus 布局缓冲区 (1080p: stride=1920 对齐128, y_height=1088 对齐32, uv_height=544)
    auto [s, yh, uh, sz] = get_nv12_info(CAM_W, CAM_H);
    stride = s; y_height = yh; uv_height = uh; yuv_size = sz; uv_offset = stride * y_height;
    vipc_server->create_buffers_with_sizes(cc.stream_type, VIPC_BUFFER_COUNT, CAM_W, CAM_H,
                                           yuv_size, stride, uv_offset);
    LOGD("camera %s: vipc Venus layout stride=%u y_h=%u uv_h=%u size=%u", cc.device_path,
         stride, y_height, uv_height, yuv_size);
  }

  // AE 统计区域: 图像中心 2/3
  ae_rect = {CAM_W / 6, CAM_H / 6, CAM_W * 2 / 3, CAM_H * 2 / 3};

  pm = std::make_unique<PubMaster>(std::vector{cc.publish_name});
  enabled = true;
  return 0;
}

// V4L2 捕获层配置 (S_FMT/REQBUFS/mmap/EXPBUF/import + VIC rect)。
// 首次 camera_open 与断链恢复 v4l2_reinit 共用, 保证两条路径完全一致。
int JetsonCameraState::v4l2_setup() {
  // 设置捕获格式: 优先模组原生 1920x1080 UYVY@30; 不支持则回退 1920x1200 采集,
  // 由 VIC transform 中心裁剪到 1080 (src_rect 上下各去 60 行, 与色度转换同次完成, 零额外开销)。
  // 注意 V4L2 S_FMT 可能"调整"到最接近的合法格式而不报错, 必须校验返回值。
  struct v4l2_format fmt = {};
  fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  fmt.fmt.pix.width = CAM_W;
  fmt.fmt.pix.height = CAM_H;
  fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_UYVY;
  fmt.fmt.pix.field = V4L2_FIELD_NONE;
  bool fmt_ok = HANDLE_EINTR(ioctl(fd, VIDIOC_S_FMT, &fmt)) == 0 &&
                fmt.fmt.pix.width == CAM_W && fmt.fmt.pix.height == CAM_H &&
                fmt.fmt.pix.pixelformat == V4L2_PIX_FMT_UYVY;
  if (!fmt_ok) {
    fmt = {};
    fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    fmt.fmt.pix.width = CAM_W;
    fmt.fmt.pix.height = CAP_H_FALLBACK;
    fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_UYVY;
    fmt.fmt.pix.field = V4L2_FIELD_NONE;
    if (HANDLE_EINTR(ioctl(fd, VIDIOC_S_FMT, &fmt)) != 0 ||
        fmt.fmt.pix.width != CAM_W || fmt.fmt.pix.height != CAP_H_FALLBACK ||
        fmt.fmt.pix.pixelformat != V4L2_PIX_FMT_UYVY) {
      LOGE("camera %s 不支持 %dx%d 或 %dx%d UYVY, got %ux%u fourcc=%c%c%c%c", cc.device_path,
           CAM_W, CAM_H, CAM_W, CAP_H_FALLBACK, fmt.fmt.pix.width, fmt.fmt.pix.height,
           fmt.fmt.pix.pixelformat & 0xff, (fmt.fmt.pix.pixelformat >> 8) & 0xff,
           (fmt.fmt.pix.pixelformat >> 16) & 0xff, (fmt.fmt.pix.pixelformat >> 24) & 0xff);
      return -1;
    }
    cap_h = CAP_H_FALLBACK;
    LOGW("camera %s: 模组无原生 1080p, 回退 %dx%d 采集 + VIC 中心裁剪到 1080", cc.device_path, CAM_W, CAP_H_FALLBACK);
  }
  cap_sizeimage = fmt.fmt.pix.sizeimage;
  cap_pitch = fmt.fmt.pix.bytesperline;
  LOGD("camera %s: UYVY %ux%u pitch=%u sizeimage=%u", cc.device_path,
       fmt.fmt.pix.width, fmt.fmt.pix.height, cap_pitch, cap_sizeimage);

  // 请求 MMAP 捕获缓冲区 (VI DMA 直写)
  struct v4l2_requestbuffers req = {};
  req.count = V4L2_BUF_COUNT;
  req.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  req.memory = V4L2_MEMORY_MMAP;
  if (HANDLE_EINTR(ioctl(fd, VIDIOC_REQBUFS, &req)) != 0 || req.count < 2) {
    LOGE("VIDIOC_REQBUFS(%d, MMAP) failed on %s (errno=%d, count=%u)", V4L2_BUF_COUNT, cc.device_path, errno, req.count);
    return -1;
  }

  for (uint32_t i = 0; i < req.count; i++) {
    struct v4l2_buffer b = {};
    b.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    b.memory = V4L2_MEMORY_MMAP;
    b.index = i;
    if (HANDLE_EINTR(ioctl(fd, VIDIOC_QUERYBUF, &b)) != 0) {
      LOGE("VIDIOC_QUERYBUF(%u) failed on %s (errno=%d)", i, cc.device_path, errno);
      return -1;
    }
    mm[i] = mmap(NULL, b.length, PROT_READ | PROT_WRITE, MAP_SHARED, fd, b.m.offset);
    if (mm[i] == MAP_FAILED) {
      LOGE("mmap capture buffer %u failed on %s (errno=%d)", i, cc.device_path, errno);
      return -1;
    }
    mm_len[i] = b.length;

    // 导出 dmabuf, 供 VIC 导入
    struct v4l2_exportbuffer exp = {};
    exp.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    exp.index = i;
    exp.flags = O_RDWR;
    if (HANDLE_EINTR(ioctl(fd, VIDIOC_EXPBUF, &exp)) != 0) {
      LOGE("VIDIOC_EXPBUF(%u) failed on %s (errno=%d)", i, cc.device_path, errno);
      return -1;
    }
    dmabuf_fd[i] = exp.fd;

    // 每个 capture buffer 只 Import 一次并缓存 (重复 Import 同一 fd 会被 NVRM 拒绝)
    NvBufSurfaceMapParams mp = {};
    mp.num_planes = 1;
    mp.fd = (uint64_t)dmabuf_fd[i];
    mp.totalSize = cap_sizeimage;
    mp.layout = NVBUF_LAYOUT_PITCH;
    // IMX390 模组(内置ISP)经 MAX9295A/MAX9296A -> tegra-video 实际按 YUYV 字节序交付:
    // 实测原始 4:2:2 帧按 UYVY 解读整屏发绿 (U/V 与 Y 互换了位置), 按 YUYV 解读颜色正常。
    // V4L2 仅接受 UYVY 四字码, 故 S_FMT 保持 UYVY, 这里必须按数据真实字节序 (YUYV) 解释。
    // 可用 CAMERA_SRC_UYVY=1 强制按 UYVY 解释 (调试/不同模组)。
    mp.colorFormat = (getenv("CAMERA_SRC_UYVY") != nullptr) ? NVBUF_COLOR_FORMAT_UYVY : NVBUF_COLOR_FORMAT_YUYV;
    mp.memType = NVBUF_MEM_SURFACE_ARRAY;  // 唯一被接受的导入类型(SYSTEM 会被拒绝)
    mp.planes[0].width = CAM_W;
    mp.planes[0].height = cap_h;  // 采集高度 (回退时为 1200, VIC src_rect 再中心裁剪到 1080)
    mp.planes[0].pitch = cap_pitch;
    mp.planes[0].psize = cap_sizeimage;
    if (NvBufSurfaceImport(&src_surf[i], &mp) != 0) {
      LOGE("NvBufSurfaceImport(capture dmabuf %u) failed on %s", i, cc.device_path);
      return -1;
    }
  }

  // VIC 转换参数: 源中心裁剪 (原生 1080p 时 top=0 为全幅; 回退 1200 时上下各去 60 行)
  // + 双线性滤波 (4:2:2 -> 4:2:0 色度降采样), dst 恒为 CAM_W x CAM_H
  src_rect = {0, (unsigned int)(cap_h - CAM_H) / 2, (unsigned int)CAM_W, (unsigned int)CAM_H};
  dst_rect = {0, 0, (unsigned int)CAM_W, (unsigned int)CAM_H};
  transform_params.transform_flag = NVBUFSURF_TRANSFORM_FILTER;
  transform_params.transform_filter = NvBufSurfTransformInter_Bilinear;
  transform_params.src_rect = &src_rect;
  last_frame_tms = millis_since_boot();
  return 0;
}

void JetsonCameraState::start_stream() {
  if (!enabled) return;
  for (int i = 0; i < V4L2_BUF_COUNT; i++) {
    if (mm[i] == nullptr) continue;
    struct v4l2_buffer b = {};
    b.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    b.memory = V4L2_MEMORY_MMAP;
    b.index = i;
    if (HANDLE_EINTR(ioctl(fd, VIDIOC_QBUF, &b)) != 0) {
      LOGE("VIDIOC_QBUF(%d) failed on %s (errno=%d)", i, cc.device_path, errno);
    }
  }
  int type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  if (HANDLE_EINTR(ioctl(fd, VIDIOC_STREAMON, &type)) != 0) {
    LOGE("VIDIOC_STREAMON failed on %s (errno=%d)", cc.device_path, errno);
    return;
  }
  streaming = true;
  stream_epoch_tms = millis_since_boot();
  LOGD("camera %s streaming started", cc.device_path);
}

bool JetsonCameraState::process_frame() {
  struct v4l2_buffer b = {};
  b.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  b.memory = V4L2_MEMORY_MMAP;

  if (HANDLE_EINTR(ioctl(fd, VIDIOC_DQBUF, &b)) != 0) {
    if (errno == EAGAIN) return false;
    LOGE("VIDIOC_DQBUF failed on %s (errno=%d)", cc.device_path, errno);
    return false;
  }
  last_frame_tms = millis_since_boot();
  reinit_attempts = 0;

  if (env_debug_frames) {
    printf("camera %s frame %u bytesused=%u ts=%lld.%06lld\n", cc.device_path,
           b.sequence, b.bytesused, (long long)b.timestamp.tv_sec, (long long)b.timestamp.tv_usec);
  }

  // 不做软件抽帧, 按传感器原生 30fps 全量发布。
  // 试过按 V4L2 sequence 每 3 帧丢 1 帧把码率降到 20fps, 但两路相机的 sequence
  // 计数器各自起算, 相位偏移时丢的不是同一批物理帧 -> main/extra 的 SOF 时间戳
  // 相差超过 camera_sync.py 的 MAX_CAMERA_SKEW_NS(20ms) -> modeld 判丢帧且
  // prepare_only 不发布, modelV2 直接掉到 0Hz。全量发布时两路天然同步。
  // 20/30fps 的一致性由 services.py 与 loggerd 的 MAIN_FPS 对齐到 30 来保证。
  VisionBuf *vb = vipc_server->get_buffer(cc.stream_type);

  if (perfd_enabled) {
    // === perfD 零拷贝路径: VIC 直写 visionipc dmabuf ===
    // vb->idx 对应 vic_surfs[vb->idx], VIC transform 直接写入该 dmabuf。
    // 无需 GPU kernel / CPU memcpy, 无需 SyncForCpu (VIC 硬件写入对 UMA 可见)。
    if (NvBufSurfTransform(src_surf[b.index], vic_surfs[vb->idx], &transform_params) != 0) {
      LOGE("NvBufSurfTransform(perfD UYVY->NV12) failed on %s frame %u", cc.device_path, b.sequence);
      goto requeue;
    }

    // v4l2 timestamp 为 CLOCK_MONOTONIC; 车载场景不休眠, 与 CLOCK_BOOTTIME 一致
    const uint64_t ts = b.timestamp.tv_sec * 1000000000ULL + b.timestamp.tv_usec * 1000ULL;
    vb->set_frame_id(frame_id);
    VisionIpcBufExtra extra = {frame_id, ts, ts};
    vipc_server->send(vb, &extra, false);

    // AE: CPU 全采样 (perfD 下无 GPU kernel 直方图可用)
    if (frame_id % 3 == 0) {
      set_camera_exposure(measure_grey_fraction(vb));
    }

    send_state(b);
    frame_id++;
  } else {
    // === 旧路径: NVMM 中间层 + GPU kernel / CPU memcpy 到 visionipc shm ===
    // VIC 硬件转换 UYVY -> NV12 (零CPU)
    if (NvBufSurfTransform(src_surf[b.index], nvmm_dst, &transform_params) != 0) {
      LOGE("NvBufSurfTransform(UYVY->NV12) failed on %s frame %u", cc.device_path, b.sequence);
      goto requeue;
    }
    // perfA: SyncForCpu 不再每帧执行。仅 CPU 需要读 NVMM 源的路径 (CPU 兜底 memcpy /
    // verify 交叉验证) 才刷 cache; CUDA 模式 kernel 经设备映射直读 NVMM, CPU 只读
    // kernel 写好的 visionipc shm, 每帧省一次 3.7MB 范围的 cache 同步。

    {
      // NVMM(pitch 2048) -> visionipc Venus(pitch 1920): 紧凑拷贝。
      // 优先 CUDA kernel 直写 shm (~366us, 快~28%), 失败降级 CPU 按行 memcpy (~514us)。
      bool cuda_ok = false;
      uint32_t ae_hist[256] = {};  // kernel 顺带输出的 AE 直方图 (全 0 = 不可用, 回退 CPU 统计)
      if (!zc_force_cpu && cuda_enabled && cuda_src_dev != nullptr) {
        void *dev_y = nullptr, *dev_uv = nullptr;
        for (auto &e : cuda_bufs) {
          if (e.vb == vb) { dev_y = e.dev_y; dev_uv = e.dev_uv; break; }
        }
        if (dev_y == nullptr) {
          // 首次使用该 buffer: hostRegister 整个 shm (UMA 下设备指针与 host 同址), 缓存映射
          void *dy = nullptr;
          if (zc_cuda_register_shm(vb->y, yuv_size, &dy)) {
            dev_y = dy;
            dev_uv = (uint8_t *)dy + uv_offset;  // vb->uv = vb->y + uv_offset
            for (auto &e : cuda_bufs) {
              if (e.vb == nullptr) { e = {vb, dev_y, dev_uv}; break; }
            }
          }
        }
        if (dev_y != nullptr && dev_uv != nullptr) {
          auto zc_t0 = std::chrono::steady_clock::now();
          if (zc_use_ce) {
            cuda_ok = zc_cuda_compact_ce(cuda_src_dev, nvmm_pitch, nvmm_uv_offset,
                                         dev_y, dev_uv, CAM_H, CAM_H / 2,
                                         (uint32_t)ae_rect.x, (uint32_t)ae_rect.y,
                                         (uint32_t)ae_rect.w, (uint32_t)ae_rect.h, ae_hist, nullptr);
          } else {
            cuda_ok = zc_cuda_compact(cuda_src_dev, nvmm_pitch, nvmm_uv_offset,
                                      dev_y, dev_uv, CAM_H, CAM_H / 2,
                                      (uint32_t)ae_rect.x, (uint32_t)ae_rect.y,
                                      (uint32_t)ae_rect.w, (uint32_t)ae_rect.h, ae_hist, nullptr);
          }
          double zc_us = std::chrono::duration<double, std::micro>(
              std::chrono::steady_clock::now() - zc_t0).count();
          if (!cuda_ok) {
            // kernel 失败 (sync 阶段报错即 context 已被 sticky error 污染, 重试无意义):
            // 本 camera 回落 CPU 按行 memcpy, 显性打印一次根因参数, 不逐帧刷屏。
            fprintf(stderr, "camera %s: CUDA compact 失败, 本 camera 回落 CPU 按行 memcpy "
                            "(pitch=%u uv_offset=%u yuv_size=%u)\n",
                    cc.device_path, nvmm_pitch, nvmm_uv_offset, yuv_size);
            LOGW("camera %s: CUDA compact 失败, 回落 CPU 按行 memcpy", cc.device_path);
            cuda_enabled = false;
          } else if (zc_verify && cuda_time_n < 300) {
            cuda_time_sum_us += zc_us;
            if (++cuda_time_n == 300) {
              fprintf(stderr, "camera %s: CUDA compact 平均耗时 %.0f us (前 300 帧)\n",
                      cc.device_path, cuda_time_sum_us / cuda_time_n);
            }
          }
          if (cuda_ok && zc_verify && frame_id < 2) {
            // 同帧交叉验证: 拷贝完成后再 SyncForCpu 固化 CPU 视图 (实测顺序敏感: CE 引擎
            // 直读 DRAM, 先 invalidate 会得到与 CE 不同的视图; 拷贝后 sync 则双引擎全 MATCH),
            // 以 CPU 按行紧凑生成期望输出, 与 GPU 写好的 shm 内容 memcmp, 应完全一致。
            if (NvBufSurfaceSyncForCpu(nvmm_dst, 0, -1) != 0) {
              fprintf(stderr, "camera %s frame %u: CUDA verify 跳过 (SyncForCpu 失败)\n", cc.device_path, frame_id);
            } else {
            static std::vector<uint8_t> exp_y, exp_uv;
            exp_y.resize((size_t)CAM_H * stride);
            exp_uv.resize((size_t)(CAM_H / 2) * stride);
            for (uint32_t row = 0; row < CAM_H; row++) {
              memcpy(exp_y.data() + (size_t)row * stride, nvmm_y + (size_t)row * nvmm_pitch, CAM_W);
            }
            for (uint32_t row = 0; row < CAM_H / 2; row++) {
              memcpy(exp_uv.data() + (size_t)row * stride, nvmm_uv + (size_t)row * nvmm_pitch, CAM_W);
            }
            const uint8_t *py = (const uint8_t *)vb->y, *pu = (const uint8_t *)vb->uv;
            bool y_ok = memcmp(py, exp_y.data(), (size_t)CAM_H * stride) == 0;
            bool uv_ok = memcmp(pu, exp_uv.data(), (size_t)(CAM_H / 2) * stride) == 0;
            fprintf(stderr, "camera %s frame %u: CUDA verify Y=%s UV=%s\n", cc.device_path, frame_id,
                    y_ok ? "MATCH" : "DIFF", uv_ok ? "MATCH" : "DIFF");
            if (!y_ok) {
              for (size_t i = 0; i < (size_t)CAM_H * stride; i++) {
                if (py[i] != exp_y[i]) { fprintf(stderr, "  Y first diff @%zu got=%02x exp=%02x\n", i, py[i], exp_y[i]); break; }
              }
            }
            if (!uv_ok) {
              for (size_t i = 0; i < (size_t)(CAM_H / 2) * stride; i++) {
                if (pu[i] != exp_uv[i]) { fprintf(stderr, "  UV first diff @%zu got=%02x exp=%02x\n", i, pu[i], exp_uv[i]); break; }
              }
            }

            // AE 直方图交叉验证 (perfA/perfB, SM kernel 与 CE+hist 两条路径均适用):
            // CPU 按原算法从期望帧 exp_y (VIC 真实内容) 采样, kernel 从源 (pitch 2048)
            // 采样, 直方图应完全相等。
            uint32_t cpu_hist[256] = {};
            unsigned hist_samples = 0;
            const uint8_t *pix = exp_y.data();
            for (int y = ae_rect.y; y < ae_rect.y + ae_rect.h; y += 2) {
              for (int x = ae_rect.x; x < ae_rect.x + ae_rect.w; x += 2) {
                cpu_hist[pix[(y * stride) + x]]++;
                hist_samples++;
              }
            }
            bool hist_ok = memcmp(cpu_hist, ae_hist, sizeof(cpu_hist)) == 0;
            fprintf(stderr, "camera %s frame %u: CUDA AE hist %s (samples=%u)\n", cc.device_path, frame_id,
                    hist_ok ? "MATCH" : "DIFF", hist_samples);
            if (!hist_ok) {
              for (int i = 0; i < 256; i++) {
                if (cpu_hist[i] != ae_hist[i]) {
                  fprintf(stderr, "  hist first diff bin=%d cpu=%u gpu=%u\n", i, cpu_hist[i], ae_hist[i]);
                  break;
                }
              }
            }
            }  // else (verify 同步成功)
          }
        }
      }
      if (!cuda_ok) {
        // CPU 兜底路径需要读 NVMM 源: 先刷 cache 保证 CPU 视图包含 VIC 本帧写入
        if (NvBufSurfaceSyncForCpu(nvmm_dst, 0, -1) != 0) {
          LOGE("NvBufSurfaceSyncForCpu failed on %s", cc.device_path);
          goto requeue;
        }
        uint8_t *dst_y = vb->y;
        const uint8_t *src_y = nvmm_y;
        for (uint32_t row = 0; row < CAM_H; row++) {
          memcpy(dst_y + row * stride, src_y + row * nvmm_pitch, CAM_W);
        }
        uint8_t *dst_uv = vb->uv;
        const uint8_t *src_uv = nvmm_uv;
        for (uint32_t row = 0; row < CAM_H / 2; row++) {
          memcpy(dst_uv + row * stride, src_uv + row * nvmm_pitch, CAM_W);
        }
      }

      // v4l2 timestamp 为 CLOCK_MONOTONIC; 车载场景不休眠, 与 CLOCK_BOOTTIME 一致
      const uint64_t ts = b.timestamp.tv_sec * 1000000000ULL + b.timestamp.tv_usec * 1000ULL;
      vb->set_frame_id(frame_id);
      VisionIpcBufExtra extra = {frame_id, ts, ts};
      vipc_server->send(vb, &extra, false);

      // CUDA A/B 对比: 导出内容区帧 (先于 AE/状态发送, 读取本帧已写入的数据)
      if (zc_dump_frames && frame_id < 2) {
        zc_dump_frame(vb, cc.publish_name);
      }

      // 自动曝光 (每3帧一次, 补偿模组生效延迟)
      // perfA: CUDA 模式直接用 kernel 顺带输出的 AE 直方图求中值 (省去 CPU 每帧
      // ~25.6 万次 shm 采样); 直方图全 0 (设备缓冲分配失败) 或 CUDA 回落时走 CPU 全采样。
      float grey_frac;
      {
        unsigned hist_total = 0;
        for (int i = 0; i < 256; i++) hist_total += ae_hist[i];
        if (cuda_ok && hist_total > 0) {
          unsigned int lum_cur = 0;
          int lum_med = 255;
          for (; lum_med >= 0; lum_med--) {
            lum_cur += ae_hist[lum_med];
            if (lum_cur >= hist_total / 2) break;
          }
          grey_frac = lum_med / 256.0f;
        } else {
          grey_frac = measure_grey_fraction(vb);
        }
      }
      if (frame_id % 3 == 0) {
        set_camera_exposure(grey_frac);
      }

      send_state(b);
      frame_id++;
    }
  }

requeue:
  if (HANDLE_EINTR(ioctl(fd, VIDIOC_QBUF, &b)) != 0) {
    LOGE("VIDIOC_QBUF(requeue %u) failed on %s (errno=%d)", b.index, cc.device_path, errno);
  }
  return true;
}

float JetsonCameraState::measure_grey_fraction(const VisionBuf *vb) const {
  // 中心区域 1/4 采样 Y 中值 (与 camera_qcom2.cc calculate_exposure_value 同算法)
  // 每 4px 双向采样 (相对每 2px 精度足够, CPU 开销 /4)
  uint32_t lum_binning[256] = {};
  unsigned int lum_total = 0;
  const uint8_t *pix = vb->y;
  for (int y = ae_rect.y; y < ae_rect.y + ae_rect.h; y += 4) {
    for (int x = ae_rect.x; x < ae_rect.x + ae_rect.w; x += 4) {
      uint8_t lum = pix[(y * stride) + x];
      lum_binning[lum]++;
      lum_total++;
    }
  }
  if (lum_total == 0) return 0.0f;

  unsigned int lum_cur = 0;
  int lum_med = 0;
  for (lum_med = 255; lum_med >= 0; lum_med--) {
    lum_cur += lum_binning[lum_med];
    if (lum_cur >= lum_total / 2) break;
  }
  return lum_med / 256.0f;
}

void JetsonCameraState::set_camera_exposure(float grey_frac) {
  measured_grey_fraction = grey_frac;

  const float dt = 0.05f, ts_ev = 0.05f;
  const float k_ev = (dt / ts_ev) / (1.0f + dt / ts_ev);

  // 目标灰度随亮度自适应 (夜间提高目标避免噪声放大)
  float new_target_grey = std::clamp(0.4f - 0.3f * log2f(1.0f + 60.0f * (float)(exposure_us * gain) / 481.0f) / log2f(6000.0f), 0.1f, 0.4f);
  target_grey_fraction = (1.0f - k_ev) * target_grey_fraction + k_ev * new_target_grey;

  if (grey_frac <= 0.0f) return;  // 无有效数据, 保持当前曝光

  // 期望EV调整: 依据目标/实测灰度比
  float desired_ev = std::clamp((float)(exposure_us * gain) * target_grey_fraction / grey_frac,
                                30.0f * 1.0f, 660001.0f * 481.0f);

  // 优先调曝光时间, 余量不足时调增益 (低增益优先保证信噪比)
  int64_t new_exposure = std::clamp<int64_t>((int64_t)std::round(desired_ev / std::max<int64_t>(gain, 1)), 30, 660001);
  int64_t new_gain = std::clamp<int64_t>((int64_t)std::round(desired_ev / new_exposure), 1, 481);
  new_gain = (new_gain - 1 + 2) / 3 * 3 + 1;  // gain 合法序列为 1+3k (min=1 step=3, v4l2-ctl 实测)

  if (new_exposure == exposure_us && new_gain == gain) return;

  // twgmsl 的 gain/exposure ctrl 为 int64 类型, 必须通过 VIDIOC_S_EXT_CTRLS + value64 设置
  // (VIDIOC_S_CTRL 的 __s32 value 对 int64 ctrl 一律返回 EINVAL, v4l2 core 行为)
  struct v4l2_ext_control ctrls[2] = {};
  ctrls[0].id = JETSON_CID_EXPOSURE;
  ctrls[0].value64 = (__s64)new_exposure;
  ctrls[1].id = JETSON_CID_GAIN;
  ctrls[1].value64 = (__s64)new_gain;
  struct v4l2_ext_controls ecs = {};
  ecs.ctrl_class = JETSON_CID_GAIN & 0xffff0000;  // V4L2_CTRL_CLASS_CAMERA
  ecs.count = 2;
  ecs.controls = ctrls;
  if (HANDLE_EINTR(ioctl(fd, VIDIOC_S_EXT_CTRLS, &ecs)) != 0) {
    LOGE("VIDIOC_S_EXT_CTRLS(gain=%lld exposure=%lld) failed on %s (errno=%d)",
         (long long)new_gain, (long long)new_exposure, cc.device_path, errno);
    return;
  }
  LOGD("camera %s AE: grey=%.3f target=%.3f exposure=%lldus gain=%lld", cc.device_path,
       grey_frac, target_grey_fraction, (long long)new_exposure, (long long)new_gain);
  exposure_us = new_exposure;
  gain = new_gain;
}

void JetsonCameraState::send_state(const struct v4l2_buffer &b) {
  const uint64_t ts = b.timestamp.tv_sec * 1000000000ULL + b.timestamp.tv_usec * 1000ULL;

  MessageBuilder msg;
  if (cc.stream_type == VISION_STREAM_ROAD) {
    auto f = msg.initEvent().initRoadCameraState();
    f.setFrameId(frame_id);
    f.setRequestId(frame_id);
    f.setTimestampSof(ts);
    f.setTimestampEof(ts);
    f.setIntegLines((float)exposure_us);
    f.setGain((float)gain / 481.0f);
    f.setMeasuredGreyFraction(measured_grey_fraction);
    f.setTargetGreyFraction(target_grey_fraction);
    f.setSensor(cereal::FrameData::ImageSensor::IMX390);
  } else {
    auto f = msg.initEvent().initWideRoadCameraState();
    f.setFrameId(frame_id);
    f.setRequestId(frame_id);
    f.setTimestampSof(ts);
    f.setTimestampEof(ts);
    f.setIntegLines((float)exposure_us);
    f.setGain((float)gain / 481.0f);
    f.setMeasuredGreyFraction(measured_grey_fraction);
    f.setTargetGreyFraction(target_grey_fraction);
    f.setSensor(cereal::FrameData::ImageSensor::IMX390);
  }

  pm->send(cc.publish_name, msg);
}

void JetsonCameraState::v4l2_teardown() {
  if (streaming) {
    int type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    HANDLE_EINTR(ioctl(fd, VIDIOC_STREAMOFF, &type));
    streaming = false;
  }
  // 只释放 capture 层; vic_surfs (visionipc 的 dmabuf) 与 vipc_server 必须保留,
  // 否则 modeld/encoderd 的客户端 buffer 会失效。
  for (int i = 0; i < V4L2_BUF_COUNT; i++) {
    if (src_surf[i] != nullptr) {
      NvBufSurfaceDestroy(src_surf[i]);
      src_surf[i] = nullptr;
    }
    if (dmabuf_fd[i] >= 0) {
      close(dmabuf_fd[i]);
      dmabuf_fd[i] = -1;
    }
    if (mm[i] != nullptr && mm[i] != MAP_FAILED) {
      munmap(mm[i], mm_len[i]);
      mm[i] = nullptr;
      mm_len[i] = 0;
    }
  }
  if (fd >= 0) {
    close(fd);
    fd = -1;
  }
}

bool JetsonCameraState::v4l2_reinit() {
  const double now = millis_since_boot();
  last_reinit_tms = now;
  ++reinit_attempts;

  v4l2_teardown();
  // 给 GMSL serdes 链路重新 lock 的时间; 太快重开往往还是拿不到帧
  usleep(300 * 1000);

  fd = HANDLE_EINTR(open(cc.device_path, O_RDWR | O_NONBLOCK));
  if (fd < 0) {
    LOGE("camera %s 重开失败 (errno=%d: %s), %.1fs 后重试", cc.device_path, errno, strerror(errno),
         now / 1000.);
    return false;
  }

  if (v4l2_setup() != 0) {
    LOGE("camera %s 重新配置失败, 关闭后重试", cc.device_path);
    if (fd >= 0) { close(fd); fd = -1; }
    return false;
  }

  start_stream();
  if (!streaming) {
    LOGE("camera %s 重启流失败", cc.device_path);
    return false;
  }
  // 注意: 这里只代表 V4L2 配置/开流成功, 不代表传感器真的开始送帧 (VI 仍可能
  // request timed out)。重试计数只在 process_frame 真正拿到帧时复位, 否则退避
  // 永远停在 2s, 物理链路不通时会变成每 5 秒一次的无意义重连。
  last_frame_tms = millis_since_boot();
  stream_epoch_tms = last_frame_tms;
  return true;
}

void JetsonCameraState::release_capture() {
  // 释放 V4L2 捕获层: STREAMOFF + 关闭 fd。此后 VI 不再被反复 DQBUF,
  // uncorr_err 风暴停止, 整机硬件看门狗不会被触发 (实测相机死链伴随
  // 持续 uncorr_err, 数分钟后 systemd watchdog 直接重启整机)。
  // vic_surfs 与 vipc_server 保留, 恢复时可快速重建。
  v4l2_teardown();
  released = true;
  last_reinit_tms = millis_since_boot();
  LOGW("camera %s 释放捕获层 (retired), 停止 DQBUF 等待 GMSL 恢复", cc.device_path);
}

void JetsonCameraState::camera_close() {
  if (streaming) {
    int type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    HANDLE_EINTR(ioctl(fd, VIDIOC_STREAMOFF, &type));
    streaming = false;
  }
  for (int i = 0; i < V4L2_BUF_COUNT; i++) {
    if (src_surf[i] != nullptr) {
      NvBufSurfaceDestroy(src_surf[i]);
      src_surf[i] = nullptr;
    }
    if (dmabuf_fd[i] >= 0) {
      close(dmabuf_fd[i]);
      dmabuf_fd[i] = -1;
    }
    if (mm[i] != nullptr && mm[i] != MAP_FAILED) {
      munmap(mm[i], mm_len[i]);
      mm[i] = nullptr;
    }
  }
  if (perfd_enabled) {
    // perfD: 释放 18 个 visionipc dmabuf surfaces。
    // VisionBuf 持有 dup 的 fd 和 raw mmap, 由 VisionIpcServer 析构时 munmap+close;
    // dmabuf 内存由 fd/mmap 引用计数保活, 此处 Destroy 安全。
    for (int i = 0; i < VIPC_BUFFER_COUNT; i++) {
      if (vic_surfs[i] != nullptr) {
        NvBufSurfaceDestroy(vic_surfs[i]);
        vic_surfs[i] = nullptr;
      }
    }
    perfd_enabled = false;
  }
  if (nvmm_dst != nullptr) {
    // 先解绑 CUDA 映射的 shm (若有), 再释放 NVMM
    for (auto &e : cuda_bufs) {
      if (e.vb != nullptr) {
        zc_cuda_unregister_shm(e.vb->y);
        e.vb = nullptr;
        e.dev_y = e.dev_uv = nullptr;
      }
    }
    cuda_enabled = false;
    NvBufSurfaceUnMap(nvmm_dst, 0, -1);
    NvBufSurfaceDestroy(nvmm_dst);
    nvmm_dst = nullptr;
  }
}

void camerad_thread() {
  VisionIpcServer v("camerad");

  // camerad 完全不需要 X11。若进程继承了 DISPLAY (manager 从桌面 session 启动时会有),
  // NVIDIA EGL 初始化会经 libnvidia-glsi -> libX11 -> XOpenDisplay() 连接 :0,
  // 而 gdm 的 X server 未就绪/不接受新 client 时该调用会永久阻塞在 poll(),
  // 导致 camerad 卡死在 NvBufSurfTransformSetSessionParams 而永远不产出帧。
  if (getenv("DISPLAY") != nullptr) {
    LOGW("camerad: 清除继承的 DISPLAY=%s, 强制 EGL 走 headless 路径", getenv("DISPLAY"));
    unsetenv("DISPLAY");
  }
  // 同时清掉 EGL 相关变量, 避免驱动尝试连 windowing system
  unsetenv("WAYLAND_DISPLAY");

  // VIC 会话参数: 全局一次
  NvBufSurfTransformConfigParams cfg = {};
  cfg.compute_mode = NvBufSurfTransformCompute_VIC;
  if (NvBufSurfTransformSetSessionParams(&cfg) != 0) {
    LOGE("NvBufSurfTransformSetSessionParams(VIC) failed, cannot start camerad on Jetson");
    return;
  }

  std::vector<std::unique_ptr<JetsonCameraState>> cams;
  for (const auto &config : ALL_JETSON_CAMERA_CONFIGS) {
    auto cam = std::make_unique<JetsonCameraState>();
    cam->cc = config;
    int ret = cam->camera_open(&v);
    if (ret != 0) {
      LOGE("camera %s (%s) failed to open, exiting camerad", config.device_path, config.publish_name);
      cam->camera_close();
      for (auto &c : cams) c->camera_close();
      return;
    }
    cams.emplace_back(std::move(cam));
  }

  v.start_listener();

  LOG("-- Starting devices");
  for (auto &cam : cams) cam->start_stream();

  LOG("-- Dequeueing V4L2 frames");
  while (!do_exit) {
    // pollfd 与相机一一对应 (保留指针, 避免 fds 索引与 cams 顺序错位)
    struct pollfd fds[8] = {};
    JetsonCameraState *poll_cams[8] = {};
    int n = 0;
    for (auto &cam : cams) {
      if (cam->streaming && !cam->released) {
        fds[n] = {.fd = cam->fd, .events = POLLIN};
        poll_cams[n++] = cam.get();
      }
    }

    if (n > 0) {
      int ret = poll(fds, n, 200);
      if (ret < 0) {
        if (errno == EINTR || errno == EAGAIN) continue;
        LOGE("poll failed (errno=%d)", errno);
        break;
      }
      for (int i = 0; i < n; i++) {
        if (fds[i].revents & POLLIN) {
          poll_cams[i]->process_frame();
        } else if (fds[i].revents & (POLLERR | POLLNVAL)) {
          LOGE("camera %s poll error (revents=0x%x)", poll_cams[i]->cc.device_path, fds[i].revents);
        }
      }
    } else {
      // 所有相机都 retired: 不阻塞, 让看门狗按时钟慢速重试
      util::sleep_for(200);
    }

    // === 断链看门狗 (分级恢复) ===
    // L1: 该相机重建 V4L2 层 (覆盖 tegra-video "poll 有事件但 DQBUF EAGAIN" 病态)
    // L2: L1 连续失败 -> 释放断链相机捕获层 + 重启 twgmsl bring 让 GMSL serdes 重新 lock
    //     (物理拔插/重新上电后无需整机重启即可恢复)。60s 退避。
    // L3: bring 试过且过宽限期仍无帧 -> 该相机进入 retired: 停止 DQBUF, 消除 uncorr_err
    //     风暴 (实测风暴持续数分钟会触发 systemd 硬件看门狗把整机重启), 5 分钟慢速重试。
    // L4: (可选, CAMERA_AUTO_REBOOT=1) 持续 15 分钟无帧 -> 受控重启整机。
    {
      const double now_ms = millis_since_boot();

      // bring 等待期: 不做任何恢复动作, 健康的相机继续正常出帧
      bool bring_waiting = false;
      if (g_bring_pending) {
        if (now_ms < g_bring_wait_until) {
          bring_waiting = true;
        } else {
          LOGW("GMSL bring 重启完成 (第 %d 次), 重新尝试打开断链相机", g_bring_restarts);
          g_bring_pending = false;
          ++g_bring_restarts;
          for (auto &cam : cams) {
            cam->released = false;
            cam->reinit_attempts = 0;
            cam->last_reinit_tms = 0.;
          }
        }
      }

      bool any_stalled = false;
      if (!bring_waiting) {
        for (auto &cam : cams) {
          if (!cam->enabled) continue;
          const double ref = std::max(cam->last_frame_tms, cam->stream_epoch_tms);
          if (now_ms - ref < CAMERA_STALL_RECOVER_MS) continue;
          any_stalled = true;
          if (g_stall_epoch_tms <= 0.) g_stall_epoch_tms = now_ms;

          // retired: 只做 5 分钟一次的慢速重试
          if (cam->released) {
            if (now_ms - cam->last_reinit_tms < CAMERA_RETIRED_RETRY_MS) continue;
            LOGE("camera %s retired 已 %.0fs, 尝试重新打开", cam->cc.device_path, (now_ms - ref) / 1000.);
            cam->released = false;
            cam->reinit_attempts = 0;
            cam->last_reinit_tms = 0.;
          }

          // L3: L1 已耗尽 + bring 已试过 + 过了宽限期 -> 退休该相机, 停止错误风暴
          if (cam->streaming && cam->reinit_attempts >= CAMERA_V4L2_RETRIES_BEFORE_BRING &&
              g_bring_restarts > 0 && !g_bring_pending &&
              now_ms - g_bring_restart_tms > CAMERA_RETIRE_AFTER_MS) {
            LOGE("camera %s bring 后仍未恢复, 进入 retired (停止 DQBUF 错误风暴, %.0fs 后重试)",
                 cam->cc.device_path, CAMERA_RETIRED_RETRY_MS / 1000.);
            cam->release_capture();
            continue;
          }

          const double backoff = std::min(CAMERA_REINIT_BACKOFF_MS * std::pow(2.0, cam->reinit_attempts), 30000.);
          if (now_ms - cam->last_reinit_tms < backoff) continue;

          // ----- L1: V4L2 层重建 -----
          if (cam->reinit_attempts < CAMERA_V4L2_RETRIES_BEFORE_BRING) {
            LOGE("camera %s 已 %.1fs 无帧, 自动重初始化 (L1, 第 %d 次)",
                 cam->cc.device_path, (now_ms - ref) / 1000., cam->reinit_attempts + 1);
            if (cam->v4l2_reinit()) {
              LOGW("camera %s 已重新配置开流, 等待首帧", cam->cc.device_path);
            } else {
              LOGE("camera %s L1 恢复失败, 稍后重试", cam->cc.device_path);
            }
            continue;
          }

          // ----- L2: 重启 GMSL bring (全局一次, 60s 退避) -----
          if (now_ms - g_bring_restart_tms < CAMERA_BRING_BACKOFF_MS) continue;
          g_bring_restart_tms = now_ms;
          LOGE("camera %s L1 %d 次失败, 重启 GMSL bring 让 serdes 重新 lock",
               cam->cc.device_path, CAMERA_V4L2_RETRIES_BEFORE_BRING);
          // 只释放断链相机 (停止它的 DQBUF 风暴); 健康的相机继续出帧
          cam->release_capture();
          g_bring_pending = true;
          g_bring_wait_until = now_ms + CAMERA_BRING_BOOT_MS;
          const int rc = std::system("sudo -n systemctl restart twgmsl-cam");
          LOGW("systemctl restart twgmsl-cam rc=%d, %.0fs 后重新打开相机", rc,
               CAMERA_BRING_BOOT_MS / 1000.);
        }
      }
      if (!any_stalled && !g_bring_pending) g_stall_epoch_tms = 0.;

      // ----- L4: (可选) 受控重启 -----
      if (camera_auto_reboot_enabled() && any_stalled && g_stall_epoch_tms > 0. &&
          now_ms - g_stall_epoch_tms > CAMERA_REBOOT_AFTER_MS) {
        LOGE("相机断链已 %d 分钟且 bring 未能恢复, 受控重启整机 (CAMERA_AUTO_REBOOT)",
             (int)((now_ms - g_stall_epoch_tms) / 60000.));
        const int rcb = std::system("sudo -n systemctl reboot");
        (void)rcb;
      }
    }
  }

  LOG("-- closing cameras");
  for (auto &cam : cams) cam->camera_close();
}
