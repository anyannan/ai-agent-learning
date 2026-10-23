import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent
# 安全沙箱目录（Agent 只能在这个目录下操作）
SANDBOX_DIR = BASE_DIR / "sandbox"
SANDBOX_DIR.mkdir(exist_ok=True)

# 硅基流动配置
API_KEY = os.getenv("SILICONFLOW_API_KEY")
BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"

# 安全限制
MAX_FILE_SIZE = 1024 * 1024  # 1MB，防止读取超大文件撑爆内存
MAX_RETRY_COUNT = 3