import json

from certifi import contents

# 修复 1：补全 get_weather 的 function 包装，保持格式一致
tool_schema = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "用于执行基础数学运算，如加减乘除。",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["add", "subtract", "multiply", "divide"],
                        "description": "要执行的数学运算类型"
                    },
                    "num1": {"type": "number", "description": "第一个数字"},
                    "num2": {"type": "number", "description": "第二个数字"}
                },
                "required": ["operation", "num1", "num2"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "用于获取天气信息，如温度，天气，湿度。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "将要获取的城市名称，如北京，上海，广州等。"
                    }
                },
                "required": ["city"]
            }
        }
    },
    {
        "type":"function",
        "function": {
            "name":"exchange_rate",
            "description":"用于汇率转换",
            "parameters":{
                "type":"object",
                "properties":{
                    "amount":{
                        "type":"number",
                        "description":"要转换的金额"
                    }
                },
                "required":["amount"]
            }
        }
    },
]
def exchange_rate(amount):
    return amount /7.2

def calculator(operation, num1, num2):
    if operation == "add": return num1 + num2
    elif operation == "subtract": return num1 - num2
    elif operation == "multiply": return num1 * num2
    elif operation == "divide":
        return num1 / num2 if num2 != 0 else "错误：除数不能为0"

def get_weather(city):
    weather_data = {
        "北京": "晴，26℃，微风",
        "上海": "小雨，22℃，东南风3级",
        "长沙": "多云，28℃，空气优"
    }
    return weather_data.get(city, f"抱歉，暂时没有{city}的天气数据。")

# 修复 2：形参统一改为 messages，修正 tools_schema 拼写
def run_agent(client, messages):
    # 1. 第一次调用模型，带上 tools 参数
    response = client.chat.completions.create(
        model="Qwen/Qwen2.5-7B-Instruct",
        messages=messages,
        tools=tool_schema  # 修正了这里的变量名
    )

    response_message = response.choices[0].message

    # 2. 检查模型是否要调用工具
    if response_message.tool_calls:
        messages.append(response_message)

        for tool_call in response_message.tool_calls:
            function_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)

            # 3. 本地执行工具
            if function_name == "calculator":
                result = calculator(**arguments)
            elif function_name == "get_weather":
                result = get_weather(**arguments)
            elif function_name == "exchange_rate":
                result = exchange_rate(**arguments)
            else:
                result = f"未知工具：{function_name}"

            # 4. 将工具执行结果返回给模型
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(result)
            })

        # 5. 第二次调用模型，让它总结结果
        second_response = client.chat.completions.create(
            model="Qwen/Qwen2.5-7B-Instruct",
            messages=messages
        )
        return second_response.choices[0].message.content

    return response_message.content