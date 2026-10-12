#!/usr/bin/env python3
"""阶段3 测试:lane_change_request 决策逻辑。"""
import sys
sys.path.insert(0, "/data/openpilot")
from openpilot.selfdrive.carrot.radar_motion.avoidance import ObstacleAvoidance


class FakeLead:
  def __init__(self, dRel, vRel, dPath=0.0, vLead=None, yRel=0.0):
    self.dRel = dRel
    self.vRel = vRel
    self.dPath = dPath
    self.vLead = vLead if vLead is not None else 30.0
    self.yRel = yRel


class FakeCar:
  def __init__(self, vEgo=20.0):
    self.vEgo = vEgo


def make_active(av):
  ob = FakeLead(dRel=6, vRel=-20.0, vLead=0.0)
  for _ in range(3):
    av.update(ob, FakeCar(vEgo=20.0))
  assert av.is_active()


def test_lc():
  av = ObstacleAvoidance()
  make_active(av)

  # 1) 车速过低 -> 不换道
  assert av.lane_change_request(20.0, None, None) is None
  # 2) 两侧都有车 -> 不换道
  left = FakeLead(dRel=10, vRel=-1.0, yRel=-3.0)
  right = FakeLead(dRel=12, vRel=-1.0, yRel=3.0)
  assert av.lane_change_request(80.0, left, right) is None
  # 3) 左空右有车 -> 向左绕
  assert av.lane_change_request(80.0, None, right) == "LEFT"
  # 4) 冷却中 -> 再次请求返回 None
  assert av.lane_change_request(80.0, None, right) is None
  # 5) 冷却后右空左有车 -> 向右绕(重置冷却)
  av._lc_last_request = 0.0
  assert av.lane_change_request(80.0, left, None) == "RIGHT"

  # 6) 换道进行中 -> 不触发
  av._lc_last_request = 0.0
  assert av.lane_change_request(80.0, None, right, lane_change_active=True) is None

  # 7) 未激活(障碍解除) -> 不触发
  av._lc_last_request = 0.0
  for _ in range(6):
    av.update(FakeLead(dRel=20, vRel=0.5, vLead=20.0), FakeCar(vEgo=20.0))
  assert not av.is_active()
  assert av.lane_change_request(80.0, None, None) is None
  print("lane_change_request: 7/7 PASS")


if __name__ == "__main__":
  test_lc()
  print("阶段3 测试 PASS")