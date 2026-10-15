#!/usr/bin/env bash
set -euo pipefail

# Build the CH347 (USB-I2C) IMU daemon for AGX Orin / Linux.
# Produces  openpilot/system/sensord/ch347t
#
# Usage: bash build_ch347t.sh [hint-dir]   (从任意 cwd 都能跑)
#
# 布局自适应 (老布局 openpilot/ 是软链 / 新布局 openpilot/ 是真实子目录):
#   SELF_DIR  = 本脚本所在目录 = 真实物理路径
#   REPO_ROOT = 从 SELF_DIR 向上找到第一个含 msgq_repo/ 的目录
#               (msgq_repo 在两种布局里都落在树根; 不要再靠 ../.. 数级数)
#   SRC/OUT   = SELF_DIR 下的 ch347t.cc / ch347t, 与目录层级无关
# Links only against libc/libstdc++/libdl + the CH347 vendor .so at runtime
# (dlopen), so it does NOT need a full openpilot build -- but it DOES need three
# scons artifacts (see preflight below).

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

if [ -n "${1:-}" ] && [ -d "${1}" ]; then
  REPO_ROOT="$(cd "${1}" && pwd -P)"
else
  REPO_ROOT="$SELF_DIR"
fi

# 若传入的不是树根 (比如 cwd/sensord 目录), 向上找到含 msgq_repo 的那一级
while [ "$REPO_ROOT" != "/" ] && [ ! -d "$REPO_ROOT/msgq_repo" ]; do
  REPO_ROOT="$(dirname "$REPO_ROOT")"
done
if [ ! -d "$REPO_ROOT/msgq_repo" ]; then
  echo "ERROR: 从 $SELF_DIR 向上找不到含 msgq_repo/ 的树根 (is this an openpilot tree?)" >&2
  exit 1
fi

SRC="$SELF_DIR/ch347t.cc"
OUT="$SELF_DIR/ch347t"
MSGQ="$REPO_ROOT/openpilot/cereal/messaging"

echo "[build_ch347t] src=$SRC"
echo "[build_ch347t] out=$OUT"

if [ ! -f "$SRC" ]; then
  echo "ERROR: $SRC not found (is this a sunnypilot tree?)" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"

# Compile msgq + cereal support sources (path-independent of old/new layout).
# Old layout uses cereal/messaging at root; new layout under openpilot/.
if [ -f "$REPO_ROOT/cereal/messaging/socketmaster.cc" ]; then
  CEREAL_ROOT="$REPO_ROOT"
elif [ -f "$REPO_ROOT/openpilot/cereal/messaging/socketmaster.cc" ]; then
  CEREAL_ROOT="$REPO_ROOT/openpilot"
else
  echo "ERROR: cannot find cereal/messaging" >&2
  exit 1
fi

find_lib() { # relpath
  if [ -f "$REPO_ROOT/$1" ]; then
    echo "$REPO_ROOT/$1"
  elif [ -f "$CEREAL_ROOT/$1" ]; then
    echo "$CEREAL_ROOT/$1"
  else
    return 1
  fi
}

# --- preflight ---------------------------------------------------------------
# 这三个都是 scons 产物, 不入库。缺任何一个都编不出来。
# 一次性全部报出来, 而不是像以前那样 find_lib 失败一个 exit 1。
#
# 只检查这三个文件是否存在 —— 系统库(zmq/capnp/kj)不做预检: 它们不是系统包,
# 而是由 tools/op.sh setup 装进 .venv 的 Python 包(SConstruct 里通过
# importlib.import_module('zeromq') 等取 LIB_DIR), 按 /usr/lib 探测必然误报。
# 系统库缺失留给 g++ 自己报错, 见下面的提示。
REQUIRED_LIBS="msgq_repo/libmsgq.a common/libcommon.a third_party/json11/json11.o"

missing=""
for rel in $REQUIRED_LIBS; do
  find_lib "$rel" >/dev/null 2>&1 || missing="$missing $rel"
done

if [ -n "$missing" ]; then
  cat >&2 <<EOF

[build_ch347t] ============================================================
 缺少 scons 产物, 无法编译
========================================================================
EOF
  for rel in $missing; do echo "   - $rel"; done
  cat >&2 <<EOF

 这些是 scons 的构建产物, 不入库。在仓库根目录执行:
     scons                 # 生成上面列出的库

 首次还需要先装系统依赖(联网, 需要几分钟):
     tools/op.sh setup

 或者设 CH347_AUTODEPS=1 让本脚本自己调 scons(只补库, 不做全量构建):
     CH347_AUTODEPS=1 bash build_ch347t.sh
========================================================================

EOF
  # opt-in 自动补 scons 产物。只在显式设置 CH347_AUTODEPS 时才做, 因为 scons
  # 可能跑很久, 而本脚本是被 manager 以 always_run 拉起的, 阻塞太久会拖累进程树。
  if [ "${CH347_AUTODEPS:-0}" = "1" ]; then
    if command -v scons >/dev/null 2>&1; then
      echo "[build_ch347t] CH347_AUTODEPS=1 -> 正在用 scons 补建缺失库..."
      ( cd "$REPO_ROOT" && scons -j"$(nproc)" ) || {
        echo "[build_ch347t] scons 失败, 无法继续" >&2
        exit 1
      }
      still=""
      for rel in $REQUIRED_LIBS; do
        find_lib "$rel" >/dev/null 2>&1 || still="$still $rel"
      done
      if [ -n "$still" ]; then
        echo "[build_ch347t] scons 跑完但仍缺:$still" >&2
        exit 1
      fi
      echo "[build_ch347t] 依赖补齐, 继续编译"
    else
      echo "[build_ch347t] CH347_AUTODEPS=1 但找不到 scons 命令" >&2
      echo "  先装: sudo apt install scons   或先跑 tools/op.sh setup" >&2
      exit 1
    fi
  else
    exit 1
  fi
fi

MSGQ_LIB="$(find_lib msgq_repo/libmsgq.a)"
COMMON_LIB="$(find_lib common/libcommon.a)"
JSON11_O="$(find_lib third_party/json11/json11.o)"

echo "[build_ch347t] deps ok: $MSGQ_LIB / $COMMON_LIB / $JSON11_O"

g++ -O2 -std=c++17 -o "$OUT" "$SRC" \
  "$CEREAL_ROOT/cereal/messaging/socketmaster.cc" \
  "$MSGQ_LIB" "$COMMON_LIB" "$JSON11_O" \
  -I"$CEREAL_ROOT" -I"$CEREAL_ROOT/cereal/gen/cpp" -I"$REPO_ROOT/msgq_repo" -I"$REPO_ROOT" \
  -pthread -ldl -lzmq -lcapnp -lkj || {
  echo "[build_ch347t] g++ 失败。若报 -lzmq/-lcapnp/-lkj 找不到, 说明系统依赖没装:" >&2
  echo "  在仓库根目录执行: tools/op.sh setup" >&2
  exit 1
}

echo "[build_ch347t] done: $OUT"