#!/bin/bash
# 从 GitHub 仓库同步 HA 集成（在 HA 容器内运行）
#
# 用法:
#   bash /config/sync_integrations.sh               # 检查并更新，有更新则重启 HA
#   bash /config/sync_integrations.sh --check-only  # 只检查，不下载不重启
#   bash /config/sync_integrations.sh --no-restart  # 更新但不重启
#
# 机制:
#   1. 下载 https://codeload.github.com/<REPO>/tar.gz/refs/heads/main
#   2. 读远端 versions.json，与本地状态 /config/.integration_sync_state.json 比较
#   3. 有变化的集成 → 覆盖到 /config/custom_components/<名>/
#   4. 有更新 → 发 HA 通知 + 重启 Core（可用 --no-restart 关闭）
#
# 仓库由 GitHub Actions 每周自动检查上游并更新（见仓库 .github/workflows/）

set -uo pipefail

REPO="${SYNC_REPO:-Testplayers/ha-integrations-auto}"
BRANCH="${SYNC_BRANCH:-main}"
CONFIG="${CONFIG:-/config}"
STATE="$CONFIG/.integration_sync_state.json"
LOG="$CONFIG/sync_integrations.log"
TMP="$(mktemp -d /tmp/sync_int.XXXXXX)"
URL="https://codeload.github.com/$REPO/tar.gz/refs/heads/$BRANCH"

CHECK_ONLY=0
DO_RESTART=1
for a in "$@"; do
  case "$a" in
    --check-only) CHECK_ONLY=1 ;;
    --no-restart) DO_RESTART=0 ;;
  esac
done

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

notify() {   # $1=标题 $2=内容
  [ -n "${SUPERVISOR_TOKEN:-}" ] || return 0
  BODY="$(python3 -c 'import json,sys; print(json.dumps({"title":sys.argv[1],"message":sys.argv[2],"notification_id":"integration_sync"}))' "$1" "$2")"
  curl -s -m 15 -X POST \
    -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$BODY" \
    http://supervisor/core/api/services/persistent_notification/create >/dev/null 2>&1
}

log "=== 开始同步（仓库 $REPO@$BRANCH, check_only=$CHECK_ONLY）"

if ! curl -sL -m 120 -o "$TMP/repo.tar.gz" "$URL"; then
  log "✗ 下载仓库失败（网络问题？）"; rm -rf "$TMP"; exit 1
fi
tar xzf "$TMP/repo.tar.gz" -C "$TMP" 2>/dev/null || { log "✗ 解压失败"; rm -rf "$TMP"; exit 1; }
ROOT="$(find "$TMP" -maxdepth 1 -type d -name 'ha-integrations-auto-*' | head -1)"
[ -d "$ROOT/integrations" ] || { log "✗ 包结构异常"; rm -rf "$TMP"; exit 1; }
REMOTE="$ROOT/versions.json"

# 比较远端 versions.json 与本地 state，输出需要更新的集成名（空格分隔）
UPDATED="$(python3 - "$REMOTE" "$STATE" <<'PYEOF'
import json, os, sys
remote = json.load(open(sys.argv[1], encoding="utf-8"))["integrations"]
state = json.load(open(sys.argv[2], encoding="utf-8")) if os.path.exists(sys.argv[2]) else {}
out = []
for name, info in remote.items():
    key = "%s|%s" % (info.get("version"), info.get("ref", ""))
    old = state.get(name, {})
    if key != "%s|%s" % (old.get("version"), old.get("ref", "")):
        out.append(name)
print(" ".join(out))
PYEOF
)"

if [ -z "$UPDATED" ]; then
  log "✓ 已是最新，无需更新"; rm -rf "$TMP"; exit 0
fi
log "发现更新: $UPDATED"

if [ "$CHECK_ONLY" = "1" ]; then
  log "（--check-only，不执行更新）"
  notify "集成有可用更新" "GitHub 上检测到新版本：$UPDATED。每周一 12:00 会自动同步，也可手动运行 shell_command.sync_integrations。"
  rm -rf "$TMP"; exit 0
fi

FAIL=0
for name in $UPDATED; do
  SRC="$ROOT/integrations/$name"
  DST="$CONFIG/custom_components/$name"
  if [ ! -d "$SRC" ]; then log "  × $name: 包里没有该目录，跳过"; FAIL=1; continue; fi
  mkdir -p "$CONFIG/custom_components"
  rm -rf "$DST"
  cp -r "$SRC" "$DST"
  log "  ✓ $name 已更新（$(grep -o '"version": *"[^"]*"' "$DST/manifest.json" | head -1)）"
done

python3 - "$REMOTE" "$STATE" <<'PYEOF'
import json, sys
remote = json.load(open(sys.argv[1], encoding="utf-8"))["integrations"]
json.dump(remote, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PYEOF

rm -rf "$TMP"

if [ "$FAIL" = "1" ]; then
  log "⚠ 部分集成更新失败，请查看日志"
  notify "集成同步部分失败" "见 /config/sync_integrations.log"
  exit 1
fi

if [ "$DO_RESTART" = "1" ]; then
  notify "集成已自动更新" "已更新：$UPDATED。HA 将重启以生效。"
  log "完成，重启 HA ..."
  if [ -n "${SUPERVISOR_TOKEN:-}" ]; then
    curl -s -m 20 -X POST -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
      http://supervisor/core/restart >/dev/null 2>&1 && log "已发出重启请求" || log "重启请求失败"
  fi
else
  notify "集成已自动更新" "已更新：$UPDATED，请手动重启 HA。"
  log "完成（未重启）"
fi
exit 0
