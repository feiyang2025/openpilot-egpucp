#!/usr/bin/env bash
# Sim-mode stack: real GMSL cameras, fake panda (ignition), no hardware panda.
# Stop with: tmux kill-session -t opsim
set -e
cd /data/openpilot
export PATH="$HOME/.local/bin:$PATH"
source .venv/bin/activate

# tw_camera_cfg MUST keep running (its warning: exiting breaks the cameras).
# It needs /dev/i2c-30..33; on this box the twgmsl mux busses are i2c-9..12.
for n in 30 31 32 33; do
  [ -e /dev/i2c-$n ] || sudo ln -sf /dev/i2c-$((n-21)) /dev/i2c-$n
done
if ! pgrep -x tw_camera_cfg > /dev/null; then
  echo "[sim_stack] starting tw_camera_cfg"
  sudo bash -c "cd / && nohup tw_camera_cfg > /dev/null 2>&1 &"
  sleep 8
fi
pgrep -x tw_camera_cfg > /dev/null && echo "[sim_stack] tw_camera_cfg running" || echo "[sim_stack] WARNING: tw_camera_cfg NOT running"

export PASSIVE="0"
export NOBOARD="1"
export SIMULATION="1"
export SKIP_FW_QUERY="1"
export FINGERPRINT="TOYOTA_COROLLA_TSS2"
# camerad/loggerd/encoderd: camera pipeline is Qualcomm-UAPI-only (spectra.cc
# asserts on qcom device paths) -> unusable on Jetson; same on-road. Match the
# official sim BLOCK list so the stack runs quiet and stable.
# dmonitoringmodeld/dmonitoringd: USE_WEBCAM=1 enables them, but no driver cam
# is configured (DRIVER_CAM unset) -> block them.
export BLOCK="camerad,loggerd,encoderd,micd,logmessaged,manage_athenad,dmonitoringmodeld,dmonitoringd"

# Use the Python webcamerad instead: it reads the GMSL camera via OpenCV and
# publishes roadCameraState + vision stream, which unblocks modeld (it waits
# for camerad streams). video0/1 = 1920x1080 cam (works); video2/3 = 1920x1536
# cam currently does NOT deliver frames (stream read blocks) - do not enable
# WIDE_CAM until that link is fixed.
export USE_WEBCAM="1"
export ROAD_CAM="0"
# Modeld warp table only has (1344,760) and (1928,1208) precompiled inputs;
# 1344x760 matches the 1920x1080 cam aspect (16:9) so resize is undistorted.
export CAM_WIDTH="1344"
export CAM_HEIGHT="760"
# IMX390 default exposure is dim; brighten the webcam stream for the UI.
export CAM_BRIGHTNESS="2.0"

# UI: 1920x1200 monitor. Keep the 2160x1080 big-UI design canvas and scale it
# down uniformly (1920/2160) so everything fits on screen; window ends up
# 1920x960 (window manager places it below the title bar, well inside 1200).
export BIG="1"
export SCALE="0.889"
export DISPLAY=":0"

python3 -c "from openpilot.selfdrive.test.helpers import set_params_enabled; set_params_enabled()"
cd openpilot/system/manager && exec ./manager.py