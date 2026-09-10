# ============================================
# 文件: backend/app/schemas/recording.py
# 功能: 录音上传 / 详情 / 列表 的请求与响应模型。
# ============================================
"""录音相关 Pydantic Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RecordingUploadResponse(BaseModel):
    """上传录音成功响应。

    若命中幂等（同一文件已存在），task_id 会指向已有最新 task，
    status 为其当前状态。
    """

    model_config = ConfigDict(from_attributes=True)

    recording_id: str
    task_id: str
    status: str = Field(..., description="任务当前状态")
    idempotent_reused: bool = Field(default=False, description="是否命中幂等复用")
    transcript: str | None = Field(
        default=None,
        description="已有任务的转写文本（仅幂等命中且任务曾执行过时返回）",
    )


class RecordingSummary(BaseModel):
    """列表项中的录音摘要。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    file_size: int
    created_at: datetime
    latest_task_status: str | None = Field(default=None, description="最新任务状态")


class RecordingDetail(BaseModel):
    """录音详情。

    当处理完成时包含 transcript 与 summary。
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    file_path: str
    file_size: int
    mime_type: str | None
    created_at: datetime
    latest_task: "TaskStatusInfo | None" = None  # noqa: F821


class TaskStatusInfo(BaseModel):
    """录音详情中内嵌的任务状态信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    current_stage: str | None
    error_message: str | None
    transcript: str | None
    summary_json: dict | None
