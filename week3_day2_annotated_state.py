# week3_day2_annotated_state.py
# ---------------------------------------------------------------
# Week3 Day2: LangGraph 状态进阶 —— Annotated 与 operator.add
# 目标：解决多个节点修改同一字段时的“覆盖冲突”问题
# ---------------------------------------------------------------

from typing import TypedDict, Annotated
import operator
from langgraph.graph import StateGraph, END


# ① 定义状态
class ReducerState(TypedDict):
    # 👇 核心重点：使用 Annotated 声明合并规则
    # Annotated[类型, 合并函数]
    # operator.add 对于列表就是 extend（追加），对于数字就是相加
    messages: Annotated[list, operator.add]
    count: Annotated[int, operator.add]

    # 👇 对比项：没有加 Annotated，默认是“覆盖”
    simple_field: str


# ② 定义节点
def node_a(state: ReducerState):
    print("--- 执行节点 A ---")
    return {
        "messages": ["A发了一条消息"],
        "count": 1,
        "simple_field": "这是A的值"
    }


def node_b(state: ReducerState):
    print("--- 执行节点 B ---")
    return {
        "messages": ["B发了一条消息"],
        "count": 1,
        "simple_field": "这是B的值"
    }


def node_c(state: ReducerState):
    print("--- 执行节点 C ---")
    return {
        "messages": ["C发了一条消息"],
        "count": 1,
        "simple_field": "这是C的值"
    }


# ③ 构建图
workflow = StateGraph(ReducerState)
workflow.add_node("node_a", node_a)
workflow.add_node("node_b", node_b)
workflow.add_node("node_c", node_c)

workflow.set_entry_point("node_a")
workflow.add_edge("node_a", "node_b")
workflow.add_edge("node_b", "node_c")
workflow.add_edge("node_c", END)

app = workflow.compile()

# ④ 运行测试
if __name__ == "__main__":
    print("🚀 开始执行 LangGraph 状态合并测试...\n")

    initial_state = {
        "messages": ["初始消息"],
        "count": 0,
        "simple_field": "初始值"
    }

    final_state = app.invoke(initial_state)

    print("\n✅ 执行完毕！最终状态：")
    print(f"messages: {final_state['messages']}")
    print(f"count: {final_state['count']}")
    print(f"simple_field: {final_state['simple_field']}")