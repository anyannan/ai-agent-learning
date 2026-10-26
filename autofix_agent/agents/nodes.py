from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from core.config import API_KEY, BASE_URL, MODEL_NAME
from tools.scan_tools import run_sast_scan
from services.rag_service import retrieve_security_standard

llm = ChatOpenAI(model=MODEL_NAME, api_key=API_KEY, base_url=BASE_URL, temperature=0)

def supervisor_node(state: dict):
    print("\n--- [Supervisor] 正在分析进度... ---")
    if not state.get("security_done"):
        decision = "security_expert"
    elif not state.get("dev_done"):
        decision = "dev_team"
    else:
        decision = "FINISH"
    print(f"👉 [Supervisor] 强制决策：{decision}")
    return {"next": decision}

def security_expert_node(state: dict, config: RunnableConfig):
    print("  [Security Expert] 正在调用 SAST 工具检查漏洞...")
    # 从用户输入中提取出需要扫描的文件名
    source_file = "source.py"
    for msg in state["messages"]:
        if "source.py" in msg.content: source_file = "source.py"
        elif "demo.py" in msg.content: source_file = "demo.py"

    scan_result = run_sast_scan.invoke({"file_path": source_file}, config=config)

    rag_enhancement = ""
    if "❌" in scan_result:
        print("  [Security Expert] 发现漏洞，正在检索 RAG 知识库...")
        rag_enhancement = retrieve_security_standard("Eval 注入 SQL 注入 修复规范")
        print(f"    [RAG 检索成功] 找到规范: {rag_enhancement[:30]}...")

    final_report = f"【安全扫描报告】：\n{scan_result}\n\n"
    if rag_enhancement:
        final_report += f"【企业安全规范参考】：\n{rag_enhancement}\n\n"
        final_report += "请 Coder 严格参考上述企业规范进行修复！"

    return {"messages": [AIMessage(content=final_report, name="security")], "security_done": True}