"""amapnavi 的实测数据日志：把两套盲区判定的输入与中间量按行写成 JSONL。

路上跑完之后要能回答"为什么报了 / 为什么没报"，只靠体感不行。这里把
**原车前雷达**和**外挂激光雷达**两条链路的原始量、判定中间量、最终输出
都落盘，事后可以离线复盘。

写盘位置 ``/data/amapnavi_debug/``，行缓冲（断电最多丢最后一行），
按大小滚动，总量有上限。开关是 nav_params 的 ``LogDebugData``。

每行一个 JSON 对象。``ty`` 区分记录类型，字段名刻意用短名压体积：

  ty="hb"  1Hz 心跳：车速、外挂设备在线、动态盲区开关
  ty="sf"  原车前雷达单侧：``radarState.leadLeft/leadRight`` 的原始
           dRel/yRel/vRel/vLead + ``evaluate_side`` 的完整判定 + 最终标志
  ty="ld"  激光雷达单角：去抖后的 drel/vrel、``side_object_risky`` 的
           中间量、横向屏蔽、去抖计数、该角最终输出
  ty="sd"  左右两侧的聚合标志：激光侧方 / 车身 / 前侧 / 模块上报 / 实线
           （对应 UI 上每一侧画的那几个圈）

字段对照::

  sf: side  d=dRel(m)  y=yRel(m)  vr=vRel(m/s)  vl=vLead(m/s)  pre=present
      raw=判定  act=去抖后  rs=reason  cl=clearance(m)  ttc=ttc(s)
      lat=lateral(m)  ve=vEgo(m/s)  fin=最终 leftFrontBlind/rightFrontBlind

  ld: c=角(lf/lb/rf/rb)  d=drel(mm)  x=xrel(mm)  vr=vrel(m/s)
      obj=object_detected  rs=risky
      cl=clearance_m  dd=danger_dist_m  cls=closing_mps
      msk=blind_mask  stl=standstill  cnt=去抖后  fin=该角 lidar_*blind

  sd: side  ldr=激光侧方  car=车身盲区  fr=前侧盲区  bl=模块上报  lane=实线
"""

from __future__ import annotations

import json
import os
import time

LOG_DIR = "/data/amapnavi_debug"
MAX_FILE_BYTES = 32 * 1024 * 1024   # 单文件上限 32MB（约 1.5~2 小时）
MAX_FILES = 12                      # 保留最近 12 个文件（约 400MB 上限）
HEARTBEAT_S = 1.0                   # 心跳间隔
SIDE_REFRESH_S = 5.0                # 侧一级标志没变化时的补写间隔


def _num(value):
  """把可能为 None / 非有限的值转成 JSON 友好的形式。"""
  if value is None:
    return None
  try:
    out = float(value)
  except (TypeError, ValueError):
    return None
  return out if out == out and abs(out) != float("inf") else None


