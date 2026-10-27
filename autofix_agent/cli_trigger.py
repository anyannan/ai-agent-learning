# cli_trigger.py
"""本地 CLI：把文件发给 AutoFix API，预览 Diff 后决定是否覆写。

同时被 pre-commit 钩子调用，所以必须用退出码表达结论：
    0 = 通过（无需修复 / 已修复并接受 / 只做解释）
    1 = 未通过（需人工 / 用户拒绝应用 / 请求失败）
否则钩子永远以为"检查通过"，等于没有钩子。
"""

import argparse
import difflib
import os
import shutil
import sys
from urllib.parse import urlparse

import requests

DEFAULT_API = "http://127.0.0.1:8000/api/v1/fix"
DEFAULT_TASK = "请扫描并修复代码中的漏洞，必须符合企业私有安全规范。"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def _session_for(api: str) -> requests.Session:
    """本地服务不走系统代理。

    实测踩过：环境里配了 http_proxy 时，发往 127.0.0.1 的请求也会被塞给代理，
    结果是「服务明明正常，却报连接失败/502」。企业网络里这是必踩的坑。
    """
    session = requests.Session()
    if (urlparse(api).hostname or "") in LOCAL_HOSTS:
        session.trust_env = False
    return session


def show_diff_and_confirm(original_code, fixed_code, assume_yes=False):
    """展示 Diff 并请求人工审批。assume_yes 供 CI / 钩子场景使用。"""
    print("\n" + "=" * 20 + " 🔍 修复预览 (Diff) " + "=" * 20)

    diff = difflib.unified_diff(
        original_code.splitlines(),
        fixed_code.splitlines(),
        fromfile="原始代码",
        tofile="修复后代码",
        lineterm="",
    )

    has_diff = False
    for line in diff:
        has_diff = True
        if line.startswith("+") and not line.startswith("+++"):
            print(f"\033[92m{line}\033[0m")
        elif line.startswith("-") and not line.startswith("---"):
            print(f"\033[91m{line}\033[0m")
        elif line.startswith("@@"):
            print(f"\033[96m{line}\033[0m")
        else:
            print(line)

    if not has_diff:
        print("代码没有变化。")
        return False

    print("=" * 60)
    if assume_yes:
        print("--yes 已指定，自动应用。")
        return True
    choice = input("⚠️ 是否应用以上修复？(y/n): ").strip().lower()
    return choice == "y"


def trigger_agent(source_path, task_desc, intent="fix", api=DEFAULT_API, timeout=300, assume_yes=False):
    """返回进程退出码：0 通过，1 未通过。"""
    if not os.path.exists(source_path):
        print(f"文件不存在: {source_path}")
        return 1

    with open(source_path, "r", encoding="utf-8") as f:
        original_code = f.read()

    source_name = os.path.basename(source_path)
    print(f"📡 正在将 {source_name} 发送至 AutoFix API...")
    print(f"💬 任务诉求: {task_desc}")

    headers = {}
    api_key = os.getenv("AUTOFIX_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        response = _session_for(api).post(
            api,
            json={
                "source_name": source_name,
                "source_code": original_code,
                "task_description": task_desc,
                # 意图显式声明，不再靠 task_desc 里出现"解释"两个字去猜
                "intent": intent,
            },
            headers=headers,
            timeout=timeout,
        )
    except requests.RequestException as e:
        print(f"❌ 请求失败: {e}")
        return 1

    if response.status_code != 200:
        hint = ""
        if response.status_code == 401:
            hint = "\n   服务端已开启鉴权，请设置环境变量 AUTOFIX_API_KEY=<你的key>"
        elif response.status_code == 429:
            hint = f"\n   触发限流/配额，建议 {response.headers.get('Retry-After', '稍后')} 秒后重试"
        elif response.status_code == 503:
            hint = "\n   模型服务暂不可用，可稍后重试（不是代码问题）"
        print(f"❌ 请求失败（HTTP {response.status_code}）: {response.text[:300]}{hint}")
        return 1

    res = response.json()
    # fail-closed：只有服务端明确给出 status=fixed 才允许覆盖本地文件。
    # 缺失 status 一律当作"不确定"，绝不落盘。
    status = res.get("status", "needs_human")

    if status == "no_issue":
        print(f"\n✅ 未发现需要修复的问题，跳过。\n{res.get('message', '')}")
        return 0

    if status == "explained":
        print(f"\n💬 Agent 回复:\n{res.get('message', '')}")
        return 0

    if status != "fixed":
        print(f"\n⛔ 未确认修复成功（status={status}），提交应被拦截。\n{res.get('message', '')}")
        return 1

    print("\n✅ 修复已通过判定！")
    audit = res.get("audit_report")
    if audit:
        print("-" * 40)
        print("📋 自动化审计报告：")
        print(f"  - 发现漏洞: {audit.get('vulnerability_found')}")
        print(f"  - 检索私有规范 (RAG): {audit.get('rag_used')}")
        print(f"  - 契约测试: {audit.get('test_status')}")
        print(f"  - 安全复扫: {audit.get('scan_status')}")
        print(f"  - 规范符合: {audit.get('policy_status')}")
        print(f"  - 终态判定: {audit.get('verdict')}")
        print("-" * 40)

    fixed_code = res.get("fixed_code", "")
    if not fixed_code:
        print("⚠️ 服务端未返回修复后代码，未做改动。")
        return 1

    if show_diff_and_confirm(original_code, fixed_code, assume_yes=assume_yes):
        shutil.copy2(source_path, source_path + ".bak")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write(fixed_code)
        print(f"\n🎉 已接受修复并覆写原文件: {source_path}")
        return 0

    print("\n🛑 已取消修复，原文件未作修改。")
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="调用 AutoFix API 修复单个文件的漏洞")
    parser.add_argument("path", nargs="?", default="sandbox/demo.py", help="目标 .py 文件")
    parser.add_argument("--intent", default="fix", choices=["fix", "explain"])
    parser.add_argument("--task", default=DEFAULT_TASK)
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--yes", action="store_true", help="跳过交互确认（CI/钩子用）")
    args = parser.parse_args(argv)

    return trigger_agent(
        args.path,
        args.task,
        intent=args.intent,
        api=args.api,
        timeout=args.timeout,
        assume_yes=args.yes,
    )


if __name__ == "__main__":
    sys.exit(main())
