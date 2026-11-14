#!/usr/bin/env python3
# G13 逐箱定额 CI 骨架(§6.6/G13):缺箱即红,不许总体数盖过缺箱。
# 用法:
#   1) boxes.json 按本脚本同目录模板建箱(箱=姿态×距离段×类别,n_quota 预注册)
#   2) 采好一批数据后把真实目标·次计数填进 n_actual(手工或脚本从标注统计)
#   3) python check_boxes.py boxes.json   → 缺箱 exit 1
# 纯 stdlib,训练机/CI 均可跑。
import json
import math
import sys

def quota(alpha=1e-4, p=0.8):
  """n ≥ ln(α)/ln(1−p)(§3.4):漏检目标·次下限反推。"""
  return math.ceil(math.log(alpha) / math.log(1 - p))

path = sys.argv[1] if len(sys.argv) > 1 else "boxes.json"
doc = json.load(open(path, encoding="utf-8"))
bad = []
for box in doc["boxes"]:
  need = box.get("n_quota", quota(doc.get("alpha", 1e-4), box.get("p_assumed", 0.8)))
  got = box.get("n_actual", 0)
  status = "OK" if got >= need else "MISSING"
  if status == "MISSING":
    bad.append(box)
  print("%-28s [%s] 类=%-9s 距离段=%-8s 姿态=%-6s n=%5d / 需 %5d" % (
    box["box_id"], status, box["cls"], box["dist_band"], box["posture"], got, need))

if bad:
  print("\nG13: %d/%d 箱缺额——缺箱即红,不许用其它箱的总量放行。" % (len(bad), len(doc["boxes"])))
  sys.exit(1)
print("\nG13: 全箱达标(%d/%d)。允许进入 G1-G5 精度门。" % (len(doc["boxes"]), len(doc["boxes"])))
