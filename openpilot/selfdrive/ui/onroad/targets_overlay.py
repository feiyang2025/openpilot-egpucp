# §7.16 观察面 targets overlay v2(dev overlay,默认关闭)。
# 设计文档: 文档/T906_jp7.2/主动避让20261112.md 修订 18/19/20。
# v2: 每个目标在路面原位(车体系→屏投影,与 lead 同一变换)画类色标记 + 距离文字
#     "XXm"(用户要求: 与以前 lead 显示距离一致);矩阵未就绪时退回底部鸟瞰带。
# 硬规则不变: 单消息双消费;渲染单调 coast 0.5s;confirmed+coast 永不截断,
#     tentative cap16 +k 本地计数;连续 2 帧失败自动隐藏零行车回退;未启用零成本。
import json
import math
import time

import numpy as np
import pyray as rl

from openpilot.cereal import messaging
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.text_draw import draw_text_ui_style

try:
  import time as _t, os as _os
  with open("/tmp/dev_overlay_import_root.log", "a") as _f:
    _f.write("%.3f pid=%d %s\n" % (_t.time(), _os.getpid(), __file__))
except Exception:
  pass

PARAM_KEY = "DevTargetsOverlay"
PROBE_PATH = "/tmp/dev_overlay_render.log"
COAST_HOLD_S = 0.5
TENTATIVE_CAP = 16
PARAM_REFRESH_S = 2.0
HEARTBEAT_S = 2.0
HEARTBEAT_PATH = "/tmp/dev_targets_overlay.json"
HIDE_AFTER_ERRS = 2
PX_GATE = 30.0
F_PX_1280 = 1372.0
ADULT_H = 1.7

CLS_NAMES = {0: "PED", 1: "CHD", 2: "CYC", 3: "MOT", 4: "ANI", 5: "CONE", 6: "DEB", 7: "UNK"}
# v2.7: 类别真实几何(世界系高度 m 与 宽/高比),供原位框双点投影
CLS_H = {0: 1.70, 1: 1.10, 2: 1.60, 3: 1.40, 4: 0.70, 5: 0.75, 6: 0.35, 7: 1.00}
CLS_AR = {0: 0.45, 1: 0.45, 2: 0.60, 3: 0.95, 4: 0.90, 5: 0.55, 6: 0.90, 7: 0.60}


def _cls_color(cls_id: int):
  if cls_id == 0:
    return rl.Color(0xE5, 0x39, 0x35, 255)
  if cls_id == 1:
    return rl.Color(0xD5, 0x00, 0xB0, 255)
  if cls_id == 2:
    return rl.Color(0xFB, 0x8C, 0x00, 255)   # 骑行者 橙
  if cls_id == 3:
    return rl.Color(0x21, 0x96, 0xF3, 255)   # 车辆 蓝
  if cls_id == 5:
    return rl.Color(0xFF, 0xD5, 0x4F, 255)   # 雪糕桶 黄
  if cls_id == 6:
    return rl.Color(0xB0, 0xBE, 0xC5, 255)   # 物体 灰白
  return rl.Color(0x9E, 0x9E, 0x9E, 255)


def _with_a(c: rl.Color, a: int) -> rl.Color:
  return rl.Color(c.r, c.g, c.b, a)


class _Row:
  __slots__ = ("tid", "cls", "d", "y", "px", "status", "ttc", "conf", "score", "age_s")
  def __init__(self, tid, cls, d, y, px, status, ttc, conf, score, age_s):
    self.tid, self.cls, self.d, self.y = tid, cls, d, y
    self.px, self.status, self.ttc = px, status, ttc
    self.conf, self.score, self.age_s = conf, score, age_s


