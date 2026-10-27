"""fail-closed 回归测试。

这些用例存在的唯一目的：证明"工具挂了/没结论"时，系统绝不会输出 PASS。
之前的实现里，Bandit 缺失会返回不带 ❌ 的字符串，被上层读成"无漏洞"，
然后宣布"✅ 漏洞已彻底修复" —— 这类 bug 靠读代码容易漏，必须用测试钉住。

运行：cd autofix_agent && python -m pytest tests -q
"""

import subprocess

import pytest
from langchain_core.messages import ToolMessage
from pydantic import ValidationError

from agents import dev_subgraph
from agents.dev_subgraph import evaluate_node
from agents.nodes import orchestrator_node
from api.schemas import FixRequest
from tools import exec_tools, scan_tools
from tools.file_tools import _get_safe_path
from tools.result import (
    VERDICT_NEEDS_HUMAN,
    VERDICT_NO_ISSUE,
    VERDICT_PASS,
    Status,
    envelope,
    parse_tool_result,
)


# ---------- 1. 信封解析 ----------

def test_parse_garbage_is_unknown():
    assert parse_tool_result("✅ 扫描完毕：未发现任何安全漏洞。")["status"] == Status.UNKNOWN.value


def test_parse_invalid_status_is_unknown():
    assert parse_tool_result('{"status": "looks_fine"}')["status"] == Status.UNKNOWN.value


def test_parse_roundtrip():
    raw = envelope(Status.VULNERABLE, "run_sast_scan", "发现 1 处", issue_count=1)
    data = parse_tool_result(raw)
    assert data["status"] == Status.VULNERABLE.value
    assert data["tool"] == "run_sast_scan"


# ---------- 2. 扫描工具：所有失败路径必须是 UNKNOWN ----------

@pytest.fixture
def sandbox(tmp_path):
    (tmp_path / "demo.py").write_text("def f(x):\n    return eval(x)\n", encoding="utf-8")
    return {"configurable": {"sandbox_dir": str(tmp_path)}}


def test_scan_missing_bandit_is_unknown(sandbox, monkeypatch):
    """bandit 未安装：stdout 为空、非零退出。这必须是 UNKNOWN，不能是 CLEAN。"""
    fake = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="No module named bandit"
    )
    monkeypatch.setattr(scan_tools.subprocess, "run", lambda *a, **k: fake)
    data = parse_tool_result(scan_tools.run_sast_scan.invoke({"file_path": "demo.py"}, config=sandbox))
    assert data["status"] == Status.UNKNOWN.value


def test_scan_timeout_is_unknown(sandbox, monkeypatch):
    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="bandit", timeout=30)

    monkeypatch.setattr(scan_tools.subprocess, "run", _timeout)
    data = parse_tool_result(scan_tools.run_sast_scan.invoke({"file_path": "demo.py"}, config=sandbox))
    assert data["status"] == Status.UNKNOWN.value


def test_scan_clean(sandbox, monkeypatch):
    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout='{"results": []}', stderr="")
    monkeypatch.setattr(scan_tools.subprocess, "run", lambda *a, **k: fake)
    data = parse_tool_result(scan_tools.run_sast_scan.invoke({"file_path": "demo.py"}, config=sandbox))
    assert data["status"] == Status.CLEAN.value


def test_scan_vulnerable(sandbox, monkeypatch):
    payload = '{"results": [{"test_name": "blacklist", "issue_severity": "MEDIUM", "line_number": 2, "issue_text": "eval"}]}'
    fake = subprocess.CompletedProcess(args=[], returncode=1, stdout=payload, stderr="")
    monkeypatch.setattr(scan_tools.subprocess, "run", lambda *a, **k: fake)
    data = parse_tool_result(scan_tools.run_sast_scan.invoke({"file_path": "demo.py"}, config=sandbox))
    assert data["status"] == Status.VULNERABLE.value


