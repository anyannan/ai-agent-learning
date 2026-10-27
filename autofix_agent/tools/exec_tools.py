"""沙箱内测试执行工具。

fail-closed 要点：超时不是"测试失败"，是"不知道"——两者对流程的影响完全不同：
失败可以打回让模型再改，不知道只能转人工。混为一谈会导致模型在超时上反复空转。
"""

import subprocess
import sys
from pathlib import Path

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from core.guard import guard_sandbox
from tools.result import Status, envelope

TEST_TIMEOUT_SEC = 20
TOOL_NAME = "run_sandbox_test"
MAX_OUTPUT_CHARS = 3000


def _resolve_in_sandbox(test_file_path: str, config: RunnableConfig) -> Path:
    sandbox = config.get("configurable", {}).get("sandbox_dir")
    if not sandbox:
        raise RuntimeError("缺少 sandbox_dir 配置")
    sandbox_path = Path(sandbox).resolve()
    target = (sandbox_path / test_file_path).resolve()
    if not target.is_relative_to(sandbox_path):
        raise ValueError(f"禁止执行沙箱外脚本: {test_file_path}")
    return target


@tool
def run_sandbox_test(test_file_path: str, config: RunnableConfig) -> str:
    """运行沙箱内的测试脚本，返回结构化信封（status=clean/failed/unknown）。"""
    print(f"        [Tool执行] 正在运行测试: {test_file_path}")
    try:
        target = _resolve_in_sandbox(test_file_path, config)
    except Exception as e:
        return envelope(Status.UNKNOWN, TOOL_NAME, f"路径解析失败: {e}")

    if not target.exists():
        return envelope(Status.UNKNOWN, TOOL_NAME, f"文件不存在: {test_file_path}")

    sandbox_path = Path(config["configurable"]["sandbox_dir"]).resolve()

    # 执行前静态防护：不是安全边界，是拦"手滑"的护栏。
    # 命中可疑构造就拒绝执行并转人工 —— 不确定就不跑，不赌模型不会乱写。
    guard = guard_sandbox(sandbox_path)
    if guard.blocked:
        print(f"        [Tool执行] ⛔ 执行前检查拦截：{len(guard.violations)} 处可疑构造")
        return envelope(Status.UNKNOWN, TOOL_NAME, guard.summary(), blocked=True)

    try:
        result = subprocess.run(
            [sys.executable, str(target)],
            cwd=str(sandbox_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TEST_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return envelope(
            Status.UNKNOWN, TOOL_NAME, f"测试超时（>{TEST_TIMEOUT_SEC}s），无法判定结果"
        )
    except Exception as e:
        return envelope(Status.UNKNOWN, TOOL_NAME, f"执行器异常: {e}")

    if result.returncode == 0:
        return envelope(
            Status.CLEAN,
            TOOL_NAME,
            f"测试通过 (returncode=0)\n输出：\n{(result.stdout or '').strip()[:MAX_OUTPUT_CHARS]}",
        )

    return envelope(
        Status.FAILED,
        TOOL_NAME,
        f"测试失败 (returncode={result.returncode})\n错误栈：\n{(result.stderr or '').strip()[:MAX_OUTPUT_CHARS]}",
    )
