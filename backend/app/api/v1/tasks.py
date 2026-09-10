# ============================================
# 文件: backend/app/api/v1/tasks.py
# 功能: /v1/tasks 系列接口。
#      GET   /v1/tasks/{task_id}            查询状态
#      POST  /v1/tasks/{task_id}/retry      重试失败任务
# ============================================
"""任务路由。"""

from fastapi import APIRouter

from app.api.deps import DBDep
from app.core.logging import get_logger
from app.schemas.task import TaskRetryResponse, TaskStatusResponse
from app.services.task_service import TaskService
from app.workers.pipeline_worker import get_pipeline_worker

router = APIRouter(prefix="/tasks", tags=["tasks"])
logger = get_logger(__name__)


@router.get(
    "/{task_id}",
    response_model=TaskStatusResponse,
    summary="查询任务状态",
)
async def get_task_status(
    db: DBDep,
    task_id: str,
) -> TaskStatusResponse:
    """查询任务当前状态与所属阶段。"""
    task = await TaskService.get(db, task_id)
    return TaskStatusResponse.model_validate(task)


@router.post(
    "/{task_id}/retry",
    response_model=TaskRetryResponse,
    summary="重试失败任务",
)
async def retry_task(
    db: DBDep,
    task_id: str,
) -> TaskRetryResponse:
    """将失败任务重置回 pending 并重新入队。

    仅允许对 status=failed 的任务调用，否则返回 409。
    同一 task 重复并发调用 retry 也只会被处理一次。
    """
    task = await TaskService.retry(db, task_id)
    worker = get_pipeline_worker()
    await worker.enqueue(task.id)
    logger.info(f"任务 {task_id} 已重置为 pending 并重新入队")
    return TaskRetryResponse.model_validate(task)
