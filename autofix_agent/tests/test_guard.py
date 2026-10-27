"""执行前静态防护测试。

重点不是"能拦住多少"，而是"拦不住的时候系统怎么表现"：
被拦 = UNKNOWN = 转人工，绝不出现"检查失败但照样跑完还判 PASS"。
"""

from pathlib import Path

from agents.dev_subgraph import evaluate_node
from core.guard import BLOCKED, OK, guard_sandbox, scan_source
from tools import exec_tools
from tools.result import VERDICT_NEEDS_HUMAN, Status, envelope, parse_tool_result

CLEAN_SRC = "from corp_sec import safe_calc\n\ndef f(x):\n    return safe_calc(x)\n"


# ---------- 1. 放行正常代码 ----------

def test_clean_code_passes():
    assert scan_source(CLEAN_SRC) == []


def test_ast_and_sys_are_allowed():
    src = "import ast\nimport sys\n\ndef f(x):\n    return ast.literal_eval(x) if sys else x\n"
    assert scan_source(src) == []


def test_syntax_error_is_not_a_security_finding():
    """语法错误交给运行时暴露成测试失败（可重试），不该在这里被当成安全问题。"""
    assert scan_source("def f(:\n") == []


# ---------- 2. 拦截危险导入 ----------

def test_subprocess_import_blocked():
    assert scan_source("import subprocess\n")


def test_from_import_blocked():
    assert scan_source("from shutil import rmtree\n")


def test_socket_and_ctypes_blocked():
    assert scan_source("import socket\n") and scan_source("import ctypes\n")


# ---------- 3. 拦截危险调用（含别名） ----------

def test_os_system_blocked():
    violations = scan_source('import os\nos.system("rm -rf /")\n')
    assert any("os.system" in v for v in violations)


def test_aliased_dangerous_call_blocked():
    """`from os import system as s` 这种改写法也要认出来。"""
    violations = scan_source('from os import system as s\ns("whoami")\n')
    assert any("os.system" in v for v in violations)


def test_dunder_import_blocked():
    violations = scan_source('__import__("os").system("x")\n')
    assert any("__import__" in v for v in violations)


# ---------- 4. 沙箱级扫描：源文件也要扫 ----------

def test_guard_scans_source_not_only_test(tmp_path):
    """测试脚本干净、源码危险 —— 只扫测试脚本就会漏。"""
    (tmp_path / "test_demo.py").write_text("import demo\n", encoding="utf-8")
    (tmp_path / "demo.py").write_text("import subprocess\n", encoding="utf-8")
    result = guard_sandbox(tmp_path)
    assert result.status == BLOCKED
    assert any("demo.py" in v for v in result.violations)


def test_guard_clean_sandbox(tmp_path):
    (tmp_path / "demo.py").write_text(CLEAN_SRC, encoding="utf-8")
    assert guard_sandbox(tmp_path).status == OK


# ---------- 5. 接入执行工具：被拦 = UNKNOWN ----------

def test_blocked_execution_returns_unknown(tmp_path):
    (tmp_path / "test_demo.py").write_text("import demo\n", encoding="utf-8")
    (tmp_path / "demo.py").write_text("import subprocess\nsubprocess.run(['ls'])\n", encoding="utf-8")
    cfg = {"configurable": {"sandbox_dir": str(tmp_path)}}

    raw = exec_tools.run_sandbox_test.invoke({"test_file_path": "test_demo.py"}, config=cfg)
    data = parse_tool_result(raw)
    assert data["status"] == Status.UNKNOWN.value
    assert data.get("blocked") is True
    assert "subprocess" in data["summary"]


def test_blocked_execution_goes_to_human():
    """被护栏拦下的代码，Evaluator 必须转人工，不能重试也不能判 PASS。"""
    from langchain_core.messages import ToolMessage

    blocked = ToolMessage(
        content=envelope(Status.UNKNOWN, "run_sandbox_test", "执行前安全检查未通过", blocked=True),
        tool_call_id="c1",
        name="run_sandbox_test",
    )
    out = evaluate_node({"messages": [blocked], "retry_count": 0}, {"configurable": {"sandbox_dir": "."}})
    assert out["verdict"] == VERDICT_NEEDS_HUMAN
    assert out["next_action"] == "end"
