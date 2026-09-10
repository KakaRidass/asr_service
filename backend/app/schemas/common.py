# ============================================
# 文件: backend/app/schemas/common.py
# 功能: 通用响应模型（分页、错误）。
# ============================================
"""通用 Schema。"""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Pagination(BaseModel):
    """分页元数据。"""

    page: int = Field(..., ge=1, description="当前页码")
    page_size: int = Field(..., ge=1, le=100, description="每页条数")
    total: int = Field(..., ge=0, description="总条数")


class PageResponse(BaseModel, Generic[T]):
    """通用分页响应。"""

    items: list[T]
    pagination: Pagination


class ErrorResponse(BaseModel):
    """统一错误响应。

    与 rules.md 中规定的 {"detail": "..."} 格式保持一致。
    """

    detail: str
