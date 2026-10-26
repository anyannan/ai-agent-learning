import ast
def calculate(expression):
    # 修复：使用了 ast.literal_eval
    return ast.literal_eval(expression)

if __name__ == '__main__':
    print(calculate('[1, 2, 3]'))