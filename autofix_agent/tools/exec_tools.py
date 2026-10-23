import sys
import subprocess
from pathlib import Path
from langchain_core.tools import tool
from core.config import SANDBOX_DIR


@tool
def run_sandbox_test(test_file_path: str) -> str:
    """运行沙箱内的测试脚本（如 'test_demo.py'），返回真实的 stdout 和 stderr。"""
    try:
        # 安全校验
        target_path = (SANDBOX_DIR / test_file_path).resolve()
        if not str(target_path).startswith(str(SANDBOX_DIR.resolve())):
            return "安全拒绝：禁止执行沙箱外的脚本。"

        # 使用当前虚拟环境的解释器执行，捕获输出，设置 10 秒超时防死循环
        result = subprocess.run(
            [sys.executable, str(target_path)],
            cwd=str(SANDBOX_DIR),  # 必须在沙箱目录下运行
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            return f"✅ 测试通过 (returncode=0)\n输出：\n{result.stdout}"
        else:
            return f"❌ 测试失败 (returncode={result.returncode})\n错误栈：\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return "⚠️ 测试执行超时 (超过 10 秒)，可能发生了死循环！"
    except Exception as e:
        return f"执行器异常：{str(e)}"