# main.py
from langchain_core.messages import HumanMessage
from agents.main_graph import main_app

if __name__ == "__main__":
    print("🚀 启动 AutoFix Agent 企业级全自动修复流水线...\n")

    config = {"configurable": {"thread_id": "autofix-run-1"}, "recursion_limit": 50}
    user_input = "请检查并修复 sandbox/demo.py 中的 eval 漏洞，修好后请运行 test_demo.py 验证。"

    initial_state = {
        "messages": [HumanMessage(content=user_input)],
        "next": "supervisor",
        "security_done": False,
        "dev_done": False
    }

    try:
        # 运行主图
        final_state = main_app.invoke(initial_state, config=config)

        print("\n" + "=" * 40)
        print("✅ 最终执行完毕！消息记录：")
        for msg in final_state["messages"]:
            role = getattr(msg, "name", "User")
            print(f"[{role}]: {str(msg.content)[:100]}...")

    except Exception as e:
        print(f"\n❌ 系统运行崩溃：{e}")