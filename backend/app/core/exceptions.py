# ============================================
# 文件: backend/app/core/exceptions.py
# 功能: 自定义业务异常体系 + 全局异常处理器。
#      所有 API 错误最终转换为统一 JSON 结构：{"detail": "..."}
# ============================================
"""业务异常与错误处理模块。"""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


# ---------- 业务异常基类 ----------
class BusinessError(Exception):
    """业务异常基类。

    携带 HTTP 状态码与面向用户的错误描述。
    """

    def __init__(self, message: str, http_status: int = status.HTTP_400_BAD_REQUEST):
        """初始化业务异常。

        参数:
            message: 错误描述，会原样返回给客户端
            http_status: 对应的 HTTP 状态码，默认 400
        """
        self.message = message
        self.http_status = http_status
        super().__init__(message)


class RecordingNotFoundError(BusinessError):
    """录音记录不存在。"""

    def __init__(self, recording_id: str):
        super().__init__(
            message=f"录音不存在: {recording_id}",
            http_status=status.HTTP_404_NOT_FOUND,
        )


class TaskNotFoundError(BusinessError):
    """任务不存在。"""

    def __init__(self, task_id: str):
        super().__init__(
            message=f"任务不存在: {task_id}",
            http_status=status.HTTP_404_NOT_FOUND,
        )


class InvalidAudioError(BusinessError):
    """音频文件校验失败（扩展名或大小不合法）。"""

    def __init__(self, message: str):
        super().__init__(message=message, http_status=status.HTTP_400_BAD_REQUEST)


class TaskStateConflictError(BusinessError):
    """任务状态冲突（如：非 failed 状态调用 retry）。"""

    def __init__(self, message: str):
        super().__init__(message=message, http_status=status.HTTP_409_CONFLICT)


# ---------- 全局异常处理器 ----------
def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器到 FastAPI 应用。

    参数:
        app: FastAPI 应用实例
    """
    # 功能说明：将业务异常（BusinessError 及其子类）转为统一 JSON 响应
    app.add_exception_handler(BusinessError, _business_error_handler)
    # 功能说明：将 Pydantic 校验错误（请求体格式错误）转为 422
    app.add_exception_handler(RequestValidationError, _validation_error_handler)


async def _business_error_handler(request: Request, exc: BusinessError) -> JSONResponse:
    """BusinessError 处理器：统一 JSON 错误响应。"""
    return JSONResponse(
        status_code=exc.http_status,
        content={"detail": exc.message},
    )


async def _validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """RequestValidationError 处理器：返回 422 及详细字段错误。"""
    # 功能说明：FastAPI 自带的 RequestValidationError 错误信息较冗长，
    #          这里只取第一个错误的 message 简化展示
    errors = exc.errors()
    if errors:
        first = errors[0]
        msg = f"{'.'.join(str(loc) for loc in first.get('loc', []))}: {first.get('msg', '')}"
    else:
        msg = "请求参数校验失败"
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": msg},
    )
