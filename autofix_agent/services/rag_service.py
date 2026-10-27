# services/rag_service.py
"""企业私有安全规范的检索服务。

两处刻意的设计：
1. 懒加载：不在 import 期建索引。否则任何 import 这个模块的代码（包括单测）
   都会打网络建 FAISS；而且一旦初始化失败，整个进程生命周期内 RAG 都是死的。
2. 不可用时返回空串而不是一句提示语。返回提示语会让上层"看起来拿到了规范"，
   审计里就会记成 rag_used=True —— 这是审计撒谎，比没有审计更糟。
"""

import os
import re
import threading

from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

from core.config import (
    API_KEY,
    BASE_URL,
    EMBEDDING_MAX_RETRIES,
    EMBEDDING_MODEL,
    EMBEDDING_TIMEOUT_SEC,
)
from core.policy import select_rules

KB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "security_kb.txt")
# k=1 时 top-1 错配会给出错误的企业约束，而"错误约束"比"没有约束"更危险：
# 模型会严格服从它。所以宁可多召回几条候选让模型自己挑。
TOP_K = 3
MAX_DOCS_IN_PROMPT = 2
KB_ID_RE = re.compile(r"【(CWE-\d+)\s*[:：]")

_lock = threading.Lock()
_retriever = None
_init_done = False


def build_retriever():
    print("⏳ 正在初始化安全知识库 RAG 服务...")
    if not os.path.exists(KB_PATH):
        print("⚠️ 未找到安全知识库文件，RAG 不可用。")
        return None

    with open(KB_PATH, "r", encoding="utf-8") as f:
        text = f.read()
    chunks = [c.strip() for c in text.split("\n\n") if c.strip()]
    if not chunks:
        print("⚠️ 知识库为空，RAG 不可用。")
        return None

    try:
        embeddings = OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            api_key=API_KEY,
            base_url=BASE_URL,
            timeout=EMBEDDING_TIMEOUT_SEC,
            max_retries=EMBEDDING_MAX_RETRIES,
        )
        vector_store = FAISS.from_texts(chunks, embeddings)
        print("✅ RAG 知识库初始化成功！")
        return vector_store.as_retriever(search_kwargs={"k": TOP_K})
    except Exception as e:
        print(f"🚨 RAG 初始化失败（网络或额度问题）: {e}")
        print("⚠️ 已降级：本次运行不注入企业规范，修复将只依赖模型通用知识，审计中会标记 rag_used=False。")
        return None


def get_retriever():
    global _retriever, _init_done
    with _lock:
        if not _init_done:
            _init_done = True
            _retriever = build_retriever()
        return _retriever


def is_available() -> bool:
    return get_retriever() is not None


def retrieve_security_standard(query: str) -> str:
    """纯向量检索（兜底路径）；不可用或检索失败返回空串。"""
    retriever = get_retriever()
    if retriever is None:
        return ""
    try:
        docs = retriever.invoke(query)
    except Exception as e:
        print(f"⚠️ RAG 检索失败: {e}")
        return ""
    if not docs:
        return ""
    return "\n\n".join(d.page_content[:300] for d in docs[:MAX_DOCS_IN_PROMPT])


def load_chunks() -> dict:
    """把知识库切成 {CWE-ID: 段落}。KB 是封闭小库，切分按段落即可。"""
    try:
        text = open(KB_PATH, "r", encoding="utf-8").read()
    except OSError:
        return {}
    chunks = {}
    for part in (p.strip() for p in text.split("\n\n")):
        if not part:
            continue
        m = KB_ID_RE.match(part)
        if m:
            chunks[m.group(1)] = part
    return chunks


def retrieve_for_scan(scan_summary: str, max_chars: int = 600) -> str:
    """按扫描结果取企业规范：规则优先路由，向量检索只做兜底。

    为什么不直接用向量检索做路由：实测中"blacklist ... ast.literal_eval"这条
    扫描文本会被召回成 SQL 注入规范（recall@1 见 eval_rag.py）。规范选择错了，
    模型会严格服从错误约束 —— 这比不检索更糟。

    规则里的 issue_contains 本来就是确定性的路由条件，用它选 kb_id 是可解释的；
    只有规则没覆盖的漏洞才退回向量检索。
    """
    kb_ids = [r.kb_id for r in select_rules(scan_summary) if r.kb_id]
    chunks = load_chunks()
    picked = [chunks[i] for i in kb_ids if i in chunks]
    if picked:
        return "\n\n".join(picked)[:max_chars]

    print("  [RAG] 无规则覆盖，退回向量检索（结果仅供参考，不参与判定）")
    return retrieve_security_standard(scan_summary)[:max_chars]
