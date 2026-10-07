import os
from dotenv import load_dotenv
# 1. 导入相关库
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 加载环境变量
load_dotenv()


def create_vector_store(file_path, save_path="faiss_index"):
    """加载文档、分块、向量化并保存到本地 FAISS 向量库"""
    print(f"==== 正在处理文件：{file_path} ====")

    # 1. 加载文档
    loader = TextLoader(file_path, encoding="utf-8")
    documents = loader.load()

    # 2. 切分文档（沿用昨天学过的递归切分）
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "！", "？", " ", ""]
    )
    chunks = text_splitter.split_documents(documents)
    print(f"✅ 成功切分为 {len(chunks)} 个文本块")

    # 3. 初始化 Embedding 模型
    # 注意：这里使用的是硅基流动的 Embedding 模型 BAAI/bge-m3
    embeddings = OpenAIEmbeddings(
        model="BAAI/bge-m3",
        api_key=os.getenv("SILICONFLOW_API_KEY"),
        base_url=os.getenv("SILICONFLOW_BASE_URL")
    )

    # 4. 将文本块转化为向量，并存入 FAISS 向量库
    print("⏳ 正在生成向量并构建 FAISS 索引，请稍候...")
    vector_store = FAISS.from_documents(chunks, embeddings)
    print("✅ 向量库构建完成！")

    # 5. 将向量库保存到本地（防止每次运行都重新计算，节省 Token）
    vector_store.save_local(save_path)
    print(f"✅ 向量库已保存到本地目录：{save_path}")

    return vector_store


def search_similarity(vector_store, query, k=2):
    """在向量库中搜索与问题最相似的文本块"""
    print(f"\n==== 正在检索问题：{query} ====")
    # 相似度搜索，返回最相似的 k 个文档
    results = vector_store.similarity_search(query, k=k)

    for i, doc in enumerate(results):
        print(f"\n--- 匹配结果 {i + 1} ---")
        print(doc.page_content)
        print(f"来源元数据: {doc.metadata}")


if __name__ == "__main__":
    # 1. 构建或加载向量库
    index_path = "faiss_index"
    if os.path.exists(index_path):
        print("检测到本地已有 FAISS 索引，直接加载...")
        embeddings = OpenAIEmbeddings(
            model="BAAI/bge-m3",
            api_key=os.getenv("SILICONFLOW_API_KEY"),
            base_url=os.getenv("SILICONFLOW_BASE_URL")
        )
        # 注意：加载本地索引时，必须传入相同的 Embedding 模型
        vector_store = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
    else:
        # 如果本地没有，则从头构建
        vector_store = create_vector_store("data/test.txt")

    # 2. 测试检索（这就是未来 RAG 里的 retriever 的底层逻辑）
    query = "我的项目有哪些架构亮点？"
    search_similarity(vector_store, query, k=2)