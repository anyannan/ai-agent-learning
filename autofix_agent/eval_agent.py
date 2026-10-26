# eval_agent.py
import os
import json
from dotenv import load_dotenv
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from services.rag_service import retrieve_security_standard

load_dotenv()


def run_ragas_eval():
    # 模拟测试集：问题 + 标准答案（Ground Truth）
    test_data = [
        {
            "question": "发现 eval 漏洞，且代码中有数学运算 1+1，应该怎么安全修复？",
            "ground_truth": "应使用 eval(expression, {'__builtins__': None}, {}) 来限制内置函数，禁用恶意代码执行，同时保证数学运算正常。"
        }
    ]

    questions, answers, contexts = [], [], []

    for item in test_data:
        q = item["question"]
        # 1. 模拟 Agent 的检索与回答
        ctx = retrieve_security_standard(q)
        # 这里我们直接模拟大模型基于 RAG 增强后的回答
        # 实际项目中，你应该去调用 AutoFix API 获取真实结果
        ans = "使用带受限环境的 eval 进行修复，如 `eval(expression, {'__builtins__': None}, {})`。"

        questions.append(q)
        answers.append(ans)
        contexts.append([ctx])

    dataset = Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": [item["ground_truth"] for item in test_data]
    })

    llm = ChatOpenAI(
        model="Qwen/Qwen2.5-7B-Instruct", api_key=os.getenv("SILICONFLOW_API_KEY"),
        base_url=os.getenv("SILICONFLOW_BASE_URL"), temperature=0
    )
    embeddings = OpenAIEmbeddings(
        model="BAAI/bge-m3", api_key=os.getenv("SILICONFLOW_API_KEY"),
        base_url=os.getenv("SILICONFLOW_BASE_URL")
    )

    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy],
        llm=LangchainLLMWrapper(llm),
        embeddings=LangchainEmbeddingsWrapper(embeddings)
    )
    print("\n" + "=" * 30 + " RAGAS 评估结果 " + "=" * 30)
    print(result)
    print("=" * 72)


if __name__ == "__main__":
    run_ragas_eval()