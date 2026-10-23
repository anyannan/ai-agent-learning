# api/routes.py
import os
import uuid
from fastapi import APIRouter, HTTPException
from api.schemas import FixRequest, FixResponse
from langchain_core.messages import HumanMessage
from agents.main_graph import main_app
from core.config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

router = APIRouter()

# 防御性初始化 Langfuse
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


@router.post("/fix", response_model=FixResponse)
def fix_code(req: FixRequest):
    """
    接收代码，触发 AutoFix Agent 进行修复。
    注意：这里用 def 而不是 async def，防止同步的 Agent 阻塞事件循环。
    """
    # 1. 生成唯一的会话 ID
    thread_id = f"api-req-{uuid.uuid4().hex[:8]}"
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 50
    }

    # 2. 挂载 Langfuse
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]
        config["metadata"] = {"langfuse_tags": ["api-fix"]}

    # 3. 将用户传入的代码写入沙箱临时文件（由 Coder 去读取和修改）
    file_path = "api_target.py"
    sandbox_file = os.path.join(os.path.dirname(__file__), "..", "sandbox", file_path)
    with open(sandbox_file, "w", encoding="utf-8") as f:
        f.write(req.file_content)

    # 4. 组装初始 State
    user_input = f"请读取 {file_path} 的内容。{req.requirement}"
    initial_state = {
        "messages": [HumanMessage(content=user_input)],
        "next": "supervisor",
        "security_done": False,
        "dev_done": False
    }

    try:
        # 5. 运行 Agent（这里会阻塞直到跑完）
        final_state = main_app.invoke(initial_state, config=config)

        # 6. 提取最终结果（从沙箱读取修复后的代码）
        with open(sandbox_file, "r", encoding="utf-8") as f:
            fixed_code = f.read()

        # 提取最后一条汇报
        final_msg = final_state["messages"][-1].content

        return FixResponse(
            success=True,
            message=final_msg,
            fixed_code=fixed_code,
            logs=f"Thread ID: {thread_id}"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent 执行崩溃: {str(e)}")