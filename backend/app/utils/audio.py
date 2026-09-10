# ============================================
# 文件: backend/app/utils/audio.py
# 功能: 音频文件校验。
#      - 扩展名白名单
#      - 大小上限
#      - 文件存在
# ============================================
"""音频校验工具。"""

from pathlib import Path

from fastapi import UploadFile

from app.core.exceptions import InvalidAudioError


def validate_audio_filename(filename: str | None, allowed_exts: tuple[str, ...]) -> str:
    """校验文件名非空且扩展名合法。

    参数:
        filename: 原始文件名
        allowed_exts: 允许的扩展名小写元组，如 (".wav", ".mp3")

    返回:
        规范化后的小写扩展名（含点）

    异常:
        InvalidAudioError: 文件名为空或扩展名不在白名单
    """
    # 功能说明：检查 filename 非 None 非空，避免 FastAPI 传入空字符串
    if not filename:
        raise InvalidAudioError("文件名不能为空")
    # 功能说明：提取后缀（小写）后比对白名单
    ext = Path(filename).suffix.lower()
    if ext not in allowed_exts:
        raise InvalidAudioError(
            f"不支持的音频格式: {ext}，仅支持 {', '.join(allowed_exts)}"
        )
    return ext


def check_upload_size(size_bytes: int, max_size_mb: int) -> None:
    """校验文件大小不超过上限。

    参数:
        size_bytes: 实际字节数
        max_size_mb: 最大 MB 数

    异常:
        InvalidAudioError: 超过上限
    """
    max_bytes = max_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise InvalidAudioError(
            f"文件大小 {size_bytes / 1024 / 1024:.1f}MB 超过上限 {max_size_mb}MB"
        )


def ensure_upload_dir(upload_dir: str) -> Path:
    """确保上传目录存在，不存在则创建。"""
    path = Path(upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def validate_audio_upload(
    upload: UploadFile,
    allowed_exts: tuple[str, ...],
    max_size_mb: int,
) -> dict:
    """对 UploadFile 做完整校验，返回元数据字典。

    参数:
        upload: FastAPI UploadFile 对象
        allowed_exts: 允许的扩展名
        max_size_mb: 文件大小上限 MB

    返回:
        {
            "ext": 扩展名（如 ".wav"）,
            "mime_type": MIME 类型,
            "size": 文件大小（字节，从 content_length 读取）,
        }

    异常:
        InvalidAudioError: 校验失败
    """
    # 功能说明：校验扩展名
    ext = validate_audio_filename(upload.filename, allowed_exts)
    # 功能说明：从 headers 中读取 content-length，若缺失则从 UploadFile 读取实际大小
    # 功能说明：FastAPI UploadFile.size 在内存文件时可用
    size = upload.size
    if size is None:
        raise InvalidAudioError("无法获取文件大小")
    check_upload_size(size, max_size_mb)
    # 功能说明：取 content_type 作为 mime_type，缺失则根据扩展名推断
    mime_type = upload.content_type or ""
    return {
        "ext": ext,
        "mime_type": mime_type or None,
        "size": size,
    }
