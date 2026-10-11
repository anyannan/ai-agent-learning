import os
import requests
from dotenv import load_dotenv
from typing import List, Optional, Sequence
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_core.documents import Document
from langchain_core.documents.compressor import BaseDocumentCompressor
load_dotenv()


class SiliconFlowReranker(BaseDocumentCompressor):
    """自定义的硅基流动重排序压缩器"""
    api_key: str
    base_url: str = "https://api.siliconflow.cn/v1/rerank"
    model: str = "BAAI/bge-reranker-v2-m3"

    def compress_documents(
            self,
            documents: Sequence[Document],
            query: str,
            callbacks: Optional[any] = None,
    ) -> Sequence[Document]:
        if not documents:
            return []

        # 构建请求体
        payload = {
            "model": self.model,
            "query": query,
            "documents": [doc.page_content for doc in documents],
            "top_n": 3  # 精排后只保留最相似的 3 个
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(self.base_url, json=payload, headers=headers)
            response.raise_for_status()
            results = response.json().get("results", [])

            # 按重排分数重新组织文档
            reranked_docs = []
            for res in results:
                index = res["index"]
                reranked_docs.append(documents[index])
            return reranked_docs
        except Exception as e:
            print(f"⚠️ Rerank API 调用失败，降级返回原始顺序: {e}")
            return documents[:3]


def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)


def build_advanced_rag():
    embeddings = OpenAIEmbeddings(
        model="BAAI/bge-m3",
        api_key=os.getenv("SILICONFLOW_API_KEY"),
        base_url=os.getenv("SILICONFLOW_BASE_URL")
    )

    vector_store = FAISS.load_local(
        "faiss_index", embeddings, allow_dangerous_deserialization=True
    )

    # 1. 基础检索器：召回 Top 10 候选
    base_retriever = vector_store.as_retriever(search_kwargs={"k": 10})

    # 2. 自定义 Rerank 压缩器
    reranker = SiliconFlowReranker(api_key=os.getenv("SILICONFLOW_API_KEY"))

    # 3. 上下文压缩检索器：先召回10个，再精排保留3个
    from langchain_classic.retrievers import ContextualCompressionRetriever
    compression_retriever = ContextualCompressionRetriever(
        base_compressor=reranker, base_retriever=base_retriever
    )

    llm = ChatOpenAI(
        model="Qwen/Qwen2.5-7B-Instruct",
        api_key=os.getenv("SILICONFLOW_API_KEY"),
        base_url=os.getenv("SILICONFLOW_BASE_URL"),
        temperature=0.1
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个严谨的AI知识库助手。请严格根据背景资料回答：\n\n{context}"),
        ("user", "{question}")
    ])

    # 4. 构建带 Rerank 的 RAG 链路
    rag_chain = (
            {"context": compression_retriever | format_docs, "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
    )
    return rag_chain


if __name__ == "__main__":
    rag_chain = build_advanced_rag()
    print("==== 带 Rerank 的高级 RAG 已启动 (输入 exit 退出) ====")
    while True:
        q = input("\n你：")
        if q.strip().lower() == "exit": break
        print("AI：", end="")
        for chunk in rag_chain.stream(q):
            print(chunk, end="", flush=True)
        print()