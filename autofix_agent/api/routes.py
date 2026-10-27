# api/routes.py
"""AutoFix API。

判据约定（fail-closed）：
- 只有 final_state["verdict"] == "pass" 才算修复成功；
- verdict 缺失一律按 needs_human 处理，默认值就是"不确定"；
- needs_human 时不清理沙箱，把现场留给人工复核 —— 转了人工却没有现场，等于没转。

访问控制：鉴权 → 限流 → 配额，任何一环不通过，请求都不会碰 LLM。
"""

import ast
import os
import shutil
import uuid
from datetime import datetime

import black
import openai
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from langchain_core.messages import HumanMessage

from agents.main_graph import main_app
from api.schemas import AuditDetails, FixRequest, FixResponse
from core.auth import require_api_key
from core.config import (
    DAILY_QUOTA,
    LANGFUSE_HOST,
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
    RATE_LIMIT_PER_MIN,
    SANDBOX_DIR,
)
from core.limits import DailyQuota, SlidingWindow
from tools.result import VERDICT_NEEDS_HUMAN, VERDICT_NO_ISSUE, VERDICT_PASS

router = APIRouter()

# 进程内状态：单机够用，多副本各算各的（见 README 已知限制）。
# 测试里可以整体替换掉这两个对象来构造 429 场景，不用真打满配额。
rate_limiter = SlidingWindow(limit=RATE_LIMIT_PER_MIN, window_sec=60.0)
daily_quota = DailyQuota(limit=DAILY_QUOTA)


def _enforce_limits(identity: str, response: Response) -> None:
    """鉴权之后、执行业务之前的三道闸。"""
    allowed, retry_after = rate_limiter.allow(identity)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"请求过于频繁（上限 {rate_limiter.limit}/分钟），请 {int(retry_after) + 1} 秒后重试",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )

    allowed, remaining = daily_quota.consume(identity)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"今日配额已用尽（上限 {daily_quota.limit} 次/天），请明天再试或联系管理员提额",
        )

    response.headers["X-Quota-Remaining"] = str(remaining)

# ====== Langfuse 初始化 ======
langfuse_handler = None
if LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY:
    try:
        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler

        Langfuse(public_key=LANGFUSE_PUBLIC_KEY, secret_key=LANGFUSE_SECRET_KEY, host=LANGFUSE_HOST)
        langfuse_handler = CallbackHandler()
        print("✅ [API] Langfuse 监控已启用")
    except ImportError:
        print("⚠️ [API] 未安装 langfuse 库，跳过监控")


# ====== 后台清理函数 ======
def cleanup_sandbox_dir(dir_path: str):
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)
        print(f"🧹 [GC] 已自动清理沙箱临时目录: {dir_path}")


