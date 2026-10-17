# week3_day6_tools_agent.py
# ---------------------------------------------------------------
# Week3 Day6: LangGraph 工具集成 —— @tool 与 ToolNode
# 目标：让大模型真正调用外部 Python 函数，实现 ReAct 闭环
# ---------------------------------------------------------------

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing import TypedDict, Annotated
from datetime import datetime

load_dotenv()


# ① 定义工具（给模型发说明书）
@tool
def search_cve(cve_id: str) -> str:
    """根据 CVE 编号查询漏洞详情。例如：search_cve('CVE-2023-1234')"""
    # 这里用假数据模拟本地数据库查询
    print(f"    [Tool执行] 正在查询数据库：{cve_id}")
    if "CVE-2021-44228" in cve_id:
        return "Log4j2 远程代码执行漏洞，危害等级：严重（Critical）。建议升级到 2.15.0 以上版本。"
    elif "CVE-2023" in cve_id:
        return f"{cve_id} 是一个高危漏洞，涉及权限绕过，建议尽快打补丁。"
    else:
        return f"未找到 {cve_id} 的相关记录。"


@tool
def get_current_time() -> str:
    """获取当前的系统日期和时间。"""
    print("    [Tool执行] 正在获取当前时间...")
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# 把工具装进一个列表
tools = [search_cve, get_current_time]

# ② 初始化模型，并绑定工具
llm = ChatOpenAI(
    model="Qwen/Qwen2.5-7B-Instruct",
    api_key=os.getenv("SILICONFLOW_API_KEY"),
    base_url=os.getenv("SILICONFLOW_BASE_URL"),
    temperature=0.1
)
# 核心：让模型知道有哪些工具可用
llm_with_tools = llm.bind_tools(tools)


# ③ 定义状态
# 注意：这里引入了 messages，并且使用了 add_messages 这个内置 Reducer
# 它会自动把 HumanMessage、AIMessage、ToolMessage 拼接到一起
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


# ④ 定义节点
def agent_node(state: AgentState):
    """Agent 的大脑：思考并决定是否调用工具"""
    print("--- [Agent] 正在思考... ---")
    # 把历史消息（包含用户的问题和之前的工具执行结果）全部发给模型
    response = llm_with_tools.invoke(state["messages"])

    # 如果模型决定调用工具，response 里会包含 tool_calls
    if response.tool_calls:
        print(f"    👉 决定：调用工具 {response.tool_calls[0]['name']}")
    else:
        print("    👉 决定：直接回答用户")

    return {"messages": [response]}


# 使用 LangGraph 内置的 ToolNode 作为“行动节点”
# 它会自动执行模型请求的工具，并返回 ToolMessage
tool_node = ToolNode(tools)


# ⑤ 定义路由函数
def route_after_agent(state: AgentState):
    """判断模型是要调用工具，还是直接结束"""
    last_message = state["messages"][-1]
    # 如果最新的一条消息包含 tool_calls，说明要执行工具
    if last_message.tool_calls:
        return "tools"
    # 否则，说明模型已经给出了最终答案
    return "end"


# ⑥ 构建图
workflow = StateGraph(AgentState)

workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)

workflow.add_edge(START, "agent")

# 核心：Agent 思考完后，走条件边
workflow.add_conditional_edges(
    "agent",
    route_after_agent,
    {
        "tools": "tools",  # 去执行工具
        "end": END  # 结束
    }
)

# 核心：工具执行完后，必定连回 Agent，让 Agent 拿着工具结果继续思考
workflow.add_edge("tools", "agent")

app = workflow.compile()

# ⑦ 运行测试
if __name__ == "__main__":
    print("🚀 开始执行带真实工具的 Agent...\n")

    # 测试 1：需要调用工具的查询
    print("【测试 1：查询特定 CVE】")
    inputs = {"messages": [HumanMessage(content="请帮我查一下 CVE-2021-44228 漏洞是怎么回事？")]}

    # 循环打印每一个流转步骤，方便观察
    for event in app.stream(inputs):
        for key, value in event.items():
            print(f"\n[{key} 节点输出完毕]")
            # 👇 新增：提取并打印具体的消息内容
            if "messages" in value and len(value["messages"]) > 0:
                last_msg = value["messages"][-1]
                # 如果是模型回复，打印它的自然语言内容
                if hasattr(last_msg, "content") and last_msg.content:
                    print(f"💬 文本内容：{last_msg.content}")

    print("\n" + "=" * 50 + "\n")

    # 测试 2：复合问题
    print("【测试 2：复合问题】")
    inputs = {"messages": [HumanMessage(content="你好，你是谁？现在是什么时间")]}
    for event in app.stream(inputs):
        for key, value in event.items():
            print(f"\n[{key} 节点输出完毕]")
            if "messages" in value and len(value["messages"]) > 0:
                last_msg = value["messages"][-1]
                if hasattr(last_msg, "content") and last_msg.content:
                    print(f"💬 文本内容：{last_msg.content}")

    # ⑧ 可视化
    print("\n📊 工作流 Mermaid 图结构：")
    print(app.get_graph().draw_mermaid())