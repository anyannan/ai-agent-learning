# week3_day4_conditional_edges.py
# ---------------------------------------------------------------
# Week3 Day4: LangGraph 条件边与路由 —— add_conditional_edges
# 目标：根据 State 里的数据，动态决定下一步走哪个节点
# ---------------------------------------------------------------

from typing import TypedDict
from langgraph.graph import StateGraph, START, END

# ① 定义状态
class RouterState(TypedDict):
    question: str      # 用户问题
    route: str         # 路由结果（记录走了哪条路）
    answer: str        # 最终答案

# ② 定义节点
def classify_question(state: RouterState):
    """分类节点：判断问题类型"""
    print("--- 执行节点：问题分类 ---")
    # 简单模拟：如果问题长度大于 5，就走详细回答
    if len(state["question"]) > 5:
        return {"route": "detailed"}
    else:
        return {"route": "simple"}

def simple_answer(state: RouterState):
    """简单回答节点"""
    print("--- 执行节点：简单回答 ---")
    return {"answer": f"简答：{state['question']}的答案是 42。"}

def detailed_answer(state: RouterState):
    """详细回答节点"""
    print("--- 执行节点：详细回答 ---")
    return {"answer": f"详答：关于“{state['question']}”，这涉及到深度的知识库检索，我们会在后续的 RAG 中详细展开。"}

# ③ 定义路由函数
# 这是条件边的核心：它接收 State，返回一个字符串，告诉图接下来去哪个节点
def route_question(state: RouterState):
    print(f"--- 执行路由判断：当前分类结果是 {state['route']} ---")
    if state["route"] == "detailed":
        return "node_detailed"
    else:
        return "node_simple"

# ④ 构建图
workflow = StateGraph(RouterState)

workflow.add_node("node_classify", classify_question)
workflow.add_node("node_simple", simple_answer)
workflow.add_node("node_detailed", detailed_answer)

# 入口
workflow.add_edge(START, "node_classify")

# 👇 核心：添加条件边
# 参数1：从哪个节点出发（node_classify）
# 参数2：路由函数（route_question），它决定下一步去哪
# 参数3：路径映射字典（可选，但强烈建议写，用于明确告诉图有哪些分支）
workflow.add_conditional_edges(
    "node_classify",           # 起点
    route_question,            # 路由函数
    {
        "node_simple": "node_simple",       # 如果路由返回 "node_simple"，就去 node_simple
        "node_detailed": "node_detailed",   # 如果路由返回 "node_detailed"，就去 node_detailed
    }
)

# 两个分支的终点都指向 END
workflow.add_edge("node_simple", END)
workflow.add_edge("node_detailed", END)

app = workflow.compile()

# ⑤ 运行测试
if __name__ == "__main__":
    print("🚀 开始执行 LangGraph 条件边测试...\n")

    # 测试 1：短问题（走简单分支）
    print("【测试 1：短问题】")
    res1 = app.invoke({"question": "1+1"})
    print(f"最终结果：{res1['answer']}\n")

    # 测试 2：长问题（走详细分支）
    print("【测试 2：长问题】")
    res2 = app.invoke({"question": "请解释一下什么是跨站脚本攻击以及如何防范？"})
    print(f"最终结果：{res2['answer']}\n")

    # ⑥ 可视化
    print("📊 工作流 Mermaid 图结构：")
    print(app.get_graph().draw_mermaid())