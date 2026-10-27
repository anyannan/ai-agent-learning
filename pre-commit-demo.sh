#!/bin/sh
# Git pre-commit 钩子：对暂存的 .py 文件跑一次自动修复检查，未通过则拦截提交。
#
# 安装：cp pre-commit-demo.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
# 跳过：SKIP_AUTOFIX=1 git commit -m "..."（故意留的逃生口，不用改脚本）
#
# 设计取舍：服务不可达时**拦截**提交，而不是静默放行。
# 安全门禁静默降级等于没有门禁；宁可挡住一次提交，让人决定要不要跳过。

set -u

PYTHON="${PYTHON:-python}"
API="${AUTOFIX_API:-http://127.0.0.1:8000/api/v1/fix}"
HEALTH="${AUTOFIX_HEALTH:-http://127.0.0.1:8000/health}"

if [ "${SKIP_AUTOFIX:-0}" = "1" ]; then
    echo "⏭️  SKIP_AUTOFIX=1，跳过自动修复检查。"
    exit 0
fi

echo "🐶 [AutoFix] 正在扫描暂存的 Python 文件..."

FILES=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.py$' || true)
if [ -z "$FILES" ]; then
    echo "没有需要扫描的 Python 文件。"
    exit 0
fi

"$PYTHON" - "$HEALTH" <<'PY' || {
import sys
import urllib.request

url = sys.argv[1]
# 本地服务不走代理：环境里配了 http_proxy 时，127.0.0.1 也会被塞给代理，
# 结果是「服务正常但检查失败」，在企业网络里必然踩到。
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    with opener.open(url, timeout=3) as resp:
        if resp.status != 200:
            raise RuntimeError(f"health check returned {resp.status}")
except Exception as e:
    print(f"❌ AutoFix 服务不可达（{url}）: {e}")
    print("   启动服务: cd autofix_agent && uvicorn main:app --port 8000")
    print("   或跳过本次检查: SKIP_AUTOFIX=1 git commit ...")
    sys.exit(1)
PY
    echo "🚫 自动修复服务不可用，提交被拦截。"
    exit 1
}

FAILED=0
for FILE in $FILES; do
    [ -f "$FILE" ] || continue
    echo "🔍 扫描文件: $FILE"
    "$PYTHON" autofix_agent/cli_trigger.py "$FILE" --api "$API" --yes
    if [ $? -ne 0 ]; then
        FAILED=1
        echo "❌ $FILE 未通过自动修复检查"
    fi
done

if [ "$FAILED" -ne 0 ]; then
    echo "🚫 存在未修复的安全问题，提交被拦截。"
    exit 1
fi

echo "✅ 安全检查通过，允许提交！"
exit 0
