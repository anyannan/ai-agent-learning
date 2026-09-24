import logging
import sys

def setup_logger():
    """配置全局日志记录器"""
    logger = logging.getLogger("AIAgent")
    logger.setLevel(logging.DEBUG) # 记录 DEBUG 及以上级别

    # 创建控制台输出格式
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 输出到控制台
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    # 将控制台的级别调高，终端只显示 INFO 及以上（DEBUG 信息只写入文件不打印给用户）
    console_handler.setLevel(logging.INFO)
    # 输出到文件（方便后续排查线上问题）
    file_handler = logging.FileHandler("agent.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

# 全局单例，其他文件直接 import 这个变量即可
log = setup_logger()
