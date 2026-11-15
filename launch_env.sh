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
  export AGNOS_VERSION="19.8-carrot-bt1"
fi

export STAGING_ROOT="/data/safe_staging"

# --- egpucp UI scaling for 132 touch panel (1024x600) ---
# canvas 2160x1080 x 0.474 = 1024x512; fonts hardcoded for 2160
export BIG=1
export SCALE=0.474
export UI_WIDTH=2160
export UI_HEIGHT=1080
# window joins bottom margin: 1024x600 -> 1024x512 @ y=32 (56px free below)
export UI_OFFSET_X=0
export UI_OFFSET_Y=32
# X display for the UI process (gnome session on :0); ssh-launched stacks
# inherit neither DISPLAY nor XAUTHORITY, leaving UI windowless & spin-locked
export DISPLAY=:0
export XAUTHORITY=/run/user/1000/gdm/Xauthority

# scons shim for launcher/manager (system python has no scons)
export PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.local/bin:$PATH"

# venv toolchain (arm-none-eabi-gcc etc.) appended, system python still wins
export PATH="$PATH:$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.venv/bin"

# --- JY62 / WitMotion UART IMU on Jetson AGX Orin ---
# IMU module plugged to /dev/ttyTHS2 (UART2, 115200 8N1)
export IMU_UART_PATH=/dev/ttyTHS2
export IMU_UART_BAUD=115200
