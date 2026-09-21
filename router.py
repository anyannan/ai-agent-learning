from prompts import MATH_ASSISTANT_PROMPT, WEATHER_ASSISTANT_PROMPT, SECURITY_EXPERT_PROMPT, PIRATE_TONE

def route_prompt(user_input: str) -> str:
    """根据用户输入，返回对应的 System Prompt（已附加海盗语气）"""
    user_input = user_input.lower()

    # 1. 数学计算意图
    if any(keyword in user_input for keyword in ["计算", "算一下", "乘以", "加", "减", "除", "*", "+"]):
        # 拼接语气尾巴
        return MATH_ASSISTANT_PROMPT + PIRATE_TONE

    # 2. 天气查询意图
    elif any(keyword in user_input for keyword in ["天气", "气温", "下雨", "温度"]):
        return WEATHER_ASSISTANT_PROMPT + PIRATE_TONE

    # 3. 默认：网络安全专家
    else:
        return SECURITY_EXPERT_PROMPT + PIRATE_TONE