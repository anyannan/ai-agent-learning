# data/test_demo.py
from demo import process_data


def test_process_data():
    assert process_data("hello") == "HELLO"


if __name__ == "__main__":
    test_process_data()
    print("PASSED")