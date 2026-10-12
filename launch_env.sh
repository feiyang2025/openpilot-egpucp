#!/usr/bin/env bash

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1

# models get lower priority than ui
# - ui is ~5ms
# - modeld is 20ms
# - DM is 10ms
# in order to run ui at 60fps (16.67ms), we need to allow
# it to preempt the model workloads. we have enough
# headroom for this until ui is moved to the CPU.
export QCOM_PRIORITY=12

if [ -z "$AGNOS_VERSION" ]; then
  export AGNOS_VERSION="19.6.3-carrot"
fi

export STAGING_ROOT="/data/safe_staging"

# Ensure the repo venv is used no matter how this shell was started
# (build.py / params_check.py / recovery all call bare "python3").
if [ -f "$(dirname "${BASH_SOURCE[0]}")/.venv/bin/activate" ]; then
  source "$(dirname "${BASH_SOURCE[0]}")/.venv/bin/activate"
fi

# UI: 1920x1200 monitor -> big-UI canvas (2160x1080) scaled to fit (0.889)
export BIG="1"
export SCALE="1.0"
export UI_WIDTH="1920"
export UI_HEIGHT="1048"
# gdm 用 -displayfd 启动 Xorg,重启后 display 号会漂移(:0/:1/:2...)。
# 动态检测真实 Xorg socket(排除 X99=Xvfb 虚拟屏),避免 UI 连不上 X。
_OP_DISPLAY=""
for _sock in /tmp/.X11-unix/X*; do
  [ -S "$_sock" ] || continue
  _n="${_sock##*/X}"
  [ "$_n" = "99" ] && continue
  _OP_DISPLAY=":$_n"
  break
done
export DISPLAY="${_OP_DISPLAY:-:0}"
unset _OP_DISPLAY _sock _n

# SSH/tmux sessions do not inherit the graphical login's X cookie. Without
# this, GLFW sees the X socket but cannot initialize a monitor on the panel.
if [ -r /run/user/1000/gdm/Xauthority ]; then
  export XAUTHORITY=/run/user/1000/gdm/Xauthority
fi

# T906G desktop Xorg currently uses the modesetting provider. Do not force
# a vendor-specific GLX library here: that causes GLXBadFBConfig on this panel.
unset __GLX_VENDOR_LIBRARY_NAME
export RAYLIB_BACKEND="desktop"
#!/usr/bin/env bash
# Jetson dev/sim mode: the Qualcomm-only camerad (spectra.cc) asserts on this
# platform, so block it and use the Python webcamerad instead; fake panda
# provides ignition + CAN. Real panda hardware (TICI/AGNOS or USB panda) is
# NOT affected: these vars only apply on non-TICI aarch64 (Jetson).
if [ "$(uname -m)" = "aarch64" ] && [ ! -e /TICI ]; then
  export SKIP_FW_QUERY="1"
  export FINGERPRINT="TOYOTA_COROLLA_TSS2"
  export PASSIVE="0"
  export BLOCK="${BLOCK:+${BLOCK},}camerad,loggerd,encoderd,dmonitoringmodeld,dmonitoringd,micd,logmessaged,manage_athenad"
  export USE_WEBCAM="1"
  # 摄像头节点号由下方 resolve_cams.sh 按设备名动态解析,勿在此硬编码
  export CAM_WIDTH="1344"
  export CAM_HEIGHT="760"
  export CAM_BRIGHTNESS="1.0"
fi

# v4l2 节点号会随枚举顺序漂移,启动时按设备名动态解析(ROAD=30°/WIDE=196°/DRIVER=USB)
if [ -f "$(dirname "${BASH_SOURCE[0]}")/scripts/resolve_cams.sh" ]; then
  eval "$(bash "$(dirname "${BASH_SOURCE[0]}")/scripts/resolve_cams.sh" 2>/dev/null)"
fi
# 兜底:解析未设置时置空,webcamerad 会日志提示并跳过,不残留旧值错连
export ROAD_CAM="${ROAD_CAM:-}"
export WIDE_CAM="${WIDE_CAM:-}"
export DRIVER_CAM="${DRIVER_CAM:-}" 

# ---- AGX Orin 实验环境默认 (master-c3 适配): 相机/USE_WEBCAM/全屏/输出尺寸 ----
# 全部用 ${VAR:-default} 形式, 命令行显式赋值可覆盖。
# USE_WEBCAM=1 -> webcamerad(Python) 替代原生 camerad 二进制(未编译, FileNotFoundError)
# CAM_WIDTH/HEIGHT=1344x760 -> 原生 modeld 只认编译过的 1928x1208 / 1344x760
# BIG=1 -> raylib UI 2160x1080 自动缩放全屏 (默认是 536x240 小窗)
# ENABLE_FAKE_PANDA=1 -> 无 panda 卡时用假 panda (ignition/CAN)
export USE_WEBCAM="${USE_WEBCAM:-1}"
export ROAD_CAM="${ROAD_CAM:-0}"
export WIDE_CAM="${WIDE_CAM:-1}"
export CAM_WIDTH="${CAM_WIDTH:-1344}"
export CAM_HEIGHT="${CAM_HEIGHT:-760}"
export BIG="${BIG:-1}"
export ENABLE_FAKE_PANDA="${ENABLE_FAKE_PANDA:-1}"
