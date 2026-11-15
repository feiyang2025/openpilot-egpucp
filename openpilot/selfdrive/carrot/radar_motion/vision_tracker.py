#!/usr/bin/env python3
"""vision_tracker.py —— 视觉目标多目标跟踪与运动预测。

## 为什么需要这个模块

原始链路每帧独立检测, 没有目标身份、没有速度、没有位置预测, 由此产生四类
真实安全漏洞(复查发现):

1. **相邻车道目标被整体丢弃**
   avoidance.py 只取 `abs(y_rel) <= MAX_TRIGGER_DPATH_M(3.5m)` 的目标。相邻
   车道中心正好在 ±3.5m, 正在切入本车道的车在 3.5m 那一刻还没进窗口, 等它
   到 3.4m 才突然被看见 —— 丢掉了最宝贵的 1~2 秒预警。

2. **无横向速度 -> 无法预测切入**
   切入车与"平行同速行驶的邻道车"在单帧里长得一模一样。没有横向速度就
   无法区分, 也就不可能预测"它 1 秒后会撞到我"。

3. **切进本车道后完全隐形**（最危险）
   carrot_serv 的相邻车道占用判定是 `0.5 <= abs(y) <= 6.5`。一辆车切到
   y=0.3m 时既不在占用判定里(下界挡住), 又因为车类不进避让链路, 于是
   系统对它完全没有反应。

4. **视觉目标被硬编码当成静止**
   avoidance.py 里 `vlead.vRel = -3.0 / vlead.vLead = 0.0`。一辆 50km/h 的
   摩托车因此被当静止障碍处理 -> 无谓急刹; 反过来一架真正静止的车会被
   当"移动前车"而完全不介入。

## 设计原则(安全第一)

- **预测只用于纵向减速/预警, 绝不用于触发横向打方向。**
  预测有误差, 打方向是不可逆的高风险动作。横向避让仍然只走
  avoidance.py 现有几何间隙判据(用当前实测位置)。
- **相邻车道目标不触发横向避让**, 只触发降速。避免邻道正常车辆造成
  无谓的左右蛇形。
- **保守偏置**: 速度估计偏"接近"方向、预测位置偏"向本车道移动"方向、
  侵入判据用最小安全间隙而不是理论碰撞点。
- **失败安全**: 跟踪器任何异常都退化为"无跟踪信息", 上层回退到原始
  单帧行为, 不能让跟踪失败阻断安全逻辑。

## 坐标系

沿用 VisionObstacle 定义:
  d_rel  纵向距离 m (前方为正)
  y_rel  横向偏移 m (画面右正; 注意 car frame 是左正, 上层会取负)
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

# ---- 目标物理半宽(米) -------------------------------------------------- #
# 这些值直接参与"会不会撞"的几何判定, 低估会误判"能过"而刮蹭。
# 摩托车按车把宽度算, 不能按行人算: 原代码把 motorcycle 归入 OBJ_HALF_HUMAN
# (0.35m), 相对实际 0.45~0.5m 低估 0.1~0.15m, 属于真实刮蹭风险。
OBJ_HALF_BY_CLASS = {
  "person": 0.35, "pedestrian": 0.35,
  "bicycle": 0.40, "bike": 0.40, "cyclist": 0.40,
  "motorcycle": 0.50, "motorbike": 0.50,
  "car": 0.95, "truck": 1.25, "bus": 1.25, "van": 1.0,
  "cat": 0.15, "dog": 0.20, "horse": 0.40,
  "cow": 0.50, "sheep": 0.35, "deer": 0.35, "goat": 0.35, "cattle": 0.50,
  "barrel": 0.30, "box": 0.30,
  "traffic light": 0.20, "traffic sign": 0.20, "stop sign": 0.20,
}
# 未知类别按车辆宽 0.95m 保守估(与 avoidance.OBJ_HALF_VEHICLE_M 对齐)。
# 面对不确定的障碍物必须按最宽假设处理: 低估宽度会让系统误判"能绕",
# 而这正是刮蹭的来源。
DEFAULT_OBJ_HALF_M = 0.95

EGO_HALF_M = 0.90          # 自车半宽(含后视镜)
CLEAR_MARGIN_M = 0.50      # 要求的最小横向间隙, 与 avoidance.CLEAR_MARGIN_M 同值

# ---- 跟踪器参数 -------------------------------------------------------- #
CONFIRM_HITS = 2           # 连续命中几次才算确认轨迹(5Hz 下 2 次 = 0.2s)
LOST_KEEP_S = 0.90         # 丢失后保留多久(容忍短暂遮挡/漏检)
MAX_MATCH_D_M = 6.0        # 相邻帧纵向匹配门限(m); 5Hz 下 10m/s 相对速度移 2m
MAX_MATCH_Y_M = 2.5        # 相邻帧横向匹配门限(m)
MAX_TRACKS = 40            # 轨迹上限, 防止内存/CPU 无界增长
VEL_EMA_ALPHA = 0.55       # 速度平滑权重(新值占比); 越高越灵敏、越低越稳
MIN_DT_S = 0.05            # dt 下限, 防止除零/异常放大
MAX_DT_S = 1.00            # dt 上限, 间隔太久不更新速度(丢帧后不可信)

# ---- 预测与侵入判定参数 ------------------------------------------------ #
PRED_HORIZONS_S = (0.5, 1.0, 1.5, 2.0)   # 预测时域
# 侵入预警的距离窗口: 太近(<=2m)已经撞上, 讨论"将撞"无意义; 太远(>50m)
# 预测误差大于收益。与 avoidance.MAX_TRIGGER_DREL_M(40m) 对齐取 45m。
INTRUDE_MIN_D_M = 2.0
INTRUDE_MAX_D_M = 45.0
# 当前横向位置超过这个值才算"相邻车道", 否则走原有本车道避让链路,
# 避免同一目标被两条路径重复处理。与 avoidance.MAX_TRIGGER_DPATH_M 同值。
ADJACENT_Y_MIN_M = 3.5
# 相邻车道监控上限: 超过这个横向距离的目标即使侵入也不影响本车
ADJACENT_Y_MAX_M = 7.0
# 速度可信所需的最少观测次数(少了就不做预测, 只报位置)
MIN_HITS_FOR_VEL = 3
# 速度/方向判定需要连续成立多少帧才采信(5Hz 下 3 帧 = 0.6s)。
# 距离由框高反推, 实测相邻帧噪声可达 ±1.5m -> 假速度 ±2.5m/s。
# 单帧越界一律不采信, 否则本车道前车会被噪声反复误判成"快速接近"。
STREAK_N = 3
# 采信"快速接近"所需的相对接近速度(m/s), 1.5 = 5.4km/h
CLOSING_FAST_MPS = 1.5
# 采信"横向侵入"所需横向速度(m/s)
LATERAL_INTRUDE_MPS = 0.15


@dataclass
class Track:
  """单条目标轨迹。"""
  tid: int
  cls: str
  d_rel: float
  y_rel: float
  conf: float
  bbox: tuple = ()
  # 速度(米/秒)
  v_closing: float = 0.0     # 相对接近速度, 正 = 距离在缩短
  v_lat: float = 0.0         # 横向速度, 正 = 向画面右侧移动
  # 状态
  hits: int = 1
  misses: int = 0
  first_seen: float = field(default_factory=time.monotonic)
  last_seen: float = field(default_factory=time.monotonic)
  # 上次更新速度用的位置/时刻(内部用)
  _prev_d: float = 0.0
  _prev_y: float = 0.0
  _prev_t: float = 0.0
  # 持续性去抖: 连续满足条件的帧数(噪声防护, 见 STREAK_N 注释)
  high_close_streak: int = 0     # 连续"快速接近"帧数
  intrude_dir_streak: int = 0    # 连续"横向朝本车道"帧数

  @property
  def obj_half(self) -> float:
    return OBJ_HALF_BY_CLASS.get(self.cls.lower(), DEFAULT_OBJ_HALF_M)

  @property
  def confirmed(self) -> bool:
    return self.hits >= CONFIRM_HITS

  @property
  def vel_valid(self) -> bool:
    return self.hits >= MIN_HITS_FOR_VEL

  def clearance_now(self) -> float:
    """当前横向间隙(m)。负值 = 已经横向重叠。"""
    return abs(self.y_rel) - self.obj_half - EGO_HALF_M

  def predict(self, t: float) -> tuple[float, float]:
    """预测 t 秒后的 (d_rel, y_rel)。只做匀速外推。"""
    if not self.vel_valid:
      return self.d_rel, self.y_rel
    pd = self.d_rel - self.v_closing * t
    py = self.y_rel + self.v_lat * t
    return pd, py

  def clearance_at(self, t: float) -> float:
    """预测 t 秒后的横向间隙(m)。"""
    _, py = self.predict(t)
    return abs(py) - self.obj_half - EGO_HALF_M

  def time_to_conflict(self) -> float | None:
    """预测多久后横向间隙会低于安全余量(秒); None = 预测窗口内不会。

    只在当前间隙充足时才有意义(已经重叠的目标由当前帧判据处理)。
    """
    if not self.vel_valid:
      return None
    # 方向未经持续确认 -> 不做时间预测(避免噪声驱动的假 TTC)
    if self.intrude_dir_streak < STREAK_N:
      return None
    if self.clearance_now() < CLEAR_MARGIN_M:
      return 0.0
    for t in PRED_HORIZONS_S:
      if self.clearance_at(t) < CLEAR_MARGIN_M:
        return t
    return None

  def closing_in_window(self) -> bool:
    """横向接近是否真的朝本车道: 目标在左则需向右移, 在右则需向左移。

    单向行驶的车横向速度符号若与"朝本车"相反, 是在远离, 不该预警。
    """
    if not self.vel_valid:
      return False
    return self.intrude_dir_streak >= STREAK_N

  def fast_closing(self) -> bool:
    """是否持续快速接近本车(用于 in_lane_veh 判据)。

    要求连续 STREAK_N 帧 v_close >= CLOSING_FAST_MPS。
    单帧超门可能是距离估算噪声(实测 ±2.5m/s), 不能采信。
    """
    if not self.vel_valid:
      return False
    return self.high_close_streak >= STREAK_N


@dataclass
class IntrusionWarning:
  """相邻车道目标预测侵入本车道。"""
  tid: int
  cls: str
  d_rel: float
  y_rel: float
  v_lat: float
  ttc_s: float | None        # 预计多久后间隙不足(秒)
  clearance_now: float
  clearance_pred: float


class VisionTracker:
  """多目标跟踪 + 运动预测。

  用法:
    trk = VisionTracker()
    tracks = trk.update(objs, now)   # objs: 带 cls/d_rel/y_rel/conf/bbox 的对象
    warns  = trk.intrusion_warnings()

  线程安全性: 只在 vision_worker 单线程内使用, 不加锁。
  """

  def __init__(self) -> None:
    self._tracks: dict[int, Track] = {}
    self._next_id = 1
    self._last_update = 0.0

  # ---- 内部 ----------------------------------------------------------- #
  def _make_track(self, o, now: float) -> Track:
    t = Track(
      tid=self._next_id,
      cls=str(getattr(o, "cls", "") or ""),
      d_rel=float(getattr(o, "d_rel", 0.0)),
      y_rel=float(getattr(o, "y_rel", 0.0)),
      conf=float(getattr(o, "conf", 0.0) or 0.0),
      bbox=tuple(getattr(o, "bbox", ()) or ()),
    )
    t._prev_d, t._prev_y, t._prev_t = t.d_rel, t.y_rel, now
    t.first_seen = t.last_seen = now
    self._next_id += 1
    return t

  def _update_velocity(self, trk: Track, nd: float, ny: float, now: float) -> None:
    dt = now - trk._prev_t
    if dt < MIN_DT_S or dt > MAX_DT_S:
      trk._prev_d, trk._prev_y, trk._prev_t = nd, ny, now
      return
    # 接近速度: 距离变小 -> 正
    v_close_new = (trk._prev_d - nd) / dt
    v_lat_new = (ny - trk._prev_y) / dt
    if trk.hits <= 1:
      trk.v_closing, trk.v_lat = v_close_new, v_lat_new
    else:
      a = VEL_EMA_ALPHA
      trk.v_closing = a * v_close_new + (1 - a) * trk.v_closing
      trk.v_lat = a * v_lat_new + (1 - a) * trk.v_lat
    trk._prev_d, trk._prev_y, trk._prev_t = nd, ny, now
    # 去抖计数: 连续满足才采信, 中断立即清零。
    # 放在速度更新之后, 保证用的是本帧平滑后的速度。
    if trk.v_closing >= CLOSING_FAST_MPS:
      trk.high_close_streak += 1
    else:
      trk.high_close_streak = 0
    if ((trk.y_rel > 0 and trk.v_lat < -LATERAL_INTRUDE_MPS)
        or (trk.y_rel < 0 and trk.v_lat > LATERAL_INTRUDE_MPS)):
      trk.intrude_dir_streak += 1
    else:
      trk.intrude_dir_streak = 0

  @staticmethod
  def _match_cost(trk: Track, o) -> float | None:
    """匹配代价; None = 不允许匹配。"""
    if str(getattr(o, "cls", "") or "").lower() != trk.cls.lower():
      return None
    nd = float(getattr(o, "d_rel", 0.0))
    ny = float(getattr(o, "y_rel", 0.0))
    dd = abs(nd - trk.d_rel)
    dy = abs(ny - trk.y_rel)
    if dd > MAX_MATCH_D_M or dy > MAX_MATCH_Y_M:
      return None
    return dd + 2.0 * dy     # 横向差权重更高(车道判定靠横向)

  # ---- 对外 ----------------------------------------------------------- #
  def update(self, objs, now: float | None = None) -> list[Track]:
    """喂入本帧检测结果, 返回当前确认的轨迹列表。"""
    now = time.monotonic() if now is None else now
    self._last_update = now

    objs = list(objs or [])
    used_tracks: set[int] = set()
    used_objs: set[int] = set()

    # 贪心匹配: 目标数 <= 40, O(n*m) 足够
    pairs: list[tuple[float, int, int]] = []
    for tid, trk in self._tracks.items():
      for oi, o in enumerate(objs):
        c = self._match_cost(trk, o)
        if c is not None:
          pairs.append((c, tid, oi))
    pairs.sort()

    for cost, tid, oi in pairs:
      if tid in used_tracks or oi in used_objs:
        continue
      trk = self._tracks[tid]
      o = objs[oi]
      nd = float(getattr(o, "d_rel", trk.d_rel))
      ny = float(getattr(o, "y_rel", trk.y_rel))
      self._update_velocity(trk, nd, ny, now)
      trk.d_rel, trk.y_rel = nd, ny
      trk.conf = float(getattr(o, "conf", trk.conf) or trk.conf)
      trk.bbox = tuple(getattr(o, "bbox", trk.bbox) or trk.bbox)
      trk.hits += 1
      trk.misses = 0
      trk.last_seen = now
      used_tracks.add(tid)
      used_objs.add(oi)

    # 未匹配的轨迹: 记为丢失, 超时删除
    for tid in list(self._tracks.keys()):
      if tid in used_tracks:
        continue
      trk = self._tracks[tid]
      trk.misses += 1
      if now - trk.last_seen > LOST_KEEP_S:
        del self._tracks[tid]

    # 未匹配的检测: 新建轨迹
    for oi, o in enumerate(objs):
      if oi in used_objs:
        continue
      if len(self._tracks) >= MAX_TRACKS:
        # 满了就淘汰最久未见的
        oldest = min(self._tracks.values(), key=lambda t: t.last_seen, default=None)
        if oldest is not None:
          del self._tracks[oldest.tid]
      nt = self._make_track(o, now)
      self._tracks[nt.tid] = nt

    return self.confirmed_tracks()

  def confirmed_tracks(self) -> list[Track]:
    return [t for t in self._tracks.values() if t.confirmed]

  def intrusion_warnings(self) -> list[IntrusionWarning]:
    """相邻车道目标中, 预测会侵入本车道的那些。

    判据(全部满足):
      1. 当前横向位置在相邻车道带(3.5~7.0m), 不在本车道
         —— 本车道目标由 avoidance.py 原有链路处理, 不重复
      2. 轨迹已确认且速度可信(>=3 次观测)
      3. 横向速度指向本车道(|v_lat| >= 0.15 m/s, 符号朝向本车)
      4. 纵向距离在可处置窗口(2~45m)
      5. 预测 2 秒内横向间隙会低于安全余量
    """
    out: list[IntrusionWarning] = []
    for trk in self._tracks.values():
      if not trk.confirmed or not trk.vel_valid:
        continue
      ay = abs(trk.y_rel)
      if ay < ADJACENT_Y_MIN_M or ay > ADJACENT_Y_MAX_M:
        continue
      if not (INTRUDE_MIN_D_M <= trk.d_rel <= INTRUDE_MAX_D_M):
        continue
      if not trk.closing_in_window():
        continue
      ttc = trk.time_to_conflict()
      if ttc is None:
        continue
      worst = min(PRED_HORIZONS_S)
      out.append(IntrusionWarning(
        tid=trk.tid, cls=trk.cls, d_rel=trk.d_rel, y_rel=trk.y_rel,
        v_lat=trk.v_lat, ttc_s=ttc,
        clearance_now=trk.clearance_now(), clearance_pred=trk.clearance_at(worst),
      ))
    # 最紧急的排前面
    out.sort(key=lambda w: (w.ttc_s if w.ttc_s is not None else 99.0, w.d_rel))
    return out

  def adjacent_tracks(self) -> list[Track]:
    """相邻车道上的确认轨迹(仅监控用, 不参与任何车辆动作)。"""
    return [t for t in self._tracks.values()
            if t.confirmed and ADJACENT_Y_MIN_M <= abs(t.y_rel) <= ADJACENT_Y_MAX_M]

  def in_lane_tracks(self) -> list[Track]:
    """本车道内的确认轨迹。"""
    return [t for t in self._tracks.values()
            if t.confirmed and abs(t.y_rel) < ADJACENT_Y_MIN_M]

  def reset(self) -> None:
    self._tracks.clear()
    self._next_id = 1

  # ---- 诊断 ----------------------------------------------------------- #
  def summary(self) -> dict:
    trks = list(self._tracks.values())
    warn = self.intrusion_warnings()
    return {
      "n_tracks": len(trks),
      "n_confirmed": sum(1 for t in trks if t.confirmed),
      "n_in_lane": len(self.in_lane_tracks()),
      "n_adjacent": len(self.adjacent_tracks()),
      "n_intrusion": len(warn),
      "worst_ttc": (warn[0].ttc_s if warn else None),
    }


def obj_half_for(cls: str) -> float:
  """给 avoidance 用的类别半宽查询(替代原来的 if/else)。"""
  return OBJ_HALF_BY_CLASS.get(str(cls or "").lower(), DEFAULT_OBJ_HALF_M)
