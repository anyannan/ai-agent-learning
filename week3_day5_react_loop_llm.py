# week3_day5_react_loop_llm.py
# ---------------------------------------------------------------
# Week3 Day5: LangGraph 循环迭代 —— 真实模型版 ReAct
# 目标：用 Qwen 模型驱动“思考”，替换之前的硬编码 if-else
# ---------------------------------------------------------------

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

load_dotenv()

# ① 初始化真实的 Qwen 模型
llm = ChatOpenAI(
    model="Qwen/Qwen2.5-7B-Instruct",
    api_key=os.getenv("SILICONFLOW_API_KEY"),
    base_url=os.getenv("SILICONFLOW_BASE_URL"),
    temperature=0.1
)

# ② 定义状态
class ReActState(TypedDict):
    question: str
    thought: str
    action: str
    observation: str
    iterations: int
    final_answer: str

# ③ 思考节点：用真实模型来决策
def think_node(state: ReActState):
    iterations = state.get("iterations", 0)
    print(f"\n--- [Think] 第 {iterations + 1} 次思考（调用 Qwen）---")

    # 构建 System Prompt，强制模型按格式输出
    system_prompt = """你是一个 ReAct Agent。请根据用户问题和当前观察结果，决定下一步行动。

规则：
- 如果你已经有足够信息回答用户问题，请输出：FINAL_ANSWER: <你的答案>
- 如果你还需要更多信息，请输出：NEED_ACTION: <你需要执行的行动>

请严格按上述格式输出，只输出一行，不要加任何其他内容。"""

    user_content = f"""用户问题：{state['question']}
当前观察：{state.get('observation', '暂无观察结果')}"""

    # 调用真实模型
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ])
    content = response.content.strip()
    print(f"    模型原始输出：{content}")

    # 解析模型输出
    if "FINAL_ANSWER" in content:
        # 提取最终答案
        answer = content.split("FINAL_ANSWER:", 1)[-1].strip()
        print(f"    👉 解析结果：给出最终答案")
        return {
            "final_answer": answer,
            "iterations": iterations + 1
        }
    elif "NEED_ACTION" in content:
        # 提取行动
        action = content.split("NEED_ACTION:", 1)[-1].strip()
        print(f"    👉 解析结果：需要执行行动 -> {action}")
        return {
            "thought": content,
            "action": action,
            "iterations": iterations + 1
        }
    else:
        # ⚠️ 模型没按格式输出，兜底处理
        print(f"    ⚠️ 警告：模型未按格式输出，触发兜底")
        return {
            "final_answer": f"模型输出格式异常，兜底回答：{content}",
            "iterations": iterations + 1
        }

# ④ 行动节点：模拟工具执行（Day 6 会换成真实工具）
def act_node(state: ReActState):
    print(f"--- [Act] 执行行动：{state['action']} ---")
    # 模拟一个数据库查询（Day 6 会替换成真实的工具调用）
    observation = f"数据库查询结果：关于「{state['question']}」的相关资料已找到。"
    return {"observation": observation}

# ⑤ 路由函数：决定循环是否继续
def route_after_think(state: ReActState):
    if state.get("final_answer"):
        print("--- [Router] 检测到最终答案，结束循环 ---")
        return "end"
    if state["iterations"] >= 3:
        print("--- [Router] 触发熔断：达到最大迭代次数 ---")
        return "end"
    print("--- [Router] 继续循环，前往行动节点 ---")
    return "act"

# ⑥ 构建图
workflow = StateGraph(ReActState)
workflow.add_node("think", think_node)
workflow.add_node("act", act_node)

workflow.add_edge(START, "think")
workflow.add_conditional_edges(
    "think",
    route_after_think,
    {"act": "act", "end": END}
)
workflow.add_edge("act", "think")

app = workflow.compile()

# ⑦ 运行测试
if __name__ == "__main__":
    print("🚀 开始执行真实模型驱动的 ReAct 循环...\n")

    initial_state = {
        "question": "请帮我查询一下网络安全中 XSS 攻击的定义",
        "iterations": 0,
        "final_answer": ""
    }

    final_state = app.invoke(initial_state)

    print("\n✅ 循环执行完毕！最终状态：")
    print(f"迭代次数：{final_state['iterations']}")
    print(f"最终答案：{final_state['final_answer']}")