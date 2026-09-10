# ============================================
# 文件: backend/app/schemas/task.py
# 功能: 任务查询、重试的响应模型。
# ============================================
"""任务相关 Pydantic Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TaskStatusResponse(BaseModel):
    """任务状态查询响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    recording_id: str
    status: str
    current_stage: str | None
    error_message: str | None
    retry_count: int
    created_at: datetime
    updated_at: datetime


class TaskRetryResponse(BaseModel):
    """任务重试响应。

    重试成功后任务重新进入 pending 队列，等待 worker 调度。
    """

    model_config = ConfigDict(from_attributes=True)

    task_id: str
    status: str
    retry_count: int
