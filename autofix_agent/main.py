# main.py
from fastapi import FastAPI
from api.routes import router

app = FastAPI(
    title="AutoFix Agent API",
    description="企业级自动化代码安全修复系统",
    version="1.0.0"
)

# 注册路由
app.include_router(router, prefix="/api/v1")

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "autofix-agent"}

if __name__ == "__main__":
    import uvicorn
    # 注意：uvicorn 启动时，不要用 reload=True（以免子进程干扰 MemorySaver）
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)