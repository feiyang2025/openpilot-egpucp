#!/usr/bin/env python3
"""avoidance.py 单元测试:检测逻辑 + 状态机(防抖/触发/释放)。"""
import sys
sys.path.insert(0, "/data/openpilot")

from openpilot.selfdrive.carrot.radar_motion.avoidance import ObstacleAvoidance, AvoidanceEstimate


class FakeLead:
  def __init__(self, dRel, vRel, dPath=0.0, vLead=None):
    self.dRel = dRel
    self.vRel = vRel      # m/s
    self.dPath = dPath
    self.vLead = vLead if vLead is not None else 30.0  # m/s


class FakeCar:
  def __init__(self, vEgo=20.0):  # m/s => 72 kph
    self.vEgo = vEgo


def test_detect():
  av = ObstacleAvoidance()
  # 1) 无数据 -> 不触发
  est = av._detect_obstacle(None, None)
  assert not est.active and est.reason == "no-data", est

  # 2) 前方正常行驶的前车 -> 不触发(moving-lead)
  est = av._detect_obstacle(FakeLead(dRel=20, vRel=0.5, vLead=20.0), FakeCar())
  assert not est.active and est.reason == "moving-lead", est

  # 3) 本车道静止障碍近距离(dRel=6, vRel=-20) -> 触发且限速低
  est = av._detect_obstacle(FakeLead(dRel=6, vRel=-20.0, vLead=0.0), FakeCar())
  assert est.active, est
  assert est.speed_kph < 40.0, f"限速应按距离缩: {est.speed_kph}"

  # 3b) 中距离静止障碍(dRel=20) -> 40m 内线性限速(消除旧 12~40m 盲区)
  est = av._detect_obstacle(FakeLead(dRel=20, vRel=-20.0, vLead=0.0), FakeCar())
  assert est.active and est.reason == "stopped-obstacle", est
  assert abs(est.speed_kph - 72.0 * 20.0 / 40.0) < 0.5, f"20m 限速应为 36: {est.speed_kph}"

  # 4) 相邻车道(偏离路径)即使很近也不触发
  est = av._detect_obstacle(FakeLead(dRel=10, vRel=-20.0, dPath=5.0, vLead=0.0), FakeCar())
  assert not est.active and est.reason == "off-path", est

  # 5) 太远不触发
  est = av._detect_obstacle(FakeLead(dRel=60, vRel=-20.0, vLead=0.0), FakeCar())
  assert not est.active and est.reason == "far", est

  # 6) 本车太慢(排队中)不触发
  est = av._detect_obstacle(FakeLead(dRel=10, vRel=-5.0, vLead=0.0), FakeCar(vEgo=0.5))
  assert not est.active and est.reason == "slow-ego", est
  print("detect 逻辑: 6/6 PASS")


def test_state_machine():
  av = ObstacleAvoidance()
  car = FakeCar(vEgo=20.0)
  obstacle = FakeLead(dRel=6, vRel=-20.0, vLead=0.0)   # 近距离静止障碍
  clear = FakeLead(dRel=20, vRel=0.5, vLead=20.0)      # 正常前车

  # 防抖:前 2 帧不触发(需 CONFIRM_FRAMES=3)
  for i in range(2):
    av.update(obstacle, car)
    assert not av.is_active(), f"第{i+1}帧不应触发"
  # 第 3 帧触发
  av.update(obstacle, car)
  assert av.is_active(), "第3帧应触发"
  speed = av.suggested_speed()
  # 6m/12m × 72kph = 36kph:应显著低于巡航 72,且 >0
  assert speed is not None and 0 < speed < 72.0, f"限速异常: {speed}"

  # 持续触发(保持限速)
  for _ in range(5):
    av.update(obstacle, car)
    assert av.is_active() and av.suggested_speed() is not None

  # 障碍离开(正常前车) -> 防抖后释放(RELEASE_FRAMES=5)
  for i in range(4):
    av.update(clear, car)
    assert av.is_active(), f"释放防抖:第{i+1}帧应仍触发"
  av.update(clear, car)
  assert not av.is_active(), "第5帧应释放"
  assert av.suggested_speed() is None
  print("状态机: 防抖/触发/保持/释放 PASS")


def test_linear_speed():
  av = ObstacleAvoidance()
  car = FakeCar(vEgo=20.0)  # 72 kph
  # 40m 内距离越近限速越低(40m 整数是边界=不限速)
  speeds = []
  for d in (39.9, 6, 3, 1):
    est = av._detect_obstacle(FakeLead(dRel=d, vRel=-20.0, vLead=0.0), car)
    assert est.active, f"{d}m 应触发"
    speeds.append((d, est.speed_kph))
  # 验证单调递减(距离越近速度越低)
  sp = [s for _, s in speeds]
  assert all(sp[i] >= sp[i+1] for i in range(len(sp)-1)), f"应单调递减: {speeds}"
  assert abs(sp[0] - 72.0 * 39.9 / 40.0) < 1.0, f"接近40m应≈72*39.9/40: {sp[0]}"
  # 很近时接近 0
  assert speeds[-1][1] < 10.0, f"最近距离限速应<10: {speeds}"
  print(f"线性限速: {speeds} 单调递减 PASS")


if __name__ == "__main__":
  test_detect()
  test_state_machine()
  test_linear_speed()
  print("\n全部测试 PASS")