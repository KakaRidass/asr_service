# ============================================
# 文件: backend/app/api/deps.py
# 功能: FastAPI 公共依赖。
#      目前主要暴露 get_db() 转发，也可用于注入 service 单例。
# ============================================
"""API 依赖模块。"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

# 类型别名：路由方法直接 `db: DBDep` 即可获得 Session
DBDep = Annotated[AsyncSession, Depends(get_db)]
