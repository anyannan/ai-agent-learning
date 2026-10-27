# agents/main_graph.py
import os
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from agents.dev_subgraph import build_dev_subgraph
from agents.nodes import explain_agent_node, llm, orchestrator_node, security_expert_node

class MainState(TypedDict):
    messages: Annotated[list, add_messages]
    next: str
    intent: str          # fix / explain，由调用方显式声明
    transitions: int     # 编排转移计数，配合 MAX_TRANSITIONS 做图级熔断
    security_done: bool
    dev_done: bool
    # 判据：三层状态 + 终态结论。verdict 只在 "pass" 时代表修复成功，
    # 缺省（"")在 API 层按 needs_human 处理 —— fail-closed 的最后一环。
    verdict: str         # pass / needs_human / no_issue
    scan_status: str     # clean / vulnerable / unknown
    test_status: str     # clean / failed / unknown
    policy_status: str   # compliant / violated / not_covered / unknown
    scan_summary: str    # 初始扫描的漏洞描述，规范规则按它匹配
    rag_used: bool

dev_subgraph = build_dev_subgraph()

def memory_compress_node(state: dict):
    messages = state.get("messages", [])

    # 阈值：超过 10 条消息（约 5 轮对话）就触发压缩
    if len(messages) > 10:
        print("\n🧠 [Memory] 历史消息过多，触发上下文压缩...")
        summary_prompt = [
            SystemMessage(
                content="请精简总结以下对话，只保留：1. 用户的原始诉求；2. 当前正在尝试的方案；3. 已有的结论或错误。字数控制在 100 字以内。")
        ] + messages[:-4]

        try:
            summary_res = llm.invoke(summary_prompt).content
            messages_to_remove = [RemoveMessage(id=m.id) for m in messages[:-4] if hasattr(m, "id")]

            print(f"  -> 压缩完成，生成摘要: {summary_res[:30]}...")
            return {
                "messages": messages_to_remove + [SystemMessage(content=f"【历史记忆摘要】：{summary_res}")]
            }
        except Exception as e:
            print(f"  -> 记忆压缩失败: {e}，跳过压缩。")
            return {}

    return {}


def dev_team_node(state: MainState, config: RunnableConfig):
    print("\n  [主图] 呼叫开发部子图入场...")
    cfg = config.get("configurable", {})
    source_file = cfg.get("source_file", "demo.py")
    test_file = cfg.get("test_file", "test_demo.py")

    # 文件名从 config 取，不再硬编码 —— 否则 API 传了别的 source_name 就会全线错位
    sub_messages = list(state["messages"][-2:])
    sub_messages.append(
        HumanMessage(
            content=f"⚠️ 系统强制指令：目标源码文件名是 `{source_file}`，测试脚本文件名是 `{test_file}`。"
                    "你必须严格使用这两个文件名调用工具，绝对禁止编造其他文件名！")
    )

    sub_inputs = {
        "messages": sub_messages,
        "retry_count": 0,
        "next_action": "",
        "verdict": "",
        "test_status": "unknown",
        "scan_status": "unknown",
        "policy_status": "unknown",
        "scan_summary": state.get("scan_summary", ""),
    }
    sub_output = dev_subgraph.invoke(sub_inputs, config=config)

    # 子图的 verdict 必须原样带上来。之前这里只有 dev_done=True，
    # 导致"修没修好"这个信息在子图出口处丢失，上层只能靠匹配字符串猜。
    verdict = sub_output.get("verdict") or ""
    print(f"  [主图] 开发部汇报完毕，verdict={verdict or '(空)'}")

    return {
        "messages": [AIMessage(content=f"【开发部最终汇报】：{sub_output['messages'][-1].content}", name="dev_team")],
        "dev_done": True,
        "verdict": verdict,
        "test_status": sub_output.get("test_status", "unknown"),
        "scan_status": sub_output.get("scan_status") or state.get("scan_status", "unknown"),
        "policy_status": sub_output.get("policy_status", "unknown"),
    }

workflow = StateGraph(MainState)

# 🌟 注册所有节点
workflow.add_node("memory_compress", memory_compress_node)
workflow.add_node("orchestrator", orchestrator_node)
workflow.add_node("security_expert", security_expert_node)
workflow.add_node("dev_team", dev_team_node)
workflow.add_node("explain_agent", explain_agent_node) # 新增解释节点

workflow.add_edge(START, "memory_compress")
workflow.add_edge("memory_compress", "orchestrator")

# 🌟 完善条件边映射字典
workflow.add_conditional_edges(
    "orchestrator",
    lambda state: state["next"],
    {
        "security_expert": "security_expert",
        "dev_team": "dev_team",
        "explain_agent": "explain_agent", # 新增解释路由
        "FINISH": END
    }
)

workflow.add_edge("security_expert", "orchestrator")
workflow.add_edge("dev_team", "orchestrator")
# 解释完不需要回 orchestrator，直接结束
workflow.add_edge("explain_agent", END)


# 默认**不挂 checkpointer**：API 是单次请求-响应，每个请求一个 thread_id，
# 没有跨轮恢复、也没有 interrupt 等待，checkpoint 存了永远没人读。
# 之前的 MemorySaver 会为每个请求留一份永不释放的状态 —— 长跑必 OOM。
#
# 需要多轮 / 断点续跑时再打开（例如调试 HITL 流程）：
#   AUTOFIX_CHECKPOINT=1 uvicorn main:app
if os.getenv("AUTOFIX_CHECKPOINT") == "1":
    main_app = workflow.compile(checkpointer=MemorySaver())
else:
    main_app = workflow.compile()