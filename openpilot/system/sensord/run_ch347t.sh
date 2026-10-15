#!/usr/bin/env bash
set -euo pipefail

# Run the CH347 USB-I2C IMU daemon. Builds the binary on first invocation,
# then execs it. If no CH347 device is present the daemon exits cleanly.
#
# Launched by the manager as a NativeProcess with cwd = <repo>/openpilot/system/sensord
#
# manager 用 always_run 拉起本进程, 退出即被重启。如果构建前置条件不满足(没跑
# scons / 没装系统库), 直接非零退出 -> manager 立刻重启 -> 再构建 -> 再失败,
# 变成刷屏死循环。所以构建失败时先退避一轮再安静退出, 并留一个时间戳让下一轮
# 知道"刚失败过", 避免立刻再试。
#
# 退避时长: CH347_BUILD_BACKOFF 秒, 默认 60。可设 0 关闭。

# Resolve our own real directory. REPO_ROOT is *not* derived by counting
# "../.." levels any more — the layout differs (old: openpilot/ is a symlink,
# new: openpilot/ is a real subdir). build_ch347t.sh finds the repo root itself
# by walking up to the first dir containing msgq_repo/.
SELF_DIR="$(cd "$(dirname "$0")" && pwd -P)"

BIN="$SELF_DIR/ch347t"
STAMP="$SELF_DIR/.ch347t_build_failed"
BACKOFF="${CH347_BUILD_BACKOFF:-60}"

# 上一轮刚失败过 -> 退避, 不再重试构建
if [ -f "$STAMP" ]; then
  age=$(( $(date +%s) - $(stat -c %Y "$STAMP" 2>/dev/null || echo 0) ))
  if [ "$BACKOFF" -gt 0 ] && [ "$age" -lt "$BACKOFF" ]; then
    echo "[ch347t] 上次构建失败($((BACKOFF - age))s 前), 静默跳过, $((BACKOFF - age))s 后再试"
    exit 0
  fi
  rm -f "$STAMP"
fi

# Rebuild also when the source is newer than the binary: the cereal schema
# changes across forks and a stale binary fails to publish / crashes manager.
if [ ! -x "$BIN" ] || [ "$SELF_DIR/ch347t.cc" -nt "$BIN" ]; then
  echo "[ch347t] building..."
  if ! bash "$SELF_DIR/build_ch347t.sh"; then
    date +%s > "$STAMP" 2>/dev/null || true
    echo "[ch347t] 构建失败(通常是缺 scons 产物; 见上方提示)。${BACKOFF}s 后重试" >&2
    sleep "$BACKOFF"
    exit 0
  fi
  rm -f "$STAMP"
fi

exec "$BIN"