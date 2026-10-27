"""第一周产物：命令行 Agent（手写 Function Calling + 意图路由 + Pydantic 结构化输出）。

和 autofix_agent 的区别：这里**不用** LangChain / LangGraph，
tool_calls 的解析、工具分发、JSON 校验重试全是手写的 —— 用来搞清框架替你做了什么。

依赖同目录的 tools_func / router / prompts / models / logger，
所以工作目录必须是 week1_basics：
    cd week1_basics && python 03_cli_agent.py
"""

from openai import OpenAI
import os
from dotenv import load_dotenv
from logger import log
load_dotenv()

from tools_func import run_agent
from router import route_prompt
api_key = os.environ.get("SILICONFLOW_API_KEY")
base_url = os.environ.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
if not api_key:
    log.error("❌ 致命错误：未在环境变量或 .env 文件中找到 SILICONFLOW_API_KEY")
    raise ValueError("错误：未找到 SILICONFLOW_API_KEY，请检查配置！")
# 日志里不留 key 的任何片段：安全类工具的日志出现凭据残片，审计会直接记为问题。
# 需要确认"用的是不是那把 key"应该看环境变量，不该看日志。
log.info("✅ 系统初始化成功 | 已加载 API Key（长度 %d）", len(api_key))
client = OpenAI(
    api_key=api_key,
    base_url=base_url,
    timeout=60.0,
    max_retries=3
)

# 初始化消息列表，system全局设定
log.info("====命令行聊天程序====")
log.info("输入消息和AI对话，输入 exit 退出程序")

while True:
    # 获取用户控制台输入
    user_input = input("\n你：")
    if user_input.strip().lower() == "exit":
        log.info("程序结束")
        break
    system_prompt = route_prompt(user_input)
    # 用户消息加入上下文列表
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}]

    try:
        reply_content = run_agent(client,messages)

        #统一在结果出来后再打印 AI 回复，保持整洁
        print("\n" + "=" * 55)
        print(f"🏴‍☠️ AI：{reply_content}")  # 如果喜欢可以直接加个emoji
        print("=" * 55 + "\n")

        messages.append({"role": "assistant", "content": reply_content})
    except Exception as err:
        log.error(f"程序异常：{err}")