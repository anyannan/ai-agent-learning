"""企业规范符合性校验测试。

核心断言：`not_covered`（没规则）不等于 `compliant`（合规）。
这条区分是这次改动的重点 —— 没有规则却判 PASS，本质上和 fail-open 是同一类错误。
"""

from langchain_core.messages import ToolMessage

from agents import dev_subgraph
from agents.dev_subgraph import evaluate_node
from core.policy import (
    COMPLIANT,
    NOT_COVERED,
    UNKNOWN,
    VIOLATED,
    check_source,
    load_rules,
    select_rules,
)
from tools.result import VERDICT_NEEDS_HUMAN, VERDICT_PASS, Status, envelope

EVAL_SCAN = "发现安全问题:\n- blacklist (MEDIUM) 行 2: Use of possibly insecure function - eval"
SQL_SCAN = "发现安全问题:\n- hardcoded_sql_expression (MEDIUM) 行 5: SQL injection"


# ---------- 1. 规则装载与匹配 ----------

def test_rules_load():
    ids = {r.id for r in load_rules()}
    assert "CWE-95-dynamic-exec" in ids


def test_rule_selection_by_scan_text():
    assert [r.id for r in select_rules(EVAL_SCAN)] == ["CWE-95-dynamic-exec"]
    assert [r.id for r in select_rules(SQL_SCAN)] == ["CWE-89-sql-injection"]


def test_unrelated_scan_is_not_covered():
    assert select_rules("发现安全问题:\n- hardcoded password") == []


# ---------- 2. CWE-95：必须用 corp_sec.safe_calc ----------

def test_compliant_usage():
    src = "from corp_sec import safe_calc\n\ndef f(x):\n    return safe_calc(x)\n"
    assert check_source(src, EVAL_SCAN).status == COMPLIANT


def test_eval_still_present_is_violated():
    src = "def f(x):\n    return eval(x)\n"
    result = check_source(src, EVAL_SCAN)
    assert result.status == VIOLATED
    assert "eval" in result.summary()


def test_ast_literal_eval_is_violated():
    """Bandit 对这个写法零告警，唯一挡得住的就是这层 AST 校验。"""
    src = "import ast\n\ndef f(x):\n    return ast.literal_eval(x)\n"
    result = check_source(src, EVAL_SCAN)
    assert result.status == VIOLATED
    assert "ast.literal_eval" in result.summary()


def test_aliased_import_counts():
    src = "from corp_sec import safe_calc as sc\n\ndef f(x):\n    return sc(x)\n"
    assert check_source(src, EVAL_SCAN).status == COMPLIANT


def test_module_style_call_counts():
    src = "import corp_sec\n\ndef f(x):\n    return corp_sec.safe_calc(x)\n"
    assert check_source(src, EVAL_SCAN).status == COMPLIANT


def test_missing_required_call_is_violated():
    src = "def f(x):\n    return x\n"
    result = check_source(src, EVAL_SCAN)
    assert result.status == VIOLATED
    assert "缺少必需调用" in result.summary()


def test_syntax_error_is_unknown():
    assert check_source("def f(:\n", EVAL_SCAN).status == UNKNOWN


# ---------- 3. CWE-89：禁止拼接 SQL ----------

def test_sql_fstring_is_violated():
    src = 'def f(cur, name):\n    cur.execute(f"SELECT * FROM u WHERE n={name}")\n'
    assert check_source(src, SQL_SCAN).status == VIOLATED


def test_sql_parameterized_is_compliant():
    src = 'def f(cur, name):\n    cur.execute("SELECT * FROM u WHERE n=%s", (name,))\n'
    assert check_source(src, SQL_SCAN).status == COMPLIANT


# ---------- 4. 接入 Evaluator ----------

def _scan_clean():
    class _FakeScan:
        @staticmethod
        def invoke(_args, config=None):
            return envelope(Status.CLEAN, "run_sast_scan", "未发现安全问题")

    return _FakeScan()


def _msg() -> ToolMessage:
    return ToolMessage(
        content=envelope(Status.CLEAN, "run_sandbox_test", "测试通过"),
        tool_call_id="call_1",
        name="run_sandbox_test",
    )


def test_evaluator_policy_violation_retries(tmp_path, monkeypatch):
    (tmp_path / "demo.py").write_text("def f(x):\n    return eval(x)\n", encoding="utf-8")
    monkeypatch.setattr(dev_subgraph, "run_sast_scan", _scan_clean())
    cfg = {"configurable": {"sandbox_dir": str(tmp_path), "source_file": "demo.py"}}
    out = evaluate_node(
        {"messages": [_msg()], "retry_count": 0, "scan_summary": EVAL_SCAN}, cfg
    )
    assert out["next_action"] == "retry"
    assert out["policy_status"] == "violated"


def test_evaluator_not_covered_goes_to_human(tmp_path, monkeypatch):
    (tmp_path / "demo.py").write_text("from corp_sec import safe_calc\nf = safe_calc\n", encoding="utf-8")
    monkeypatch.setattr(dev_subgraph, "run_sast_scan", _scan_clean())
    cfg = {"configurable": {"sandbox_dir": str(tmp_path), "source_file": "demo.py"}}
    out = evaluate_node(
        {"messages": [_msg()], "retry_count": 0, "scan_summary": "发现安全问题:\n- hardcoded password"}, cfg
    )
    assert out["verdict"] == VERDICT_NEEDS_HUMAN
    assert out["policy_status"] == NOT_COVERED


def test_evaluator_compliant_passes(tmp_path, monkeypatch):
    src = "from corp_sec import safe_calc\n\ndef f(x):\n    return safe_calc(x)\n"
    (tmp_path / "demo.py").write_text(src, encoding="utf-8")
    monkeypatch.setattr(dev_subgraph, "run_sast_scan", _scan_clean())
    cfg = {"configurable": {"sandbox_dir": str(tmp_path), "source_file": "demo.py"}}
    out = evaluate_node(
        {"messages": [_msg()], "retry_count": 0, "scan_summary": EVAL_SCAN}, cfg
    )
    assert out["verdict"] == VERDICT_PASS
    assert out["policy_status"] == COMPLIANT
