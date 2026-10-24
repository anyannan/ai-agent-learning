from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from pathlib import Path
from core.config import SANDBOX_DIR, MAX_FILE_SIZE


def _get_safe_path(file_path: str, config: RunnableConfig) -> Path:
    # 🌟 核心：从 config 中获取当前请求的独立目录
    current_sandbox_str = config.get("configurable", {}).get("sandbox_dir", str(SANDBOX_DIR))
    current_sandbox = Path(current_sandbox_str).resolve()

    target_path = (current_sandbox / file_path).resolve()
    if not str(target_path).startswith(str(current_sandbox)):
        raise ValueError(f"安全拒绝：禁止越权访问沙箱外部路径！{file_path}")
    return target_path


@tool
def read_sandbox_file(file_path: str, config: RunnableConfig) -> str:
    """读取沙箱内的代码文件。"""
    try:
        safe_path = _get_safe_path(file_path, config)
        if not safe_path.exists(): return f"错误：文件 {file_path} 不存在"
        with open(safe_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"读取失败：{str(e)}"


@tool
def write_sandbox_file(file_path: str, content: str, config: RunnableConfig) -> str:
    """将修复后的代码覆盖写入沙箱文件。"""
    try:
        safe_path = _get_safe_path(file_path, config)
        if content.strip().startswith("```"):
            lines = content.strip().splitlines()
            if lines[0].startswith("```"): lines = lines[1:]
            if lines[-1].startswith("```"): lines = lines[:-1]
            content = "\n".join(lines)
        with open(safe_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"✅ 成功写入 {file_path}（{len(content)} 字符）"
    except Exception as e:
        return f"写入失败：{str(e)}"