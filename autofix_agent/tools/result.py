"""工具结果的统一信封（structured envelope）。

为什么不用字符串标记（"✅"/"❌"）：
判定逻辑一旦依赖人类可读文本，改一个字就静默改变了控制流。更糟的是
——失误的方向不可控：某天工具报错时恰好没带 ❌，系统就会把"工具挂了"
读成"没有问题"，然后宣布修复成功。这是 fail-open，安全系统里最危险的一类 bug。

所以这里只剩三值，且 UNKNOWN 永远不能被降级成 CLEAN：

    CLEAN       明确无问题
    VULNERABLE  明确有问题
    FAILED      明确执行失败（测试跑挂 / 写入失败）
    UNKNOWN     没有结论：工具缺失、超时、输出无法解析、配置缺失

UNKNOWN 的处理原则是 fail-closed：终止流程并转人工，绝不猜。
"""

import json
from enum import Enum


class Status(str, Enum):
    CLEAN = "clean"
    VULNERABLE = "vulnerable"
    FAILED = "failed"
    UNKNOWN = "unknown"


# 终态判定：只有 test=clean 且 scan=clean 且 policy=compliant 才可能拿到 PASS。
VERDICT_PASS = "pass"
VERDICT_NEEDS_HUMAN = "needs_human"
VERDICT_NO_ISSUE = "no_issue"  # 扫描就没发现漏洞，无需修复

_VALID_STATUS = {s.value for s in Status}


def envelope(status: Status, tool: str, summary: str, **extra) -> str:
    """把工具结果序列化成 JSON 信封，同时给模型一段可读 summary。

    工具返回值是 str（LangChain ToolMessage 的 content 只能是字符串），
    但内部是结构化数据 —— 模型读 summary，代码读 status。
    """
    payload = {"status": status.value, "tool": tool, "summary": summary}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


def parse_tool_result(content) -> dict:
    """解析工具返回；任何异常都归为 UNKNOWN，不抛、不猜。"""
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        return {
            "status": Status.UNKNOWN.value,
            "tool": "unknown",
            "summary": f"工具返回非结构化内容: {str(content)[:200]}",
        }
    if not isinstance(data, dict):
        return {"status": Status.UNKNOWN.value, "tool": "unknown", "summary": "工具返回结构非法"}
    if data.get("status") not in _VALID_STATUS:
        # 状态值不在枚举里，等价于"没有结论"，不能当作 clean
        return {
            "status": Status.UNKNOWN.value,
            "tool": data.get("tool", "unknown"),
            "summary": f"未知状态: {data.get('status')!r}",
        }
    return data
