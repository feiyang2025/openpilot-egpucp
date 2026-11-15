#pragma once

// CUDA kernel 直写 visionipc 共享内存的 C 接口（camera_jetson.cc 的 g++ 侧使用）。
// 实现见 camera_jetson_cuda.cu（nvcc 编译）。

#include <cstddef>

#ifdef __cplusplus
extern "C" {
#endif

// 每 camera 一次：导入 VIC 输出 dmabuf，返回可被 kernel 读取的源设备指针。
// dmabuf_fd: nvmm_dst->surfaceList[0].bufferDesc；ext_size: 实际 dmabuf 大小（dataSize/st_size）。
// 失败返回 false（调用方应降级 CPU 路径）。
bool zc_cuda_init(int dmabuf_fd, size_t ext_size, void **src_dev);

// 注册一块 visionipc 共享内存（tmpfs shm），返回设备侧指针（Orin UMA 下 kernel 必须经此访问）。
bool zc_cuda_register_shm(void *host_ptr, size_t len, void **dev_ptr);

// 每帧：把 VIC 输出 NV12(pitch=srcPitchB, 2048) 紧凑为 Venus 布局(stride=1920)，
// uvBaseB 为源 UV plane 的字节偏移（camera_jetson.cc 用 nvmm_uv-nvmm_y 实测传入）。
// AE 直方图: ae_*/hist_out 非 0/非空时，同一次 launch 顺带输出中心区域(ae_x,ae_y,ae_w,ae_h)
// 步长 2 采样的 256-bin Y 灰度直方图（与 camera_jetson.cc measure_grey_fraction 同算法，
// 区别仅是从源 buffer 采样；源与目标内容字节一致，直方图相同）。hist_out 不可用时置全 0，
// 调用方以全 0 判定回退 CPU 统计。
// 同步等待完成后返回。失败返回 false（调用方降级 CPU 按行 memcpy）。
bool zc_cuda_compact(void *src_dev, size_t srcPitchB, size_t uvBaseB,
                     void *dst_y_dev, void *dst_uv_dev,
                     int y_rows, int uv_rows,
                     uint32_t ae_x, uint32_t ae_y, uint32_t ae_w, uint32_t ae_h,
                     uint32_t *hist_out,
                     void *stream);

// perfB A/B: CE (copy engine) 路径 —— cudaMemcpy2DAsync 按 2D 行拷贝完成同样的紧凑
// (行数由 y_rows/uv_rows 运行时传入, 如 1080p: Y 1080 行 + UV 540 行, 行宽 1920B), 不经过 SM。hist_out 非空时同 stream 追加独立
// AE 直方图 kernel (与 kernel 路径输出一致)。
// 同步等待完成后返回。失败返回 false（调用方降级 CPU 按行 memcpy）。
bool zc_cuda_compact_ce(void *src_dev, size_t srcPitchB, size_t uvBaseB,
                        void *dst_y_dev, void *dst_uv_dev,
                        int y_rows, int uv_rows,
                        uint32_t ae_x, uint32_t ae_y, uint32_t ae_w, uint32_t ae_h,
                        uint32_t *hist_out,
                        void *stream);

// 注销一块 shm 内存（与 zc_cuda_register_shm 成对）。
void zc_cuda_unregister_shm(void *host_ptr);

#ifdef __cplusplus
}
#endif