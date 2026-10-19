# week4_day4_subgraph.py
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


# ==========================================
# 🟢 第一部分：构建【子图】（开发部）
# ==========================================
class DevState(TypedDict):
    messages: Annotated[list, add_messages]
    code_fixed: bool
    test_passed: bool
    retry_count: int


def coder_node(state: DevState):
    print("    [子图-Coder] 正在写代码...")
    prompt = [SystemMessage(content="你是一个码农。请修复代码中的漏洞，并输出修复后的代码。")] + state["messages"]
    response = llm.invoke(prompt)
    return {
        "messages": [AIMessage(content=f"【码农改了代码】：{response.content}", name="coder")],
        "code_fixed": True
    }


def tester_node(state: DevState):
    print("    [子图-Tester] 正在跑测试...")
    # 模拟测试：如果码农提到了 `eval` 没被修复，就报错
    prompt = [SystemMessage(
        content="你是一个测试员。请检查码农的代码。如果代码里还有 eval，输出 FAILED，否则输出 PASSED。")] + state["messages"]
    response = llm.invoke(prompt)
    is_passed = "PASSED" in response.content

    return {
        "messages": [AIMessage(content=f"【测试员结论】：{response.content}", name="tester")],
        "test_passed": is_passed,
        "retry_count": state.get("retry_count", 0) + 1
    }


def route_after_test(state: DevState):
    if state.get("test_passed"):
        print("    [子图] 测试通过，准备向大老板汇报！")
        return "end"
    if state.get("retry_count", 0) >= 2:
        print("    [子图] 重试次数用完，强行结束，准备向大老板汇报！")
        return "end"
    print("    [子图] 测试失败，打回给码农重写！")
    return "retry"


# 构建子图
dev_builder = StateGraph(DevState)
dev_builder.add_node("coder", coder_node)
dev_builder.add_node("tester", tester_node)
dev_builder.add_edge(START, "coder")
dev_builder.add_edge("coder", "tester")
dev_builder.add_conditional_edges(
    "tester",
    route_after_test,
    {"end": END, "retry": "coder"}
)
# 编译子图（它现在是一个可以当作节点使用的独立模块了）
dev_subgraph = dev_builder.compile()


# ==========================================
# 🔵 第二部分：构建【主图】（公司）
# ==========================================
class TeamState(TypedDict):
    messages: Annotated[list, add_messages]
    next: str
    security_done: bool
    dev_done: bool


class Route(BaseModel):
    next_worker: Literal["security_expert", "dev_team", "FINISH"] = Field(description="下一步交给谁")


structured_supervisor_llm = llm.with_structured_output(Route, method="function_calling")


def supervisor_node(state: TeamState):
    print("\n--- [主图-Supervisor] 正在分析进度... ---")
    done_summary = []
    if state.get("security_done"): done_summary.append("安全检查已完成")
    if state.get("dev_done"): done_summary.append("代码开发已完成")

    system_prompt = f"""你是主管。团队有：
    - security_expert: 检查漏洞
    - dev_team: 负责写代码和测试（内部是一整个团队）
    - FINISH: 结束
    当前进度：{', '.join(done_summary) if done_summary else '刚开始'}
    请决定下一步。"""

    try:
        decision = structured_supervisor_llm.invoke(
            [SystemMessage(content=system_prompt)] + state["messages"][-4:]).next_worker
    except Exception:
        decision = "FINISH"

    # 代码层拦截
    if decision == "security_expert" and state.get("security_done"): decision = "dev_team"
    if decision == "dev_team" and state.get("dev_done"): decision = "FINISH"

    print(f"👉 [主图] 主管决定：{decision}")
    return {"next": decision}


def security_expert_node(state: TeamState):
    print("  [主图-Security] 检查漏洞...")
    prompt = [SystemMessage(content="你是安全专家。一句话指出代码漏洞。")] + state["messages"]
    res = llm.invoke(prompt)
    return {"messages": [AIMessage(content=f"【安全汇报】：{res.content}", name="security")], "security_done": True}


# 🔑 核心魔法：把子图当作一个普通节点，塞进主图里！
def dev_team_node(state: TeamState):
    print("  [主图] 呼叫开发部子图入场干活...")

    # 将主图的状态精简后，传入子图
    sub_inputs = {
        "messages": state["messages"][-2:],  # 只传最近两条，避免子图被历史干扰
        "code_fixed": False,
        "test_passed": False,
        "retry_count": 0
    }

    # 运行子图
    sub_output = dev_subgraph.invoke(sub_inputs)

    # 子图跑完后，把子图里的关键结果提取出来，带回给主图
    print("  [主图] 开发部汇报完毕，返回主流程。")
    return {
        # 只需要把子图里最后一条测试结论带回主图即可
        "messages": [AIMessage(content=f"【开发部总汇报】：{sub_output['messages'][-1].content}", name="dev_team")],
        "dev_done": True
    }


# 构建主图
workflow = StateGraph(TeamState)
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("security_expert", security_expert_node)
workflow.add_node("dev_team", dev_team_node)  # 注册子图节点

workflow.add_edge(START, "supervisor")
workflow.add_conditional_edges(
    "supervisor",
    lambda state: state["next"],
    {"security_expert": "security_expert", "dev_team": "dev_team", "FINISH": END}
)
workflow.add_edge("security_expert", "supervisor")
workflow.add_edge("dev_team", "supervisor")

app = workflow.compile()

if __name__ == "__main__":
    print("🚀 启动带【子图隔离】的多 Agent 协作网络...\n")

    test_code = "def calculate(user_input): return eval(user_input)"
    initial_state = {
        "messages": [HumanMessage(content=f"请修复这段代码：\n{test_code}")],
        "next": "supervisor",
        "security_done": False,
        "dev_done": False
    }

    final_state = app.invoke(initial_state, config={"recursion_limit": 15})
    print("\n✅ 协作流程结束！")