# week4_day1_autofix_trace.py
# ---------------------------------------------------------------
# Week4 Day1: AutoFix Agent 最小骨架 + Langfuse 全链路追踪
# 目标：让 Agent 具备"读 -> 改 -> 写 -> 测"的闭环能力，
#       并通过 Langfuse 让每一步都可观测。
# ---------------------------------------------------------------
import os
import subprocess
import sys
from typing import Annotated, TypedDict

from dotenv import load_dotenv

load_dotenv()

# ---------- 0. 防御性导入 Langfuse：装不上也不影响 Agent 本体 ----------
LANGFUSE_ENABLED = False
langfuse_handler = None

try:
    from langfuse import Langfuse, get_client
    from langfuse.langchain import CallbackHandler

    _public = os.getenv("LANGFUSE_PUBLIC_KEY")
    _secret = os.getenv("LANGFUSE_SECRET_KEY")
    _host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    if _public and _secret:
        Langfuse(public_key=_public, secret_key=_secret, host=_host)
        langfuse_handler = CallbackHandler()
        LANGFUSE_ENABLED = True
        print("[Langfuse] ✅ 追踪已启用")
    else:
        print("[Langfuse] ⚠️ 未检测到 API Key，追踪已跳过（Agent 仍可运行）")
except ImportError:
    print("[Langfuse] ⚠️ langfuse 未安装，追踪已跳过（Agent 仍可运行）")
except Exception as e:
    print(f"[Langfuse] ⚠️ 初始化失败：{e}，追踪已跳过")

# ---------- 1. 工具定义：AutoFix Agent 的"手" ----------
from langchain_core.tools import tool


@tool
def read_file(file_path: str) -> str:
    """读取指定路径的文件内容，返回纯文本。"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"错误：文件 {file_path} 不存在"
    except Exception as e:
        return f"读取失败：{e}"


@tool
def write_file(file_path: str, content: str) -> str:
    """将内容覆盖写入指定文件，返回写入结果。"""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"✅ 已写入 {file_path}（{len(content)} 字符）"
    except Exception as e:
        return f"写入失败：{e}"


@tool
def run_test(test_path: str) -> str:
    """运行指定的 Python 测试文件，返回 PASSED / FAILED 与 stderr。"""
    try:
        proc = subprocess.run(
            [sys.executable, test_path],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode == 0:
            return f"✅ {test_path} 运行通过\nstdout: {proc.stdout.strip()}"
        return f"❌ {test_path} 运行失败\nreturncode: {proc.returncode}\nstderr: {proc.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return f"⚠️ {test_path} 运行超时（>15s）"
    except Exception as e:
        return f"运行失败：{e}"


tools = [read_file, write_file, run_test]

# ---------- 2. LLM + LangGraph 图 ----------
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


llm = ChatOpenAI(
    model="Qwen/Qwen2.5-7B-Instruct",
    api_key=os.getenv("SILICONFLOW_API_KEY"),
    base_url=os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"),
    temperature=0,
)
llm_with_tools = llm.bind_tools(tools)


def agent_node(state: AgentState):
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}


builder = StateGraph(AgentState)
builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(tools))
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")
graph = builder.compile()


# ---------- 3. 执行入口：在根调用挂 Langfuse ----------
def run_agent(user_input: str, user_id: str = "debug-user", session_id: str = "debug-session"):
    config = {}
    if LANGFUSE_ENABLED and langfuse_handler:
        config["callbacks"] = [langfuse_handler]
        config["metadata"] = {
            "langfuse_user_id": user_id,
            "langfuse_session_id": session_id,
            "langfuse_tags": ["autofix-agent", "week4-day1"],
        }

    # 注意：这里用 invoke 而非 stream，是新手期最简单的验证路径；
    # Day 5 我们会改成 stream 做可视化。
    result = graph.invoke(
        {"messages": [("user", user_input)]},
        config=config,
    )
    return result


if __name__ == "__main__":
    # 测试输入：让 Agent 读 -> 改 -> 写 -> 测
    test_input = (
        "请读取 data/demo.py 的内容。"
        "如果文件中存在 eval( 调用，请把它改成 ast.literal_eval 或安全的安全求值方式，"
        "并将修改后的完整文件内容写入 data/demo.py，"
        "最后运行 data/test_demo.py 验证是否通过。"
    )

    print("🚀 启动 AutoFix Agent，输入：\n", test_input, "\n")
    result = run_agent(test_input, user_id="tester", session_id="day1-demo")
    print("\n===== 最终回答 =====")
    print(result["messages"][-1].content)

    if LANGFUSE_ENABLED:
        get_client().flush()
        print("\n[Langfuse] Trace 已 flush，请前往 Dashboard 查看。")