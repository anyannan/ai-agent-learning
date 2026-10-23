import sys
import subprocess
from pathlib import Path
from langchain_core.tools import tool
from core.config import SANDBOX_DIR


@tool
def run_sandbox_test(test_file_path: str) -> str:
    """运行沙箱内的测试脚本，返回真实的 stdout 和 stderr。"""
    print(f"        [Tool执行] 正在运行测试: {test_file_path}")
    try:
        # 🌟 修复：补全安全校验和路径解析逻辑
        target_path = (SANDBOX_DIR / test_file_path).resolve()
        if not str(target_path).startswith(str(SANDBOX_DIR.resolve())):
            return "安全拒绝：禁止执行沙箱外的脚本。"
        if not target_path.exists():
            return f"❌ 错误：文件 {test_file_path} 不存在，无法执行测试！"

        result = subprocess.run(
            [sys.executable, str(target_path)],
            cwd=str(SANDBOX_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10
        )

        print(f"        [Tool执行] 测试执行完毕, returncode={result.returncode}")

        if result.returncode == 0:
            return f"✅ 测试通过 (returncode=0)\n输出：\n{result.stdout}"
        else:
            return f"❌ 测试失败 (returncode={result.returncode})\n错误栈：\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return "❌ 测试执行超时 (超过 10 秒)，可能发生了死循环！"
    except Exception as e:
        print(f"        [Tool执行] 工具异常: {e}")
        # 🌟 修复：也加上 ❌ 符号，方便 Evaluator 识别
        return f"❌ 执行器异常：{str(e)}"