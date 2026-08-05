#!/usr/bin/env bash
# 三平台同步推送 + 实证脚本
#
# 为什么需要它（2026-08-05 实战教训）：
#   1. 串行 `git push origin && git push github && git push gitee` 时，
#      GitHub 经 Steam++ 反代可能长连接僵死，卡住整条链，后面平台全部漏推；
#   2. "Everything up-to-date" / "nothing to commit" 提示语不可靠，
#      实际可能未推送（曾多次误导）；
#   3. 本脚本每平台独立 push（一个卡住不影响其它），并强制 ls-remote 实证。
#
# 用法：
#   bash scripts/sync_all.sh            # 推 main 并实证三平台
#   bash scripts/sync_all.sh v2.1.0     # 推 tag 并实证（main 也可以这样推）
#
# 若某平台 MISMATCH：先 `curl -sk -w "%{http_code}" https://github.com/<owner>/<repo>.git/info/refs?service=git-receive-pack`
# 自检链路（401/200=链路通），再单点 `git push <remote> <ref>` 补推。

set -u
set -o pipefail

REF="${1:-main}"
# 支持推 tag 名（refs/tags/xxx）或分支名（main）
case "$REF" in
  refs/*) LOCAL_SHA=$(git rev-parse "$REF") ;;
  *)      LOCAL_SHA=$(git rev-parse "refs/heads/$REF" 2>/dev/null || git rev-parse "$REF") ;;
esac
if [ -z "${LOCAL_SHA:-}" ]; then
  echo "❌ 找不到本地引用: $REF"
  exit 1
fi
echo "本地 $REF = $LOCAL_SHA"

FAIL=0
for R in origin github gitee; do
  echo "--- push $R $REF ---"
  if git push "$R" "$REF" 2>&1 | tail -2; then
    echo "    $R push 命令完成"
  else
    echo "    [!] $R push 失败（反代僵死?），稍后实证决定是否补推"
    FAIL=1
  fi
done

echo "=== 实证三平台 ==="
for R in origin github gitee; do
  REMOTE=$(git ls-remote "$R" "refs/heads/$REF" "refs/tags/$REF" 2>/dev/null | awk '{print $1}' | head -1)
  if [ "$REMOTE" = "$LOCAL_SHA" ]; then
    echo "  $R: OK ($REMOTE)"
  else
    echo "  $R: MISMATCH 本地=$LOCAL_SHA 远程=${REMOTE:-空} ← 需补推"
    FAIL=1
  fi
done

if [ "$FAIL" -eq 0 ]; then
  echo "✅ 三平台同步完成"
else
  echo "❌ 存在未同步项，请按上面 MISMATCH 行单点补推"
  exit 1
fi
