# week4_day5_mcp_client.py
import os
import asyncio
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()


async def main():
    # 1. 初始化大模型（硅基流动 Qwen）
    llm = ChatOpenAI(
        model="Qwen/Qwen2.5-7B-Instruct",
        api_key=os.getenv("SILICONFLOW_API_KEY"),
        base_url=os.getenv("SILICONFLOW_BASE_URL"),
        temperature=0
    )

    # 2. 连接 MCP Server
    # MultiServerMCPClient 支持同时连接多个 MCP Server
    # 这里我们通过 stdio 方式启动本地的 mcp_server_demo.py
    client = MultiServerMCPClient(
        {
            "autofix_local_tools": {
                "command": "python",
                "args": ["mcp_server_demo.py"],  # 相对路径，确保在项目根目录运行
                "transport": "stdio",
            }
        }
    )

    # 3. 动态发现工具
    print("🔍 正在连接 MCP Server 并发现工具...")
    tools = await client.get_tools()
    print(f"✅ 发现 {len(tools)} 个工具：{[t.name for t in tools]}")

    # 4. 创建 ReAct Agent（LangGraph 预构建的智能体）
    # 注意：这里我们一行硬编码的工具定义都没有写！
    agent = create_agent(model=llm, tools=tools)

    # 5. 运行测试
    print("\n🚀 启动 MCP 驱动的 Agent...\n")
    user_input = "请帮我算一下 15 加 27 等于多少，然后再告诉我现在的具体时间。"

    # 使用 astream 流式输出，方便观察执行过程
    async for chunk in agent.astream(
            {"messages": [{"role": "user", "content": user_input}]}
    ):
        for node_name, node_output in chunk.items():
            print(f"\n--- [{node_name}] ---")
            if "messages" in node_output:
                last_msg = node_output["messages"][-1]
                content = getattr(last_msg, "content", "")
                tool_calls = getattr(last_msg, "tool_calls", [])

                if tool_calls:
                    for tc in tool_calls:
                        print(f"🛠️ 决定调用工具：{tc['name']}，参数：{tc['args']}")
                elif content:
                    print(f"💬 输出：{content}")


if __name__ == "__main__":
    asyncio.run(main())