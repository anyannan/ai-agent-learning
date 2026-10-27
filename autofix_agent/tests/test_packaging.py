"""打包与配置的回归测试。

这类问题不影响逻辑，但直接决定"别人 clone 下来能不能跑"——
对简历项目来说，这是第一个会被撞上的失败点。
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT.parent / "requirements.txt"

# import 名 → PyPI 包名（两者不一致的才需要写）
PKG_MAP = {
    "dotenv": "python-dotenv",
    "faiss": "faiss-cpu",
    "langchain_openai": "langchain-openai",
    "langchain_core": "langchain-core",
    "langchain_community": "langchain-community",
    "langchain_classic": "langchain-classic",
    "langchain_mcp_adapters": "langchain-mcp-adapters",
    "yaml": "pyyaml",
}
LOCAL_MODULES = {
    "agents",
    "api",
    "core",
    "services",
    "tools",
    "tests",
    "main",
    "cli_trigger",
    "eval_agent",
    "eval_pipeline",
    "eval_harness",
    "eval_rag",
}


def declared_packages() -> set:
    names = set()
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if not line or line.startswith("-"):
            continue
        names.add(line.split("==")[0].split(">=")[0].strip().lower())
    return names


def imported_roots() -> set:
    roots = set()
    for path in ROOT.rglob("*.py"):
        # sandbox/ 是运行时产物（含模型写的代码），tests/ 里是自己造的数据
        if {"__pycache__", "tests", "sandbox"} & set(path.parts):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    roots.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
    return roots


def test_every_import_is_declared():
    """代码里 import 的每个第三方包都必须在 requirements.txt 里。"""
    declared = declared_packages()
    missing = []
    for root in sorted(imported_roots()):
        if root in sys.stdlib_module_names or root in LOCAL_MODULES:
            continue
        package = PKG_MAP.get(root, root).lower()
        if package not in declared:
            missing.append(f"{root} -> {package}")
    assert not missing, f"requirements.txt 缺少依赖: {missing}"


def test_requirements_is_utf8_without_bom():
    """之前这份文件是 UTF-16 LE（带 BOM），在 Linux/macOS 上 pip 解析会出问题。"""
    raw = REQUIREMENTS.read_bytes()
    assert not raw.startswith(b"\xff\xfe"), "requirements.txt 仍是 UTF-16"
    assert not raw.startswith(b"\xef\xbb\xbf"), "requirements.txt 带 UTF-8 BOM"
    raw.decode("utf-8")


def test_graph_has_no_checkpointer_by_default():
    """单次请求-响应不需要 checkpoint；留着会按 thread_id 无限累积。"""
    from agents.main_graph import main_app

    assert getattr(main_app, "checkpointer", None) is None