class DebugLogger:
  """按行写 JSONL 的实测日志器。"""

  def __init__(self, enabled: bool = False, log_dir: str = LOG_DIR):
    self.enabled = bool(enabled)
    self.dir = log_dir
    self._fh = None
    self._path = None
    self._bytes = 0
    self._last_hb = 0.0
    self._last_side = {}
    self._last_side_t = {}
    self.rows = 0

  # ---------------------------------------------------------------- 文件管理
  def _open(self) -> bool:
    try:
      os.makedirs(self.dir, exist_ok=True)
      # 同一秒内重复打开时加序号，避免覆盖
      stamp = time.strftime("%Y%m%d_%H%M%S")
      path = os.path.join(self.dir, f"amapnavi_{stamp}.jsonl")
      seq = 1
      while os.path.exists(path):
        path = os.path.join(self.dir, f"amapnavi_{stamp}_{seq}.jsonl")
        seq += 1
      self._fh = open(path, "a", encoding="utf-8", buffering=1)
      self._path = path
      self._bytes = 0
      self._prune()
      return True
    except OSError as e:
      # 写不了日志绝不能影响主循环
      print(f"debug_log: 打开 {self.dir} 失败: {e}")
      self._fh = None
      return False

  def _prune(self) -> None:
    """只保留最近 MAX_FILES 个文件，防止长期开着把磁盘写满。"""
    try:
      files = [os.path.join(self.dir, f) for f in os.listdir(self.dir)
               if f.endswith(".jsonl")]
      files.sort(key=lambda p: os.path.getmtime(p))
      for path in files[:-MAX_FILES]:
        os.remove(path)
    except OSError:
      pass

  def _rotate_if_needed(self) -> None:
    if self._bytes < MAX_FILE_BYTES:
      return
    try:
      if self._fh:
        self._fh.close()
    except OSError:
      pass
    self._fh = None
    self._open()

  def close(self) -> None:
    try:
      if self._fh:
        self._fh.close()
    except OSError:
      pass
    self._fh = None

  # ---------------------------------------------------------------- 写一行
  def _write(self, rec: dict) -> None:
    if not self.enabled:
      return
    if self._fh is None and not self._open():
      return
    try:
      line = json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
      return
    try:
      self._fh.write(line + "\n")
      self._bytes += len(line) + 1
      self.rows += 1
    except OSError as e:
      print(f"debug_log: 写入失败: {e}")
      self.close()
      return
    self._rotate_if_needed()

  # ---------------------------------------------------------------- 记录类型
  def heartbeat(self, v_ego, left_device, right_device,
                dynamic_range, dynamic_distance, now=None) -> None:
    """1Hz 心跳：确认"当时参数是什么、设备在不在"，缺了它事后没法判读。"""
    if not self.enabled:
      return
    now = time.monotonic() if now is None else now
    if now - self._last_hb < HEARTBEAT_S:
      return
    self._last_hb = now
    self._write({
      "ty": "hb",
      "t": round(now, 3),
      "ve": round(_num(v_ego) or 0.0, 2),
      "devL": int(bool(left_device)),
      "devR": int(bool(right_device)),
      "dbr": int(dynamic_range),
      "dbd": int(dynamic_distance),
    })

  def stock(self, side, lead, decision, v_ego, final=None) -> None:
    """原车前雷达单侧一帧。只在确实有目标时写，避免空行灌满文件。"""
    if not self.enabled:
      return
    present = bool(getattr(lead, "present", False)) if lead is not None else False
    if not present:
      return
    rec = {
      "ty": "sf",
      "t": round(time.monotonic(), 3),
      "side": side,
      "d": _num(getattr(lead, "dRel", None)),
      "y": _num(getattr(lead, "yRel", None)),
      "vr": _num(getattr(lead, "vRel", None)),
      "vl": _num(getattr(lead, "vLead", None)),
      "pre": 1,
      "ve": round(_num(v_ego) or 0.0, 2),
    }
    if decision is not None:
      rec.update({
        "raw": int(bool(getattr(decision, "raw", False))),
        "act": int(bool(getattr(decision, "active", False))),
        "rs": str(getattr(decision, "reason", "")),
        "cl": round(_num(getattr(decision, "clearance_m", 0.0)) or 0.0, 3),
        "ttc": _num(getattr(decision, "ttc_s", None)),
        "lat": round(_num(getattr(decision, "lateral_m", 0.0)) or 0.0, 3),
      })
    if final is not None:
      # 写入 shared_data.leftFrontBlind / rightFrontBlind 的最终值（含视觉 OR）
      rec["fin"] = int(bool(final))
    self._write(rec)

  def side(self, side, lidar_side, car_blind, front_blind,
           module_blind, lane_blind) -> None:
    """单侧的聚合盲区标志（对应 UI 上这一侧画的各个圈）。

    ``ld`` 只到角一级（lf/lb/rf/rb），这里补上侧一级的量：
      lidar_side   激光侧方（盲区合并来源里的 lidar_lblind/rblind）
      car_blind    车身盲区（body_blind，由四角距离算）
      front_blind  前侧盲区（原车前雷达+视觉，即 sf 的 fin）
      module_blind 模块上报的 left_blind / right_blind
      lane_blind   实线（laneBlindL/R）
    """
    if not self.enabled:
      return
    flags = (int(bool(lidar_side)), int(bool(car_blind)), int(bool(front_blind)),
             int(bool(module_blind)), int(bool(lane_blind)))
    now = time.monotonic()
    # 这些标志很少变化：只在变化时写，另外每隔 SIDE_REFRESH_S 补一行确认状态，
    # 否则 20Hz × 2 侧 = 40 行/秒全是同样的 0，白白吃空间。
    if (self._last_side.get(side) == flags
            and now - self._last_side_t.get(side, 0.0) < SIDE_REFRESH_S):
      return
    self._last_side[side] = flags
    self._last_side_t[side] = now
    self._write({
      "ty": "sd",
      "t": round(now, 3),
      "side": side,
      "ldr": flags[0],
      "car": flags[1],
      "fr": flags[2],
      "bl": flags[3],
      "lane": flags[4],
    })

  def lidar(self, corner, drel, xrel, vrel, object_detected, risk,
            masked, standstill, counter_active, final) -> None:
    """激光雷达单角一帧。只在有距离或有判定结果时写。"""
    if not self.enabled:
      return
    if drel is None and not object_detected and not counter_active and not masked:
      return
    rec = {
      "ty": "ld",
      "t": round(time.monotonic(), 3),
      "c": corner,
      "d": _num(drel),
      "x": _num(xrel),
      "vr": _num(vrel),
      "obj": int(bool(object_detected)),
      "msk": int(bool(masked)),
      "stl": int(bool(standstill)),
      "cnt": int(bool(counter_active)),
      "fin": int(bool(final)),
    }
    if risk is not None:
      rec.update({
        "rs": int(bool(getattr(risk, "risky", False))),
        "cl": round(_num(getattr(risk, "clearance_m", 0.0)) or 0.0, 3),
        "dd": round(_num(getattr(risk, "danger_dist_m", 0.0)) or 0.0, 3),
        "cls": round(_num(getattr(risk, "closing_mps", 0.0)) or 0.0, 3),
      })
    self._write(rec)
