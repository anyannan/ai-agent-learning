# agents/nodes.py
import os
from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, AIMessage, ToolMessage
from pydantic import BaseModel, Field
from core.config import API_KEY, BASE_URL, MODEL_NAME

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
    print("  [Security Expert] 正在检查漏洞...")
    prompt = [SystemMessage(content="你是安全专家。一句话指出代码漏洞，并给出修复建议。")] + state["messages"]
    res = llm.invoke(prompt)
    return {"messages": [AIMessage(content=f"【安全汇报】：{res.content}", name="security")], "security_done": True}