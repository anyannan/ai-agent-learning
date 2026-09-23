import json
from pydantic import ValidationError
from models import WeatherReport,MathReport,SecurityReport
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
def run_agent(client, messages, retry_count=3):
    # 1. 第一次调用模型，带上 tools 参数
    response = client.chat.completions.create(
        model="Qwen/Qwen2.5-7B-Instruct",
        messages=messages,
        tools=tool_schema,  # 修正了这里的变量名
        temperature=0.1
    )

    response_message = response.choices[0].message
    print(f"\n[DEBUG 系统日志] 模型是否触发真实工具调用: "
          f"{response_message.tool_calls is not None}\n")
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
        called_tools = [tool_call.function.name for tool_call in response_message.tool_calls]
        target_model = None

        if "get_weather" in called_tools:
            target_model = WeatherReport
        elif "calculator" in called_tools or "exchange_rate" in called_tools:
            target_model = MathReport

        # 兜底：如果模型调用了工具但匹配不到对应的模型，默认使用 MathReport 防止 JSON 乱跑
        if not target_model:
            target_model = MathReport
        temp_messages = messages.copy()
        if target_model:
            schema_json = json.dumps(target_model.model_json_schema(),ensure_ascii=False)
            temp_messages.append({
                "role":"system",
                "content":f"请务必严格按以下JSON Schema 输出最终结果，不要包含任何Markdown代码块标记，直接输出纯JSON：\n{schema_json}"
            })
        for attempt in range(retry_count):
            raw_content = ""
            try:
                second_response = client.chat.completions.create(
                    model="Qwen/Qwen2.5-7B-Instruct",
                    messages=temp_messages,
                    response_format={"type": "json_object"},
                    temperature = 0.8
                )
                raw_content = second_response.choices[0].message.content

                # 拦截空JSON和无效JSON
                if not raw_content or raw_content.strip() == "{}":
                    raise ValueError("模型返回了空对象 {}，必须包含完整的字段！")

                    # ⚠️ 新增：拦截不以 { 开头的非法 JSON 结构（如 XML 乱码）
                if not raw_content.strip().startswith("{"):
                    raise ValueError("模型输出了非法的非 JSON 格式，请重新输出纯 JSON。")

                if target_model:
                    validated_data = target_model.model_validate_json(raw_content)
                    if isinstance(validated_data, MathReport):
                        # 数学/汇率意图：强制拼接真实数字，剥离幻觉
                        return (
                            f"【推理过程】：{validated_data.reasoning}\n"
                            f"【最终结果】：{validated_data.result}\n"
                            f"🏴‍☠️ 海盗播报：{validated_data.pirate_tone_summary}"
                        )
                    elif isinstance(validated_data, WeatherReport):
                        # 天气意图：返回结构化的天气 JSON 或拼接好的字符串
                        return f"🌤️ {validated_data.city} 天气：{validated_data.weather}，温度 {validated_data.temperature}℃。{validated_data.suggestion} | {validated_data.pirate_tone_summary}"
                    else:
                        # 安全/其他意图：保留 JSON 格式化输出
                        return validated_data.model_dump_json(indent=2)
                return raw_content
            except Exception as e:
                print(f"\n[⚠️ 校验失败，第 {attempt + 1} 次重试] 错误信息：{e}")
                # 把错误信息喂回给模型，让它反思修正
                temp_messages.append({
                    "role": "user",
                    "content": f"你刚才的输出格式有误，Pydantic 校验失败，错误信息如下：\n{str(e)}\n请严格按照 Schema 重新输出纯 JSON，"
                               f"不要包含任何 markdown 标记,不要留空！必须包含所有required字段！"
                })

        return "程序异常：模型连续多次未能输出符合规范的结构化数据。"

    # ⚠️ 新增：如果模型没有调用工具，直接返回它的文本回复，防止返回 None
    if response_message.content and "【调用工具】" in response_message.content:
        # 强制提示用户，不要让它蒙混过关
        return f"⚠️ 系统拦截：模型试图绕过工具调用产生幻觉。\n它的虚假回复如下：\n{response_message.content}\n\n请重新提问，我会强制它调用真实工具。"

    return response_message.content or "抱歉，我不太明白您的意思，请换一种说法。"