# ============================================
# 文件: backend/app/db/session.py
# 功能: 异步 SQLAlchemy 引擎与 Session 工厂。
#      提供 get_db() 依赖，供 FastAPI 路由注入。
# ============================================
"""数据库会话模块。

使用 SQLAlchemy 2.0 异步 API（asyncmy / aiomysql 驱动）。
"""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


# 全局引擎与 Session 工厂（启动时懒加载）
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine() -> AsyncEngine:
    """初始化全局异步引擎。

    返回:
        创建好的 AsyncEngine 实例

    异常:
        RuntimeError: 当 DATABASE_URL 未配置
    """
    global _engine, _session_factory  # noqa: PLW0603
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL 未配置，请检查 .env 文件")
    # 功能说明：create_async_engine 接收 mysql+aiomysql://... 或 sqlite+aiosqlite:///... 格式的 URL
    # 功能说明：SQLite 是文件型数据库，必须传 connect_args={"check_same_thread": False}
    #          才能在 FastAPI 多线程事件循环里复用同一连接
    is_sqlite = settings.DATABASE_URL.lower().startswith("sqlite")
    engine_kwargs: dict = {
        "echo": settings.DB_ECHO,
        # TODO: pool_pre_ping 当前与 aiomysql 0.3.x 不兼容
        #       (SQLAlchemy 2.0.30 do_ping 调用 ping() 不传 reconnect 参数)
        #       升级 SQLAlchemy >= 2.0.31 后再开启
        "pool_pre_ping": False,
    }
    if is_sqlite:
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        engine_kwargs["pool_size"] = settings.DB_POOL_SIZE
        engine_kwargs["max_overflow"] = settings.DB_MAX_OVERFLOW
    _engine = create_async_engine(
        settings.DATABASE_URL,
        **engine_kwargs,
    )
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,  # 功能说明：commit 后不自动 expire 对象，方便响应序列化
    )
    return _engine


def get_engine() -> AsyncEngine:
    """获取全局引擎单例（惰性初始化）。"""
    global _engine  # noqa: PLW0603
    if _engine is None:
        init_engine()
    assert _engine is not None
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """获取 Session 工厂。"""
    global _session_factory  # noqa: PLW0603
    if _session_factory is None:
        init_engine()
    assert _session_factory is not None
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, Any]:
    """FastAPI 依赖：提供异步 Session。

    使用方式:
        @router.get(...)
        async def handler(db: AsyncSession = Depends(get_db)): ...

    Yields:
        AsyncSession: 请求作用域内的数据库会话
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            # 功能说明：任何异常都回滚，保证数据一致性
            await session.rollback()
            raise
        finally:
            # 功能说明：显式关闭会话，归还连接到池
            await session.close()


async def dispose_engine() -> None:
    """应用关闭时释放连接池。"""
    global _engine, _session_factory  # noqa: PLW0603
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
