# agents/main_graph.py
from typing import Annotated, TypedDict
from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from agents.nodes import supervisor_node, security_expert_node
from agents.dev_subgraph import build_dev_subgraph


class MainState(TypedDict):
    messages: Annotated[list, add_messages]
    next: str
    security_done: bool
    dev_done: bool


# 实例化子图
dev_subgraph = build_dev_subgraph()


def dev_team_node(state: MainState):
    print("\n  [主图] 呼叫开发部子图入场...")
    # 将上下文精简后传入子图
    sub_inputs = {"messages": state["messages"][-2:]}
    sub_output = dev_subgraph.invoke(sub_inputs)

    print("  [主图] 开发部汇报完毕。")
    return {
        "messages": [AIMessage(content=f"【开发部最终汇报】：{sub_output['messages'][-1].content}", name="dev_team")],
        "dev_done": True
    }


# 构建主图
workflow = StateGraph(MainState)
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("security_expert", security_expert_node)
workflow.add_node("dev_team", dev_team_node)

workflow.add_edge(START, "supervisor")
workflow.add_conditional_edges(
    "supervisor",
    lambda state: state["next"],
    {"security_expert": "security_expert", "dev_team": "dev_team", "FINISH": END}
)
workflow.add_edge("security_expert", "supervisor")
workflow.add_edge("dev_team", "supervisor")

memory = MemorySaver()
main_app = workflow.compile(checkpointer=memory)