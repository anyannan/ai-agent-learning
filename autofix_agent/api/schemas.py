# api/schemas.py
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# 只允许"扁平文件名"：拒绝路径分隔符、..、以及任何非 .py 后缀。
# 之前这里不校验，source_name="../../x.py" 会在进入沙箱校验前就写到磁盘任意位置。
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*\.py$")


class FixRequest(BaseModel):
    source_name: str = Field(default="demo.py", description="待修复文件名，仅支持 .py 且不含路径")
    source_code: str = Field(..., max_length=200_000, description="源码内容")
    task_description: str = Field(default="请帮我修复这段代码中的安全漏洞", description="用户的自然语言诉求")
    # 意图由调用方声明，不让编排层猜字符串
    intent: Literal["fix", "explain"] = Field(default="fix", description="fix=修复闭环；explain=只解释代码")

    @field_validator("source_name")
    @classmethod
    def _validate_source_name(cls, v: str) -> str:
        if ".." in v or not _SAFE_NAME.match(v):
            raise ValueError(f"非法文件名: {v!r}（仅允许扁平 .py 文件名）")
        return v


class AuditDetails(BaseModel):
    vulnerability_found: str = Field(description="发现的漏洞类型，如 CWE-95 Eval Injection")
    rag_used: bool = Field(description="是否使用了 RAG 检索规范")
    tests_passed: bool = Field(description="契约测试是否通过")
    fix_strategy: str = Field(description="修复策略简述")
    # 三值状态是审计的核心：unknown 表示"没有结论"，不等同于 clean
    scan_status: Literal["clean", "vulnerable", "unknown"] = "unknown"
    test_status: Literal["clean", "failed", "unknown"] = "unknown"
    # not_covered = 没有匹配到规范规则，不等于合规
    policy_status: Literal["compliant", "violated", "not_covered", "unknown"] = "unknown"
    verdict: Literal["pass", "needs_human", "failed", "no_issue"] = "needs_human"


class FixResponse(BaseModel):
    success: bool
    # explained 只用于 intent=explain：它既不是"修好了"，也不是"需要人工修"
    status: Literal["fixed", "needs_human", "failed", "explained", "no_issue"]
    message: str
    fixed_code: str = ""
    audit_report: Optional[AuditDetails] = None
