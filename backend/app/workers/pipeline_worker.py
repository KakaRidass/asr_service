# ============================================
# 文件: backend/app/workers/pipeline_worker.py
# 功能: 异步任务调度器。
#      - 维护 asyncio.Queue
#      - 信号量限制最大并发数（默认 3）
#      - 后台 worker 协程从队列取任务并调用 TranscriptionService
#      - 应用启动时由 FastAPI lifespan 拉起
# ============================================
"""异步任务调度 Worker。

设计取舍：
    - 使用 asyncio.Queue + Semaphore 实现轻量级调度，避免引入 Celery/Redis
    - 持久化仅靠数据库表，未实现"服务重启后自动恢复 pending 任务"，
      需在 README 中明确说明（用户已知情，不做加分项）
"""

import asyncio
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.clients.llm_client import LLMClient
    from app.services.transcription_service import TranscriptionService

logger = get_logger(__name__)

# ---------- 全局 Worker 单例 ----------
_worker: "PipelineWorker | None" = None


def get_pipeline_worker() -> "PipelineWorker":
    """获取全局 Worker 单例（供 API 路由注入 enqueue）。"""
    if _worker is None:
        raise RuntimeError("PipelineWorker 尚未初始化，请确认应用已启动")
    return _worker


def init_pipeline_worker(
    session_factory: async_sessionmaker,
    llm_client: "LLMClient",
) -> "PipelineWorker":
    """初始化并注册全局 Worker 单例（lifespan startup 时调用）。"""
    global _worker  # noqa: PLW0603
    _worker = PipelineWorker(session_factory, llm_client)
    return _worker


# ---------- Worker 实现 ----------
class PipelineWorker:
    """后台任务调度器。

    生命周期与 FastAPI 应用一致，由 lifespan 控制 start/stop。
    """

    def __init__(
        self,
        session_factory: async_sessionmaker,
        llm_client: "LLMClient",
    ):
        """初始化 Worker。

        参数:
            session_factory: 异步 Session 工厂
            llm_client: LLM 客户端实例
        """
        self._session_factory = session_factory
        self._llm_client = llm_client
        # 功能说明：asyncio.Queue 用于任务排队，max_concurrent 控制同时处理的任务数
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_TASKS)
        # 功能说明：worker_tasks 保存所有后台协程的 Task 对象，用于 stop 时取消
        self._worker_tasks: list[asyncio.Task] = []
        self._started = False

    async def start(self) -> None:
        """启动 Worker。

        在 FastAPI startup 阶段被调用。
        """
        if self._started:
            logger.warning("PipelineWorker 已经启动，忽略重复调用")
            return
        # 功能说明：创建 N 个 worker 协程（asyncio.create_task 将协程调度到事件循环）
        for i in range(settings.MAX_CONCURRENT_TASKS):
            task = asyncio.create_task(self._worker_loop(i), name=f"pipeline-worker-{i}")
            self._worker_tasks.append(task)
        self._started = True
        logger.info(
            f"PipelineWorker 已启动，{settings.MAX_CONCURRENT_TASKS} 个并发 worker"
        )

    async def stop(self) -> None:
        """停止 Worker。

        取消所有 worker 协程并等待其结束。
        """
        if not self._started:
            return
        # 功能说明：向所有 worker 协程发送取消信号
        for task in self._worker_tasks:
            task.cancel()
        # 功能说明：等待所有协程执行完取消后的清理逻辑
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()
        self._started = False
        logger.info("PipelineWorker 已停止")

    async def enqueue(self, task_id: str) -> None:
        """将任务加入处理队列。

        参数:
            task_id: 任务 UUID
        """
        await self._queue.put(task_id)
        logger.info(f"任务 {task_id} 已入队，当前队列长度: {self._queue.qsize()}")

    async def _worker_loop(self, worker_id: int) -> None:
        """单个 worker 协程的主循环。

        参数:
            worker_id: 协程编号（仅用于日志）
        """
        # 强制让出控制权，确保任务被调度进事件循环
        await asyncio.sleep(0)
        logger.info(f"Worker {worker_id} 已启动，等待任务...")
        while True:
            try:
                # 功能说明：从队列中取出任务，若队列为空则阻塞等待
                task_id = await self._queue.get()
                # 功能说明：用信号量控制同时运行的任务数
                async with self._semaphore:
                    try:
                        await self._run_task(task_id, worker_id)
                    finally:
                        self._queue.task_done()
            except asyncio.CancelledError:
                # 功能说明：收到取消信号时优雅退出
                logger.info(f"Worker {worker_id} 收到取消信号，退出循环")
                break
            except Exception as exc:
                # 兜底，避免 worker 协程因未预期异常静默死亡
                logger.error(f"Worker {worker_id} 循环异常: {exc}", exc_info=True)

    async def _run_task(self, task_id: str, worker_id: int) -> None:
        """执行单个转写任务。

        参数:
            task_id: 任务 UUID
            worker_id: 执行此任务的 worker 编号
        """
        # 功能说明：构造流水线服务（使用独立 Session，避免跨请求污染）
        pipeline = self._build_pipeline()
        logger.info(f"Worker {worker_id} 开始处理任务 {task_id}")
        try:
            await pipeline.run_pipeline(
                db_factory=self._session_factory,
                task_id=task_id,
            )
            logger.info(f"任务 {task_id} 处理完成")
        except Exception as exc:
            # 功能说明：流水线内部已处理异常（标记 failed），此处只记录未预期错误
            logger.error(f"任务 {task_id} 处理异常（未预期）: {exc}", exc_info=True)

    def _build_pipeline(self) -> "TranscriptionService":
        """构造流水线服务实例。"""
        # 延迟导入避免循环依赖
        from app.services.transcription_service import TranscriptionService
        return TranscriptionService(llm_client=self._llm_client)
