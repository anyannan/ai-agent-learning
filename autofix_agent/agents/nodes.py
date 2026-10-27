# agents/nodes.py
from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from core.config import (
    API_KEY,
    BASE_URL,
    LLM_MAX_RETRIES,
    LLM_TIMEOUT_SEC,
    MODEL_NAME,
)
from tools.result import VERDICT_NEEDS_HUMAN, VERDICT_NO_ISSUE, Status, parse_tool_result
from tools.scan_tools import run_sast_scan
from services.rag_service import retrieve_for_scan

# ==========================================
# 0. 基础 LLM 实例（供其他模块如 dev_subgraph 调用）
# ==========================================
llm = ChatOpenAI(
    model=MODEL_NAME,
    api_key=API_KEY,
    base_url=BASE_URL,
    temperature=0,
    timeout=LLM_TIMEOUT_SEC,
    max_retries=LLM_MAX_RETRIES,
)


# ==========================================
# 1. 编排节点（确定性编排 + 有界自主）
# ==========================================
# 意图常量：意图由调用方显式声明，不在节点内做字符串猜测。
INTENT_FIX = "fix"
INTENT_EXPLAIN = "explain"
VALID_INTENTS = (INTENT_FIX, INTENT_EXPLAIN)

# 编排转移次数上限：图级死循环的最后一道闸。子图内有 retry_count=3，
# 这里再兜一层，防止未来加节点后编排层自己绕圈。
MAX_TRANSITIONS = 6


def orchestrator_node(state: dict):
    """确定性编排器，不是 LLM Supervisor。

    为什么不用 LLM 决策下一步：安全扫描必须先于修复，这是业务不变量，
    不是可以交给模型"判断"的东西。让 7B 模型决定拓扑只会引入不确定性——
    它可能跳过安全扫描直接改代码，而这个错误在产物上看不出来（代码确实被改了）。
    所以这里把拓扑写死，LLM 的自主性被收在子图内部：选哪个工具、改几轮、怎么改。

    代价：无法处理流程本身需要动态生成的场景（比如按漏洞类型插入不同的检查节点）。
    真需要时的对照实现见 week4_day3_supervisor_agent.py（LLM 路由 + done 标记 + 代码层拦截）。
    """
    intent = state.get("intent") or INTENT_FIX
    if intent not in VALID_INTENTS:
        # 非法意图不猜测、不降级到"看起来最像"的分支，直接拒绝执行。
        raise ValueError(f"非法 intent: {intent}，允许值: {VALID_INTENTS}")

    transitions = state.get("transitions", 0) + 1
    if transitions > MAX_TRANSITIONS:
        print(f"⚠️ [Orchestrator] 编排转移次数超过 {MAX_TRANSITIONS}，强制终止。")
        return {"next": "FINISH", "transitions": transitions}

    # fail-closed：上游已判定"无法确定"，就不再继续往下走。
    # 继续执行的唯一结果是产出一个看似成功的产物。
    if state.get("verdict") == VERDICT_NEEDS_HUMAN:
        print("👉 [Orchestrator] 上游判定需人工介入，终止流程。")
        return {"next": "FINISH", "transitions": transitions}

    print(f"\n--- [Orchestrator] intent={intent} transitions={transitions} --- ")

    if intent == INTENT_EXPLAIN:
        print("👉 [Orchestrator] 解释分支（单节点，结束即完成）。")
        return {"next": "explain_agent", "transitions": transitions}

    # fix 分支：阶段的唯一真实来源是 done 标记，顺序由代码保证。
    if not state.get("security_done"):
        print("👉 [Orchestrator] 阶段 1/2：security_expert")
        return {"next": "security_expert", "transitions": transitions}

    # 扫描就是干净的：没有活可干。之前这里会继续进 dev_team，
    # 让模型去"修"一个不存在的漏洞 —— 产出的是没人要的改动。
    # 注意必须判 dev_done：修复后的复扫同样是 clean，不判的话会把
    # 已经拿到的 verdict=pass 覆盖成 no_issue。
    if state.get("scan_status") == "clean" and not state.get("dev_done"):
        print("👉 [Orchestrator] 初始扫描无漏洞，无需修复，结束。")
        return {"next": "FINISH", "transitions": transitions, "verdict": VERDICT_NO_ISSUE}

    if not state.get("dev_done"):
        print("👉 [Orchestrator] 阶段 2/2：dev_team")
        return {"next": "dev_team", "transitions": transitions}

    print("👉 [Orchestrator] 两阶段均已完成，结束。")
    return {"next": "FINISH", "transitions": transitions}


