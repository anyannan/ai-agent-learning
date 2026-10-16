# week3_day3_parallel_graph.py
# ---------------------------------------------------------------
# Week3 Day3: LangGraph 节点与边进阶 —— 并行执行(Fan-out)与汇聚(Fan-in)
# 目标：让多个节点同时工作，并正确合并状态
# ---------------------------------------------------------------

from typing import TypedDict, Annotated
import operator
from langgraph.graph import StateGraph, START, END


# ① 定义状态
# ⚠️ 并行图必须使用 Reducer，否则并行节点同时写入会报错
class ParallelState(TypedDict):
    messages: Annotated[list, operator.add]


# ② 定义节点
def node_start(state: ParallelState):
    print("--- 执行节点 A：发起任务 ---")
    return {"messages": ["A：任务已启动"]}


def node_b(state: ParallelState):
    print("--- 执行节点 B：买材料（并行） ---")
    return {"messages": ["B：材料买好了"]}


def node_c(state: ParallelState):
    print("--- 执行节点 C：准备工具（并行） ---")
    return {"messages": ["C：工具备好了"]}


def node_d(state: ParallelState):
    print("--- 执行节点 D：汇总（汇聚点） ---")
    return {"messages": ["D：汇总完毕"]}


# ③ 构建图
workflow = StateGraph(ParallelState)

workflow.add_node("node_a", node_start)
workflow.add_node("node_b", node_b)
workflow.add_node("node_c", node_c)
workflow.add_node("node_d", node_d)

# ④ 定义边：使用 START 和并行路由
# 显式使用 START 常量作为入口（比 set_entry_point 更现代）
workflow.add_edge(START, "node_a")

# 👇 核心：A 走完后，B 和 C 同时开始（Fan-out）
workflow.add_edge("node_a", "node_b")
workflow.add_edge("node_a", "node_c")

# 👇 汇聚：B 和 C 都走完后，才进入 D（Fan-in）
# 注意：D 会执行两次吗？LangGraph 默认会自动等待 B 和 C 都完成，再执行一次 D
workflow.add_edge("node_b", "node_d")
workflow.add_edge("node_c", "node_d")

workflow.add_edge("node_d", END)

app = workflow.compile()

# ⑤ 运行测试
if __name__ == "__main__":
    print("🚀 开始执行 LangGraph 并行图测试...\n")

    initial_state = {"messages": ["初始消息"]}

    final_state = app.invoke(initial_state)

    print("\n✅ 执行完毕！最终状态：")
    for msg in final_state["messages"]:
        print(f"  - {msg}")

    # ⑥ 可视化：打印 Mermaid 格式的流程图
    print("\n📊 工作流 Mermaid 图结构：")
    print(app.get_graph().draw_mermaid())