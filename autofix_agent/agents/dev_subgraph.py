# agents/dev_subgraph.py
"""开发子图：Coder 自主改代码，Evaluator 用结构化判据把关。

判定原则（与 tools/result.py、core/policy.py 一致）：
- 测试 FAILED 且扫描 VULNERABLE → 打回重试（知道错在哪，可以修）
- 任一环节 UNKNOWN（超时、工具缺失、输出无法解析）→ 转人工（不知道就不猜）
- 只有 测试 CLEAN + 复扫 CLEAN + 规范 compliant 三项齐了才判 PASS
"""

from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from agents.nodes import llm
from core.config import MAX_RETRY_COUNT
from core.policy import COMPLIANT, VIOLATED, check_file
from tools.exec_tools import run_sandbox_test
from tools.file_tools import read_sandbox_file, write_sandbox_file
from tools.result import VERDICT_NEEDS_HUMAN, VERDICT_PASS, Status, parse_tool_result
from tools.scan_tools import run_sast_scan

dev_tools = [read_sandbox_file, write_sandbox_file, run_sandbox_test]
llm_with_tools = llm.bind_tools(dev_tools)

TEST_TOOL = "run_sandbox_test"
WRITE_TOOL = "write_sandbox_file"
READ_TOOL = "read_sandbox_file"


class DevState(TypedDict):
    messages: Annotated[list, add_messages]
    retry_count: int
    next_action: str
    verdict: str        # pass / needs_human
    test_status: str    # clean / failed / unknown
    scan_status: str    # clean / vulnerable / unknown
    policy_status: str  # compliant / violated / not_covered / unknown
    scan_summary: str   # 初始扫描的漏洞描述，用于匹配企业规范规则


def coder_node(state: DevState, config: RunnableConfig):
    print("    [子图-Coder] 正在思考...")
    cfg = config.get("configurable", {})
    source_file = cfg.get("source_file", "demo.py")
    test_file = cfg.get("test_file", "test_demo.py")

    sys_msg = SystemMessage(
        content="你是资深自动化码农。\n"
                "【强制规则】\n"
                f"1. 调用 {READ_TOOL} 读取源码，文件名固定为 {source_file}。\n"
                "2. 仔细阅读上下文中【安全扫描报告】和【企业安全规范参考】。\n"
                "3. 如果【企业安全规范参考】给出了特定修复标准（指定的库或函数），必须无条件遵从，"
                "不要用你的通用经验替代企业规范。\n"
                f"4. 调用 {WRITE_TOOL} 时，content 参数直接传真实代码文本，不要带 \\n 等转义字符。\n"
                f"5. 必须调用 {TEST_TOOL} 执行测试脚本 {test_file}。"
    )
    response = llm_with_tools.invoke([sys_msg] + state["messages"][-6:])
    return {"messages": [response]}


def _give_up(
    reason: str, *, test_status: str = "unknown", scan_status: str = "unknown", policy_status: str = "unknown"
) -> dict:
    """终止并转人工。注意：这里的 verdict 绝不是 pass。"""
    print(f"    [子图-Evaluator] ⛔ 转人工：{reason}")
    return {
        "next_action": "end",
        "verdict": VERDICT_NEEDS_HUMAN,
        "test_status": test_status,
        "scan_status": scan_status,
        "policy_status": policy_status,
        "messages": [AIMessage(content=f"【Evaluator 终止】{reason}", name="evaluator")],
    }


def _retry(feedback: str, retries: int, **status) -> dict:
    if retries >= MAX_RETRY_COUNT:
        return _give_up(f"重试预算 {MAX_RETRY_COUNT} 次已用尽，仍未达成修复目标。", **status)
    print(f"    [子图-Evaluator] 打回重试（{retries + 1}/{MAX_RETRY_COUNT}）")
    return {
        # 用 HumanMessage 而不是 AIMessage：模型对"用户指出错误"的响应率明显更高
        "messages": [HumanMessage(content=feedback)],
        "next_action": "retry",
        "retry_count": retries + 1,
        **status,
    }


