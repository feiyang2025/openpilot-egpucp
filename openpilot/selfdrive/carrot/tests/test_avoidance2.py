#!/usr/bin/env python3
"""阶段2 测试:lateral_offset 方向判断。"""
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


def test_lateral():
  av = ObstacleAvoidance()
  car = FakeCar(vEgo=20.0)
  obstacle = FakeLead(dRel=6, vRel=-20.0, vLead=0.0)
  # 激活避障(3帧确认)
  for _ in range(3):
    av.update(obstacle, car)
  assert av.is_active()

  # 1) 左空右有车 -> 向左避让(负偏移)
  off = av.lateral_offset(None, FakeLead(dRel=10, vRel=-1.0))
  assert off < 0, f"左空右有车应左避: {off}"

  # 2) 右空左有车 -> 向右避让(正偏移)
  off = av.lateral_offset(FakeLead(dRel=10, vRel=-1.0), None)
  assert off > 0, f"右空左有车应右避: {off}"

  # 3) 两侧都空 -> 不横移(只减速)
  off = av.lateral_offset(None, None)
  assert off == 0.0, f"两侧空不应横移: {off}"

  # 4) 两侧都有车 -> 不横移
  off = av.lateral_offset(FakeLead(dRel=10, vRel=-1.0), FakeLead(dRel=12, vRel=-1.0))
  assert off == 0.0, f"两侧有车不应横移: {off}"

  # 5) 未激活(障碍离开) -> 不横移
  av.update(FakeLead(dRel=20, vRel=0.5, vLead=20.0), car)
  for _ in range(5):
    av.update(FakeLead(dRel=20, vRel=0.5, vLead=20.0), car)
  assert not av.is_active()
  off = av.lateral_offset(None, FakeLead(dRel=10, vRel=-1.0))
  assert off == 0.0, f"未激活不应横移: {off}"

  # 6) 偏移量上限
  off = av.lateral_offset(FakeLead(dRel=10, vRel=-1.0), None, max_offset=0.35)
  assert abs(off) <= 0.35, f"偏移超限: {off}"
  print("lateral_offset: 6/6 PASS")


if __name__ == "__main__":
  test_lateral()
  print("阶段2 测试 PASS")