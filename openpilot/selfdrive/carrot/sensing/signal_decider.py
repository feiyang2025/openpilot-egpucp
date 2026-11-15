#!/usr/bin/env python3
"""P4 信号灯停车决策核(台架)——灯色→动作映射(D4),全部已签判据,零发明。

判据索引:
  修订 23/§7.11: 红灯 1 帧确认即刹;绿灯须连续 3 帧 + ≥0.3 s 保持 + 车道绑定成功才放行;
      绑定失败按 unknown 处理 → 停车 MRM;灯灭 100% 停车 + MRM(不自主通行)
  §7.11 黄灯: dilemma |a|≤3.0 可停则停,不可停则通过(禁急加速抢灯)
  虚拟停车目标: 经 a_signal_stop 以 min-only 并入执行链(§7.4/P1);优先级 AEB > 信号 > 小目标
  停车带: 前保险杠净距 0.3–2.0 m;保守提前量——宁停远 2 m 不押 0.3 m
  计数: signal_unknown_stop 单列,不计入 G4 ghost 分母
  独立参数 EnableSignalStop(默认 OFF,失效安全);诚实边界: 本核为纯逻辑,tl_detd 的
  cereal 发布与 daemon 接线随影子期落地,不在本单元。
"""
GREEN_SET = ("green", "green_left", "green_right")


class SignalStopDecider:
  RED_FRAMES = 1
  GREEN_FRAMES = 3
  GREEN_HOLD_S = 0.3
  AIM_M = 2.0            # 宁停远 2 m
  BAND_MIN, BAND_MAX = 0.3, 2.0
  A_YELLOW_MAX = 3.0
  A_FLOOR_MIN = -6.0     # AEB 交接语义下限(§7.4)

  ST_PROCEED, ST_STOPPING, ST_STOPPED = "PROCEED", "STOPPING", "STOPPED"

  def __init__(self, enabled: bool = False):
    self.enabled = enabled
    self.state = self.ST_PROCEED
    self.green_n = 0
    self.green_t0 = None
    self.had_light = False
    self.counters = {"red_stops": 0, "yellow_stops": 0, "yellow_clears": 0,
                     "unknown_stops": 0, "green_gos": 0, "mrm": 0}

  def reset(self):
    self.__init__(enabled=self.enabled)

  def _a_floor(self, v_ms: float, d_stop: float | None) -> float | None:
    """虚拟停车目标 → min-only 减速度 floor(aim=净距−2.0,clamp ≥0.3)。"""
    if d_stop is None:
      return None
    d_aim = max(d_stop - self.AIM_M, self.BAND_MIN)
    return max(self.A_FLOOR_MIN, -(v_ms * v_ms) / (2.0 * d_aim))

  def update(self, obs: str | None, conf: float, d_stop: float | None,
             v_ms: float, lane_bind_ok: bool, now_s: float) -> dict:
    """obs ∈ {"red","yellow",green*},None=无观测(灯灭或无灯);d_stop=前保险杠→停止线净距。"""
    if not self.enabled:
      return {"state": self.ST_PROCEED, "reason": "disabled", "aFloor": None,
              "aim": None, "counters": dict(self.counters)}

    out = {"state": self.state, "reason": "", "aFloor": None, "aim": None}

    if obs is None:
      if self.had_light:
        # 灯灭: 100% 停车 + MRM(§7.11)
        self.state = self.ST_STOPPING
        self.counters["mrm"] += 1
        out.update(state=self.state, reason="light_off_mrm",
                   aFloor=self._a_floor(v_ms, d_stop), aim=self.AIM_M)
      elif d_stop is None:
        out.update(reason="no_signal")   # 无灯路口: 不在本单元域
      else:
        out.update(reason="no_obs_hold")
    elif obs == "red":
      self.green_n, self.green_t0 = 0, None
      if self.state != self.ST_STOPPING:
        self.counters["red_stops"] += 1
      self.state = self.ST_STOPPING
      self.had_light = True
      out.update(state=self.state, reason="red_1f",
                 aFloor=self._a_floor(v_ms, d_stop), aim=self.AIM_M)
    elif obs == "yellow":
      self.had_light = True
      can_stop = d_stop is not None and (v_ms * v_ms) / (2.0 * max(d_stop - self.BAND_MIN, 0.1)) <= self.A_YELLOW_MAX
      if can_stop:
        if self.state != self.ST_STOPPING:
          self.counters["yellow_stops"] += 1
        self.state = self.ST_STOPPING
        out.update(state=self.state, reason="yellow_dilemma_stop",
                   aFloor=self._a_floor(v_ms, d_stop), aim=self.AIM_M)
      else:
        self.state = self.ST_PROCEED
        self.counters["yellow_clears"] += 1
        out.update(state=self.state, reason="yellow_dilemma_clear")
    elif obs in GREEN_SET:
      self.had_light = True
      if not lane_bind_ok:
        # 绑定失败=unknown → 停车 MRM(修订 23)
        self.green_n, self.green_t0 = 0, None
        if self.state != self.ST_STOPPING:
          self.counters["unknown_stops"] += 1
          self.counters["mrm"] += 1
        self.state = self.ST_STOPPING
        out.update(state=self.state, reason="bind_fail_unknown_mrm",
                   aFloor=self._a_floor(v_ms, d_stop), aim=self.AIM_M)
      else:
        if self.green_n == 0:
          self.green_t0 = now_s
        self.green_n += 1
        if self.green_n >= self.GREEN_FRAMES and \
           (self.green_t0 is None or now_s - self.green_t0 >= self.GREEN_HOLD_S):
          if self.state != self.ST_PROCEED:
            self.counters["green_gos"] += 1
          self.state = self.ST_PROCEED
          out.update(state=self.state, reason="green_3f_hold_go")
        else:
          out.update(state=self.state, reason="green_counting",
                     aFloor=self._a_floor(v_ms, d_stop) if self.state == self.ST_STOPPING else None,
                     aim=self.AIM_M if self.state == self.ST_STOPPING else None)
    else:
      # 未知灯色/低置信 → unknown 停车 MRM
      if self.state != self.ST_STOPPING:
        self.counters["unknown_stops"] += 1
        self.counters["mrm"] += 1
      self.state = self.ST_STOPPING
      self.had_light = True
      out.update(state=self.state, reason="unknown_mrm",
                 aFloor=self._a_floor(v_ms, d_stop), aim=self.AIM_M)

    # 停车带收敛: v<0.1 且净距 ≤2.0 → STOPPED(只等绿灯,不自主放行)
    if self.state == self.ST_STOPPING and v_ms < 0.1 and d_stop is not None and d_stop <= self.BAND_MAX:
      self.state = self.ST_STOPPED
      out.update(state=self.state, reason="stopped_in_band")
    out["counters"] = dict(self.counters)
    return out
