from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from pathlib import Path
from core.config import SANDBOX_DIR, MAX_FILE_SIZE


def _get_safe_path(file_path: str, config: RunnableConfig) -> Path:
    # 从 config 中获取当前请求的独立目录
    current_sandbox_str = config.get("configurable", {}).get("sandbox_dir", str(SANDBOX_DIR))
    current_sandbox = Path(current_sandbox_str).resolve()
    target_path = (current_sandbox / file_path).resolve()

    if not str(target_path).startswith(str(current_sandbox)):
        raise ValueError(f"安全拒绝：禁止越权访问沙箱外部路径！{file_path}")
    return target_path


def _clean_content(content: str) -> str:
    """清洗大模型返回的代码，防止语法污染"""
    # 1. 剥离 Markdown 代码块
    if content.strip().startswith("```"):
        lines = content.strip().splitlines()
        if lines[0].startswith("```"): lines = lines[1:]
        if lines[-1].startswith("```"): lines = lines[:-1]
        content = "\n".join(lines)

    # 2. 暴力清洗转义字符：把模型自作聪明转义的字面量（如 \\n, \\t）替换为真实字符
    content = content.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\'", "'")
    return content


@tool
def read_sandbox_file(file_path: str, config: RunnableConfig) -> str:
    """读取沙箱内的代码文件。"""
    try:
        safe_path = _get_safe_path(file_path, config)
        if not safe_path.exists(): return f"错误：文件 {file_path} 不存在"
        if safe_path.stat().st_size > MAX_FILE_SIZE: return f"错误：文件过大"

        with open(safe_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"读取失败：{str(e)}"


@tool
def write_sandbox_file(file_path: str, content: str, config: RunnableConfig) -> str:
    """将修复后的代码覆盖写入沙箱文件。"""
    try:
        safe_path = _get_safe_path(file_path, config)

        # 🌟 核心：执行内容清洗
        cleaned_content = _clean_content(content)

        with open(safe_path, "w", encoding="utf-8") as f:
            f.write(cleaned_content)
        return f"✅ 成功写入 {file_path}（{len(cleaned_content)} 字符）"
    except Exception as e:
        return f"写入失败：{str(e)}"