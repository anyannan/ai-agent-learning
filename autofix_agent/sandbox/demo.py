def calculate(expression):
    # 漏洞：使用了 eval，极其危险
    return eval(expression)

if __name__ == "__main__":
    print("Result:", calculate("1 + 1"))