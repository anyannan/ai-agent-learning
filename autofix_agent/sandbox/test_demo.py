from demo import calculate

def test_calculate():
    assert calculate("1 + 1") == 2
    print("Test Passed!")

if __name__ == "__main__":
    test_calculate()