"""沙箱文件读写工具。

读取工具返回**原始代码文本**（模型需要直接读代码，不能包成 JSON）；
写入工具返回结构化信封（上层需要知道写成功还是写失败）。
"""

from pathlib import Path

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from core.config import MAX_FILE_SIZE
from tools.result import Status, envelope

WRITE_TOOL_NAME = "write_sandbox_file"


def _get_safe_path(file_path: str, config: RunnableConfig) -> Path:
    """解析并校验沙箱内路径。

    用 is_relative_to 而不是 startswith：`sandbox/run_abc/../run_abcdef/x.py`
    解析后前缀相同，startswith 会放行，is_relative_to 会拒绝。
    配置缺失时直接失败，不退回 SANDBOX_DIR（fail-closed）。
    """
    sandbox = config.get("configurable", {}).get("sandbox_dir")
    if not sandbox:
        raise RuntimeError("缺少 sandbox_dir 配置")
    sandbox_path = Path(sandbox).resolve()
    target_path = (sandbox_path / file_path).resolve()
    if not target_path.is_relative_to(sandbox_path):
        raise ValueError(f"安全拒绝：禁止越权访问沙箱外部路径！{file_path}")
    return target_path


def _clean_content(content: str) -> str:
    """清洗模型返回的代码。

    只在"整段代码没有真实换行"时才做转义还原：这种形态基本可以确定是模型
    把换行写成了字面量 \\n。若原本就有真实换行，则不做全局替换 ——
    否则会破坏代码里合法出现的 "\\n"（如 print("a\\nb")、正则、JSON 字符串）。
    """
    if content.strip().startswith("```"):
        lines = content.strip().splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines)

    if "\n" not in content and "\\n" in content:
        content = content.replace("\\n", "\n").replace("\\t", "\t")
    return content


@tool
def read_sandbox_file(file_path: str, config: RunnableConfig) -> str:
    """读取沙箱内的代码文件，返回原始文本。"""
    try:
        safe_path = _get_safe_path(file_path, config)
        if not safe_path.exists():
            return f"错误：文件 {file_path} 不存在"
        if safe_path.stat().st_size > MAX_FILE_SIZE:
            return f"错误：文件过大（上限 {MAX_FILE_SIZE} 字节）"

        with open(safe_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"读取失败：{e}"


@tool
def write_sandbox_file(file_path: str, content: str, config: RunnableConfig) -> str:
    """将修复后的代码覆盖写入沙箱文件，返回结构化信封。"""
    try:
        safe_path = _get_safe_path(file_path, config)
        cleaned_content = _clean_content(content)
        # 先写临时文件再原子替换：进程中途崩溃不会留下半截源码
        tmp_path = safe_path.with_suffix(safe_path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(cleaned_content)
        tmp_path.replace(safe_path)
        return envelope(
            Status.CLEAN,
            WRITE_TOOL_NAME,
            f"成功写入 {file_path}（{len(cleaned_content)} 字符）",
            char_count=len(cleaned_content),
        )
    except Exception as e:
        return envelope(Status.FAILED, WRITE_TOOL_NAME, f"写入失败：{e}")