def evaluate_node(state: DevState, config: RunnableConfig):
    print("    [子图-Evaluator] 正在审查结果...")
    last_msg = state["messages"][-1]
    retries = state.get("retry_count", 0)
    source_file = config.get("configurable", {}).get("source_file", "demo.py")

    # 1) 模型没调工具，只是在说话 —— 打回要求它真的动手
    if not isinstance(last_msg, ToolMessage):
        if getattr(last_msg, "tool_calls", None):
            return {"next_action": "continue"}
        return _retry(f"你没有调用任何工具。请立刻调用 {WRITE_TOOL} 写入修复后的代码。", retries)

    # 2) 按工具名分派。名字由 LangChain 从 tool_call 带出来，比嗅探文本可靠。
    tool_name = getattr(last_msg, "name", None)
    data = parse_tool_result(last_msg.content)
    status = data.get("status")

    if tool_name == READ_TOOL:
        return {"next_action": "continue"}

    if tool_name == WRITE_TOOL:
        if status != Status.CLEAN.value:
            return _retry(f"写入失败：{data.get('summary')}\n请重新写入完整代码。", retries)
        return {"next_action": "continue"}

    if tool_name != TEST_TOOL:
        # 认不出是哪个工具的结果 —— 不猜，转人工
        return _give_up(f"无法识别的工具结果（tool={tool_name!r}）。")

    # 3) 测试结果
    if status == Status.UNKNOWN.value:
        # 超时 / 执行器异常：我们不知道测试有没有问题。
        # 重试只会烧预算并掩盖真实故障，直接转人工更快。
        return _give_up(f"测试结果无法判定：{data.get('summary')}", test_status="unknown")

    if status == Status.FAILED.value:
        detail = str(data.get("summary", ""))
        if "SyntaxError" in detail:
            detail += "\n\n⚠️ 语法错误：你很可能把换行写成了字面量 \\n，请输出真实换行。"
        return _retry(f"测试未通过：\n{detail}\n请修复后重试。", retries, test_status="failed")

    # 测试 CLEAN → 安全复扫。测试只证明"能导入/契约成立"，不证明漏洞已修。
    print("    [子图-Evaluator] 测试通过，执行 Bandit 安全复扫...")
    scan = parse_tool_result(run_sast_scan.invoke({"file_path": source_file}, config=config))
    scan_status = scan.get("status")

    if scan_status == Status.VULNERABLE.value:
        # 不在这里硬编码修复方案（如 ast.literal_eval）——那会和 RAG 私有规范冲突，
        # 而私有规范才是判定依据。把扫描详情喂回去，让 Coder 自己对齐规范。
        return _retry(
            f"安全复扫未通过：\n{scan.get('summary')}\n"
            "请严格按上下文中【企业安全规范参考】给出的方式修复，不要自行选择通用方案。",
            retries,
            test_status="clean",
            scan_status="vulnerable",
        )

    if scan_status != Status.CLEAN.value:
        # 扫描器没给出结论，绝不能当"已修复"
        return _give_up(
            f"安全复扫结果无法判定：{scan.get('summary')}",
            test_status="clean",
            scan_status="unknown",
        )

    # 测试干净 + 复扫干净，仍然不够：Bandit 查通用漏洞，不查企业私有规范。
    # 实测中模型给出 ast.literal_eval（规范明令禁止），Bandit 零告警。
    print("    [子图-Evaluator] 执行企业规范符合性校验...")
    cfg = config.get("configurable", {})
    source_path = Path(cfg.get("sandbox_dir", ".")) / cfg.get("source_file", "demo.py")
    policy = check_file(source_path, state.get("scan_summary", ""))
    print(f"    [子图-Evaluator] 规范校验结果: {policy.status}")

    if policy.status == VIOLATED:
        return _retry(
            f"修复方式不符合企业规范：\n{policy.summary()}\n请严格按规范重写，不要用你的通用经验替代。",
            retries,
            test_status="clean",
            scan_status="clean",
            policy_status="violated",
        )

    if policy.status != COMPLIANT:
        # not_covered / unknown：没有规则或规则读不了，等于"没校验"，不能判 PASS
        return _give_up(
            f"规范符合性无法确认：{policy.summary()}",
            test_status="clean",
            scan_status="clean",
            policy_status=policy.status,
        )

    print("    [子图-Evaluator] ✅ 测试通过 + 复扫干净 + 规范合规，判 PASS。")
    return {
        "next_action": "end",
        "verdict": VERDICT_PASS,
        "test_status": "clean",
        "scan_status": "clean",
        "policy_status": "compliant",
        "messages": [AIMessage(
            content=f"【Evaluator】测试通过、复扫干净、规范合规（{policy.summary()}）。", name="evaluator")],
    }


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
    builder.add_conditional_edges(
        "evaluator", lambda state: state["next_action"], {"continue": "coder", "retry": "coder", "end": END}
    )

    return builder.compile()
