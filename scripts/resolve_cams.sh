#!/bin/bash
# resolve_cams.sh — 按 v4l2 设备名解析摄像头节点号并输出 export 语句。
# v4l2 节点号(/dev/videoN)会随 USB 枚举/GMSL 驱动加载顺序漂移,不能硬编码。
# 设备名(来自 /sys/class/video4linux/videoN/name):
#   twgmsl 9-0028 -> GMSL 30° 窄角(远距离主相机)
#   twgmsl 9-002a -> GMSL 196° 鱼眼(近距离超广角)
#   USB Camera    -> USB IMX678 90°(稳定中距离/后备)
# 输出: export ROAD_CAM='N' 等(与 launch_env.sh 的用法一致)
#
# 容错优先级:
#   ROAD   = 30°(若死则用 USB)
#   WIDE   = 196°(若死则用 30°;再不行用 USB)
#   DRIVER = USB(仅当 ROAD 已由 30° 承担时;ROAD 用了 USB 则 DRIVER 留空)

find_by_name() {
  local pat="$1"
  for d in /sys/class/video4linux/video*; do
    [ -d "$d" ] || continue
    if grep -q "$pat" "$d/name" 2>/dev/null; then
      echo "/dev/$(basename "$d")"
      return 0
    fi
  done
  return 1
}

CAM30=$(find_by_name "twgmsl 9-0028")
CAM196=$(find_by_name "twgmsl 9-002a")
CAMUSB=$(find_by_name "USB Camera")

ROAD=""
WIDE=""
DRIVER=""

# 30° 窄角优先做主路(远距离)
if [ -n "$CAM30" ]; then
  ROAD="$CAM30"
else
  ROAD="$CAMUSB"
fi
# 196° 鱼眼优先做 wide(近距离)
if [ -n "$CAM196" ]; then
  WIDE="$CAM196"
elif [ -n "$CAM30" ] && [ "$CAM30" != "$ROAD" ]; then
  WIDE="$CAM30"
elif [ -n "$CAMUSB" ] && [ "$CAMUSB" != "$ROAD" ]; then
  WIDE="$CAMUSB"
fi
# USB 作为第三路(仅当 ROAD 不是 USB 时才有独立意义;否则留空避免重复)
if [ -n "$CAMUSB" ] && [ "$CAMUSB" != "$ROAD" ] && [ "$CAMUSB" != "$WIDE" ]; then
  DRIVER="$CAMUSB"
fi

echo "export ROAD_CAM='${ROAD#/dev/video}'"
echo "export WIDE_CAM='${WIDE#/dev/video}'"
echo "export DRIVER_CAM='${DRIVER#/dev/video}'"
