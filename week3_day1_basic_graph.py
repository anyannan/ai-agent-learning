# week3_day1_basic_graph.py
# ---------------------------------------------------------------
# Week3 Day1: LangGraph 基础 —— 定义状态、节点和边
# 目标：构建一个 A -> B -> C 的线性工作流
# ---------------------------------------------------------------

from typing import TypedDict
from langgraph.graph import StateGraph, END


# ① 定义状态（State）
# 这就像是一个共享的“公文包”，在节点之间传递
class SimpleState(TypedDict):
    user_name: str  # 用户名字
    greeting: str  # 问候语
    final_message: str  # 最终消息


# ② 定义节点（Node）
# 节点本质上是 Python 函数，接收 State，返回要更新的字段（字典）
def node_a(state: SimpleState):
    print("--- 执行节点 A：接收用户名字 ---")
    # 这里我们打印一下当前状态，看看公文包里有什么
    print(f"当前状态：{state}")
    # 返回更新后的字段，LangGraph 会自动合并到全局 State 中
    return {"user_name": state["user_name"]}


def node_b(state: SimpleState):
    print("--- 执行节点 B：生成问候语 ---")
    # 从 state 里取到上一个节点的数据
    name = state["user_name"]
    greeting = f"你好，{name}！欢迎来到 AI Agent 的世界。"
    return {"greeting": greeting}


def node_c(state: SimpleState):
    print("--- 执行节点 C：组装最终消息 ---")
    # 从 state 里取到之前所有节点的数据
    greeting = state["greeting"]
    final = f"{greeting} 今天是你学习 LangGraph 的第一天！"
    return {"final_message": final}


# ③ 构建图（StateGraph）
# 创建一张以 SimpleState 为模板的地图
workflow = StateGraph(SimpleState)

# 把刚才定义的节点注册进去，起个名字
workflow.add_node("node_a", node_a)
workflow.add_node("node_b", node_b)
workflow.add_node("node_c", node_c)

# ④ 定义边（Edge）
# 设置入口点：从哪个节点开始
workflow.set_entry_point("node_a")

# 连接节点：A -> B -> C
workflow.add_edge("node_a", "node_b")
workflow.add_edge("node_b", "node_c")

# 设置终点：C 走完了，流程结束（END 是 LangGraph 内置常量）
workflow.add_edge("node_c", END)

# ⑤ 编译（Compile）
# 把地图变成可执行程序，就像把图纸变成真正的机器
app = workflow.compile()

# ⑥ 运行测试
if __name__ == "__main__":
    print("🚀 开始执行 LangGraph 工作流...\n")

    # invoke 传入初始状态，这里我们只给 user_name，其他字段让节点去填
    initial_state = {"user_name": "梨花诗"}

    # 运行！看看每个节点是不是按顺序执行了
    final_state = app.invoke(initial_state)

    print("\n✅ 执行完毕！最终状态：")
    print(final_state)

    print("\n📝 最终生成的消息：")
    print(final_state["final_message"])