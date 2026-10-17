import ast

# data/demo.py —— 故意带 eval 漏洞，用于测试 AutoFix
def calculate(user_input):
    # ⚠️ 高危：eval 直接执行用户输入
    result = ast.literal_eval(user_input)
    return result

def process_data(data):
    return data.upper()
