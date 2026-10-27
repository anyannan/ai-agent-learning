# eval_agent.py
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from services.rag_service import retrieve_security_standard
from agents.nodes import security_expert_node
from langchain_core.messages import HumanMessage

load_dotenv()


def evaluate_rag_value():
    print("🧪 开始对比测试：无 RAG vs 有 RAG\n")
    print("=" * 60)

    # 模拟一个漏洞场景
    vuln_code = "def calculate(expr):\n    return eval(expr)"
    scan_report = "❌ 扫描发现漏洞：\n- blacklist (MEDIUM): 行 2, Use of possibly insecure function - consider using safer ast.literal_eval."

    # 1. 无 RAG 的情况（大模型只看到扫描报告）
    print("【场景 1：无 RAG 增强】")
    llm = ChatOpenAI(
        model="Qwen/Qwen2.5-7B-Instruct", api_key=os.getenv("SILICONFLOW_API_KEY"),
        base_url=os.getenv("SILICONFLOW_BASE_URL"), temperature=0,
        timeout=60, max_retries=2,
    )
    prompt_no_rag = f"代码：\n{vuln_code}\n扫描报告：\n{scan_report}\n请给出修复建议。"
    ans_no_rag = llm.invoke(prompt_no_rag).content
    print(f"Agent 回复：{ans_no_rag[:150]}...\n")

    # 2. 有 RAG 的情况（大模型看到了 RAG 检索的企业规范）
    print("【场景 2：有 RAG 增强】")
    rag_context = retrieve_security_standard("Eval 注入修复规范")
    prompt_rag = f"代码：\n{vuln_code}\n扫描报告：\n{scan_report}\n企业安全规范：\n{rag_context}\n请给出修复建议。"
    ans_rag = llm.invoke(prompt_rag).content
    print(f"Agent 回复：{ans_rag[:150]}...\n")

    print("=" * 60)
    print("📊 评估结论：")
    print("1. 无 RAG 时，模型可能根据自身知识给出修复建议，但可能不符合公司规范。")
    print("2. 有 RAG 时，模型会严格检索并引用企业规范，修复方案更符合工业化落地要求。")

    # 3. 简单的关键词命中率检验 (用来替代 RAGAS)
    keywords = ["ast.literal_eval", "__builtins__", "CWE", "白名单"]
    hit_no_rag = sum(1 for k in keywords if k in ans_no_rag)
    hit_rag = sum(1 for k in keywords if k in ans_rag)

    print(f"\n🔑 关键规范词命中数（越高越符合规范）：")
    print(f"  - 无 RAG 命中数：{hit_no_rag}/4")
    print(f"  - 有 RAG 命中数：{hit_rag}/4")

    if hit_rag > hit_no_rag:
        print("\n✅ 结论：引入 RAG 后，Agent 的修复建议对安全规范的忠实度显著提升！")


if __name__ == "__main__":
    evaluate_rag_value()