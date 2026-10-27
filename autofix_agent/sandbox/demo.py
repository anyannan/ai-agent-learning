from corp_sec import safe_calc


def calculate(expression):
    return safe_calc(expression)


if __name__ == "__main__":
    print(calculate("[1, 2, 3]"))