def test_scan_missing_file_is_unknown(sandbox):
    data = parse_tool_result(scan_tools.run_sast_scan.invoke({"file_path": "nope.py"}, config=sandbox))
    assert data["status"] == Status.UNKNOWN.value


# ---------- 3. 测试执行工具 ----------

def test_exec_timeout_is_unknown_not_failed(sandbox, monkeypatch):
    """超时不是"测试失败"：失败可以打回重试，不知道只能转人工。"""
    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="pytest", timeout=20)

    from pathlib import Path

    Path(sandbox["configurable"]["sandbox_dir"], "test_demo.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(exec_tools.subprocess, "run", _timeout)
    data = parse_tool_result(exec_tools.run_sandbox_test.invoke({"test_file_path": "test_demo.py"}, config=sandbox))
    assert data["status"] == Status.UNKNOWN.value


# ---------- 4. Evaluator 判定 ----------

def _tool_msg(name: str, status: Status) -> ToolMessage:
    return ToolMessage(content=envelope(status, name, "detail"), tool_call_id="call_1", name=name)


CFG = {"configurable": {"sandbox_dir": ".", "source_file": "demo.py"}}


def test_evaluator_test_unknown_goes_to_human():
    out = evaluate_node({"messages": [_tool_msg("run_sandbox_test", Status.UNKNOWN)], "retry_count": 0}, CFG)
    assert out["verdict"] == VERDICT_NEEDS_HUMAN
    assert out["next_action"] == "end"


def test_evaluator_test_failed_retries():
    out = evaluate_node({"messages": [_tool_msg("run_sandbox_test", Status.FAILED)], "retry_count": 0}, CFG)
    assert out["next_action"] == "retry"
    assert out["retry_count"] == 1


def test_evaluator_scan_unknown_never_passes(monkeypatch):
    """测试通过但扫描没结论 —— 这是原实现里最危险的分支，必须转人工。"""
    class _FakeScan:
        @staticmethod
        def invoke(_args, config=None):
            return envelope(Status.UNKNOWN, "run_sast_scan", "扫描器超时")

    monkeypatch.setattr(dev_subgraph, "run_sast_scan", _FakeScan())
    out = evaluate_node({"messages": [_tool_msg("run_sandbox_test", Status.CLEAN)], "retry_count": 0}, CFG)
    assert out["verdict"] == VERDICT_NEEDS_HUMAN
    assert out["next_action"] == "end"


def test_evaluator_pass_requires_both_clean_and_compliant(tmp_path, monkeypatch):
    """三项齐了才 PASS：契约测试 clean + 复扫 clean + 规范 compliant。"""
    src = "from corp_sec import safe_calc\n\ndef f(x):\n    return safe_calc(x)\n"
    (tmp_path / "demo.py").write_text(src, encoding="utf-8")
    cfg = {"configurable": {"sandbox_dir": str(tmp_path), "source_file": "demo.py"}}

    class _FakeScan:
        @staticmethod
        def invoke(_args, config=None):
            return envelope(Status.CLEAN, "run_sast_scan", "未发现安全问题")

    monkeypatch.setattr(dev_subgraph, "run_sast_scan", _FakeScan())
    out = evaluate_node(
        {
            "messages": [_tool_msg("run_sandbox_test", Status.CLEAN)],
            "retry_count": 0,
            "scan_summary": "发现安全问题:\n- blacklist (MEDIUM) 行 2: eval",
        },
        cfg,
    )
    assert out["verdict"] == VERDICT_PASS
    assert out["test_status"] == "clean" and out["scan_status"] == "clean"
    assert out["policy_status"] == "compliant"


def test_evaluator_scan_clean_but_no_policy_rule_goes_to_human(tmp_path, monkeypatch):
    """复扫干净但没有匹配的规范规则 —— 不能判 PASS，因为"没校验"≠"合规"。"""
    (tmp_path / "demo.py").write_text("def f(x):\n    return x\n", encoding="utf-8")
    cfg = {"configurable": {"sandbox_dir": str(tmp_path), "source_file": "demo.py"}}

    class _FakeScan:
        @staticmethod
        def invoke(_args, config=None):
            return envelope(Status.CLEAN, "run_sast_scan", "未发现安全问题")

    monkeypatch.setattr(dev_subgraph, "run_sast_scan", _FakeScan())
    out = evaluate_node(
        {
            "messages": [_tool_msg("run_sandbox_test", Status.CLEAN)],
            "retry_count": 0,
            "scan_summary": "发现安全问题:\n- hardcoded password",
        },
        cfg,
    )
    assert out["verdict"] == VERDICT_NEEDS_HUMAN
    assert out["next_action"] == "end"


def test_evaluator_retry_budget_exhausted_is_human():
    out = evaluate_node(
        {"messages": [_tool_msg("run_sandbox_test", Status.FAILED)], "retry_count": 3}, CFG
    )
    assert out["verdict"] == VERDICT_NEEDS_HUMAN
    assert out["next_action"] == "end"


def test_evaluator_write_failure_retries():
    out = evaluate_node({"messages": [_tool_msg("write_sandbox_file", Status.FAILED)], "retry_count": 0}, CFG)
    assert out["next_action"] == "retry"


# ---------- 5. 编排器 ----------

def test_orchestrator_stops_on_needs_human():
    state = {"intent": "fix", "verdict": VERDICT_NEEDS_HUMAN, "transitions": 0}
    assert orchestrator_node(state)["next"] == "FINISH"


def test_orchestrator_clean_scan_skips_fix_stage():
    """扫描干净时不该进 dev_team —— 否则模型会去"修"一个不存在的漏洞。"""
    out = orchestrator_node({"intent": "fix", "security_done": True, "scan_status": "clean", "transitions": 1})
    assert out["next"] == "FINISH"
    assert out["verdict"] == VERDICT_NO_ISSUE


def test_orchestrator_does_not_overwrite_pass_after_dev():
    """修复后复扫也是 clean，不能因此把 verdict=pass 覆盖成 no_issue。"""
    out = orchestrator_node(
        {
            "intent": "fix",
            "security_done": True,
            "dev_done": True,
            "verdict": VERDICT_PASS,
            "scan_status": "clean",
            "transitions": 2,
        }
    )
    assert out["next"] == "FINISH"
    assert "verdict" not in out


# ---------- 6. 边界：路径与入参 ----------

def test_sandbox_prefix_bypass_is_rejected(tmp_path):
    root = tmp_path / "run_abc"
    root.mkdir()
    (tmp_path / "run_abcdef").mkdir()
    with pytest.raises(ValueError):
        _get_safe_path("../run_abcdef/payload.py", {"configurable": {"sandbox_dir": str(root)}})


def test_missing_sandbox_dir_raises():
    with pytest.raises(RuntimeError):
        _get_safe_path("demo.py", {"configurable": {}})


def test_source_name_rejects_traversal():
    with pytest.raises(ValidationError):
        FixRequest(source_code="x = 1", source_name="../../evil.py")


def test_source_name_rejects_non_py():
    with pytest.raises(ValidationError):
        FixRequest(source_code="x = 1", source_name="notes.txt")


# ---------- 7. 审计提取：不能把检索到的规范标题误报成发现的漏洞 ----------

def test_extract_vuln_ignores_rag_section():
    from api.routes import _extract_vuln

    msg = (
        "【安全扫描报告】：\n发现安全问题:\n- blacklist (MEDIUM) 行 2: eval\n\n"
        "【企业安全规范参考】：\n【CWE-89: SQL 注入】\n风险描述..."
    )
    assert _extract_vuln(msg) == "blacklist (MEDIUM) 行 2: eval"


def test_extract_vuln_clean_scan():
    from api.routes import _extract_vuln

    assert _extract_vuln("【安全扫描报告】：未发现安全问题") == "None"
