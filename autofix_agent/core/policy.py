"""企业规范符合性校验：把自然语言规范变成可执行的断言。

为什么不用 LLM 判断"是否符合规范"：
1. 判据必须可回归 —— 同一份代码判两次必须一致，LLM 做不到；
2. 判据不能既当运动员又当裁判 —— 模型写代码、模型判合规，等于没判。
所以规则以数据形式声明（data/security_policy.json），校验用 AST 做，纯确定性。

四种结论：
    compliant   明确符合
    violated    明确提出违反了某条规则
    not_covered 没有匹配到任何规则 —— 不等于合规，只等于"没校验"
    unknown     解析失败 / 规则文件读不了

只有 compliant 能通向 PASS。not_covered 会转人工，这是刻意的：
"没有规则"和"符合规则"是两件事，混为一谈就是又一次 fail-open。
"""

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from core.ast_utils import call_sites, import_bindings, name_matches

POLICY_PATH = Path(__file__).resolve().parent.parent / "data" / "security_policy.json"

COMPLIANT = "compliant"
VIOLATED = "violated"
NOT_COVERED = "not_covered"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class Rule:
    id: str
    description: str
    kb_id: str = ""  # 对应 security_kb.txt 里的条目编号（如 CWE-95）
    issue_contains: tuple[str, ...] = ()
    forbidden_calls: tuple[str, ...] = ()
    required_calls: tuple[str, ...] = ()
    forbidden_patterns: tuple[str, ...] = ()


@dataclass
class PolicyResult:
    status: str
    rule_ids: list = field(default_factory=list)
    violations: list = field(default_factory=list)

    def summary(self) -> str:
        if self.status == COMPLIANT:
            return f"符合规范（命中规则 {', '.join(self.rule_ids) or '无'}）"
        if self.status == VIOLATED:
            return "违反规范：\n" + "\n".join(f"- {v}" for v in self.violations)
        if self.status == NOT_COVERED:
            return "没有匹配到任何规范规则，无法判定合规性"
        return "规范校验无法执行"


def load_rules(path: Path = POLICY_PATH) -> list:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"⚠️ [Policy] 规则文件读取失败: {e}")
        return []
    rules = []
    for item in raw.get("rules", []):
        rules.append(
            Rule(
                id=item["id"],
                description=item.get("description", ""),
                kb_id=item.get("kb_id", ""),
                issue_contains=tuple(x.lower() for x in item.get("issue_contains", ())),
                forbidden_calls=tuple(item.get("forbidden_calls", ())),
                required_calls=tuple(item.get("required_calls", ())),
                forbidden_patterns=tuple(item.get("forbidden_patterns", ())),
            )
        )
    return rules


def select_rules(scan_summary: str, rules=None) -> list:
    """按扫描报告文本匹配规则。匹配不上就是"没有规则"，不是"没问题"。"""
    rules = rules if rules is not None else load_rules()
    low = (scan_summary or "").lower()
    return [r for r in rules if any(k in low for k in r.issue_contains)]


def check_source(source: str, scan_summary: str, rules=None) -> PolicyResult:
    """对源码做规范符合性校验。"""
    if rules is None:
        rules = load_rules()
        if not rules:
            return PolicyResult(UNKNOWN, [], ["规则文件缺失或为空"])

    selected = select_rules(scan_summary, rules)
    if not selected:
        return PolicyResult(NOT_COVERED)

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return PolicyResult(UNKNOWN, [r.id for r in selected], [f"源码无法解析: {e}"])

    calls = call_sites(tree, import_bindings(tree))

    violations = []
    for rule in selected:
        for target in rule.forbidden_calls:
            hit = next(((n, ln) for n, ln in calls if name_matches(n, target)), None)
            if hit:
                violations.append(
                    f"[{rule.id}] 第 {hit[1]} 行调用了被禁止的 {target}；规范要求：{rule.description}"
                )

        for target in rule.required_calls:
            if not any(name_matches(n, target) for n, _ in calls):
                violations.append(f"[{rule.id}] 缺少必需调用 {target}；规范要求：{rule.description}")

        for pattern in rule.forbidden_patterns:
            for m in re.finditer(pattern, source):
                line_no = source.count("\n", 0, m.start()) + 1
                violations.append(f"[{rule.id}] 第 {line_no} 行命中禁止模式 {pattern!r}")

    if violations:
        return PolicyResult(VIOLATED, [r.id for r in selected], violations)
    return PolicyResult(COMPLIANT, [r.id for r in selected])


def check_file(file_path, scan_summary: str, rules=None) -> PolicyResult:
    try:
        source = Path(file_path).read_text(encoding="utf-8")
    except OSError as e:
        return PolicyResult(UNKNOWN, [], [f"源码读取失败: {e}"])
    return check_source(source, scan_summary, rules)
