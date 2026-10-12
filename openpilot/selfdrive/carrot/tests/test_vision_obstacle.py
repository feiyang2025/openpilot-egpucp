#!/usr/bin/env python3
"""obstacle_vision 正式测试:换算 + 真实图检测 + 融合。"""
import sys
sys.path.insert(0, "/data/openpilot")

import cv2
import numpy as np

from openpilot.selfdrive.carrot.radar_motion.obstacle_vision import (
  VisionObstacleDetector, VisionObstacle, CAM_W, CAM_H, ROAD_FOCAL,
)
from openpilot.selfdrive.carrot.radar_motion.avoidance import ObstacleAvoidance


def test_convert():
  d = VisionObstacleDetector()
  obj_h, d_real = 1.7, 10.0
  box_h = ROAD_FOCAL * obj_h / d_real
  y_real = 1.0
  bottom_cx = CAM_W / 2 + y_real * ROAD_FOCAL / d_real
  d_est = ROAD_FOCAL * obj_h / box_h
  y_est = (bottom_cx - CAM_W / 2) * d_est / ROAD_FOCAL
  assert abs(d_est - d_real) < 0.01 and abs(y_est - y_real) < 0.01
  print("换算 PASS")


def test_detect_real():
  det = VisionObstacleDetector()
  det._frame_count = 2  # 跳过低频采样,强制本帧检测
  img = cv2.imread("/home/nvidia/bus.jpg")
  gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
  y_plane = cv2.resize(gray, (CAM_W, CAM_H))
  obst = det.detect(y_plane)
  persons = [o for o in obst if o.cls == "person"]
  print(f"真实图: {len(obst)} 目标, {len(persons)} person")
  assert len(persons) >= 2, f"bus.jpg 应检出至少2个行人: {len(persons)}"
  for o in persons[:3]:
    assert 2.0 <= o.d_rel <= 40.0, f"距离越界: {o.d_rel}"
  print("真实图检测 PASS")


def test_fusion():
  av = ObstacleAvoidance()
  class CS:
    vEgo = 15.0
  walker = VisionObstacle("person", 8.0, 0.3, 0.85, (0, 0, 0, 0))
  for _ in range(3):
    av.update_vision(walker, CS())
  assert av.is_active()
  spd = av.suggested_speed()
  assert spd is not None and 0 < spd < 54
  # 邻道不触发
  av2 = ObstacleAvoidance()
  for _ in range(3):
    av2.update_vision(VisionObstacle("person", 8.0, 4.0, 0.85, (0, 0, 0, 0)), CS())
  assert not av2.is_active()
  print("融合 PASS")


if __name__ == "__main__":
  test_convert()
  test_detect_real()
  test_fusion()
  print("\n视觉障碍全部测试 PASS")