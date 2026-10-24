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

# ====== Langfuse 初始化保持不变 ======
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


# 🌟 后台清理函数：跑完后自动删除沙箱目录
def cleanup_sandbox_dir(dir_path: str):
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)
        print(f"🧹 [GC] 已自动清理沙箱临时目录: {dir_path}")


@router.post("/fix", response_model=FixResponse)
def fix_code(req: FixRequest, background_tasks: BackgroundTasks):
    # 🌟 核心优化 1：时间戳 + 短 UUID 命名
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    thread_id = f"{now_str}_{short_id}"

    run_dir = SANDBOX_DIR / thread_id
    run_dir.mkdir(exist_ok=True, parents=True)
    sandbox_file = run_dir / req.file_name

    with open(sandbox_file, "w", encoding="utf-8") as f:
        f.write(req.file_content)

    config = {
        "configurable": {
            "thread_id": thread_id,
            "sandbox_dir": str(run_dir)
        },
        "recursion_limit": 50
    }

    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]
        config["metadata"] = {"langfuse_tags": ["api-fix"]}

    user_input = f"请读取 {req.file_name} 的内容。根据安全专家的报告，修复代码中的漏洞，确保能通过测试。"
    initial_state = {
        "messages": [HumanMessage(content=user_input)],
        "next": "supervisor", "security_done": False, "dev_done": False
    }

    try:
        final_state = main_app.invoke(initial_state, config=config)

        with open(sandbox_file, "r", encoding="utf-8") as f:
            fixed_code = f.read()

        return FixResponse(
            success=True,
            message=final_state["messages"][-1].content,
            fixed_code=fixed_code,
            file_name=req.file_name
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Agent 执行崩溃: {str(e)}")
    finally:
        # 🌟 核心优化 2：无论成功还是失败，API 返回前，把清理任务丢进后台
        # 这样不会阻塞 HTTP 响应，但稍后会自动删掉文件夹
        background_tasks.add_task(cleanup_sandbox_dir, str(run_dir))