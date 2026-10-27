# AutoFix Agent 服务镜像
#
# 构建上下文必须是仓库根目录（requirements.txt 在根目录）：
#   docker build -f autofix_agent/Dockerfile -t autofix-agent .
# 或：docker compose -f autofix_agent/docker-compose.yml up --build

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# 先装依赖再拷代码，改代码不会让依赖层失效
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY autofix_agent/ ./autofix_agent/

# 代码使用包内绝对导入，工作目录必须是 autofix_agent
WORKDIR /app/autofix_agent

EXPOSE 8000

# 单进程：RAG 索引与 LLM 客户端是模块级单例，多 worker 会重复初始化
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
