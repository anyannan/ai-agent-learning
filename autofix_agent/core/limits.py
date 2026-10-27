"""限流与配额。

两个不同的东西，别混：

- **限流**（滑动窗口）：防止短时间打爆，按"每分钟 N 次"算，超了返回 429 + Retry-After。
- **配额**（按天计数）：防止长期敞开了用，按"每天 N 次"算，超了当天不再服务。

都是进程内状态，够单机用。多副本部署时这不成立（每个副本各算各的），
要换成 Redis 计数器 —— 这条写在 README 的已知限制里，不假装它已经支持横向扩展。

计数口径是**请求数**，不是 token 数。精确 token 成本需要 tokenizer 与计费单价，
在没接真实账单的情况下编一个数字出来没有意义。
"""

import threading
import time
from collections import defaultdict


class SlidingWindow:
    """按 key 分桶的滑动窗口限流。线程安全（FastAPI 同步端点跑在线程池里）。"""

    def __init__(self, limit: int, window_sec: float = 60.0):
        self.limit = limit
        self.window_sec = window_sec
        self._hits = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple:
        """返回 (是否放行, 建议等待秒数)。"""
        if self.limit <= 0:  # 0 表示全禁，用于紧急刹车
            return False, self.window_sec

        now = time.monotonic()
        cutoff = now - self.window_sec
        with self._lock:
            hits = [t for t in self._hits[key] if t > cutoff]
            if len(hits) >= self.limit:
                retry_after = max(0.0, self.window_sec - (now - hits[0]))
                self._hits[key] = hits
                return False, retry_after
            hits.append(now)
            self._hits[key] = hits
            return True, 0.0


class DailyQuota:
    """按天重置的请求配额。"""

    def __init__(self, limit: int):
        self.limit = limit
        self._counts = defaultdict(int)
        self._days = {}
        self._lock = threading.Lock()

    @staticmethod
    def _today() -> str:
        return time.strftime("%Y-%m-%d")

    def consume(self, key: str) -> tuple:
        """返回 (是否放行, 剩余次数)。超配额时不消耗。"""
        if self.limit <= 0:
            return False, 0

        today = self._today()
        with self._lock:
            if self._days.get(key) != today:
                self._days[key] = today
                self._counts[key] = 0
            used = self._counts[key]
            if used >= self.limit:
                return False, 0
            self._counts[key] = used + 1
            return True, self.limit - used - 1

    def remaining(self, key: str) -> int:
        today = self._today()
        with self._lock:
            if self._days.get(key) != today:
                return self.limit
            return max(0, self.limit - self._counts[key])