def _build_contract_test(source_code: str, module_name: str) -> str:
    """生成契约测试。

    注意这是**契约测试**，不是行为测试：它只断言"模块能导入、原有函数还在且可调用"。
    它能挡住"改坏了/改丢函数"这类事故，但**不能**证明漏洞已修复 ——
    所以通过标准必须叠加 Bandit 复扫，两者都 clean 才判 PASS。
    """
    try:
        tree = ast.parse(source_code)
        funcs = [
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
    except SyntaxError:
        funcs = []

    lines = [
        "import sys",
        f"import {module_name}",
        "",
        "def _check():",
        f"    module = {module_name}",
    ]
    for name in funcs:
        lines.append(f"    assert hasattr(module, {name!r}), '契约破坏：缺少函数 {name}'")
        lines.append(f"    assert callable(getattr(module, {name!r})), '{name} 不可调用'")
    lines.append(f"    print('CONTRACT OK: {len(funcs)} function(s) present')")
    lines += ["", "if __name__ == '__main__':", "    _check()", ""]
    return "\n".join(lines)


def _extract_vuln(sec_msg: str) -> str:
    """从安全节点报告里提取"发现了什么"。

    只在【安全扫描报告】段内找。整段搜索 "CWE-" 会把 RAG 检索回来的
    企业规范标题（如 CWE-89）误报成扫描发现的漏洞 —— 审计里这一栏就会撒谎。
    """
    scan_part = sec_msg.split("【企业安全规范参考】")[0]
    if "CWE-" in scan_part:
        start = scan_part.find("CWE-")
        return scan_part[start:start + 20].split("\n")[0].strip()
    for line in scan_part.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            return stripped[2:].strip()
    return "None"


@router.get("/quota")
def get_quota(response: Response, identity: str = Depends(require_api_key)):
    """看一下自己还剩多少配额 —— 调用方需要能在被 429 之前知道自己快用完了。"""
    remaining = daily_quota.remaining(identity)
    response.headers["X-Quota-Remaining"] = str(remaining)
    return {
        "identity": identity,
        "daily_limit": daily_quota.limit,
        "remaining_today": remaining,
        "rate_limit_per_min": rate_limiter.limit,
    }


@router.post("/fix", response_model=FixResponse)
def fix_code(
    req: FixRequest,
    background_tasks: BackgroundTasks,
    response: Response,
    identity: str = Depends(require_api_key),
):
    _enforce_limits(identity, response)

    module_name = req.source_name[:-3]
    if not module_name.isidentifier():
        raise HTTPException(status_code=400, detail=f"source_name 不是合法的模块名: {req.source_name}")

    # 1. 创建并发隔离沙箱
    thread_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    run_dir = SANDBOX_DIR / thread_id
    run_dir.mkdir(exist_ok=True, parents=True)
    keep_sandbox = False

    # 2. 源码与测试脚本落盘
    source_path = run_dir / req.source_name
    source_path.write_text(req.source_code, encoding="utf-8")

    test_file_name = f"test_{req.source_name}"
    (run_dir / test_file_name).write_text(
        _build_contract_test(req.source_code, module_name), encoding="utf-8"
    )

    # 模拟公司内部私有安全库
    (run_dir / "corp_sec.py").write_text(
        "import ast\ndef safe_calc(expression):\n    return ast.literal_eval(expression)\n",
        encoding="utf-8",
    )

    # 3. 运行配置
    config = {
        "configurable": {
            "thread_id": thread_id,
            "sandbox_dir": str(run_dir),
            "source_file": req.source_name,
            "test_file": test_file_name,
            "use_rag": True,
        },
        "recursion_limit": 30,
    }
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]
        config["metadata"] = {"langfuse_tags": ["api-fix", "production"]}

    initial_state = {
        "messages": [HumanMessage(content=req.task_description)],
        "next": "orchestrator",
        "intent": req.intent,
        "transitions": 0,
        "security_done": False,
        "dev_done": False,
        "verdict": "",
        "scan_status": "unknown",
        "test_status": "unknown",
        "policy_status": "unknown",
        "scan_summary": "",
        "rag_used": False,
    }

    try:
        final_state = main_app.invoke(initial_state, config=config)
        messages = final_state.get("messages", [])

        # explain 分支不产出"修复"，不能套用 fix 的判据，单独返回答案
        if req.intent == "explain":
            answer = str(messages[-1].content) if messages else ""
            return FixResponse(
                success=False, status="explained", message=answer, fixed_code="", audit_report=None
            )

        raw_code = source_path.read_text(encoding="utf-8") if source_path.exists() else ""
        try:
            fixed_code = black.format_str(raw_code, mode=black.Mode())
        except Exception as e:
            print(f"⚠️ Black 格式化失败: {e}，返回未格式化代码")
            fixed_code = raw_code

        # verdict 缺失 → needs_human。默认值必须是"不确定"，不能是"成功"。
        verdict = final_state.get("verdict") or VERDICT_NEEDS_HUMAN
        is_success = verdict == VERDICT_PASS
        scan_status = final_state.get("scan_status") or "unknown"
        test_status = final_state.get("test_status") or "unknown"
        policy_status = final_state.get("policy_status") or "unknown"

        # 扫描就是干净的：没活可干，不是"修好了"
        if verdict == VERDICT_NO_ISSUE:
            return FixResponse(
                success=True,
                status="no_issue",
                message="扫描未发现需要修复的问题，未做任何改动。",
                fixed_code="",
                audit_report=AuditDetails(
                    vulnerability_found="None",
                    rag_used=bool(final_state.get("rag_used", False)),
                    tests_passed=False,
                    fix_strategy="无需修复",
                    scan_status="clean",
                    test_status="unknown",
                    policy_status="unknown",
                    verdict=VERDICT_NO_ISSUE,
                ),
            )

        sec_msg = next((str(m.content) for m in messages if getattr(m, "name", "") == "security"), "")
        vuln_found = _extract_vuln(sec_msg)

        dev_msg = next((str(m.content) for m in messages if getattr(m, "name", "") == "dev_team"), "")
        final_message = dev_msg or (str(messages[-1].content) if messages else "")

        if is_success:
            status = "fixed"
        elif verdict == VERDICT_NEEDS_HUMAN:
            status = "needs_human"
            # 转人工必须留现场：不删沙箱，把路径告诉调用方
            keep_sandbox = True
            final_message = (
                f"⚠️ 未能确认修复成功（scan={scan_status}, test={test_status}, policy={policy_status}），"
                f"已转人工复核。\n现场保留于: {run_dir}\n\n{final_message}"
            )
        else:
            status = "failed"

        audit = AuditDetails(
            vulnerability_found=vuln_found,
            rag_used=bool(final_state.get("rag_used", False)),
            tests_passed=test_status == "clean",
            fix_strategy="LLM 反思闭环 + 契约测试 + Bandit 复扫 + 规范 AST 校验",
            scan_status=scan_status if scan_status in ("clean", "vulnerable") else "unknown",
            test_status=test_status if test_status in ("clean", "failed") else "unknown",
            policy_status=policy_status if policy_status in ("compliant", "violated", "not_covered") else "unknown",
            verdict=verdict if verdict in (VERDICT_PASS, VERDICT_NEEDS_HUMAN) else VERDICT_NEEDS_HUMAN,
        )

        return FixResponse(
            success=is_success,
            status=status,
            message=final_message,
            fixed_code=fixed_code,
            audit_report=audit,
        )

    except (openai.APITimeoutError, openai.APIConnectionError) as e:
        # 模型侧不可用：这是"等一会儿再试"的问题，503 比 500 更能表达意图，
        # 调用方（含 pre-commit 钩子）可以据此决定重试而不是判失败。
        raise HTTPException(
            status_code=503, detail=f"模型服务暂不可用，请稍后重试: {e}", headers={"Retry-After": "5"}
        )
    except openai.RateLimitError as e:
        raise HTTPException(
            status_code=429, detail=f"上游模型限流，请稍后重试: {e}", headers={"Retry-After": "10"}
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Agent 执行崩溃: {e}")

    finally:
        if keep_sandbox:
            print(f"📌 [GC] verdict 未通过，保留沙箱供人工复核: {run_dir}")
        else:
            background_tasks.add_task(cleanup_sandbox_dir, str(run_dir))
