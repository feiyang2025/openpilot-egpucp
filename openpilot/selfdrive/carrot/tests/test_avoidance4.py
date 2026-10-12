#!/usr/bin/env python3
"""增强测试:模型 laneChangeAvailable 判据优先于雷达 side_clear。

场景:
1. 模型说可绕(无车道线有路缘)→ 即使雷达 sees 近距离侧车也按模型绕? NO!
   注意:lane_avail 已含 BSD/侧障,若传了模型判据就不该再叠加雷达矛盾
   → 模型判 True + 雷达有事 = 模型判据优先(模型已综合考虑)
2. 模型说不可绕 → 不绕(即使雷达空旷)
3. 模型未提供(None) → 退回雷达判据
"""
import sys
sys.path.insert(0, "/data/openpilot")
from openpilot.selfdrive.carrot.radar_motion.avoidance import ObstacleAvoidance


class FakeLead:
  def __init__(self, dRel, vRel, dPath=0.0, vLead=None, yRel=0.0, status=True):
    self.dRel = dRel
    self.vRel = vRel
    self.dPath = dPath
    self.vLead = vLead if vLead is not None else 30.0
    self.yRel = yRel
    self.status = status


class FakeCar:
  def __init__(self, vEgo=20.0):
    self.vEgo = vEgo


def make_active(av):
  ob = FakeLead(dRel=6, vRel=-20.0, vLead=0.0)
  for _ in range(3):
    av.update(ob, FakeCar(vEgo=20.0))
  assert av.is_active()


def test_model_priority():
  av = ObstacleAvoidance()
  make_active(av)

  # 无车道线场景:模型 meta.laneChangeAvailable 已融合路缘判定
  # 1) 模型:右可绕、左不可绕 → 应向右避让(即使雷达右侧有近车,模型已综合 BSD)
  off = av.lateral_offset(
    FakeLead(dRel=10, vRel=-1.0),            # 雷达:左有车
    FakeLead(dRel=8, vRel=-1.0, yRel=3.0),   # 雷达:右有近车
    lane_avail_left=False,
    lane_avail_right=True,
  )
  assert off > 0, f"模型判右可绕应右避: {off}"

  # 2) 模型:两侧都不可绕 → 不横移(即使雷达空旷)
  off = av.lateral_offset(None, None, lane_avail_left=False, lane_avail_right=False)
  assert off == 0.0, f"模型判不可绕应不动: {off}"

  # 3) 模型:左可绕 → 左避
  off = av.lateral_offset(None, None, lane_avail_left=True, lane_avail_right=False)
  assert off < 0, f"模型判左可绕应左避: {off}"

  # 4) 模型未提供(None) → 退回雷达判据:右空左有车 → 右避
  off = av.lateral_offset(FakeLead(dRel=10, vRel=-1.0), None)
  assert off > 0, f"无模型判据应回退雷达: {off}"

  # 5) 阶段3:模型判左可绕 → 发 LEFT 请求(雷达右侧有车也不影响)
  av._lc_last_request = 0.0
  lc = av.lane_change_request(
    80.0,
    FakeLead(dRel=5, vRel=-1.0),   # 雷达左有近车
    FakeLead(dRel=5, vRel=-1.0),   # 雷达右有近车
    lane_avail_left=True,
    lane_avail_right=False,
  )
  assert lc == "LEFT", f"模型判左可绕应发LEFT: {lc}"

  # 6) 阶段3:模型判都不可绕 → 不发请求
  av._lc_last_request = 0.0
  lc = av.lane_change_request(80.0, None, None,
                              lane_avail_left=False, lane_avail_right=False)
  assert lc is None, f"模型判不可绕不应发: {lc}"
  print("模型判据优先: 6/6 PASS")


if __name__ == "__main__":
  test_model_priority()
  print("增强测试 PASS")