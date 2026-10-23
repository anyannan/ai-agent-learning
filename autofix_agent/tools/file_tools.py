import os
from pathlib import Path
from langchain_core.tools import tool
from core.config import SANDBOX_DIR, MAX_FILE_SIZE


def _get_safe_path(file_path: str) -> Path:
    """
    防御性安全校验：防止 Agent 传入 ../../etc/passwd 这种路径穿越攻击。
    强制所有操作必须被限制在 SANDBOX_DIR 目录内。
    """
    target_path = (SANDBOX_DIR / file_path).resolve()
    if not str(target_path).startswith(str(SANDBOX_DIR.resolve())):
        raise ValueError(f"安全拒绝：禁止越权访问沙箱外部路径！{file_path}")
    return target_path


@tool
def read_sandbox_file(file_path: str) -> str:
    """读取沙箱内的代码文件。传入相对路径，如 'demo.py'。"""
    try:
        safe_path = _get_safe_path(file_path)
        if not safe_path.exists():
            return f"错误：文件 {file_path} 不存在"
        if safe_path.stat().st_size > MAX_FILE_SIZE:
            return f"错误：文件过大，超过 {MAX_FILE_SIZE / 1024 / 1024}MB 限制"

        with open(safe_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"读取失败：{str(e)}"


@tool
def write_sandbox_file(file_path: str, content: str) -> str:
    """将修复后的代码覆盖写入沙箱文件。"""
    try:
        safe_path = _get_safe_path(file_path)

        # 🌟 核心修复 1：剥离可能存在的 Markdown 代码块标记
        if content.strip().startswith("```"):
            # 去掉第一行的 ```python 或者 ```
            lines = content.strip().splitlines()
            if lines[0].startswith("```"): lines = lines[1:]
            if lines[-1].startswith("```"): lines = lines[:-1]
            content = "\n".join(lines)

        with open(safe_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"✅ 成功写入 {file_path}（{len(content)} 字符）"
    except Exception as e:
        return f"写入失败：{str(e)}"