import os
from multiprocessing.managers import all_methods

from dotenv import load_dotenv
from langchain_classic.chains.summarize.map_reduce_prompt import prompt_template
# 导入核心组件
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

# 加载环境变量
load_dotenv()


def format_docs(docs):
    """辅助函数：将检索到的多个 Document 对象拼接成一个纯文本字符串"""
    return "\n\n".join(doc.page_content for doc in docs)


def build_rag_chain():
    """构建 RAG 问答链路"""
    # 1. 初始化 Embedding 模型
    embeddings = OpenAIEmbeddings(
        model="BAAI/bge-m3",
        api_key=os.getenv("SILICONFLOW_API_KEY"),
        base_url=os.getenv("SILICONFLOW_BASE_URL")
    )

    # 2. 加载本地 FAISS 向量库
    print("⏳ 正在加载本地 FAISS 向量库...")
    vector_store = FAISS.load_local(
        "faiss_index",
        embeddings,
        allow_dangerous_deserialization=True
    )

    # 3. 将向量库转换为 Retriever（检索器）
    # search_kwargs={"k": 2} 表示每次检索最相似的 2 个文本块
    retriever = vector_store.as_retriever(search_kwargs={"k": 2})

    # 4. 初始化 LLM
    llm = ChatOpenAI(
        model="Qwen/Qwen2.5-7B-Instruct",
        api_key=os.getenv("SILICONFLOW_API_KEY"),
        base_url=os.getenv("SILICONFLOW_BASE_URL"),
        temperature=0.1  # 温度调低，RAG 问答需要严谨，不能随意发挥
    )

    # 5. 构建 Prompt 模板（重点：加入防幻觉约束）
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个严谨的AI知识库助手。
请严格根据以下背景资料回答用户的问题。
如果背景资料中不包含问题的答案，必须明确说明“根据现有资料无法回答”，绝不允许胡编乱造。

背景资料：
{context}"""),
        ("user", "{question}")
    ])

    # 6. 使用 LCEL 管道符构建 RAG 链路
    # 这是一个非常经典的 RAG 链路模板，请务必背下来！
    rag_chain = (
            {"context": retriever | format_docs, "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
    )

    return rag_chain


if __name__ == "__main__":
    rag_chain = build_rag_chain()
    print("==== RAG 知识库问答助手已启动 (输入 exit 退出) ====")

    while True:
        question = input("\n你：")
        if question.strip().lower() == "exit":
            break

        print("AI：", end="")
        # 使用 stream 方法实现流式输出（打字机效果）
        for chunk in rag_chain.stream(question):
            print(chunk, end="", flush=True)
        print()