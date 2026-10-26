import os
import uuid
import shutil
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks
from api.schemas import FixRequest, FixResponse
from langchain_core.messages import HumanMessage
from agents.main_graph import main_app
from core.config import SANDBOX_DIR, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

router = APIRouter()

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


def cleanup_sandbox_dir(dir_path: str):
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)
        print(f"🧹 [GC] 已自动清理沙箱临时目录: {dir_path}")


@router.post("/fix", response_model=FixResponse)
def fix_code(req: FixRequest, background_tasks: BackgroundTasks):
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    thread_id = f"{now_str}_{uuid.uuid4().hex[:6]}"

    run_dir = SANDBOX_DIR / thread_id
    run_dir.mkdir(exist_ok=True, parents=True)

    # 真实写入源码和测试代码
    source_file = run_dir / req.source_name
    test_file = run_dir / req.test_name

    with open(source_file, "w", encoding="utf-8") as f:
        f.write(req.source_code)
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(req.test_code)

    config = {
        "configurable": {
            "thread_id": thread_id,
            "sandbox_dir": str(run_dir)
        },
        "recursion_limit": 30
    }

    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]
        config["metadata"] = {"langfuse_tags": ["api-fix"]}

    user_input = f"请扫描 {req.source_name}，修复漏洞。修复后请运行 {req.test_name} 验证。"
    initial_state = {
        "messages": [HumanMessage(content=user_input)],
        "next": "supervisor", "security_done": False, "dev_done": False
    }

    try:
        final_state = main_app.invoke(initial_state, config=config)

        with open(source_file, "r", encoding="utf-8") as f:
            fixed_code = f.read()

        final_report = final_state["messages"][-1].content

        # 企业级真实状态反馈：检查 Agent 是否真的搞定了
        is_success = (
                                 "✅ 测试通过" in final_report or "漏洞已彻底修复" in final_report) and "⚠️ 达到最大重试次数" not in final_report

        return FixResponse(
            success=is_success,
            message=final_report,
            fixed_code=fixed_code,
            logs=f"Sandbox: {thread_id}"
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Agent 执行崩溃: {str(e)}")
    finally:
        background_tasks.add_task(cleanup_sandbox_dir, str(run_dir))