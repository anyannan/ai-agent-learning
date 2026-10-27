# core/config.py
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
SANDBOX_DIR = BASE_DIR / "sandbox"
SANDBOX_DIR.mkdir(exist_ok=True)

# 供应商通过环境变量切换（当前默认硅基流动），代码里不写死模型名。
# 换供应商时只改 .env，不用动代码。
API_KEY = os.getenv("SILICONFLOW_API_KEY") or os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")

MAX_FILE_SIZE = 1024 * 1024
MAX_RETRY_COUNT = 3

# 外部调用必须有显式超时：SDK 默认 600s，一次挂死就是十分钟。
# 实测中端到端评测曾卡在一次 LLM 调用上 420s 无响应。
LLM_TIMEOUT_SEC = int(os.getenv("LLM_TIMEOUT_SEC", "60"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))
EMBEDDING_TIMEOUT_SEC = int(os.getenv("EMBEDDING_TIMEOUT_SEC", "30"))
EMBEDDING_MAX_RETRIES = int(os.getenv("EMBEDDING_MAX_RETRIES", "1"))

# Langfuse（可选，缺 key 时自动跳过）
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

# 限流与配额（进程内计数，多副本部署时各算各的，见 README 已知限制）
RATE_LIMIT_PER_MIN = int(os.getenv("AUTOFIX_RATE_LIMIT_PER_MIN", "10"))
DAILY_QUOTA = int(os.getenv("AUTOFIX_DAILY_QUOTA", "200"))
