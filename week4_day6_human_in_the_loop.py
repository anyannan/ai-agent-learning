# week4_day6_human_in_the_loop.py
import os
from typing import Annotated, TypedDict
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

load_dotenv()


# ---------- 1. 定义高危工具 ----------
@tool
def write_file(file_path: str, content: str) -> str:
    """将内容写入文件。"""
    print(f"    [Tool执行] 真实写入文件: {file_path}")
    return f"✅ 成功写入 {file_path}"


@tool
def delete_file(file_path: str) -> str:
    """删除指定文件（高危操作）。"""
    print(f"    [Tool执行] 真实删除文件: {file_path}")
    return f"🗑️ 成功删除 {file_path}"


tools = [write_file, delete_file]
tool_node = ToolNode(tools)

llm = ChatOpenAI(
    model="Qwen/Qwen2.5-7B-Instruct",
    api_key=os.getenv("SILICONFLOW_API_KEY"),
    base_url=os.getenv("SILICONFLOW_BASE_URL"),
    temperature=0
)
llm_with_tools = llm.bind_tools(tools)


# ---------- 2. 定义状态 ----------
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    need_approval: bool  # 新增：标记是否需要人工审批
    approved: bool  # 新增：记录人工审批结果


def agent_node(state: AgentState):
    print("\n--- [Agent] 正在思考... ---")
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}


# ---------- 3. 核心：策略门禁节点（只做纯逻辑判断） ----------
def policy_gatekeeper(state: AgentState):
    print("\n--- [Policy Gatekeeper] 正在安检... ---")
    last_message = state["messages"][-1]

    # 默认不需要审批
    if not last_message.tool_calls:
        return {"need_approval": False}

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        # 🚨 门禁规则 1：绝对禁止删除核心系统目录
        if tool_name == "delete_file":
            path = tool_args.get("file_path", "").lower()
            if "c:\\" in path or "/etc/" in path or "/usr/" in path:
                print(f"❌ [门禁拦截] 发现高危路径：{path}，直接阻断！")
                return {
                    "messages": [ToolMessage(
                        content="系统安全拦截：禁止操作系统核心目录！",
                        tool_call_id=tool_call["id"]
                    )],
                    "need_approval": False
                }

        # 🚨 门禁规则 2：普通删除操作，打上需要审批的标记
        if tool_name == "delete_file":
            print(f"⚠️ [门禁提示] 检测到高危操作：{tool_name}，参数：{tool_args}")
            return {"need_approval": True}  # 打标记，不在这里 interrupt

    # 如果没被拦截，也不需要审批，直接放行
    return {"need_approval": False}


# ---------- 4. 新增：独立的人工审批节点 ----------
def human_approval_node(state: AgentState):
    print("\n--- [Human Approval] 等待人工审批... ---")
    last_message = state["messages"][-1]

    # 找到那个需要被审批的工具调用
    for tool_call in last_message.tool_calls:
        if tool_call["name"] == "delete_file":
            tool_args = tool_call["args"]
            # 只有在这个独立节点里才触发 interrupt
            user_decision = interrupt(f"是否允许执行高危操作 {tool_call['name']} ({tool_args})？(yes/no)")

            if user_decision.lower() != "yes":
                print("❌ [人工审批] 用户拒绝了该操作。")
                return {
                    "messages": [ToolMessage(
                        content="操作被用户人工拒绝。",
                        tool_call_id=tool_call["id"]
                    )],
                    "approved": False
                }
            else:
                print("✅ [人工审批] 用户批准放行。")
                return {"approved": True}

    return {"approved": True}


# ---------- 5. 构建图 ----------
workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("gatekeeper", policy_gatekeeper)
workflow.add_node("human_approval", human_approval_node)  # 注册新节点
workflow.add_node("tools", tool_node)

workflow.add_edge(START, "agent")

# Agent 思考完，先去安检
workflow.add_conditional_edges(
    "agent",
    lambda state: "gatekeeper" if state["messages"][-1].tool_calls else END,
    {"gatekeeper": "gatekeeper", END: END}
)


# 路由 1：安检完去哪？
def route_after_gatekeeper(state: AgentState):
    last_message = state["messages"][-1]

    # 如果被门禁直接拦截（返回了 ToolMessage），打回给 Agent
    if isinstance(last_message, ToolMessage):
        return "agent"

    # 如果打上了需要审批的标记，去人工审批节点
    if state.get("need_approval"):
        return "human_approval"

    # 既没拦截也不用审批，直接去执行工具
    return "tools"


workflow.add_conditional_edges(
    "gatekeeper",
    route_after_gatekeeper,
    {"tools": "tools", "agent": "agent", "human_approval": "human_approval"}
)


# 路由 2：人工审批完去哪？
def route_after_approval(state: AgentState):
    if state.get("approved"):
        return "tools"  # 同意，去执行
    return "agent"  # 拒绝，回去让 Agent 重新想怎么说


workflow.add_conditional_edges(
    "human_approval",
    route_after_approval,
    {"tools": "tools", "agent": "agent"}
)

workflow.add_edge("tools", "agent")

# 使用 MemorySaver 保存断点状态
memory = MemorySaver()
app = workflow.compile(checkpointer=memory)

# ---------- 6. 运行测试 ----------
if __name__ == "__main__":
    config = {"configurable": {"thread_id": "test-session-1"}}

    # 测试 1：正常的写文件（无需审批）
    print("==== 测试 1：写文件 ====")
    inputs = {"messages": [HumanMessage(content="你好吗")]}
    for event in app.stream(inputs, config):
        pass

    print("\n" + "=" * 40 + "\n")

    # 测试 2：高危的删除文件（触发 Human-in-the-loop）
    print("==== 测试 2：删除文件 ====")
    inputs = {"messages": [HumanMessage(content="请帮我删除 data/demo.py 文件")]}

    # 1. 启动流程，它会在 interrupt 处暂停
    for event in app.stream(inputs, config):
        pass

    # 2. 检查是否被暂停了
    current_state = app.get_state(config)
    if current_state.next:
        print(f"\n⏸️ 流程已暂停，等待人工审批。")

        # 获取中断信息
        print(f"审批提示：{current_state.tasks[0].interrupts[0].value}")

        # 3. 模拟人类输入决策
        user_choice = input("请输入决策 (yes/no): ")

        # 4. 恢复执行
        print("\n▶️ 恢复执行...")
        for event in app.stream(Command(resume=user_choice), config):
            for node_name, node_output in event.items():
                # 加上 node_output 的存在性判断
                if node_output and "messages" in node_output:
                    last_msg = node_output["messages"][-1]
                    # 兼容处理不同类型的消息
                    if hasattr(last_msg, "content") and last_msg.content:
                        print(f"[{node_name}]: {last_msg.content[:80]}")