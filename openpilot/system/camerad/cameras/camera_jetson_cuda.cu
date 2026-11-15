// camera_jetson_cuda.cu —— CUDA kernel 直写 visionipc 共享内存，替代 camera_jetson.cc 里的
//                            CPU 按行 memcpy（把 VIC 输出的 2048-pitch NV12 紧凑为 Venus 1920-pitch）。
//
// 调用关系：由 camera_jetson.cc（g++ 编译）通过 camera_jetson_cuda.h 的 C 接口调用。
// 本文件由 nvcc 编译（见 camerad/SConscript）。
//
// 设计（对应 zc_probe_v8b/v8c 验证结论）：
//   - 源：VIC 输出 NvBufSurface(SURFACE_ARRAY) 的 dmabuf fd -> cudaImportExternalMemory(OpaqueFd)
//   - 目标：visionipc tmpfs(/dev/shm) 共享内存 -> cudaHostRegister(Mapped) + cudaHostGetDevicePointer
//   - kernel：单 kernel 同时搬 Y 与 UV，每线程拷 16B(uint4)，每行 1920B = 120×uint4
//   - 实测：kernel 直写 tmpfs ~366us vs CPU 按行 ~514us（快 ~28%）
//
// 编译要求（远程 Jetson aarch64）：
//   nvcc -O2 -std=c++14 -arch=sm_87 -c camera_jetson_cuda.cu -I/usr/local/cuda/include

#include <cuda_runtime.h>

#include <cstdint>
#include <cstdio>
#include <cstring>

#include "system/camerad/cameras/camera_jetson_cuda.h"

// ---------- kernel ----------
// 输入：src = VIC 输出 NV12 (pitch=srcPitchB, 每行 2048B 含 padding)
//        Y plane 第一行为偏移 0；UV plane 第一行偏移 = uvBaseB（由调用方传入实测偏移）
// 输出：dstY/dstUV = Venus 布局 (stride=1920)
__global__ void zc_compact_nv12_kernel(const uint4 *__restrict__ src, size_t srcPitchB,
                                       size_t uvBaseB,
                                       uint4 *__restrict__ dstY, uint4 *__restrict__ dstUV,
                                       int y_rows,
                                       uint32_t ae_x, uint32_t ae_y, uint32_t ae_w, uint32_t ae_h,
                                       uint32_t *__restrict__ d_hist) {
  int r = blockIdx.y;
  if (r >= y_rows) return;

  // Y 行
  const uint4 *srowY = (const uint4 *)((const char *)src + (size_t)r * srcPitchB);
  uint4 *drowY = dstY + (size_t)r * 120;  // 1920/16
  for (int t = threadIdx.x; t < 120; t += blockDim.x) {
    drowY[t] = srowY[t];
  }

  // UV 行（同块的 0..y_rows/2 内行与 Y 共用行号索引）
  if (r < y_rows / 2) {
    const uint4 *srowUV = (const uint4 *)((const char *)src + uvBaseB + (size_t)r * srcPitchB);
    uint4 *drowUV = dstUV + (size_t)r * 120;
    for (int t = threadIdx.x; t < 120; t += blockDim.x) {
      drowUV[t] = srowUV[t];
    }
  }

  // AE 灰度统计（perfA）: 中心区域步长 2 采样 256-bin Y 直方图，并入同一次 launch，
  // 算法与 camera_jetson.cc measure_grey_fraction 一致（row 为源 pitch 行，内容与目标一致）。
  // 共享内存直方图累减全局原子，仅 AE 覆盖的 ~400 行 block 参与额外开销可忽略。
  if (d_hist != nullptr && r >= (int)ae_y && r < (int)(ae_y + ae_h) && ((int)r - (int)ae_y) % 2 == 0) {
    __shared__ uint32_t smem[256];
    for (int i = threadIdx.x; i < 256; i += blockDim.x) smem[i] = 0;
    __syncthreads();
    const uint8_t *row = (const uint8_t *)src + (size_t)r * srcPitchB;
    for (uint32_t x = ae_x + threadIdx.x * 2u; x < ae_x + ae_w; x += blockDim.x * 2u) {
      atomicAdd(&smem[row[x]], 1u);
    }
    __syncthreads();
    for (int i = threadIdx.x; i < 256; i += blockDim.x) {
      atomicAdd(&d_hist[i], smem[i]);
    }
  }
}

