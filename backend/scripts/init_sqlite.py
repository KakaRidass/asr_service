# ============================================
# 文件: backend/scripts/init_sqlite.py
# 功能: 给无 Docker 环境用的 SQLite 建表脚本。
#      用 SQLAlchemy 的 create_all 建表，无需手写 DDL。
# 运行: python -m scripts.init_sqlite
# ============================================
"""SQLite 数据库初始化脚本。

适用场景：本地无 Docker 时使用 SQLite 替代 MySQL。
脚本会自动从 .env 读取 DATABASE_URL，判断是否为 sqlite 前缀，
若是则执行 create_all 建表。
"""

import asyncio
import sys
from pathlib import Path

# 让脚本可以独立 `python -m scripts.init_sqlite` 运行
BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.logging import get_logger, setup_logging  # noqa: E402
from app.db.session import dispose_engine, init_engine  # noqa: E402
from app.models import Recording, Task  # noqa: E402,F401  # 触发 ORM 注册
from app.models.base import Base  # noqa: E402

logger = get_logger(__name__)


async def _create_all_tables() -> None:
    """异步建表：调用 SQLAlchemy 的 create_all。"""
    engine = init_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("SQLite 表结构创建完成")


def main() -> None:
    """入口：建表 + 释放连接池。"""
    setup_logging(log_level="info")
    try:
        asyncio.run(_create_all_tables())
    finally:
        asyncio.run(dispose_engine())


if __name__ == "__main__":
    main()
