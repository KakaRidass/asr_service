# ============================================
# 文件: backend/app/models/recording.py
# 功能: 录音记录 ORM 模型。
#      字段对应 SQL 迁移脚本 001_init.sql。
# ============================================
"""录音记录 ORM 模型。"""

import uuid

from sqlalchemy import BigInteger, CHAR, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.task import Task  # noqa: F401  # 用于 relationship order_by 表达式


class Recording(Base, TimestampMixin):
    """录音文件元数据表。

    一条 recording 对应磁盘上一个音频文件。
    同一文件（按 SHA256）只允许存在一条 recording，
    用于实现上传幂等。
    """

    __tablename__ = "recordings"

    id: Mapped[str] = mapped_column(
        CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="录音 UUID",
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False, comment="原始文件名")
    file_path: Mapped[str] = mapped_column(String(512), nullable=False, comment="磁盘存储路径")
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="字节数")
    file_hash: Mapped[str] = mapped_column(
        CHAR(64),
        unique=True,
        index=True,
        nullable=False,
        comment="SHA256 哈希（幂等键）",
    )
    mime_type: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="MIME 类型")

    # 反向引用：一个 recording 可关联多个 task（历史 retry 会产生多个）。
    # 显式按 created_at DESC 排序，确保 tasks[0] 始终是最新任务，
    # 否则 SQLAlchemy 不保证顺序，列表接口可能取到历史 task（重试后会看到旧状态）。
    tasks: Mapped[list["Task"]] = relationship(  # noqa: F821
        back_populates="recording",
        lazy="selectin",
        order_by=Task.created_at.desc(),
    )
