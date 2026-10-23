from tools.file_tools import read_sandbox_file, write_sandbox_file
from tools.exec_tools import run_sandbox_test

print("--- 测试读取 ---")
print(read_sandbox_file.invoke({"file_path": "demo.py"}))

print("\n--- 测试路径穿越拦截 ---")
print(read_sandbox_file.invoke({"file_path": "../../.env"}))

print("\n--- 测试运行测试脚本 ---")
print(run_sandbox_test.invoke({"test_file_path": "test_demo.py"}))