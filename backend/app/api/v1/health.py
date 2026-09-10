# ============================================
# 文件: backend/app/api/v1/health.py
# 功能: 健康检查端点。
#      用于 docker-compose 的 healthcheck 探针。
# ============================================
"""健康检查路由。"""

from fastapi import APIRouter, status
from sqlalchemy import text

from app.api.deps import DBDep

router = APIRouter(tags=["health"])


@router.get("/health", summary="健康检查")
async def healthcheck(db: DBDep) -> dict:
    """返回服务与数据库连接状态。

    返回:
        {"status": "ok", "database": "connected"}
    """
    db_status = "connected"
    db_error = None
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        db_status = "error"
        db_error = f"{exc.__class__.__name__}: {exc}"
        return {
            "status": "degraded",
            "database": db_status,
            "database_error": db_error,
        }
    return {
        "status": "ok",
        "database": db_status,
    }
