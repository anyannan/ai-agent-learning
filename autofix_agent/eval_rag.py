"""RAG 召回质量评测。

要回答的问题不是"向量检索准不准"，而是 **最终喂给模型的规范条目对不对** ——
规范选错了，模型会严格服从错误约束，这比不检索更糟。

所以对比两条路径：
- 向量检索（bge-m3 + FAISS）直接做路由
- 规则路由（issue_contains → kb_id），向量只在规则未覆盖时兜底

两个子集，因为输入分布不同：
- scan_like：模拟 Bandit 的真实输出格式（生产输入几乎都是这种）
- free_form：人类措辞的回退问法（不是生产输入，测兜底路径的退化程度）

用法：cd autofix_agent && python eval_rag.py
"""

import re

from core.policy import select_rules
from services.rag_service import get_retriever, load_chunks, retrieve_for_scan

EVAL_SCAN = (
    "发现安全问题:\n"
    "- blacklist (MEDIUM) 行 2: Use of possibly insecure function - consider using safer ast.literal_eval."
)
SQL_SCAN = (
    "发现安全问题:\n- hardcoded_sql_expression (MEDIUM) 行 5: Possible SQL injection vector "
    "through string-based query construction."
)
EXEC_SCAN = "发现安全问题:\n- exec_used (MEDIUM) 行 3: Use of exec detected."

SCAN_LIKE = [
    (EVAL_SCAN, "CWE-95"),
    (SQL_SCAN, "CWE-89"),
    (EXEC_SCAN, "CWE-95"),
    ("发现安全问题:\n- blacklist (LOW) 行 7: eval", "CWE-95"),
    ("发现安全问题:\n- hardcoded_sql_expression (HIGH) 行 12: SQL injection vector", "CWE-89"),
    ("发现安全问题:\n- blacklist (MEDIUM) 行 4: Use of possibly insecure function", "CWE-95"),
    ("发现安全问题:\n- hardcoded_sql_expression (MEDIUM) 行 2: string-based query construction", "CWE-89"),
    ("发现安全问题:\n- exec_used (MEDIUM) 行 9: Use of exec", "CWE-95"),
]

FREE_FORM = [
    ("eval 动态代码执行 修复规范", "CWE-95"),
    ("ast.literal_eval 是否安全", "CWE-95"),
    ("SQL 注入 修复规范", "CWE-89"),
    ("cursor.execute 字符串拼接怎么办", "CWE-89"),
    ("怎么安全地计算表达式字符串", "CWE-95"),
    ("用户输入拼进查询语句导致注入", "CWE-89"),
]

KB_ID_RE = re.compile(r"【(CWE-\d+)\s*[:：]")


def _doc_ids(docs):
    ids = []
    for d in docs:
        m = KB_ID_RE.match(d.page_content)
        ids.append(m.group(1) if m else "?")
    return ids


def vector_ids(query: str, k: int = 3):
    retriever = get_retriever()
    if retriever is None:
        return []
    try:
        return _doc_ids(retriever.vectorstore.similarity_search(query, k=k))
    except Exception as e:
        print(f"⚠️ 向量检索失败: {e}")
        return []


def routed_ids(query: str):
    return [r.kb_id for r in select_rules(query) if r.kb_id]


def score(pairs, k=3):
    rows = []
    for query, gold in pairs:
        vec = vector_ids(query, k)
        routed = routed_ids(query)
        rows.append(
            {
                "query": query.replace("\n", " ")[:58],
                "gold": gold,
                "vec": vec,
                "routed": routed,
                "vec_hit1": bool(vec) and vec[0] == gold,
                "vec_hitk": gold in vec,
                "routed_hit": gold in routed,
            }
        )
    return rows


def report(title, rows, show_vec=True):
    lines = [f"### {title}", ""]
    if show_vec:
        lines += ["| 查询 | 期望 | 向量 top-3 | vec@1 | vec@k | 规则路由 | 路由命中 |",
                  "|---|---|---|---|---|---|---|"]
    else:
        lines += ["| 查询 | 期望 | 规则路由 | 路由命中 |", "|---|---|---|---|"]
    for r in rows:
        if show_vec:
            lines.append(
                f"| {r['query']} | {r['gold']} | {', '.join(r['vec']) or '-'} "
                f"| {'Y' if r['vec_hit1'] else 'N'} | {'Y' if r['vec_hitk'] else 'N'} "
                f"| {', '.join(r['routed']) or '-'} | {'Y' if r['routed_hit'] else 'N'} |"
            )
        else:
            lines.append(
                f"| {r['query']} | {r['gold']} | {', '.join(r['routed']) or '-'} "
                f"| {'Y' if r['routed_hit'] else 'N'} |"
            )
    n = len(rows)
    vec1 = sum(r["vec_hit1"] for r in rows) / n
    veck = sum(r["vec_hitk"] for r in rows) / n
    route = sum(r["routed_hit"] for r in rows) / n
    lines.append("")
    lines.append(f"向量 recall@1 = {vec1:.0%}，recall@3 = {veck:.0%}；规则路由命中率 = {route:.0%}")
    lines.append("")
    return "\n".join(lines), (vec1, veck, route, n)


def main():
    chunks = load_chunks()
    print(f"知识库条目: {sorted(chunks)}\n")

    blocks = []
    scan_rows = score(SCAN_LIKE)
    block, scan_stats = report("scan_like：模拟 Bandit 输出（生产输入分布）", scan_rows)
    blocks.append(block)
    print(block)

    free_rows = score(FREE_FORM)
    block, free_stats = report("free_form：人类措辞（非生产输入，测兜底退化）", free_rows)
    blocks.append(block)
    print(block)

    covered = [q for q, g in SCAN_LIKE + FREE_FORM]
    served = sum(1 for q in covered if retrieve_for_scan(q))
    print(f"### 端到端：规范是否被成功注入\n")
    print(f"{served}/{len(covered)} 条查询拿到了非空规范文本（规则命中或向量兜底）\n")

    print("### 结论")
    print(f"- 生产输入（Bandit 输出）上，规则路由命中率 {scan_stats[2]:.0%}，向量 recall@1 只有 {scan_stats[0]:.0%}")
    print(f"- 人类措辞上向量 recall@1 {free_stats[0]:.0%}、recall@3 {free_stats[1]:.0%}，说明它不适合承担路由职责")
    print("- 因此规范选择改为规则优先、向量兜底；向量结果只作参考，不参与判定")


if __name__ == "__main__":
    main()
