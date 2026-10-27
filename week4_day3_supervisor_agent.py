# week4_day3_supervisor_agent.py
# ---------------------------------------------------------------
# 【对照实现，非生产版】LLM 路由的 Supervisor 多 Agent 协作网络。
# 生产版 autofix_agent 最终改用了确定性编排（autofix_agent/agents/nodes.py: orchestrator_node），
# 原因是"安全扫描必须先于修复"是业务不变量，交给模型决策只会引入不确定性。
# 保留此文件用于对比两种范式的取舍：LLM 路由更灵活但不可预测，
# 确定性编排可预测但无法处理"拓扑需要按输入动态生成"的场景。
# ---------------------------------------------------------------
import os
from typing import Literal, TypedDict, Annotated
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

load_dotenv()

llm = ChatOpenAI(
    model="Qwen/Qwen2.5-7B-Instruct",
    api_key=os.getenv("SILICONFLOW_API_KEY"),
    base_url=os.getenv("SILICONFLOW_BASE_URL"),
    temperature=0
)

# ---------- 1. 状态定义：加入完成标记与迭代计数 ----------
class TeamState(TypedDict):
    messages: Annotated[list, add_messages]
    next: str
    # 记录每个专家是否已完成
    security_done: bool
    coder_done: bool
    tester_done: bool
    # 迭代计数器，防止死循环
    iterations: int

class Route(BaseModel):
    next_worker: Literal["security_expert", "coder", "tester", "FINISH"] = Field(
        description="下一步应该由谁执行：安全专家、码农、测试员，或者结束。"
    )

structured_supervisor_llm = llm.with_structured_output(Route, method="function_calling")

# ---------- 2. 节点定义 ----------
def supervisor_node(state: TeamState):
    print("\n--- [Supervisor] 正在分析进度... ---")

    # 硬性熔断：超过 10 次迭代直接结束
    if state.get("iterations", 0) >= 10:
        print("⚠️ 达到最大迭代次数，强制结束。")
        return {"next": "FINISH", "iterations": state.get("iterations", 0) + 1}

    # 根据完成状态构建提示，让 LLM 知道哪些活已经干过了
    done_summary = []
    if state.get("security_done"): done_summary.append("安全专家已完成检查")
    if state.get("coder_done"): done_summary.append("码农已完成修复")
    if state.get("tester_done"): done_summary.append("测试员已完成验证")

    system_prompt = f"""你是一个项目主管（Supervisor）。你的团队有：
- security_expert: 负责检查代码漏洞
- coder: 负责修复代码
- tester: 负责运行测试
- FINISH: 任务完成

当前进度：{', '.join(done_summary) if done_summary else '尚未开始任何工作'}
请根据进度和对话记录，判断下一步应该由谁执行。
如果所有工作都已完成，请输出 FINISH。"""

    recent_messages = state["messages"][-4:]
    prompt = [SystemMessage(content=system_prompt)] + recent_messages

    try:
        route_decision = structured_supervisor_llm.invoke(prompt)
        decision = route_decision.next_worker
    except Exception as e:
        print(f"⚠️ 主管决策提取失败: {e}，强制结束。")
        decision = "FINISH"

    print(f"👉 主管决定下一步交给：{decision}")
    # 在 return {"next": decision, ...} 之前拦截
    if decision == "security_expert" and state.get("security_done"):
        print("⚠️ 拦截：安全专家已执行过，强制重新决策。")
        decision = "coder"  # 或者直接 FINISH
    elif decision == "coder" and state.get("coder_done"):
        print("⚠️ 拦截：码农已修复过，强制重新决策。")
        decision = "tester"
    elif decision == "tester" and state.get("tester_done"):
        print("⚠️ 拦截：测试员已执行过，强制结束。")
        decision = "FINISH"
    return {"next": decision, "iterations": state.get("iterations", 0) + 1}

def security_expert_node(state: TeamState):
    print("  [Security Expert] 正在检查代码漏洞...")
    prompt = [SystemMessage(content="你是一个安全专家。请检查用户的代码，指出具体的漏洞名称（如 eval 注入）。用一句话简洁汇报。")] + state["messages"]
    response = llm.invoke(prompt)
    return {
        "messages": [AIMessage(content=f"【安全专家汇报】：{response.content}", name="security_expert")],
        "security_done": True
    }

def coder_node(state: TeamState):
    print("  [Coder] 正在根据专家建议修复代码...")
    prompt = [SystemMessage(content="你是一个资深 Python 码农。请根据安全专家的汇报，提供一段安全的替代代码，并说明怎么改的。")] + state["messages"]
    response = llm.invoke(prompt)
    return {
        "messages": [AIMessage(content=f"【码农汇报】：{response.content}", name="coder")],
        "coder_done": True
    }

def tester_node(state: TeamState):
    print("  [Tester] 正在对修复后的代码进行静态逻辑验证...")
    prompt = [SystemMessage(content="你是一个严格的测试员。请评估码农给出的修复方案是否真正解决了安全问题，并且没有引入新漏洞。如果通过，请明确输出 PASSED，否则输出 FAILED。")] + state["messages"]
    response = llm.invoke(prompt)
    return {
        "messages": [AIMessage(content=f"【测试员汇报】：{response.content}", name="tester")],
        "tester_done": True
    }

# ---------- 3. 构建图 ----------
workflow = StateGraph(TeamState)
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("security_expert", security_expert_node)
workflow.add_node("coder", coder_node)
workflow.add_node("tester", tester_node)

workflow.add_edge(START, "supervisor")

workflow.add_conditional_edges(
    "supervisor",
    lambda state: state["next"],
    {
        "security_expert": "security_expert",
        "coder": "coder",
        "tester": "tester",
        "FINISH": END
    }
)

workflow.add_edge("security_expert", "supervisor")
workflow.add_edge("coder", "supervisor")
workflow.add_edge("tester", "supervisor")

app = workflow.compile()

# ---------- 4. 运行测试 ----------
if __name__ == "__main__":
    print("🚀 启动 Supervisor 多 Agent 协作网络...")

    test_code = """
    def calculate(user_input):
        return eval(user_input)
    """

    initial_state = {
        "messages": [HumanMessage(content=f"请帮我检查并修复这段代码：\n{test_code}")],
        "next": "supervisor",
        "security_done": False,
        "coder_done": False,
        "tester_done": False,
        "iterations": 0
    }

    final_state = app.invoke(initial_state, config={"recursion_limit": 15})

    print("\n" + "="*40)
    print("✅ 协作流程结束！关键节点流转记录：")
    for msg in final_state["messages"]:
        role = getattr(msg, "name", "User")
        content_preview = str(msg.content)[:80].replace('\n', ' ')
        print(f"[{role}]: {content_preview}...")