"""API 鉴权。

两种模式：

1. **配置了 `AUTOFIX_API_KEYS`**（逗号分隔）：必须带 `X-API-Key` 且命中列表。
2. **没配置**：只接受本机来源（127.0.0.1 / ::1 / testclient），外部来源一律 401。

第 2 条是刻意的 fail-closed 设计：本地开发零配置，但一旦有人把服务暴露到公网，
鉴权会自动生效而不是"忘了配就等于不设防"。这个接口一次请求要跑 5~10 次 LLM 调用，
裸奔的代价是别人的免费算力。

鉴权返回一个 identity 字符串，供限流与配额做分桶 —— 只保留可识别前缀，
不把整把 key 带进日志。
"""

import hmac
import os

from fastapi import Header, HTTPException, Request, status

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def configured_keys() -> list:
    raw = os.getenv("AUTOFIX_API_KEYS", "")
    return [k.strip() for k in raw.split(",") if k.strip()]


def _local_identity(request: Request) -> str:
    host = request.client.host if request.client else ""
    if host in LOCAL_HOSTS:
        return f"local:{host}"
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=(
            f"服务未配置 AUTOFIX_API_KEYS，仅接受本机请求（来源 {host or 'unknown'}）。"
            "请在 .env 中配置 AUTOFIX_API_KEYS 后重试。"
        ),
    )


def require_api_key(
    request: Request,
    x_api_key: str = Header(default="", alias="X-API-Key"),
) -> str:
    """FastAPI 依赖：校验通过后返回调用方身份。"""
    keys = configured_keys()
    if not keys:
        return _local_identity(request)

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 X-API-Key 请求头",
        )

    # 常量时间比较：避免用响应时间逐字符试探 key
    for candidate in keys:
        if hmac.compare_digest(x_api_key, candidate):
            return f"key:{candidate[:4]}"

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的 X-API-Key")