// perfB: 独立 AE 直方图 kernel (CE 拷贝路径配套)。grid.y = ae_h/2 个采样行, block 128。
// 仅 ~256k 次 smem 原子累加, launch 开销个位数 us。
__global__ void zc_ae_hist_kernel(const uint8_t *__restrict__ src, size_t srcPitchB,
                                  uint32_t ae_x, uint32_t ae_y, uint32_t ae_w, uint32_t ae_h,
                                  uint32_t *__restrict__ d_hist) {
  int r = (int)ae_y + blockIdx.y * 2;  // 步长 2 的采样行
  __shared__ uint32_t smem[256];
  for (int i = threadIdx.x; i < 256; i += blockDim.x) smem[i] = 0;
  __syncthreads();
  const uint8_t *row = src + (size_t)r * srcPitchB;
  for (uint32_t x = ae_x + threadIdx.x * 2u; x < ae_x + ae_w; x += blockDim.x * 2u) {
    atomicAdd(&smem[row[x]], 1u);
  }
  __syncthreads();
  for (int i = threadIdx.x; i < 256; i += blockDim.x) atomicAdd(&d_hist[i], smem[i]);
}

// ---------- C 接口 ----------
extern "C" {

// 每帧直方图的 pinned-mapped 主机落地缓冲 (惰性分配一次)
static uint32_t *zc_hist_host() {
  static uint32_t *h_hist = nullptr;
  if (h_hist == nullptr) {
    if (cudaHostAlloc(&h_hist, 256 * sizeof(uint32_t), cudaHostAllocMapped) != cudaSuccess) {
      fprintf(stderr, "zc_hist_host: cudaHostAlloc(hist) failed: %s\n", cudaGetErrorString(cudaGetLastError()));
      h_hist = nullptr;
    }
  }
  return h_hist;
}

// AE 直方图设备缓冲（惰性分配, 常驻复用）: kernel 累加到设备 d_hist, 每帧经 pinned-mapped
// 主机缓冲 zc_hist_host() 拷出 (不走 pageable D2H —— 实测会周期性停顿 6-10ms)。
// 分配失败返回 nullptr 并把 hist_out 置全 0 (调用方以全 0 判定回退 CPU 统计)。
static uint32_t *zc_hist_buf(uint32_t *hist_out, cudaStream_t st) {
  static uint32_t *d_hist = nullptr;
  if (hist_out == nullptr) return nullptr;
  if (d_hist == nullptr && zc_hist_host() != nullptr) {
    cudaError_t he = cudaMalloc(&d_hist, 256 * sizeof(uint32_t));
    if (he != cudaSuccess) {
      fprintf(stderr, "zc_hist_buf: cudaMalloc(hist) failed: %s\n", cudaGetErrorString(he));
      d_hist = nullptr;
    }
  }
  if (d_hist != nullptr) {
    cudaMemsetAsync(d_hist, 0, 256 * sizeof(uint32_t), st);
  } else {
    memset(hist_out, 0, 256 * sizeof(uint32_t));
  }
  return d_hist;
}

// 每 camera 一次：注册 CUDA device（全局一次即可）+ 导入 VIC 输出 dmabuf，返回源设备指针。
// 失败返回 false。
bool zc_cuda_init(int dmabuf_fd, size_t ext_size, void **src_dev) {
  if (src_dev == nullptr) return false;
  *src_dev = nullptr;

  cudaError_t e = cudaSetDevice(0);
  if (e != cudaSuccess) {
    fprintf(stderr, "zc_cuda_init: cudaSetDevice failed: %s\n", cudaGetErrorString(e));
    return false;
  }

  cudaExternalMemoryHandleDesc desc = {};
  desc.type = cudaExternalMemoryHandleTypeOpaqueFd;  // CUDA13 无 DmaBuf 枚举，Linux 用 OpaqueFd
  desc.handle.fd = dmabuf_fd;
  desc.size = ext_size;

  cudaExternalMemory_t ext = nullptr;
  e = cudaImportExternalMemory(&ext, &desc);
  if (e != cudaSuccess) {
    fprintf(stderr, "zc_cuda_init: cudaImportExternalMemory(fd=%d) failed: %s\n", dmabuf_fd, cudaGetErrorString(e));
    return false;
  }

  cudaExternalMemoryBufferDesc bufdesc = {};
  bufdesc.offset = 0;
  bufdesc.size = ext_size;
  void *ptr = nullptr;
  e = cudaExternalMemoryGetMappedBuffer(&ptr, ext, &bufdesc);
  if (e != cudaSuccess) {
    fprintf(stderr, "zc_cuda_init: cudaExternalMemoryGetMappedBuffer failed: %s\n", cudaGetErrorString(e));
    cudaDestroyExternalMemory(ext);
    return false;
  }

  *src_dev = ptr;
  return true;
}

// 注册一块 visionipc 共享内存（tmpfs shm），映射为设备可见地址（Orin UMA 必须）。
// 返回设备侧指针（与 host 指针数值相同，但需经 GetDevicePointer 才能被 kernel 访问）。
bool zc_cuda_register_shm(void *host_ptr, size_t len, void **dev_ptr) {
  if (host_ptr == nullptr || dev_ptr == nullptr) return false;
  *dev_ptr = nullptr;

  cudaError_t e = cudaHostRegister(host_ptr, len, cudaHostRegisterMapped);
  if (e != cudaSuccess) {
    fprintf(stderr, "zc_cuda_register_shm: cudaHostRegister(%p,%zu) failed: %s\n", host_ptr, len, cudaGetErrorString(e));
    return false;
  }

  void *dptr = nullptr;
  e = cudaHostGetDevicePointer(&dptr, host_ptr, 0);
  if (e != cudaSuccess) {
    fprintf(stderr, "zc_cuda_register_shm: cudaHostGetDevicePointer failed: %s\n", cudaGetErrorString(e));
    cudaHostUnregister(host_ptr);
    return false;
  }

  *dev_ptr = dptr;
  return true;
}

// 每帧：在 stream 上执行紧凑 kernel（Y+UV 一次完成），可选顺带输出 AE 256-bin 直方图，
// 阻塞等待完成。stream 可传 nullptr: camerad 单线程调用, 用模块内缓存 stream (首次惰性创建)。
// 返回 true 成功；失败时调用方应降级回 CPU 按行 memcpy。
bool zc_cuda_compact(void *src_dev, size_t srcPitchB, size_t uvBaseB,
                     void *dst_y_dev, void *dst_uv_dev,
                     int y_rows /*1080*/, int uv_rows /*540*/,
                     uint32_t ae_x, uint32_t ae_y, uint32_t ae_w, uint32_t ae_h,
                     uint32_t *hist_out,
                     void *stream) {
  static cudaStream_t s = nullptr;
  if (s == nullptr) {
    cudaError_t ce = cudaStreamCreate(&s);
    if (ce != cudaSuccess) {
      fprintf(stderr, "zc_cuda_compact: cudaStreamCreate failed: %s\n", cudaGetErrorString(ce));
      return false;
    }
  }
  cudaStream_t st = (stream != nullptr) ? (cudaStream_t)stream : s;

  // AE 直方图设备缓冲（惰性分配, 复用; 失败时本帧置全 0, 调用方回退 CPU 统计）
  uint32_t *hist_arg = zc_hist_buf(hist_out, st);

  (void)uv_rows;  // kernel 由 y_rows 推导 UV 行数 (y_rows/2)
  dim3 grid(1, (unsigned)y_rows), block(128);
  zc_compact_nv12_kernel<<<grid, block, 0, st>>>(
      (const uint4 *)src_dev, srcPitchB, uvBaseB,
      (uint4 *)dst_y_dev, (uint4 *)dst_uv_dev, y_rows,
      ae_x, ae_y, ae_w, ae_h, hist_arg);

  if (hist_arg != nullptr) {
    cudaMemcpyAsync(zc_hist_host(), hist_arg, 256 * sizeof(uint32_t), cudaMemcpyDeviceToHost, st);
  }

  cudaError_t e = cudaStreamSynchronize(st);
  if (e != cudaSuccess) {
    fprintf(stderr, "zc_cuda_compact: kernel sync failed: %s\n", cudaGetErrorString(e));
    return false;
  }
  if (hist_arg != nullptr) {
    memcpy(hist_out, zc_hist_host(), 256 * sizeof(uint32_t));
  }
  return true;
}

// perfB A/B: CE 引擎路径。cudaMemcpy2DAsync 由拷贝引擎执行, SM 完全空闲;
// hist_out 非空时同 stream 追加一个独立 AE 直方图 kernel (与 SM kernel 路径输出一致)。
bool zc_cuda_compact_ce(void *src_dev, size_t srcPitchB, size_t uvBaseB,
                        void *dst_y_dev, void *dst_uv_dev,
                        int y_rows, int uv_rows,
                        uint32_t ae_x, uint32_t ae_y, uint32_t ae_w, uint32_t ae_h,
                        uint32_t *hist_out,
                        void *stream) {
  static cudaStream_t s = nullptr;
  if (s == nullptr) {
    cudaError_t ce = cudaStreamCreate(&s);
    if (ce != cudaSuccess) {
      fprintf(stderr, "zc_cuda_compact_ce: cudaStreamCreate failed: %s\n", cudaGetErrorString(ce));
      return false;
    }
  }
  cudaStream_t st = (stream != nullptr) ? (cudaStream_t)stream : s;

  uint32_t *hist_arg = zc_hist_buf(hist_out, st);

  // CUDA_ZC_TRACE: 分段事件计时 (copy 阶段 / hist 阶段), 前 60 帧打印, 定位耗时构成
  static bool trace = getenv("CUDA_ZC_TRACE") != nullptr;
  static cudaEvent_t ev0 = nullptr, ev1 = nullptr, ev2 = nullptr;
  if (trace && ev0 == nullptr) {
    cudaEventCreate(&ev0); cudaEventCreate(&ev1); cudaEventCreate(&ev2);
  }
  if (trace) cudaEventRecord(ev0, st);

  // hist kernel 先于 CE 拷贝: SM 经一致互联读源 (实测 CE 直读 DRAM 可能拿到 VIC 写入的
  // 陈旧视图, 帧 1 可复现 DIFF), SM 先碰源尝试把新鲜数据拉到一致点。
  if (hist_arg != nullptr) {
    zc_ae_hist_kernel<<<dim3(1, ae_h / 2), 128, 0, st>>>(
        (const uint8_t *)src_dev, srcPitchB, ae_x, ae_y, ae_w, ae_h, hist_arg);
    cudaMemcpyAsync(zc_hist_host(), hist_arg, 256 * sizeof(uint32_t), cudaMemcpyDeviceToHost, st);
  }

  const size_t row_b = 1920;  // Venus stride (= kernel 路径每行 120×uint4)
  cudaError_t e = cudaMemcpy2DAsync(dst_y_dev, row_b, src_dev, srcPitchB,
                                    row_b, (size_t)y_rows, cudaMemcpyDeviceToDevice, st);
  if (e != cudaSuccess) {
    fprintf(stderr, "zc_cuda_compact_ce: memcpy Y failed: %s\n", cudaGetErrorString(e));
    return false;
  }
  e = cudaMemcpy2DAsync(dst_uv_dev, row_b, (const char *)src_dev + uvBaseB, srcPitchB,
                        row_b, (size_t)uv_rows, cudaMemcpyDeviceToDevice, st);
  if (e != cudaSuccess) {
    fprintf(stderr, "zc_cuda_compact_ce: memcpy UV failed: %s\n", cudaGetErrorString(e));
    return false;
  }
  if (trace) cudaEventRecord(ev1, st);
  e = cudaStreamSynchronize(st);
  if (e != cudaSuccess) {
    fprintf(stderr, "zc_cuda_compact_ce: sync failed: %s\n", cudaGetErrorString(e));
    return false;
  }
  if (hist_arg != nullptr) {
    memcpy(hist_out, zc_hist_host(), 256 * sizeof(uint32_t));
  }
  if (trace) {
    cudaEventRecord(ev2, st);
    cudaEventSynchronize(ev2);
    float ms01 = 0, ms12 = 0;
    cudaEventElapsedTime(&ms01, ev0, ev1);
    cudaEventElapsedTime(&ms12, ev1, ev2);
    static int trace_n = 0;
    if (++trace_n <= 60) {
      fprintf(stderr, "zc CE trace: copy=%.0fus hist=%.0fus\n", ms01 * 1000, ms12 * 1000);
    }
  }
  return true;
}

// 注销 shm 内存
void zc_cuda_unregister_shm(void *host_ptr) {
  if (host_ptr != nullptr) cudaHostUnregister(host_ptr);
}

}  // extern "C"