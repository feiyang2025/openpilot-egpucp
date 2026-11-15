#include <cassert>
#include <cstring>

#include "common/params.h"
#include "system/loggerd/loggerd.h"
#include "system/loggerd/encoder/jpeg_encoder.h"

#ifdef __TICI__
#include "system/loggerd/encoder/v4l_encoder.h"
#define Encoder V4LEncoder
#else
#ifdef JETSON_MAIN_ENCODER_NVENC
// 必须最先包含 (先于 ffmpeg_encoder.h -> encoder.h 的 vendored v4l2-controls),
// 让系统 v4l2-controls guard 先生效, 否则 v4l2_nv_extensions.h 编译报错
#include "system/loggerd/encoder/jetson_nvenc_encoder.h"
#endif
#include "system/loggerd/encoder/ffmpeg_encoder.h"
#ifdef JETSON_MAIN_ENCODER_NVENC
// Jetson: 主路 (road/wide/driver) 用 NVENC 硬编替代 FFV1 软编,
// qcam/stream 等次级编码器仍走 ffmpeg。
static std::unique_ptr<VideoEncoder> make_encoder(const EncoderInfo &encoder_info, int in_width, int in_height,
                                                  VisionStreamType stream_type) {
  if (strcmp(encoder_info.publish_name, "roadEncodeData") == 0 ||
      strcmp(encoder_info.publish_name, "wideRoadEncodeData") == 0 ||
      strcmp(encoder_info.publish_name, "driverEncodeData") == 0 ||
      strcmp(encoder_info.publish_name, "qRoadEncodeData") == 0) {
    // stream_type 供 JetsonNvencEncoder 定位 camerad 导出的跨进程 import 参数文件
    return std::make_unique<JetsonNvencEncoder>(encoder_info, in_width, in_height, (int)stream_type);
  }
  return std::make_unique<FfmpegEncoder>(encoder_info, in_width, in_height);
}
#else
#define Encoder FfmpegEncoder
#endif
#endif

ExitHandler do_exit;

struct EncoderdState {
  int max_waiting = 0;

  // Sync logic for startup
  std::atomic<int> encoders_ready = 0;
  std::atomic<uint32_t> start_frame_id = 0;
  bool camera_ready[VISION_STREAM_WIDE_ROAD + 1] = {};
  bool camera_synced[VISION_STREAM_WIDE_ROAD + 1] = {};
};

// Handle initial encoder syncing by waiting for all encoders to reach the same frame id
bool sync_encoders(EncoderdState *s, VisionStreamType cam_type, uint32_t frame_id) {
  if (s->camera_synced[cam_type]) return true;

  if (s->max_waiting > 1 && s->encoders_ready != s->max_waiting) {
    // add a small margin to the start frame id in case one of the encoders already dropped the next frame
    update_max_atomic(s->start_frame_id, frame_id + 2);
    if (std::exchange(s->camera_ready[cam_type], true) == false) {
      ++s->encoders_ready;
      LOGD("camera %d encoder ready", cam_type);
    }
    return false;
  } else {
    if (s->max_waiting == 1) update_max_atomic(s->start_frame_id, frame_id);
    bool synced = frame_id >= s->start_frame_id;
    s->camera_synced[cam_type] = synced;
    if (!synced) LOGD("camera %d waiting for frame %d, cur %d", cam_type, (int)s->start_frame_id, frame_id);
    return synced;
  }
}


