def calculate(expression):
    return eval(expression, {'__builtins__': None}, {})

if __name__ == '__main__':
    print('Result:', calculate('1 + 1'))