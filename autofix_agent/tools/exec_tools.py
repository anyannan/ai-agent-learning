import sys, subprocess
from pathlib import Path
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig


@tool
def run_sandbox_test(test_file_path: str, config: RunnableConfig) -> str:
    """运行沙箱内的测试脚本。"""
    print(f"        [Tool执行] 正在运行测试: {test_file_path}")
    try:
        current_sandbox = Path(config.get("configurable", {}).get("sandbox_dir", "")).resolve()
        target_path = (current_sandbox / test_file_path).resolve()

        if not str(target_path).startswith(str(current_sandbox)):
            return "❌ 安全拒绝：禁止执行沙箱外的脚本。"
        if not target_path.exists():
            return f"❌ 错误：文件 {test_file_path} 不存在，无法执行测试！"

        result = subprocess.run(
            [sys.executable, str(target_path)],
            cwd=str(current_sandbox),  # 确保在请求独立的目录下运行
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10
        )
        if result.returncode == 0:
            return f"✅ 测试通过 (returncode=0)\n输出：\n{result.stdout}"
        else:
            return f"❌ 测试失败 (returncode={result.returncode})\n错误栈：\n{result.stderr}"
    except Exception as e:
        return f"❌ 执行器异常：{str(e)}"