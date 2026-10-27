# week2_rag_api.py
# 第二周产物：把 RAG 链封成 FastAPI 服务。
# 注意：这不是主项目入口（主项目在 autofix_agent/main.py），
# 之前它叫 main.py，和 autofix_agent/main.py 同名，import main 会随机命中其中一个。
# 启动：uvicorn week2_rag_api:app --port 8001
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import time
from langchain_core.messages import HumanMessage, AIMessage

# 👇 1. 导入你写好的真实 RAG 构建函数
from week2_day6_memory_rag import build_memory_rag

# 👇 2. 在应用启动时，加载一次 RAG 链（不要放在接口里，否则每次请求都会重新加载 FAISS 和模型，慢得要命）
print("🚀 正在启动服务，加载 RAG 链和 FAISS 向量库...")
rag_chain, vector_store = build_memory_rag()
print("✅ RAG 链加载完成！")

app = FastAPI(
    title="RAG 知识库问答 API",
    description="基于 LangChain + FAISS + Qwen2.5 的 RAG 服务",
    version="0.1.0",
    swagger_ui_parameters={"lang": "zh-CN"},
)

# 👇 3. 新增：全局会话存储器（生产环境建议换成 Redis，这里用内存字典做演示）
# 结构： { "session_id_1": [HumanMessage, AIMessage, ...], "session_id_2": [...] }
session_histories: Dict[str, list] = {}


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="用户问题")
    # 👇 4. 修改：把 session_id 设为必填，以便区分不同用户
    session_id: str = Field(..., description="会话 ID，用于区分不同用户的记忆")
    top_k: int = Field(default=4, ge=1, le=10, description="检索文档数量，1~10")


class QueryResponse(BaseModel):
    answer: str
    sources: List[str] = []
    latency: float = 0.0


@app.get("/health")
def health():
    return {"status": "ok", "service": "rag-api"}


# 👇 5. 修改：使用普通的 def（不是 async def），FastAPI 会自动把它丢到线程池执行，避免阻塞事件循环
@app.post("/rag/query", response_model=QueryResponse)
def rag_query(req: QueryRequest):
    start = time.time()

    # 1. 根据 session_id 取出该用户的历史记录，如果没有就初始化一个空列表
    chat_history = session_histories.get(req.session_id, [])

    try:
        # 2. 调用真实的 RAG 链
        # 注意：这里我们先用 invoke 拿完整结果。你的脚本里用了 stream，但在 API 中一次性返回 JSON 对新手最友好。
        answer = rag_chain.invoke({
            "question": req.question,
            "chat_history": chat_history
        })

        # 3. 更新该用户的对话历史
        chat_history.append(HumanMessage(content=req.question))
        chat_history.append(AIMessage(content=answer))

        # 限制历史长度，防止 Token 爆炸（保留最近 5 轮对话）
        if len(chat_history) > 10:
            chat_history = chat_history[-10:]

        # 存回全局字典
        session_histories[req.session_id] = chat_history

        # 4. 获取检索到的来源（为了给前端展示“参考了哪些文档”）
        # 注意：你的 chain 内部已经检索过了，这里为了拿 sources 又检索了一次。
        # 生产环境建议改造 chain 让它在输出中直接带上 sources，我们后面再优化。
        docs = vector_store.similarity_search(req.question, k=req.top_k)
        sources = [f"data/test.txt#chunk-{i}" for i, _ in enumerate(docs)]  # 简化处理，用索引代替

        latency = time.time() - start
        return QueryResponse(
            answer=answer,
            sources=sources,
            latency=round(latency, 4),
        )

    except Exception as e:
        # 捕获异常，避免直接给前端抛出 500 裸报错
        raise HTTPException(status_code=500, detail=f"RAG 服务内部错误: {str(e)}")
