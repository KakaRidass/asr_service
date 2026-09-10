# ============================================
# 文件: backend/app/models/task.py
# 功能: 处理任务 ORM 模型，承载状态机字段。
# ============================================
"""处理任务 ORM 模型。"""

import uuid

from sqlalchemy import CHAR, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin


class TaskStatus:
    """任务状态常量（字符串值，与 MySQL ENUM 对应）。"""

    PENDING = "pending"
    TRANSCRIBING = "transcribing"
    SUMMARIZING = "summarizing"
    DONE = "done"
    FAILED = "failed"


class Task(Base, TimestampMixin):
    """处理任务表。

    状态机：
        pending → transcribing → summarizing → done
        任意阶段异常 → failed（可被 retry 接口重置回 pending）
    """

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(
        CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="任务 UUID",
    )
    recording_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("recordings.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="所属录音 ID",
    )
    status: Mapped[str] = mapped_column(
        SAEnum(
            "pending",
            "transcribing",
            "summarizing",
            "done",
            "failed",
            name="task_status",
        ),
        nullable=False,
        default=TaskStatus.PENDING,
        index=True,
        comment="任务状态",
    )
    current_stage: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="当前阶段可读描述"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败原因")
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True, comment="转写文本")
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="摘要 JSON")
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="已重试次数")

    recording: Mapped["Recording"] = relationship(back_populates="tasks")  # noqa: F821
