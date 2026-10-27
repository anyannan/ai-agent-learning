import os
import sys
from pathlib import Path

# 单测不调真实接口，但 ChatOpenAI 初始化要求 api_key 非空。
# 干净 clone（CI / 别人机器）没有 .env，这里补一个占位值，
# 让 `pytest` 不依赖本地私密配置就能跑。真正的密钥只从 .env 走，不参与测试。
os.environ.setdefault("SILICONFLOW_API_KEY", "test-key-placeholder")

# 项目内部使用绝对导入（from tools.xxx import ...），
# 把包根目录放进 sys.path，让 pytest 能直接跑而不用装包。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
