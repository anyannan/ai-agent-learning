import os
from langchain_community.document_loaders import TextLoader, PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter


def process_document(file_path):
    """加载并分块文档"""
    print(f"==== 正在处理文件：{file_path} ====")

    # 1. 根据文件后缀选择加载器
    if file_path.endswith(".pdf"):
        loader = PyPDFLoader(file_path)
    elif file_path.endswith(".txt"):
        loader = TextLoader(file_path, encoding="utf-8")
    else:
        print("❌ 暂时只支持 PDF 和 TXT 格式")
        return

    # 2. 加载文档 (返回 Document 对象列表)
    documents = loader.load()
    print(f"✅ 成功加载了 {len(documents)} 页/个文档")
    # print(f"第一页内容预览：\n{documents[0].page_content[:200]}...")

    # 3. 初始化递归分块器
    # chunk_size: 每个块的最大字符数
    # chunk_overlap: 块与块之间的重叠字符数（防止上下文断裂）
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "！", "？", " ", ""]  # 针对中文优化分隔符
    )

    # 4. 执行分块
    chunks = text_splitter.split_documents(documents)
    print(f"✅ 成功切分为 {len(chunks)} 个文本块")

    # 5. 打印前 3 个块的内容预览，方便观察
    for i, chunk in enumerate(chunks[:3]):
        print(f"\n===== 第 {i + 1} 块内容 (长度: {len(chunk.page_content)}) =====")
        print(chunk.page_content)
        print("-" * 40)


if __name__ == "__main__":
    # 请确保你的 data/test.txt 存在，或者替换为你自己的 PDF 文件路径
    file_path = "data/test.txt"
    process_document(file_path)