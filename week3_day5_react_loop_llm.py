# week3_day5_react_loop.py
# ---------------------------------------------------------------
# Week3 Day5: LangGraph 循环与迭代 —— 实现 ReAct 模式
# 目标：让图具备“自我反思和重试”的能力，并设置熔断机制
# ---------------------------------------------------------------

from typing import TypedDict
from langgraph.graph import StateGraph, START, END

# ① 定义状态
class ReActState(TypedDict):
    question: str         # 用户问题
    thought: str          # 当前思考
    action: str           # 当前行动
    observation: str      # 观察结果
    iterations: int       # 迭代次数（熔断计数器）
    final_answer: str     # 最终答案

# ② 定义节点
def think_node(state: ReActState):
    """思考节点：决定是否继续行动，还是给出最终答案"""
    iterations = state.get("iterations", 0)
    print(f"--- [Think] 第 {iterations + 1} 次思考 ---")

    # 模拟大模型的思考逻辑：
    # 如果已经迭代了 2 次，就给出最终答案（模拟已经找到了足够的信息）
    if iterations >= 2:
        print("    👉 决定：信息已足够，给出最终答案。")
        return {
            "final_answer": "经过 3 轮思考，我终于找到了答案：它是 42！",
            "iterations": iterations + 1
        }

    # 否则，决定继续行动
    print(f"    👉 决定：还需要更多信息，执行行动。")
    return {
        "thought": f"第 {iterations + 1} 次思考：我还需要查询更多数据。",
        "action": "查询数据库",
        "iterations": iterations + 1
    }

def act_node(state: ReActState):
    """行动节点：模拟调用外部工具（比如数据库、搜索引擎）"""
    print("--- [Act] 执行行动 ---")
    # 模拟工具返回结果
    return {
        "observation": f"行动结果：数据库返回了新的线索（基于行动：{state['action']}）"
    }

# ③ 定义路由函数（决定循环是否继续）
def route_after_think(state: ReActState):
    """思考完之后，决定是去执行行动，还是结束循环"""
    # 熔断机制：如果超过最大迭代次数（比如 3 次），强制结束
    if state["iterations"] >= 3:
        print("--- [Router] 触发熔断：达到最大迭代次数，强制结束。 ---")
        return "end"

    # 如果已经生成了最终答案，结束循环
    if state.get("final_answer"):
        print("--- [Router] 检测到最终答案，结束循环。 ---")
        return "end"

    # 否则，去执行行动，然后回到思考节点
    print("--- [Router] 继续循环，前往行动节点。 ---")
    return "act"

# ④ 构建图
workflow = StateGraph(ReActState)

workflow.add_node("think", think_node)
workflow.add_node("act", act_node)

# 入口：从思考开始
workflow.add_edge(START, "think")

# 👇 核心：在思考节点后添加条件边
# 思考完之后，要么去“act”（继续循环），要么去“end”（结束）
workflow.add_conditional_edges(
    "think",
    route_after_think,
    {
        "act": "act",     # 继续循环
        "end": END        # 结束
    }
)

# 👇 核心：行动节点完成后，连回思考节点（形成循环）
workflow.add_edge("act", "think")

app = workflow.compile()

# ⑤ 运行测试
if __name__ == "__main__":
    print("🚀 开始执行 LangGraph ReAct 循环测试...\n")

    initial_state = {
        "question": "宇宙的终极答案是什么？",
        "iterations": 0,
        "final_answer": ""
    }

    final_state = app.invoke(initial_state)

    print("\n✅ 循环执行完毕！最终状态：")
    print(f"迭代次数：{final_state['iterations']}")
    print(f"最终答案：{final_state['final_answer']}")

    # ⑥ 可视化
    print("\n📊 工作流 Mermaid 图结构：")
    print(app.get_graph().draw_mermaid())