class DevTargetsOverlay:
  def __init__(self):
    self._sock = None
    self._enabled = False
    self._param_next_t = 0.0
    self._rows = []
    self._last_msg_t = None
    self._err_streak = 0
    self._last_err = ""
    self._render_ms_max = 0.0
    self._hb_next_t = 0.0
    self._k_trunc = 0
    self._road_hits = 0
    self._diag = {}      # 本帧成功投影到屏内的目标数(心跳里看)

  def close(self):
    if self._sock is not None:
      try:
        self._sock.close()
      except Exception:
        pass
      self._sock = None

  def _ensure_sock(self):
    if self._sock is None:
      self._sock = messaging.sub_sock("smallObjectTracks", timeout=100, conflate=True)

  def update(self, now: float):
    try:
      if now >= self._param_next_t:
        self._param_next_t = now + PARAM_REFRESH_S
        self._enabled = bool(ui_state.params.get_bool(PARAM_KEY))
    except Exception:
      self._enabled = False
    if not self._enabled:
      return

    if now < self._hb_next_t:
      return
    self._hb_next_t = now + HEARTBEAT_S
    self._ensure_sock()
    now_ns = time.monotonic_ns()
    fresh = []
    try:
      last = None
      for m in messaging.drain_sock(self._sock):
        last = m
      if last is not None:
        self._last_msg_t = now
        self._err_streak = 0
        msg = last.smallObjectTracks
        period_s = max((msg.tracks[0].actualPeriodNs if len(msg.tracks) else 50_000_000) / 1e9, 0.05) if len(msg.tracks) else 0.05
        for tr in msg.tracks:
          d = math.hypot(tr.x, tr.y)
          px = tr.detPxH if tr.detPxH > 0 else int(ADULT_H * F_PX_1280 / max(d, 1.0))
          stale_s = (now_ns - tr.tExposureNs) / 1e9
          if stale_s > 1.5 * period_s:
            status = "COAST"
          elif tr.confirmed:
            status = "CONF"
          else:
            status = "TENT"
          closing = max(tr.vx, 0.05) if tr.x > 0.5 else 0.0
          ttc = (tr.x / closing) if (tr.x > 0.5 and closing > 0.1) else None
          fresh.append(_Row(tr.trackId, tr.cls, d, tr.y, px, status, ttc, tr.confirmed, tr.score, stale_s))
        fresh.sort(key=lambda r: (r.status != "CONF", -(r.d if r.ttc is None else min(r.ttc, 99.0))))
    except Exception as e:                                  # noqa: BLE001
      self._err_streak += 1
      self._last_err = repr(e)[:180]
      self._last_msg_t = self._last_msg_t  # keep state; 下一窗口重试(update 永不自禁)
      return

    if self._last_msg_t is not None:
      hold_age = now - self._last_msg_t
      if hold_age > COAST_HOLD_S:
        self._rows, self._last_msg_t = [], None
      elif fresh:
        self._rows = fresh
      else:
        for r in self._rows:
          r.status = "COAST"
    elif fresh:
      self._rows = fresh

    keep = [r for r in self._rows if r.status in ("CONF", "COAST")]
    tents = [r for r in self._rows if r.status == "TENT"][:TENTATIVE_CAP]
    self._k_trunc = max(0, len(self._rows) - len(keep) - len(tents))
    self._rows = sorted(keep + tents, key=lambda r: (r.status != "CONF", r.d if r.ttc is None else min(r.ttc, 99.0)))

    try:
      with open(HEARTBEAT_PATH, "w") as f:
        json.dump({"t": time.time(), "enabled": self._enabled, "n": len(self._rows),
                   "n_conf": sum(1 for r in self._rows if r.status == "CONF"),
                   "n_tent": sum(1 for r in self._rows if r.status == "TENT"),
                   "n_coast": sum(1 for r in self._rows if r.status == "COAST"),
                   "road_hits": self._road_hits, "diag": self._diag,
                   "k_trunc": self._k_trunc, "render_ms_max": round(self._render_ms_max, 3),
                   "msg_age_s": None if self._last_msg_t is None else round(now - self._last_msg_t, 2),
                   "err_streak": self._err_streak, "last_err": self._last_err,
                   "render_exc": getattr(self, "_diag", {}) if isinstance(getattr(self, "_diag", {}), dict) else {}}, f)
    except Exception:
      pass

  def _probe(self, reason):
    now = time.monotonic()
    bypass = reason.startswith("EXC") or reason.startswith("go")
    if not bypass and now < getattr(self, "_probe_next_t", 0.0):
      return
    self._probe_next_t = now + (0.25 if bypass else 1.0)
    try:
      with open(PROBE_PATH, "a") as f:
        f.write("%.3f %s rows=%d en=%d hid=%d err=%d id=%s\n" % (
          time.time(), reason, len(self._rows), self._enabled,
          getattr(self, "_render_hidden", False), self._err_streak, id(self) % 100000))
    except Exception:
      pass

  def render(self, rect: rl.Rectangle, model_renderer=None):   # noqa: N802
    self._probe("enter")
    if not self._enabled:
      self._probe("early:not_enabled")
      return
    self._probe("go rows=%d" % len(self._rows))
    t0 = time.monotonic()
    if self._rows:
      for label, fn in (("road", lambda: self._render_road(rect, model_renderer)),
                        ("strip", lambda: self._render_strip(rect)),
                        ("panel", lambda: self._render_panel(rect))):
        try:
          fn()
        except Exception as e:                                   # noqa: BLE001
          self._err_streak += 1
          self._last_err = repr(e)[:180]
          self._probe("EXC_%s %s" % (label, repr(e)[:170]))
    ms = (time.monotonic() - t0) * 1000.0
    self._render_ms_max = max(self._render_ms_max * 0.99, ms)
    self._probe("drew")

  def _render_road(self, rect: rl.Rectangle, model_renderer):
    # v2.7: 路面原位目标框(类色)+行进可读距离。轴序 = 相机系 (side, up, forward)。
    self._road_hits = 0
    M = getattr(model_renderer, "_car_space_transform", None) if model_renderer is not None else None
    if M is None or not M.any():
      self._diag = {"m": "none_or_zero", "fallback": True}
      return
    x0, y0 = rect.x, rect.y
    x1, y1 = rect.x + rect.width, rect.y + rect.height
    pts_diag = []

    def _proj(lat_left, up, fwd):
      # device 系: x=前, y=右(消息 y 左向取反), z=下(高度取负)
      pt = M @ np.array([fwd, -lat_left, -up], dtype=np.float32)
      if abs(pt[2]) < 1e-6:
        return None
      return float(pt[0] / pt[2]), float(pt[1] / pt[2])

    for r in self._rows:
      c = _cls_color(r.cls)
      alpha = 90 if r.px < PX_GATE else (235 if r.status == "CONF" else (165 if r.status == "COAST" else 140))
      col = _with_a(c, min(alpha + 20, 255))
      # 底=地面点(高 0), 顶=类高度点 → 透视正确、随距离缩放
      bot = _proj(r.y, 0.0, r.d)
      top = _proj(r.y, CLS_H.get(r.cls, 1.0), r.d)
      if bot is None or top is None:
        continue
      ub, vb = bot
      ut, vt = top
      if not (x0 <= ub <= x1 and y0 <= vb <= y1):
        if len(pts_diag) < 3:
          pts_diag.append([round(ub, 1), round(vb, 1), round(r.d, 1), "out"])
        continue
      self._road_hits += 1
      if len(pts_diag) < 3:
        pts_diag.append([round(ub, 1), round(vb, 1), round(r.d, 1)])
      bh = max(8.0, vb - vt)                       # 框高(px), 近大远小
      bw = max(6.0, bh * CLS_AR.get(r.cls, 0.6))    # 框宽
      bx, by = ub - bw / 2.0, vt
      rbox = rl.Rectangle(bx, by, bw, bh)
      if r.status == "COAST":
        rl.draw_rectangle_lines_ex(rbox, 2, _with_a(c, 150))   # 断续感以细线+低亮度表达
      else:
        rl.draw_rectangle_lines_ex(rbox, 3, col)
      # 距离大字:行进可读,白字黑边压在类色之上;px 低于门加灰化角标
      lbl = f"{r.d:.0f}m"
      if r.px < PX_GATE:
        lbl += " <px"
      try:
        draw_text_ui_style(lbl, ub - 14.0, by - 30.0, 22.0,
                           _with_a(rl.Color(0xFF, 0xFF, 0xFF, 255), min(alpha + 40, 255)))
      except Exception as e:                                   # noqa: BLE001
        self._probe("EXC_roadtext %s" % repr(e)[:120])
    self._diag = {"m": [round(float(v), 2) for v in np.asarray(M).flatten()[:6]],
                  "pts": pts_diag, "clip": [round(x0), round(y0), round(x1), round(y1)]}

  def _render_panel(self, rect: rl.Rectangle):
    row_h, pad, font = 17, 8, 13.0
    n = len(self._rows)
    panel_w = 252
    h = pad * 2 + 22 + row_h * max(n, 1) + (14 if self._k_trunc else 0)
    px = rect.x + rect.width - panel_w - 10
    py = rect.y + 66
    rl.draw_rectangle_rec(rl.Rectangle(px, py, panel_w, h), rl.Color(0x10, 0x14, 0x18, 165))
    title = f"TARGETS {n}" + (f" +{self._k_trunc}trunc" if self._k_trunc else "")
    draw_text_ui_style(title, px + pad, py + 4, 15.0, rl.Color(0x4F, 0xC3, 0xF7, 230))
    yy = py + 26
    for r in self._rows:
      c = _cls_color(r.cls)
      alpha = 255 if r.status == "CONF" else (120 if r.status == "TENT" else 165)
      col = _with_a(c, alpha)
      cx, cy = px + pad + 5, yy + 8
      cxi, cyi = int(cx), int(cy)
      if r.status == "COAST":
        rl.draw_circle_lines(cxi, cyi, 6, col)
      elif r.status == "TENT":
        rl.draw_rectangle_rec(rl.Rectangle(cx - 3, cy - 3, 6, 6), col)
      else:
        rl.draw_circle(cxi, cyi, 5, col)
      ttc_s = f"{r.ttc:4.1f}s" if r.ttc is not None else "  -- "
      gate = "" if r.px >= PX_GATE else f" <{PX_GATE:.0f}px"
      line = f"{CLS_NAMES.get(r.cls, '?'):4s} {r.status:5s} d{r.d:5.1f} y{r.y:+4.1f} {ttc_s}{gate}"
      draw_text_ui_style(line, px + pad + 14, yy, font,
                         _with_a(rl.Color(0xFF, 0xFF, 0xFF, 255), alpha if r.status == "CONF" else 200))
      yy += row_h
    if self._k_trunc:
      draw_text_ui_style(f"+{self._k_trunc} tentative truncated (risk-sorted, §7.16)",
                         px + pad, yy + 2, 12.0, rl.Color(0xFF, 0xD5, 0x4F, 210))

  def _render_strip(self, rect: rl.Rectangle):
    bands = [(0, 20, 0), (20, 45, 1), (45, 70, 2), (70, 200, 3)]
    base_y = rect.y + rect.height - 34
    cx = rect.x + rect.width / 2.0
    rl.draw_rectangle_rec(rl.Rectangle(rect.x, base_y - 4, rect.width, 42), rl.Color(0x10, 0x14, 0x18, 110))
    draw_text_ui_style("0m", cx - 8, base_y + 6, 11.0, rl.Color(0x90, 0xA4, 0xAE, 170))
    for r in self._rows:
      for lo, hi, band in bands:
        if lo <= r.d < hi:
          sx = max(rect.x + 8, min(rect.x + rect.width - 8, cx + r.y * (rect.width / 13.0)))
          sy = base_y - band * 10 - 6
          c = _cls_color(r.cls)
          if r.px < PX_GATE:
            rl.draw_circle(int(sx), int(sy), 3, _with_a(c, 90))
          elif r.status == "COAST":
            rl.draw_circle_lines(int(sx), int(sy), 4, _with_a(c, 160))
          else:
            rl.draw_circle(int(sx), int(sy), 4 + (1 if r.status == "CONF" else 0), _with_a(c, 235))
          draw_text_ui_style(f"{r.d:.0f}", sx + 6, sy - 8, 11.0, rl.Color(0xFF, 0xFF, 0xFF, 160))
          break
