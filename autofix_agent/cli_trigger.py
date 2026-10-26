import requests
import os
import shutil


def trigger_agent(source_path, test_path):
    if not os.path.exists(source_path) or not os.path.exists(test_path):
        print("文件不存在")
        return

    with open(source_path, "r", encoding="utf-8") as f:
        source_code = f.read()
    with open(test_path, "r", encoding="utf-8") as f:
        test_code = f.read()

    source_name = os.path.basename(source_path)
    test_name = os.path.basename(test_path)

    print(f"📡 正在将 {source_name} 和 {test_name} 发送至 AutoFix API...")

    response = requests.post(
        "http://127.0.0.1:8000/api/v1/fix",
        json={
            "source_name": source_name,
            "source_code": source_code,
            "test_name": test_name,
            "test_code": test_code
        }
    )

    if response.status_code == 200:
        res = response.json()

        if not res.get("success"):
            print(f"\n❌ 修复失败: {res['message']}")
            return

        print("\n✅ 扫描与修复完成！")
        print(f"Agent 汇报: {res['message']}")

        fixed_code = res["fixed_code"]

        # 备份并覆写原文件
        shutil.copy2(source_path, source_path + ".bak")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write(fixed_code)

        print(f"\n🎉 已自动修复并覆写原文件: {source_path}")
        print("\n===== 修复后的代码 =====")
        print(fixed_code)
    else:
        print("❌ 请求失败", response.text)


if __name__ == "__main__":
    # 确保你沙箱里有这两个独立的文件
    trigger_agent("sandbox/demo.py", "sandbox/test_demo.py")