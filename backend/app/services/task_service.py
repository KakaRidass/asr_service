# ============================================
# 文件: backend/app/services/task_service.py
# 功能: 任务状态机的读写。
#      - 创建初始任务（与 recording 绑定）
#      - 状态流转（pending → transcribing → summarizing → done/failed）
#      - 查询、重试
# ============================================
"""任务服务层。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import TaskNotFoundError, TaskStateConflictError
from app.models import Recording, Task, TaskStatus


class TaskService:
    """任务状态机管理。"""

    @staticmethod
    async def create_for_recording(db: AsyncSession, recording: Recording) -> Task:
        """为指定录音创建一条新任务，初始状态 pending。

        参数:
            db: 异步数据库会话
            recording: 已存在的 Recording 实例

        返回:
            新建的 Task 实例
        """
        task = Task(
            recording_id=recording.id,
            status=TaskStatus.PENDING,
            current_stage="等待处理",
            retry_count=0,
        )
        db.add(task)
        await db.flush()
        await db.refresh(task)
        return task

    @staticmethod
    async def get(db: AsyncSession, task_id: str) -> Task:
        """按 ID 查询任务。

        异常:
            TaskNotFoundError: 任务不存在
        """
        stmt = select(Task).where(Task.id == task_id)
        result = await db.execute(stmt)
        task = result.scalar_one_or_none()
        if task is None:
            raise TaskNotFoundError(task_id)
        return task

    @staticmethod
    async def get_latest_for_recording(db: AsyncSession, recording_id: str) -> Task | None:
        """查询某录音的最新任务（按 created_at desc）。

        返回:
            Task 实例或 None（录音暂无任务）
        """
        stmt = (
            select(Task)
            .where(Task.recording_id == recording_id)
            .order_by(Task.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def update_status(
        db: AsyncSession,
        task: Task,
        new_status: str,
        *,
        current_stage: str | None = None,
        error_message: str | None = None,
        transcript: str | None = None,
        summary_json: dict | None = None,
    ) -> Task:
        """更新任务状态及相关字段。

        参数:
            db: 异步数据库会话
            task: 待更新的 Task 实例
            new_status: 目标状态（pending/transcribing/summarizing/done/failed）
            current_stage: 可读阶段描述
            error_message: 失败原因
            transcript: 转写文本
            summary_json: 摘要 JSON

        返回:
            更新后的 Task 实例
        """
        task.status = new_status
        if current_stage is not None:
            task.current_stage = current_stage
        if error_message is not None:
            task.error_message = error_message
        if transcript is not None:
            task.transcript = transcript
        if summary_json is not None:
            task.summary_json = summary_json
        await db.commit()
        await db.refresh(task)
        return task

    @staticmethod
    async def mark_failed(db: AsyncSession, task: Task, error_message: str) -> Task:
        """将任务置为 failed 并记录原因。"""
        return await TaskService.update_status(
            db, task,
            TaskStatus.FAILED,
            current_stage="处理失败",
            error_message=error_message,
        )

    @staticmethod
    async def retry(db: AsyncSession, task_id: str) -> Task:
        """重试一个失败任务。

        行为：
            1. 校验当前状态必须为 failed，否则抛 409
            2. 清空 error_message、transcript、summary_json
            3. retry_count += 1
            4. status 重置为 pending
            5. 返回更新后的任务供 worker 重新调度

        异常:
            TaskNotFoundError: 任务不存在
            TaskStateConflictError: 状态非 failed
        """
        task = await TaskService.get(db, task_id)
        if task.status != TaskStatus.FAILED:
            raise TaskStateConflictError(
                f"只有 failed 状态的任务可以重试，当前状态: {task.status}"
            )
        # 功能说明：清空上一次失败的记录，准备重新执行
        task.error_message = None
        task.transcript = None
        task.summary_json = None
        task.retry_count += 1
        task.status = TaskStatus.PENDING
        task.current_stage = "等待重新处理"
        await db.commit()
        await db.refresh(task)
        return task

    @staticmethod
    def is_terminal(status: str) -> bool:
        """判断状态是否终态（done 或 failed）。"""
        return status in (TaskStatus.DONE, TaskStatus.FAILED)
