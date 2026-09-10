# ============================================
# 文件: backend/app/main.py
# 功能: FastAPI 应用入口。
#      - 配置 lifespan：启动 worker + DB 引擎，关闭时优雅退出
#      - 注册全局异常处理器
#      - 挂载 v1 路由
# ============================================
"""FastAPI 应用入口。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import health, recordings, tasks
from app.clients.llm_client import LLMClient
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.db.session import dispose_engine, get_session_factory, init_engine
from app.workers.pipeline_worker import init_pipeline_worker

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 生命周期：启动与关闭钩子。

    启动:
        1. 初始化日志
        2. 初始化异步 DB 引擎
        3. 构造 LLM 客户端（DeepSeek 占位 key 也允许创建，仅调用时再报错）
        4. 构造并启动 PipelineWorker
    关闭:
        1. 停止 PipelineWorker
        2. 关闭 LLM 客户端
        3. 释放 DB 连接池
    """
    # ----- 启动 -----
    setup_logging(log_level=settings.LOG_LEVEL, log_file=settings.LOG_FILE)
    logger.info("应用启动中...")
    init_engine()
    llm_client = LLMClient(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        model=settings.DEEPSEEK_MODEL,
        timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
    )
    worker = init_pipeline_worker(
        session_factory=get_session_factory(),
        llm_client=llm_client,
    )
    await worker.start()
    app.state.llm_client = llm_client
    logger.info("应用启动完成")

    try:
        yield
    finally:
        # ----- 关闭 -----
        logger.info("应用关闭中...")
        await worker.stop()
        await llm_client.close()
        await dispose_engine()
        logger.info("应用已关闭")


def create_app() -> FastAPI:
    """应用工厂函数。

    返回:
        配置完成的 FastAPI 实例
    """
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    # 注册全局异常处理器
    register_exception_handlers(app)

    # 挂载 v1 路由
    app.include_router(health.router, prefix="/v1")
    app.include_router(recordings.router, prefix="/v1")
    app.include_router(tasks.router, prefix="/v1")

    return app


# uvicorn 入口：CMD 走 `python -m uvicorn app.main:app`
app = create_app()
