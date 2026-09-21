from openai import OpenAI
import os
from dotenv import load_dotenv
load_dotenv()

from tools_func import run_agent
from router import route_prompt
api_key = os.getenv("SILICONFLOW_API_KEY")
base_url = os.getenv("SILICONFLOW_BASE_URL")
if not api_key:
    raise ValueError("错误：未在 .env 文件中找到 SILICONFLOW_API_KEY，请检查配置！")

client = OpenAI(
    api_key=api_key,
    base_url=base_url,
    timeout=60.0,
    max_retries=3
)

# 初始化消息列表，system全局设定
print("====命令行流式聊天程序====")
print("输入消息和AI对话，输入 exit 退出程序")

while True:
    # 获取用户控制台输入
    user_input = input("\n你：")
    if user_input.strip().lower() == "exit":
        print("程序结束")
        break
    system_prompt = route_prompt(user_input)
    # 用户消息加入上下文列表
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}]
    print("AI：", end="")

    try:
        reply_content = run_agent(client,messages)
        print(reply_content)
        messages.append({"role": "assistant", "content": reply_content})
    except Exception as err:
        print(f"\n程序异常：{err}")
