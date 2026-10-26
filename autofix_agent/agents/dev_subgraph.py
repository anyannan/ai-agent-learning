# agents/dev_subgraph.py
from typing import Annotated, TypedDict
from langchain_core.messages import SystemMessage, ToolMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from agents.nodes import llm
from tools.file_tools import read_sandbox_file, write_sandbox_file
from tools.exec_tools import run_sandbox_test
from tools.scan_tools import run_sast_scan

dev_tools = [read_sandbox_file, write_sandbox_file, run_sandbox_test]
llm_with_tools = llm.bind_tools(dev_tools)


class DevState(TypedDict):
    messages: Annotated[list, add_messages]
    retry_count: int
    next_action: str


def coder_node(state: DevState):
    print("    [子图-Coder] 正在思考...")
    sys_msg = SystemMessage(
        content="你是资深自动化码农。\n"
                "【强制规则】\n"
                "1. 调用 read_sandbox_file 读取源码。\n"
                "2. 必须使用 ast.literal_eval，并在最上方 import ast。\n"
                "3. 调用 write_sandbox_file 写入代码时，content 参数请直接传入真实的代码文本，不要带任何 \\n 等转义字符，不要加 Markdown 格式！\n"
                "4. 必须调用 run_sandbox_test 执行测试脚本。"
    )
    response = llm_with_tools.invoke([sys_msg] + state["messages"][-6:])
    return {"messages": [response]}


def evaluate_node(state: DevState, config: RunnableConfig):
    print("    [子图-Evaluator] 正在审查结果...")
    last_msg = state["messages"][-1]
    retries = state.get("retry_count", 0)

    # 1. 熔断检查
    if retries >= 3:
        print(f"    [子图-Evaluator] ⚠️ 达到最大重试次数，强制结束。")
        return {"next_action": "end", "messages": [HumanMessage(content="⚠️ 达到最大重试次数，Agent修复失败。")]}

    # 2. 拦截大模型摸鱼（没调用工具）
    if not isinstance(last_msg, ToolMessage) and not getattr(last_msg, "tool_calls", None):
        print(f"    [子图-Evaluator] 模型未输出工具调用，强制打回！")
        return {
            "messages": [HumanMessage(content="你必须使用工具修复代码！立刻调用 write_sandbox_file！")],
            "next_action": "retry",
            "retry_count": retries + 1
        }

    # 3. 测试执行失败
    if isinstance(last_msg, ToolMessage) and "❌" in str(last_msg.content) and "测试失败" in str(last_msg.content):
        print(f"    [子图-Evaluator] ❌ 测试失败，打回！")
        error_msg = str(last_msg.content)

        # 🌟 核心修复：针对大模型常见的转义字符/语法错误进行精准提示
        if "SyntaxError" in error_msg:
            error_msg += "\n\n⚠️ 语法错误警告：你极大概率输出了字面上的 \\n 或转义字符！请直接输出真实的换行代码，不要在代码里写 \\n！"

        return {
            "messages": [HumanMessage(content=f"测试未通过：\n{error_msg}\n请修复后重试！")],
            "next_action": "retry",
            "retry_count": retries + 1
        }

    # 4. 测试通过 -> 触发安全复扫！
    if isinstance(last_msg, ToolMessage) and "✅ 测试通过" in str(last_msg.content):
        print("    [子图-Evaluator] 测试通过，正在执行 Bandit 安全复扫...")

        # 固化源码文件名，因为测试脚本必须依赖它
        source_file = "demo.py"

        scan_result = run_sast_scan.invoke({"file_path": source_file}, config=config)

        if "❌" in scan_result:
            print(f"    [子图-Evaluator] 🚨 发现未被修复的漏洞，强制打回！")
            return {
                "messages": [HumanMessage(
                    content=f"安全复扫未通过：\n{scan_result}\n请使用 ast.literal_eval 安全的方式重写，绝对禁止出现 eval 字眼！")],
                "next_action": "retry",
                "retry_count": retries + 1
            }
        else:
            print("    [子图-Evaluator] ✅ 漏洞已彻底修复，完美通关！")
            return {"next_action": "end"}

    # 5. 中间状态（比如只读了文件、或者刚写完文件），继续
    return {"next_action": "continue"}


def build_dev_subgraph():
    builder = StateGraph(DevState)
    builder.add_node("coder", coder_node)
    builder.add_node("tools", ToolNode(dev_tools))
    builder.add_node("evaluator", evaluate_node)
    builder.add_edge(START, "coder")

    def route_coder(state: DevState):
        return "tools" if getattr(state["messages"][-1], "tool_calls", None) else "evaluator"

    builder.add_conditional_edges("coder", route_coder, {"tools": "tools", "evaluator": "evaluator"})
    builder.add_edge("tools", "evaluator")
    builder.add_conditional_edges("evaluator", lambda state: state["next_action"],
                                  {"continue": "coder", "retry": "coder", "end": END})

    return builder.compile()