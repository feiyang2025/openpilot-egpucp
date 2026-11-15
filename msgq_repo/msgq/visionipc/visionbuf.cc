#include "msgq/visionipc/visionbuf.h"

#include <atomic>
#include <stdio.h>
#include <fcntl.h>
#include <assert.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/types.h>

std::atomic<int> offset = 0;

static void *malloc_with_fd(size_t len, int *fd) {
  char full_path[0x100];

#ifdef __APPLE__
  snprintf(full_path, sizeof(full_path)-1, "/tmp/visionbuf_%d_%d", getpid(), offset++);
#else
  snprintf(full_path, sizeof(full_path)-1, "/dev/shm/msgq_visionbuf_%d_%d", getpid(), offset++);
#endif

  *fd = open(full_path, O_RDWR | O_CREAT, 0664);
  assert(*fd >= 0);

  unlink(full_path);

  int ret = ftruncate(*fd, len);
  assert(ret == 0);
  void *addr = mmap(NULL, len, PROT_READ | PROT_WRITE, MAP_SHARED, *fd, 0);
  assert(addr != MAP_FAILED);

  return addr;
}

void VisionBuf::allocate(size_t length) {
  this->len = length;
  this->mmap_len = this->len + sizeof(uint64_t);
  this->addr = malloc_with_fd(this->mmap_len, &this->fd);
  this->frame_id = (uint64_t*)((uint8_t*)this->addr + this->len);
}

// 接管外部 dmabuf fd 作为 visionipc 缓冲区 (perfD 零拷贝路径)。
// fd 指向的 dmabuf 必须已包含 pixel data + 尾部 frame_id (len + 8 bytes)。
// mmap 整个 len+8 区域, frame_id 指针位于 len 偏移处。
// 注意: mmap 长度必须 <= dmabuf 实际大小, 否则 NVRM dmabuf 返回 MAP_FAILED。
void VisionBuf::adopt(int fd, size_t length, size_t stride_, size_t uv_offset_) {
  this->fd = fd;
  this->len = length;
  this->stride = stride_;
  this->uv_offset = uv_offset_;
  this->mmap_len = this->len + sizeof(uint64_t);
  this->addr = mmap(NULL, this->mmap_len, PROT_READ | PROT_WRITE, MAP_SHARED, this->fd, 0);
  assert(this->addr != MAP_FAILED);
  this->frame_id = (uint64_t*)((uint8_t*)this->addr + this->len);
  // init_yuv 由调用方完成 (width/height 尚未确定)
}

void VisionBuf::import(){
  assert(this->fd >= 0);
  this->addr = mmap(NULL, this->mmap_len, PROT_READ | PROT_WRITE, MAP_SHARED, this->fd, 0);
  assert(this->addr != MAP_FAILED);

  this->frame_id = (uint64_t*)((uint8_t*)this->addr + this->len);
}

void VisionBuf::init_yuv(size_t init_width, size_t init_height, size_t init_stride, size_t init_uv_offset){
  this->width = init_width;
  this->height = init_height;
  this->stride = init_stride;
  this->uv_offset = init_uv_offset;

  this->y = (uint8_t *)this->addr;
  this->uv = this->y + this->uv_offset;
}

int VisionBuf::sync(int dir) {
  return 0;
}

int VisionBuf::free() {
  if (this->addr != nullptr) {
    int err = munmap(this->addr, this->mmap_len);
    if (err != 0) return err;
    this->addr = nullptr;
  }
  if (this->fd >= 0) {
    int err = close(this->fd);
    this->fd = -1;
    return err;
  }
  return 0;
}

uint64_t VisionBuf::get_frame_id() {
  return *frame_id;
}

void VisionBuf::set_frame_id(uint64_t id) {
  *frame_id = id;
}
