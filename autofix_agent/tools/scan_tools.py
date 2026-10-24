import json, subprocess, sys
from pathlib import Path
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig


@tool
def run_sast_scan(file_path: str, config: RunnableConfig) -> str:
    """使用 Bandit 扫描沙箱内代码。"""
    print(f"    [Tool执行] 正在调用 Bandit 扫描: {file_path}")
    try:
        current_sandbox = Path(config.get("configurable", {}).get("sandbox_dir", "")).resolve()
        target_path = (current_sandbox / file_path).resolve()

        if not target_path.exists(): return f"❌ 错误：文件不存在"

        result = subprocess.run(
            [sys.executable, "-m", "bandit", "-f", "json", str(target_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if result.returncode in (0, 1) and result.stdout:
            report = json.loads(result.stdout)
            results = report.get("results", [])
            if not results: return "✅ 扫描完毕：未发现任何安全漏洞。"
            issues = [
                f"- {i.get('test_name')} ({i.get('issue_severity')}): 行 {i.get('line_number')}, {i.get('issue_text')}"
                for i in results]
            return "❌ 扫描发现漏洞：\n" + "\n".join(issues)
        return f"异常: {result.stderr}"
    except Exception as e:
        return f"工具异常：{str(e)}"