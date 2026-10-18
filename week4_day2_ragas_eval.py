# week4_day2_ragas_eval.py
import os
import json
from dotenv import load_dotenv
from datasets import Dataset
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

# 导入 RAGAS
from ragas import evaluate
from ragas.metrics.collections import faithfulness, answer_relevancy, context_precision
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper

# 导入 RAG 链
from week2_day6_memory_rag import build_memory_rag

load_dotenv()


def run_evaluation():
    print("🚀 正在加载 RAG 链和 FAISS 向量库...")
    # 注意：复用之前写的链
    rag_chain, vector_store = build_memory_rag()

    print("📂 正在读取黄金测试集...")
    with open("data/eval_dataset.json", "r", encoding="utf-8") as f:
        test_data = json.load(f)

    questions = []
    answers = []
    contexts = []

    print("🔄 正在批量运行 RAG 生成回答（这可能需要一点时间）...")
    for item in test_data:
        q = item["question"]
        print(f"  -> 处理问题: {q}")

        # 1. 获取检索到的上下文 (Context)
        docs = vector_store.similarity_search(q, k=4)
        # RAGAS 需要 List[str] 格式的上下文
        ctx = [doc.page_content for doc in docs]

        # 2. 调用 RAG 链生成回答 (Answer)
        # 传入空的历史记录
        ans = rag_chain.invoke({"question": q, "chat_history": []})

        questions.append(q)
        answers.append(ans)
        contexts.append(ctx)

    # 3. 组装成 HuggingFace Dataset 格式
    data_dict = {
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": [item["ground_truth"] for item in test_data]
    }
    dataset = Dataset.from_dict(data_dict)

    # 4. 配置 RAGAS 使用的 LLM 和 Embedding（必须是硅基流动的）
    print("⚖️ 正在初始化 RAGAS 裁判（LLM）...")
    # RAGAS 的裁判模型必须支持 OpenAI 接口且输出稳定
    langchain_llm = ChatOpenAI(
        model="Qwen/Qwen2.5-7B-Instruct",
        api_key=os.getenv("SILICONFLOW_API_KEY"),
        base_url=os.getenv("SILICONFLOW_BASE_URL"),
        temperature=0
    )
    langchain_embeddings = OpenAIEmbeddings(
        model="BAAI/bge-m3",
        api_key=os.getenv("SILICONFLOW_API_KEY"),
        base_url=os.getenv("SILICONFLOW_BASE_URL")
    )

    ragas_llm = LangchainLLMWrapper(langchain_llm)
    ragas_embeddings = LangchainEmbeddingsWrapper(langchain_embeddings)

    # 5. 开始批量打分
    print("📊 开始执行 RAGAS 评估（会大量调用 LLM，请留意 Token 消耗）...")
    result = evaluate(
        dataset=dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision
        ],
        llm=ragas_llm,
        embeddings=ragas_embeddings,
    )

    print("\n" + "=" * 30 + " 评估结果 " + "=" * 30)
    print(result)
    print("=" * 72)


if __name__ == "__main__":
    run_evaluation()