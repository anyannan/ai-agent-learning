from prompts import MATH_ASSISTANT_PROMPT, WEATHER_ASSISTANT_PROMPT, SECURITY_EXPERT_PROMPT, PIRATE_TONE

GENERAL_ASSISTANT_PROMPT = "你是一个友好的AI助手，请简洁、亲切地回答用户的问题。不要使用Markdown标题格式，也不要用夸张的语气。"

def route_prompt(user_input: str) -> str:
    """根据用户输入，返回对应的 System Prompt（已附加海盗语气）"""
    user_input = user_input.lower()

    # 1. 数学计算意图
    if any(keyword in user_input for keyword in
           ["计算", "算一下", "乘以", "加", "减", "除", "*", "+", "汇率", "美元", "美金", "人民币", "兑换"]):
        return MATH_ASSISTANT_PROMPT + PIRATE_TONE

    # 2. 天气查询意图
    elif any(keyword in user_input for keyword in ["天气", "气温", "下雨", "温度"]):
        return WEATHER_ASSISTANT_PROMPT + PIRATE_TONE

    # 3. 默认：网络安全专家
    elif any(keyword in user_input for keyword in ["安全", "专家", "黑客", "病毒", "sql", "注入", "xss", "漏洞"]):
        return SECURITY_EXPERT_PROMPT + PIRATE_TONE
    else:
        return GENERAL_ASSISTANT_PROMPT