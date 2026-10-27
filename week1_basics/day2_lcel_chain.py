import os
from dotenv import load_dotenv
# 导入 LangChain 核心组件
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# 加载环境变量
load_dotenv()

# 1. 初始化大模型（兼容 OpenAI 接口）
# 这里的 api_key 和 base_url 会自动从环境变量里读取
llm = ChatOpenAI(
    model="Qwen/Qwen2.5-7B-Instruct",
    api_key=os.getenv("SILICONFLOW_API_KEY"),
    base_url=os.getenv("SILICONFLOW_BASE_URL"),
    temperature=0.7
)

# 2. 定义 Prompt 模板
prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个知识渊博的科普专家。请用通俗易懂的语言解释用户给出的主题，字数控制在100字以内。"),
    ("user", "请解释一下：{topic}")
])

# 3. 定义输出解析器
output_parser = StrOutputParser()

# 4. 使用 LCEL 管道符构建 Chain
# 这是一个极其优雅的链式调用
chain = prompt | llm | output_parser

# 5. 测试运行
if __name__ == "__main__":
    print("==== LangChain 主题解释器 ====")
    topic = input("请输入你想了解的主题：")

    # 使用 invoke 方法触发 Chain
    # 注意：langchain 的 invoke 方法支持流式输出，这里为了演示清晰先用非流式
    result = chain.invoke({"topic": topic})

    print("\n🤖 解释如下：")
    print(result)