#!/usr/bin/env python3
# DISPLAY 兜底必须在 import 之前:pyray/EGL 在 import 时就初始化,
# 若此处未设而环境缺失,GLFW 连默认 :0(NVIDIA X)会失败 → UI 卡死无窗口。
# 串流/无物理屏场景统一连 :99(Xvfb,raylib 已验证可初始化)。
import os
import re

if not os.environ.get("DISPLAY"):
  os.environ["DISPLAY"] = ":0"

# UI 尺寸兜底:manager fork 丢 UI_WIDTH/UI_HEIGHT/SCALE 时,从 launch_env.sh 恢复
def _env_fallback(name: str, default: str) -> str:
  if os.environ.get(name):
    return os.environ[name]
  try:
    with open("/data/openpilot/launch_env.sh") as f:
      for line in f:
        m = re.match(r"export\s+%s=\"?([^\"]+)\"?$" % name, line.strip())
        if m:
          return m.group(1).strip()
  except Exception:
    pass
  return default

os.environ.setdefault("BIG", _env_fallback("BIG", "0"))
os.environ.setdefault("UI_WIDTH", _env_fallback("UI_WIDTH", "1024"))
os.environ.setdefault("UI_HEIGHT", _env_fallback("UI_HEIGHT", "600"))
os.environ.setdefault("SCALE", _env_fallback("SCALE", "1.0"))

import gc

from openpilot.system.hardware import TICI
from openpilot.common.realtime import set_core_affinity
from openpilot.selfdrive.ui.carrot_ui_sched import ensure_ui_sched_other
from openpilot.system.ui.lib.application import gui_app
from openpilot.selfdrive.ui.layouts.main import MainLayout
from openpilot.selfdrive.ui.mici.layouts.main import MiciMainLayout
from openpilot.selfdrive.ui.ui_state import ui_state

BIG_UI = gui_app.big_ui()


def main():
  cores = {5, }
  # UI는 상시 SCHED_OTHER — 비RT UI는 core5의 radard(FIFO51)를 절대
  # 선점하지 못하므로 주행 프로세스가 항상 우선한다 (기존 FIFO51 UI는
  # radard와 같은 우선순위로 core5를 점유해 20Hz cadence를 위협). FIFO 승격 재도입
  # 금지, core7은 modeld+plannerd+dmonitoringmodeld 전용이라 UI 재배치도 금지.
  # GC는 계속 끈다 — 기존 config_realtime_process가 하던 GC pause(프레임
  # 히치) 방지는 유지해야 한다.
  gc.disable()
  # TICI offroad power-save는 big core4~7을 offline한다 — always_run UI는
  # 항상 online인 core0에서 부트스트랩하고, onroad에서 core5가 online되면
  # 아래 render loop가 best-effort로 re-affine한다 (실패는 삼키고 다음
  # 프레임에 재시도).
  set_core_affinity([0])
  # SCHED_OTHER 계약 명시 적용 + readback 검증 (실패는 fail-stop)
  ensure_ui_sched_other()

  gui_app.init_window("UI")
  if BIG_UI:
    MainLayout()
  else:
    MiciMainLayout()

  for should_render in gui_app.render():
    ui_state.update()
    if should_render:
      # reaffine after power save offlines our core
      if TICI and os.sched_getaffinity(0) != cores:
        try:
          set_core_affinity(list(cores))
        except OSError:
          pass


if __name__ == "__main__":
  main()
