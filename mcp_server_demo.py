# mcp_server_demo.py
# 这是一个遵循 MCP 标准的独立工具服务器
from mcp.server.fastmcp import FastMCP
import datetime

# 创建 MCP Server，起名叫 "AutoFix-Tools"
mcp = FastMCP("AutoFix-Tools")

@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    """计算两个整数的和。"""
    return a + b

@mcp.tool()
def get_current_time() -> str:
    """获取当前的系统时间。"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

if __name__ == "__main__":
    # 以 stdio（标准输入输出）方式运行，供 Client 启动
    mcp.run(transport="stdio")