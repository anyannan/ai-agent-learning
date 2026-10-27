# eval_pipeline.py
import os
import shutil
import uuid
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
from agents.main_graph import main_app
from core.config import SANDBOX_DIR

load_dotenv()


# ==========================================
# 1. 定义裁判大模型的打分结构
# ==========================================
class ScoreResult(BaseModel):
    compliance_score: int = Field(description="合规得分，0-10分。10分代表完美符合企业私有规范。")
    reasoning: str = Field(description="打分的详细理由，指出代码哪里不符合规范。")


# ==========================================
# 2. 核心执行流程
# ==========================================
def run_agent_test(use_rag: bool) -> str:
    """运行一次真实的 Agent 端到端测试，并返回修复后的代码"""
    thread_id = f"eval_{uuid.uuid4().hex[:8]}"
    run_dir = SANDBOX_DIR / thread_id
    run_dir.mkdir(exist_ok=True, parents=True)

    # 1. 准备模拟的真实业务文件
    source_file = run_dir / "demo.py"
    test_file = run_dir / "test_demo.py"
    corp_sec_file = run_dir / "corp_sec.py"  # 🌟 模拟公司内部的私有安全库

    with open(source_file, "w", encoding="utf-8") as f:
        f.write(
            "def calculate(expression):\n    return eval(expression)\n\nif __name__ == '__main__':\n    print(calculate('[1, 2, 3]'))\n")

    with open(test_file, "w", encoding="utf-8") as f:
        f.write(
            "from demo import calculate\n\ndef test_calculate():\n    assert calculate('[1, 2, 3]') == [1, 2, 3]\n    print('Test Passed!')\n\nif __name__ == '__main__':\n    test_calculate()\n")

    with open(corp_sec_file, "w", encoding="utf-8") as f:
        f.write("import ast\ndef safe_calc(expression):\n    return ast.literal_eval(expression)\n")  # 供修复时调用

    # 2. 配置 Agent 运行参数
    config = {
        "configurable": {
            "thread_id": thread_id,
            "sandbox_dir": str(run_dir),
            "use_rag": use_rag  # 🌟 核心开关：控制是否注入 RAG 知识
        },
        "recursion_limit": 30
    }

    initial_state = {
        "messages": [HumanMessage(content="请修复 demo.py 中的漏洞，并确保 test_demo.py 通过。")],
        "next": "orchestrator", "intent": "fix", "transitions": 0,
        "security_done": False, "dev_done": False
    }

    print(f"\n🚀 启动 Agent 测试 [Use RAG: {use_rag}] ...")
    try:
        main_app.invoke(initial_state, config=config)

        # 读取 Agent 最终修复好的代码
        with open(source_file, "r", encoding="utf-8") as f:
            final_code = f.read()
        return final_code
    except Exception as e:
        return f"Agent 运行失败: {e}"
    finally:
        # 清理沙箱环境
        if os.path.exists(run_dir):
            shutil.rmtree(run_dir)


# ==========================================
# 3. 裁判盲测对比
# ==========================================
def evaluate_with_judge(code_without_rag: str, code_with_rag: str):
    print("\n⚖️ 正在启动 Judge 大模型进行盲测评分...")
    judge_llm = ChatOpenAI(
        model="Qwen/Qwen2.5-7B-Instruct",
        api_key=os.getenv("SILICONFLOW_API_KEY"),
        base_url=os.getenv("SILICONFLOW_BASE_URL"),
        temperature=0,
        timeout=60,
        max_retries=2,
    ).with_structured_output(ScoreResult, method="function_calling")

    judge_prompt = f"""
        你是一名极其严格的企业级代码安全审计专家。
        我们的【企业内部安全规范】要求：
        1. 绝对不能直接使用 `eval()`，也禁止直接使用 `ast.literal_eval()`。
        2. 必须引入公司内部的安全计算库：`from corp_sec import safe_calc`。
        3. 必须使用 `safe_calc(expression)` 来替代原先的危险函数。

        下面是两名开发人员针对同一个漏洞给出的修复代码，请严格依据上述【企业内部安全规范】进行打分（0-10分）。

        【开发人员 A 的代码】：
        {code_without_rag}

        【开发人员 B 的代码】：
        {code_with_rag}

        请分别对 A 和 B 打分。如果使用了 `ast.literal_eval` 直接判 0 分。必须用了 `safe_calc` 才能给 10 分。
        （以 JSON 格式输出，compliance_score 填 A 的分数，reasoning 中要分别写出 A 和 B 的情况）
        """

    result = judge_llm.invoke(judge_prompt)
    print(f"\n📊 裁判评分结果：")
    print(f"👨‍💻 开发人员 A (无 RAG) 得分：{result.compliance_score}/10")
    print(f"🧠 裁判理由：{result.reasoning}")
    print("=" * 60)
    return result


# ==========================================
# 4. 主程序入口
# ==========================================
if __name__ == "__main__":
    print("=" * 60)
    print("开始 RAG 效果量化对比评测（私有规范测试）")
    print("=" * 60)

    # 阶段 1：跑不带 RAG 的 Agent
    print("\n>>> 阶段 1：无 RAG 增强（Agent 只能依靠自身通用知识）")
    code_without_rag = run_agent_test(use_rag=False)
    print("生成的关键代码：\n", code_without_rag)

    # 阶段 2：跑带 RAG 的 Agent
    print("\n>>> 阶段 2：有 RAG 增强（Agent 检索到了企业内部规范）")
    code_with_rag = run_agent_test(use_rag=True)
    print("生成的关键代码：\n", code_with_rag)

    # 阶段 3：裁判打分
    evaluate_with_judge(code_without_rag, code_with_rag)