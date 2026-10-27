"""规范路由测试。

eval_rag.py 的实测数据：纯向量检索在 Bandit 输出上 recall@1 只有 38%
（8 条里 5 条召回错条目），而规则路由 100%。规范选错时模型会严格服从错误约束，
比不检索更糟 —— 所以路由必须是确定性的。
"""

from core.policy import select_rules
from services.rag_service import load_chunks, retrieve_for_scan

EVAL_SCAN = (
    "发现安全问题:\n"
    "- blacklist (MEDIUM) 行 2: Use of possibly insecure function - consider using safer ast.literal_eval."
)
SQL_SCAN = (
    "发现安全问题:\n- hardcoded_sql_expression (MEDIUM) 行 5: Possible SQL injection vector "
    "through string-based query construction."
)
EXEC_SCAN = "发现安全问题:\n- exec_used (MEDIUM) 行 3: Use of exec detected."


def test_kb_has_both_entries():
    assert set(load_chunks()) == {"CWE-95", "CWE-89"}


def test_eval_scan_routes_to_cwe95():
    assert [r.kb_id for r in select_rules(EVAL_SCAN)] == ["CWE-95"]


def test_exec_scan_routes_to_cwe95():
    assert [r.kb_id for r in select_rules(EXEC_SCAN)] == ["CWE-95"]


def test_sql_scan_routes_to_cwe89():
    assert [r.kb_id for r in select_rules(SQL_SCAN)] == ["CWE-89"]


def test_execute_does_not_trigger_dynamic_exec_rule():
    """cursor.execute 不能被 "exec" 误命中动态代码执行规则。"""
    assert select_rules("cursor.execute 字符串拼接") == []


def test_retrieval_returns_right_chunk():
    eval_text = retrieve_for_scan(EVAL_SCAN)
    assert "CWE-95" in eval_text and "SQL" not in eval_text

    sql_text = retrieve_for_scan(SQL_SCAN)
    assert "CWE-89" in sql_text and "动态代码执行" not in sql_text


def test_retrieval_is_deterministic():
    """同一输入两次必须给出同一段规范 —— 这是它能参与判定的前提。"""
    assert retrieve_for_scan(EVAL_SCAN) == retrieve_for_scan(EVAL_SCAN)
