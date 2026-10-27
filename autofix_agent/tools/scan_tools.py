"""Bandit 静态扫描工具。

fail-closed 要点：任何"没拿到结论"的路径都必须返回 UNKNOWN，
不能返回一个看起来正常的字符串 —— 否则上层会把它读成"无漏洞"。
"""

import json
import subprocess
import sys
from pathlib import Path

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from tools.result import Status, envelope

SCAN_TIMEOUT_SEC = 30
TOOL_NAME = "run_sast_scan"


def _resolve_in_sandbox(file_path: str, config: RunnableConfig) -> Path:
    """解析沙箱内路径；配置缺失时直接失败（fail-closed，不退回 cwd）。"""
    sandbox = config.get("configurable", {}).get("sandbox_dir")
    if not sandbox:
        raise RuntimeError("缺少 sandbox_dir 配置")
    sandbox_path = Path(sandbox).resolve()
    target = (sandbox_path / file_path).resolve()
    if not target.is_relative_to(sandbox_path):
        raise ValueError(f"禁止访问沙箱外部路径: {file_path}")
    return target


@tool
def run_sast_scan(file_path: str, config: RunnableConfig) -> str:
    """使用 Bandit 扫描沙箱内代码，返回结构化信封（status=clean/vulnerable/unknown）。"""
    print(f"    [Tool执行] 正在调用 Bandit 扫描: {file_path}")
    try:
        target = _resolve_in_sandbox(file_path, config)
    except Exception as e:
        return envelope(Status.UNKNOWN, TOOL_NAME, f"路径解析失败: {e}")

    if not target.exists():
        return envelope(Status.UNKNOWN, TOOL_NAME, f"文件不存在: {file_path}")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "bandit", "-f", "json", str(target)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SCAN_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        # 超时 = 没有结论，不是"干净"
        return envelope(Status.UNKNOWN, TOOL_NAME, f"扫描超时（>{SCAN_TIMEOUT_SEC}s）")
    except Exception as e:
        return envelope(Status.UNKNOWN, TOOL_NAME, f"扫描器无法启动: {e}")

    # Bandit 未安装时 `python -m bandit` 会以非零码退出且 stdout 为空。
    # 只看 returncode 会把"工具缺失"读成"扫描通过"，所以先验证 stdout 能否解析。
    try:
        report = json.loads(result.stdout)
    except (TypeError, ValueError):
        detail = (result.stderr or result.stdout or "").strip()[:300]
        return envelope(
            Status.UNKNOWN,
            TOOL_NAME,
            f"扫描器输出无法解析（returncode={result.returncode}）：{detail}",
        )

    results = report.get("results", [])
    if not results:
        return envelope(Status.CLEAN, TOOL_NAME, "未发现安全问题", issue_count=0)

    issues = [
        f"{i.get('test_name')} ({i.get('issue_severity')}) 行 {i.get('line_number')}: {i.get('issue_text')}"
        for i in results
    ]
    return envelope(
        Status.VULNERABLE,
        TOOL_NAME,
        "发现安全问题:\n" + "\n".join(f"- {x}" for x in issues),
        issue_count=len(issues),
    )
