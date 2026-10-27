import sys
from pathlib import Path

# 项目内部使用绝对导入（from tools.xxx import ...），
# 把包根目录放进 sys.path，让 pytest 能直接跑而不用装包。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
