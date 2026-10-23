# agents/dev_subgraph.py
from typing import Annotated, TypedDict, Literal
from langchain_core.messages import SystemMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from agents.nodes import llm
from tools.file_tools import read_sandbox_file, write_sandbox_file
from tools.exec_tools import run_sandbox_test

dev_tools = [read_sandbox_file, write_sandbox_file, run_sandbox_test]
llm_with_tools = llm.bind_tools(dev_tools)


class DevState(TypedDict):
    messages: Annotated[list, add_messages]
    retry_count: int


def coder_node(state: DevState):
    print("    [子图-Coder] 正在思考...")
    sys_msg = SystemMessage(
        content="你是资深码农。请使用工具读取代码并修复。修复要求：\n"
                "1. 原代码使用了 eval，存在安全风险。\n"
                "2. 请不要使用 ast.literal_eval，因为它无法计算数学公式。\n"
                "3. 请使用 `return eval(expression, {'__builtins__': None}, {})` 这种限制内置函数的写法来保证安全并支持数学运算。\n"
                "4. 修复后必须调用 run_sandbox_test 验证。"
    )
    response = llm_with_tools.invoke([sys_msg] + state["messages"])
    return {"messages": [response]}


def evaluate_node(state: DevState):
    print("    [子图-Evaluator] 正在审查工具执行结果...")
    last_msg = state["messages"][-1]

    if not isinstance(last_msg, ToolMessage):
        if not getattr(last_msg, "tool_calls", None) and not last_msg.content:
            return {"next_action": "end"}
        return {"next_action": "continue"}

    if "returncode" in str(last_msg.content) or "执行器异常" in str(last_msg.content):
        if "❌" in str(last_msg.content):
            retries = state.get("retry_count", 0)
            if retries < 3:
                print(f"    [子图-Evaluator] ❌ 测试失败，打回重写！(第 {retries + 1} 次重试)")
                # 🌟 核心修复 3：把具体的报错信息提取出来喂给模型
                error_detail = str(last_msg.content)
                return {
                    "messages": [SystemMessage(
                        content=f"测试失败！请仔细查看以下报错信息，分析原因并修复代码后再次运行测试：\n{error_detail}")],
                    "next_action": "retry",
                    "retry_count": retries + 1
                }
            else:
                print("    [子图-Evaluator] ⚠️ 达到最大重试次数，强制结束。")
                return {"next_action": "end"}
        else:
            print("    [子图-Evaluator] ✅ 测试通过！")
            return {"next_action": "end"}

    return {"next_action": "continue"}


def build_dev_subgraph():
    builder = StateGraph(DevState)
    builder.add_node("coder", coder_node)
    builder.add_node("tools", ToolNode(dev_tools))
    builder.add_node("evaluator", evaluate_node)

    builder.add_edge(START, "coder")

    # Coder 走完后，如果有工具调用，去 tools；如果没有，去 evaluator
    def route_coder(state: DevState):
        if getattr(state["messages"][-1], "tool_calls", None):
            return "tools"
        return "evaluator"

    builder.add_conditional_edges("coder", route_coder, {"tools": "tools", "evaluator": "evaluator"})

    # 🌟 核心重构：工具执行完毕后，必须强制去 evaluator 裁判所！
    builder.add_edge("tools", "evaluator")

    # Evaluator 的路由判断
    builder.add_conditional_edges(
        "evaluator",
        lambda state: state["next_action"],
        {
            "continue": "coder",  # 没失败，让 coder 继续干
            "retry": "coder",  # 失败了，打回重写
            "end": END  # 成功或达到上限，退出子图
        }
    )

    return builder.compile()