void encoder_thread(EncoderdState *s, const LogCameraInfo &cam_info, bool encode_on_demand) {
  util::set_thread_name(cam_info.thread_name);

  std::vector<std::unique_ptr<VideoEncoder>> encoders;
  VisionIpcClient vipc_client = VisionIpcClient("camerad", cam_info.stream_type, false);
  Params params;

  std::unique_ptr<JpegEncoder> jpeg_encoder;

  int cur_seg = 0;
  uint64_t seg_start_ts = 0;  // E2: 当前段起始帧 timestamp_eof (ns), 时间戳判段
  bool prewarm_pending = encode_on_demand;
  while (!do_exit) {
    if (!vipc_client.connect(false)) {
      util::sleep_for(5);
      continue;
    }

    // init encoders
    if (encoders.empty()) {
      const VisionBuf &buf_info = vipc_client.buffers[0];
      LOGW("encoder %s init %zux%zu", cam_info.thread_name, buf_info.width, buf_info.height);
      assert(buf_info.width > 0 && buf_info.height > 0);

      for (const auto &encoder_info : cam_info.encoder_infos) {
#ifdef JETSON_MAIN_ENCODER_NVENC
        auto &e = encoders.emplace_back(make_encoder(encoder_info, buf_info.width, buf_info.height,
                                                     cam_info.stream_type));
#else
        auto &e = encoders.emplace_back(new Encoder(encoder_info, buf_info.width, buf_info.height));
#endif
        e->set_idle(false);
        e->encoder_open();
      }

      // Only one thumbnail can be generated per camera stream
      if (auto thumbnail_name = cam_info.encoder_infos[0].thumbnail_name) {
        jpeg_encoder = std::make_unique<JpegEncoder>(thumbnail_name, buf_info.width / 4, buf_info.height / 4);
      }
    }

    bool lagging = false;
    while (!do_exit) {
      VisionIpcBufExtra extra;
      VisionBuf* buf = vipc_client.recv(&extra);
      if (buf == nullptr) continue;

      // detect loop around and drop the frames
      if (buf->get_frame_id() != extra.frame_id) {
        if (!lagging) {
          LOGE("encoder %s lag  buffer id: %" PRIu64 " extra id: %d", cam_info.thread_name, buf->get_frame_id(), extra.frame_id);
          lagging = true;
        }
        continue;
      }
      lagging = false;

      if (!sync_encoders(s, cam_info.stream_type, extra.frame_id)) {
        continue;
      }
      if (do_exit) break;

      // Prime VIDC with one frame so firmware loading, DMA mapping, and codec
      // headers are complete before a user requests Carrot Vision.
      const bool session_active = !encode_on_demand || params.getBool("CarrotVisionActive");
      const bool idle = !session_active && !prewarm_pending;
      for (auto &e : encoders) {
        e->set_idle(idle);
      }
      if (idle) {
        continue;
      }

      // E2: 段轮转改按真实时间戳判段。camerad 现以 30fps 灌入, 原 frame_id 判据
      // (SEGMENT_LENGTH * MAIN_FPS = 60*20 = 1200 帧) 会把每段压缩到 40s。
      // 按 timestamp_eof 累计 SEGMENT_LENGTH 秒轮转, 与 camerad 帧率解耦, 段长恒为 60s。
      if (seg_start_ts == 0) {
        seg_start_ts = extra.timestamp_eof;
      }
      if (!encode_on_demand && cur_seg >= 0 &&
          extra.timestamp_eof - seg_start_ts >= (uint64_t)SEGMENT_LENGTH * 1000000000ULL) {
        LOGW("enc seg rotate: stream=%d seg=%d ts=%" PRIu64, (int)cam_info.stream_type, cur_seg + 1,
             extra.timestamp_eof);
        for (auto &e : encoders) {
          e->encoder_close();
          e->encoder_open();
        }
        ++cur_seg;
        seg_start_ts = extra.timestamp_eof;
      }

      // encode a frame
      for (int i = 0; i < encoders.size(); ++i) {
        int out_id = encoders[i]->encode_frame(buf, &extra);

        if (out_id == -1) {
          LOGE("Failed to encode frame. frame_id: %d", extra.frame_id);
        }
      }
      prewarm_pending = false;

      if (jpeg_encoder && (extra.frame_id % 1200 == 100)) {
        jpeg_encoder->pushThumbnail(buf, extra);
      }
    }
  }
}

template <size_t N>
void encoderd_thread(const LogCameraInfo (&cameras)[N], bool encode_on_demand = false) {
  EncoderdState s;

  std::set<VisionStreamType> streams;
  while (!do_exit) {
    streams = VisionIpcClient::getAvailableStreams("camerad", false);
    if (!streams.empty()) {
      break;
    }
    util::sleep_for(100);
  }

  if (!streams.empty()) {
    std::vector<std::thread> encoder_threads;
    for (auto stream : streams) {
      auto it = std::find_if(std::begin(cameras), std::end(cameras),
                             [stream](auto &cam) { return cam.stream_type == stream; });
      if (it == std::end(cameras)) {
        continue;
      }
      ++s.max_waiting;
      encoder_threads.push_back(std::thread(encoder_thread, &s, *it, encode_on_demand));
    }

    for (auto &t : encoder_threads) t.join();
  }
}

int main(int argc, char* argv[]) {
  const std::string mode = argc > 1 ? argv[1] : "";
  const bool carrot_vision_mode = mode == "--carrot-vision-road";
  if (!Hardware::PC()) {
    // Carrot Vision is optional and may drop frames. Keeping its V4L setup and
    // worker threads out of SCHED_FIFO prevents on-demand video work from
    // delaying control and camera services.
    if (!carrot_vision_mode) {
      int ret = util::set_realtime_priority(52);
      assert(ret == 0);
    }
    // Main/logging encoders keep their established core 3 placement. Keep the
    // independent Carrot Vision encoder off the UI and camera/control cores.
    int ret = util::set_core_affinity({carrot_vision_mode ? 0 : 3});
    assert(ret == 0);
  }
  if (argc > 1) {
    if (mode == "--stream") {
      encoderd_thread(stream_cameras_logged);
    } else if (carrot_vision_mode) {
      encoderd_thread(carrot_vision_cameras_logged, true);
    } else {
      LOGE("Argument '%s' is not supported", mode.c_str());
    }
  } else {
    encoderd_thread(cameras_logged);
  }
  return 0;
}