# ==========================================
# 2. 安全专家节点 (SAST + RAG 私有规范)
# ==========================================
def security_expert_node(state: dict, config: RunnableConfig):
    print("  [Security Expert] 正在调用 SAST 工具检查漏洞...")
    cfg = config.get("configurable", {})
    source_file = cfg.get("source_file", "demo.py")
    use_rag = cfg.get("use_rag", False)

    scan = parse_tool_result(run_sast_scan.invoke({"file_path": source_file}, config=config))
    status = scan.get("status")
    summary = scan.get("summary", "")

    # 扫描没拿到结论：不进入修复阶段。扫描器挂了还继续改代码，
    # 等于闭着眼睛打补丁，最后系统会说"修复成功"——那是 fail-open。
    if status == Status.UNKNOWN.value:
        print("  [Security Expert] ⛔ 扫描未取得结论，终止并转人工。")
        return {
            "messages": [AIMessage(
                content=f"【安全扫描报告】：扫描未取得结论 —— {summary}\n流程已终止，需人工核实扫描环境。",
                name="security")],
            "security_done": True,
            "scan_status": "unknown",
            "verdict": VERDICT_NEEDS_HUMAN,
        }

    if status == Status.CLEAN.value:
        print("  [Security Expert] 扫描未发现漏洞，跳过修复阶段。")
        return {
            "messages": [AIMessage(content=f"【安全扫描报告】：{summary}", name="security")],
            "security_done": True,
            "scan_status": "clean",
            "rag_used": False,
        }

    # VULNERABLE：检索企业私有规范
    rag_text = ""
    if use_rag:
        print("  [Security Expert] 发现漏洞，正在检索 RAG 知识库...")
        # 规范选择走确定性路由（规则 → kb_id），向量检索只做兜底：
        # 用 issue 名做 query 的纯向量检索实测会召回错条目。
        rag_text = retrieve_for_scan(summary)
        if rag_text:
            print(f"    [RAG 检索成功] {rag_text[:30]}...")
        else:
            print("    [RAG 不可用] 本次修复将缺少企业私有规范约束。")

    final_report = f"【安全扫描报告】：\n{summary}\n\n"
    if rag_text:
        final_report += f"【企业安全规范参考】：\n{rag_text}\n\n请 Coder 严格参考上述企业规范进行修复！"

    return {
        "messages": [AIMessage(content=final_report, name="security")],
        "security_done": True,
        "scan_status": "vulnerable",
        # 原始漏洞描述要留下来：规范规则是按"初始发现的漏洞"匹配的，
        # 修复后复扫是干净的，那时已经匹配不到规则了。
        "scan_summary": summary,
        # 审计里"是否用了 RAG"必须以实际检索成功为准，不能用字符串包含去猜
        "rag_used": bool(rag_text),
    }


# ==========================================
# 3. 代码解释节点
# ==========================================
def explain_agent_node(state: dict):
    print("  [Explain Agent] 正在分析代码逻辑...")
    prompt = [SystemMessage(content="你是一个代码专家，请向用户详细解释这段代码的功能、潜在问题以及运行逻辑。")] + state[
        "messages"]
    res = llm.invoke(prompt)
    return {
        "messages": [AIMessage(content=f"【代码解释】：\n{res.content}", name="explain")],
        # explain 分支在主图里直接连 END，本不需要这个标记。
        # 留着是为了将来若把它接回编排节点，也不会被重复调度。
        "dev_done": True
    }