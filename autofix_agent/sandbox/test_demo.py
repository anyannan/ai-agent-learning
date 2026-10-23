# sandbox/test_demo.py
from demo import calculate

def test_calculate():
    # 测试安全求值：传入列表格式的字符串，看能否正确解析
    assert calculate("[1, 2, 3]") == [1, 2, 3]
    print("Test Passed!")

if __name__ == "__main__":
    test_calculate()