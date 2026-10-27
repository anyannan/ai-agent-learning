# main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routes import router
from core.auth import configured_keys
from core.config import DAILY_QUOTA, RATE_LIMIT_PER_MIN
from core.sandbox_gc import sweep_stale_sandboxes


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 转人工的请求会保留沙箱供复核，没有回收点就会堆到磁盘满。
    # 启动时扫一次，够用；高频部署场景应换成定时任务。
    removed = sweep_stale_sandboxes(max_age_hours=24)
    if removed:
        print(f"🧹 [GC] 启动清理了 {removed} 个超过 24h 的沙箱目录")

    keys = configured_keys()
    if keys:
        print(f"🔐 鉴权已启用（{len(keys)} 个 key），限流 {RATE_LIMIT_PER_MIN}/分钟，配额 {DAILY_QUOTA}/天")
    else:
        print(
            "⚠️ 未配置 AUTOFIX_API_KEYS：仅接受本机请求（127.0.0.1）。\n"
            "   部署到网络前必须配置，否则外部调用一律 401。"
        )
    yield


app = FastAPI(
    title="AutoFix Agent API",
    description="企业级自动化代码安全修复系统",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api/v1")


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "autofix-agent"}


if __name__ == "__main__":
    import uvicorn

    # 不用 reload=True：子进程会让模块级单例（LLM、RAG）重复初始化
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
