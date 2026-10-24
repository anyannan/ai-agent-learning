import requests
import os
import shutil


def trigger_agent(filepath):
    if not os.path.exists(filepath):
        print("文件不存在")
        return

    with open(filepath, "r", encoding="utf-8") as f:
        code = f.read()

    file_name = os.path.basename(filepath)
    print(f"📡 正在将 {file_name} 发送至 AutoFix API 自动扫描...")

    response = requests.post(
        "http://127.0.0.1:8000/api/v1/fix",
        json={"file_name": file_name, "file_content": code}
    )

    if response.status_code == 200:
        res = response.json()
        print("\n✅ 扫描与修复完成！")
        print(f"Agent 汇报: {res['message']}")

        fixed_code = res["fixed_code"]

        # 保险起见，生成 .bak 备份原文件
        backup_path = filepath + ".bak"
        shutil.copy2(filepath, backup_path)

        # 将修复后的代码写入原文件
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(fixed_code)

        print(f"\n🎉 已自动修复并覆写原文件: {filepath}")
        print(f"（原文件已备份至 {backup_path}）")
        print("\n===== 修复后的代码 =====")
        print(fixed_code)
    else:
        print("❌ 请求失败", response.text)


if __name__ == "__main__":
    trigger_agent("sandbox/demo.py")