# services/rag_service.py
import os
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from core.config import API_KEY, BASE_URL


def build_retriever():
    print("⏳ 正在初始化安全知识库 RAG 服务...")
    embeddings = OpenAIEmbeddings(
        model="BAAI/bge-m3", api_key=API_KEY, base_url=BASE_URL
    )

    kb_path = os.path.join(os.path.dirname(__file__), "..", "data", "security_kb.txt")
    if not os.path.exists(kb_path):
        print("⚠️ 警告：未找到安全知识库文件，RAG 将不可用。")
        return None

    with open(kb_path, "r", encoding="utf-8") as f:
        text = f.read()

    # 按段落切分（简单处理）
    chunks = [c.strip() for c in text.split("\n\n") if c.strip()]
    vector_store = FAISS.from_texts(chunks, embeddings)
    return vector_store.as_retriever(search_kwargs={"k": 1})


# 全局单例
rag_retriever = build_retriever()

def retrieve_security_standard(query: str) -> str:
    if not rag_retriever:
        return "暂无安全规范知识库。"
    try:
        docs = rag_retriever.invoke(query)
        if not docs:
            return "未检索到相关安全规范。"
        # 🌟 核心修复：强制截断，最多保留 300 个字符，防止污染上下文
        return docs[0].page_content[:300] + "..."
    except Exception as e:
        return "检索规范失败。"