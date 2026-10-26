#!/bin/sh
# 模拟 Git Pre-commit Hook
echo "🐶 [AutoFix Agent] 正在拦截提交，进行自动化安全扫描..."

# 提取本次 git commit 暂存的 Python 文件
FILES=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$')

if [ -z "$FILES" ]; then
    echo "没有需要扫描的 Python 文件。"
    exit 0
fi

for FILE in $FILES; do
    echo "🔍 扫描文件: $FILE"
    # 这里实际上应该用 curl 发送 HTTP 请求给你的 FastAPI，为了演示我们直接调用 Python 脚本
    # 注意替换为你真实的 python 路径
    E:/01/.venv/Scripts/python.exe autofix_agent/cli_trigger.py "$FILE"

    # 如果 cli_trigger 返回了失败（即未修复），可以拦截 commit
    if [ $? -ne 0 ]; then
        echo "❌ 存在未修复的安全漏洞，提交被拦截！"
        exit 1
    fi
done

echo "✅ 安全检查通过，允许提交！"