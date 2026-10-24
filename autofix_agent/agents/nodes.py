# agents/nodes.py
import os
from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, AIMessage, ToolMessage
from pydantic import BaseModel, Field
from core.config import API_KEY, BASE_URL, MODEL_NAME
from tools.scan_tools import run_sast_scan
llm = ChatOpenAI(model=MODEL_NAME, api_key=API_KEY, base_url=BASE_URL, temperature=0)

# --- 结构化路由 ---
class Route(BaseModel):
    next_worker: Literal["security_expert", "dev_team", "FINISH"] = Field(description="下一步")

structured_supervisor_llm = llm.with_structured_output(Route, method="function_calling")


def supervisor_node(state: dict):
    print("\n--- [Supervisor] 正在分析进度... ---")

    # 🌟 核心修复：直接根据状态硬编码决定，不再用 LLM 猜
    if not state.get("security_done"):
        decision = "security_expert"
    elif not state.get("dev_done"):
        decision = "dev_team"
    else:
        decision = "FINISH"

    print(f"👉 [Supervisor] 强制决策：{decision}")
    return {"next": decision}


def security_expert_node(state: dict):
    print("  [Security Expert] 正在调用 SAST 工具检查漏洞...")
    # 假设我们在 API 层约定，传入的文件名为 target.py
    scan_result = run_sast_scan.invoke({"file_path": "target.py"})

    return {
        "messages": [AIMessage(content=f"【安全扫描报告】：\n{scan_result}", name="security")],
        "security_done": True
    }