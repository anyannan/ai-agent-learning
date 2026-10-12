import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

load_dotenv()


def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)


def build_memory_rag():
    embeddings = OpenAIEmbeddings(
        model="BAAI/bge-m3",
        api_key=os.getenv("SILICONFLOW_API_KEY"),
        base_url=os.getenv("SILICONFLOW_BASE_URL")
    )

    vector_store = FAISS.load_local(
        "faiss_index", embeddings, allow_dangerous_deserialization=True
    )
    retriever = vector_store.as_retriever(search_kwargs={"k": 4})

    llm = ChatOpenAI(
        model="Qwen/Qwen2.5-7B-Instruct",
        api_key=os.getenv("SILICONFLOW_API_KEY"),
        base_url=os.getenv("SILICONFLOW_BASE_URL"),
        temperature=0.1
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个严谨的AI知识库助手。
    请严格根据以下【背景资料】回答用户关于知识库的问题。
    如果用户的问题是询问“我们刚才聊了什么”、“之前的对话内容”等关于对话历史的问题，请只根据【对话历史】回答，绝对不要使用【背景资料】的内容来充当聊天历史！

    【背景资料】：
    {context}"""),
        MessagesPlaceholder(variable_name="chat_history"),
        ("user", "{question}")
    ])

    # 构建 RAG 链路
    rag_chain = (
            {
                # ⚠️ 核心修复：在 lambda 内部完成“检索 + 格式化”，直接返回最终字符串
                "context": lambda x: format_docs(retriever.invoke(x["question"])),
                "question": lambda x: x["question"],
                "chat_history": lambda x: x.get("chat_history", [])
            }
            | prompt
            | llm
            | StrOutputParser()
    )
    return rag_chain, vector_store


if __name__ == "__main__":
    rag_chain, vector_store = build_memory_rag()
    print("==== 带记忆的 RAG 助手已启动 (输入 exit 退出，输入 clear 清空记忆) ====")

    # ⚠️ 核心变化：在循环外维护对话历史
    chat_history = []  # 存储过往对话，格式为 [HumanMessage(...), AIMessage(...)]

    from langchain_core.messages import HumanMessage, AIMessage

    # 放在 while True: 之前
    print("\n=== 测试检索器对 A01 的召回情况 ===")
    # 临时把 k 调到 10，看看前 10 个到底有没有 A01
    test_retriever = vector_store.as_retriever(search_kwargs={"k": 10})
    test_docs = test_retriever.invoke("什么是A01")
    for i, d in enumerate(test_docs):
        print(f"\n【第 {i + 1} 块】包含A01: {'A01' in d.page_content}")
        print(d.page_content)  # 打印完整内容

    while True:
        question = input("\n你：")
        if question.strip().lower() == "exit":
            break
        if question.strip().lower() == "clear":
            chat_history = []
            print("🧹 对话记忆已清空！")
            continue
        # 在 while 循环里做判断
        if "刚才聊" in question or "历史记录" in question or "我们聊了" in question:
            # 直接调 llm 回答，不检索，或者直接回复提示
            print("AI：我就是一个AI助手，我们刚刚正在聊天呀。")
            continue  # ⚠️ 加上 continue，直接跳过下面的 RAG 流程
        print("AI：", end="")
        ai_response = ""

        # 通过 invoke/stream 传参，把历史会话和历史问答注入
        for chunk in rag_chain.stream({
            "question": question,
            "chat_history": chat_history
        }):
            print(chunk, end="", flush=True)
            ai_response += chunk
        print()

        # ⚠️ 核心变化：对话结束后，把这一轮问答追加到历史中
        chat_history.append(HumanMessage(content=question))
        chat_history.append(AIMessage(content=ai_response))

        # 可选：限制历史长度，防止 Token 爆炸（窗口记忆的思想）
        if len(chat_history) > 10:  # 保留最近 5 轮
            chat_history = chat_history[-10:]