#!/usr/bin/env bash
#if [[ "$(cat /data/params/d/EnableConnect)" == "2" ]]; then
#  export API_HOST="https://api.carrotpilot.app"
#  export ATHENA_HOST="wss://athena.carrotpilot.app"
#fi

# Jetson dev/sim mode preparation: GMSL init + fake panda (when no real panda).
# Real panda hardware auto-disables the fake one; TICI/AGNOS untouched.
if [ "$(uname -m)" = "aarch64" ] && [ ! -e /TICI ]; then
  DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

  # /data/params/d must point at THIS branch's params (~/.comma), not the
  # stale sunnypilot dir (~/.commaspold): carrot services read SupportedCars*,
  # CalibrationParams etc. from /data/params/d and the UI loses settings
  # (supported cars, toggles) when it points elsewhere.
  sudo mkdir -p /data/params 2>/dev/null
  sudo ln -sfn "$HOME/.comma/params/d" /data/params/d

  # tw_camera_cfg hardcodes /dev/i2c-30..33; twgmsl mux busses register as 9..12.
  for n in 30 31 32 33; do
    [ -e /dev/i2c-$n ] || sudo ln -sf /dev/i2c-$((n-21)) /dev/i2c-$n 2>/dev/null
  done
  # SerDes/I2C 初始化由 `tw_camera_cfg` 服务模式(不带参数)完成。本机没有
  # tw-camera-bring.service;而且 bring 是 GStreamer 预览模式,会 spawn 预览
  # 管道占住 /dev/video0/1,不要用。已在运行(例如开机自启或上次启动遗留)则跳过。
  if pgrep -x tw_camera_cfg > /dev/null 2>&1; then
    echo "[camera] tw_camera_cfg 已在运行, 跳过启动"
  elif sudo -n true 2>/dev/null; then
    echo "[camera] 启动森云相机驱动 (tw_camera_cfg, serdes 初始化)..."
    sudo tw_camera_cfg > /tmp/tw_camera_cfg.log 2>&1 &
    for _ in $(seq 1 16); do
      _cam_pid=$(pgrep -xn tw_camera_cfg 2>/dev/null || true)
      if [ -n "$_cam_pid" ] && sudo lsof -p "$_cam_pid" 2>/dev/null | grep -q "/dev/i2c-9"; then
        echo "[camera] 相机驱动就绪 (i2c 已初始化)"
        break
      fi
      sleep 0.5
    done
    pgrep -x tw_camera_cfg > /dev/null 2>&1 || \
      echo "[camera] 警告: tw_camera_cfg 未起来, 黑屏时看 /tmp/tw_camera_cfg.log"
  else
    echo "[camera] 警告: 当前无免密 sudo, 无法自动拉起相机驱动; 请手动执行 sudo tw_camera_cfg"
  fi

  # Road-test default: never synthesize ignition or CAN. The fake panda can
  # only be enabled deliberately for bench testing with ENABLE_FAKE_PANDA=1.
  if [ "${ENABLE_FAKE_PANDA:-0}" = "1" ] && ! lsusb 2>/dev/null | grep -qiE "3801|bbaa|0483"; then
    if ! pgrep -f "[f]ake_panda_state" > /dev/null 2>&1; then
      echo "[sim] explicitly starting fake panda (ignition + CAN)"
      # Remove stale publisher files left by a killed previous fake panda.
      rm -f /dev/shm/msgq_pandaStates /dev/shm/msgq_can 2>/dev/null || true
      nohup "$DIR/.venv/bin/python" "$DIR/tools/sim/fake_panda_state.py" > /tmp/fake_panda.log 2>&1 &
      sleep 2
    fi
    pgrep -f "[f]ake_panda_state" > /dev/null && echo "[sim] fake panda running" || echo "[sim] WARNING: fake panda NOT running"
  elif lsusb 2>/dev/null | grep -qiE "3801|bbaa|0483"; then
    echo "[road] real panda detected; fake panda disabled"
  else
    echo "[road] fake panda disabled; waiting for real panda"
  fi

  # These are physical sensor bridges, not simulated vehicle data. Keep them
  # running for both bench and road operation.
  # Yahboom IMU on /dev/ttyTHS2 -> accelerometer/gyroscope.
  if ! pgrep -f "[s]erial_imu" > /dev/null 2>&1; then
    echo "[sensor] starting serial IMU bridge"
    nohup "$DIR/.venv/bin/python" "$DIR/tools/sim/serial_imu.py" > /tmp/serial_imu.log 2>&1 &
    sleep 2
  fi
  pgrep -f "[s]erial_imu" > /dev/null && echo "[sensor] serial IMU running" || echo "[sensor] WARNING: serial IMU NOT running"

  # 4G-module GPS (NMEA on /dev/ttyUSB1) -> gpsLocationExternal.
  if ! pgrep -f "[s]erial_gps" > /dev/null 2>&1; then
    echo "[sensor] starting serial GPS bridge"
    nohup "$DIR/.venv/bin/python" "$DIR/tools/sim/serial_gps.py" > /tmp/serial_gps.log 2>&1 &
    sleep 1
  fi
  pgrep -f "[s]erial_gps" > /dev/null && echo "[sensor] serial GPS running" || echo "[sensor] WARNING: serial GPS NOT running"
fi

exec ./launch_chffrplus.sh
