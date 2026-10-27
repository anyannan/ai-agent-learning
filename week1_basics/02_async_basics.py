"""第一周产物：asyncio + httpx 并发基础。

用一个最短例子说明"为什么 Agent 要异步"：Agent 的耗时几乎全在等网络，
三个请求串行 3 倍于最慢那个，并发则约等于最慢那个。

    cd week1_basics && python 02_async_basics.py
"""

import httpx
import asyncio
import time
# 定义一个异步获取网页的协程
async def fetch_async(url):
    # 注意：必须用 async with，且里面加 await
    async with httpx.AsyncClient() as client:
        print(f"▶️ 发起请求：{url}")
        # await 在这里：发出请求后，不等待回复，先把控制权交出去
        response = await client.get(url)
        print(f"✅ 收到回复：{url} (状态码：{response.status_code})")
        return response.status_code

async def main():
    urls = ["https://www.baidu.com", "https://www.qq.com", "https://www.bing.com"]

    # 创建 3 个"待办事项"（协程对象）
    tasks = []
    for url in urls:
        tasks.append(fetch_async(url))

    # 并发执行！三个请求几乎同时发出
    results = await asyncio.gather(*tasks)  # *tasks 表示把列表拆开传进去
    print(f"全部完成，状态码列表：{results}")


if __name__ == "__main__":
    start = time.time()
    asyncio.run(main())
    print(f"异步总耗时：{time.time() - start:.2f}秒")
    # 输出时间：大概是最慢的那个网站的时间（约 0.5~1秒），而不是三者相加！