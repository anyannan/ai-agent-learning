"""沙箱目录回收。

转人工的请求会把沙箱保留下来供人复核，正常请求结束后由 BackgroundTasks 删除。
但保留策略没有回收点的话，目录会一直堆到磁盘满 —— 所以每次服务启动时扫一次。

只清"我们自己创建的"目录（形如 20261027_153849_365f93），
不碰 sandbox/ 下的其他文件（如手工放进去的 demo.py）。
"""

import shutil
import time
from pathlib import Path

from core.config import SANDBOX_DIR

DIR_NAME_LEN = 8  # 年月日 YYYYMMDD
DEFAULT_MAX_AGE_HOURS = 24


def _is_run_dir(path: Path) -> bool:
    return path.is_dir() and len(path.name) > DIR_NAME_LEN and path.name[:DIR_NAME_LEN].isdigit()


def sweep_stale_sandboxes(max_age_hours: int = DEFAULT_MAX_AGE_HOURS, root: Path = SANDBOX_DIR) -> int:
    root = Path(root)
    if not root.exists():
        return 0

    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    for path in root.iterdir():
        if not _is_run_dir(path):
            continue
        try:
            if path.stat().st_mtime >= cutoff:
                continue
            shutil.rmtree(path)
            removed += 1
        except OSError as e:
            print(f"⚠️ [GC] 清理失败 {path}: {e}")
    return removed
