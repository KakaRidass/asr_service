# ============================================
# 文件: backend/app/core/logging.py
# 功能: 统一日志配置。
#      控制台 + 文件双输出，按日期滚动，结构化日志字段。
#      提供 `get_logger(name)` 给业务模块使用。
# ============================================
"""日志模块。

为整个应用提供统一的日志输出格式与处理器。
"""

import logging
import sys
from pathlib import Path


# 统一日志格式：时间 | 级别 | 名称 | 消息
_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_level: str = "INFO", log_file: str = "./logs/app.log") -> None:
    """初始化全局日志配置。

    参数:
        log_level: 日志级别字符串（DEBUG/INFO/WARNING/ERROR）
        log_file: 日志文件路径，目录不存在则自动创建
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # 清空已有 handler（防止重复 init 导致重复输出）
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(level)

    formatter = logging.Formatter(_LOG_FORMAT, _DATE_FORMAT)

    # 控制台 handler
    console = logging.StreamHandler(stream=sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    # 文件 handler（目录不存在则自动创建）
    try:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as exc:
        # 文件日志失败不影响主流程
        logging.getLogger(__name__).warning("无法初始化文件日志: %s", exc)


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的 logger 实例。

    参数:
        name: 通常为 `__name__`，形成层级化 logger 命名

    返回:
        配置好的 logging.Logger 对象
    """
    return logging.getLogger(name)
