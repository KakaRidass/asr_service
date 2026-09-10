# ============================================
# 文件: backend/app/models/base.py
# 功能: SQLAlchemy 声明基类，统一表名约定、时间戳字段。
# ============================================
"""ORM 模型基类。"""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有 ORM 模型的声明基类。"""

    pass


class TimestampMixin:
    """提供 created_at / updated_at 自动维护的 Mixin。

    通过 SQLAlchemy 的 server_default 与 onupdate 实现。
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间",
    )
