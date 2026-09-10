# ============================================
# 文件: backend/app/services/recording_service.py
# 功能: 录音文件的元数据管理。
#      - 接收上传文件流，计算 SHA256
#      - 落盘到 UPLOAD_DIR
#      - 基于 file_hash 实现幂等去重
#      - 级联删除磁盘文件与关联任务
# ============================================
"""录音服务层。"""

import os
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import RecordingNotFoundError
from app.models import Recording
from app.utils.audio import ensure_upload_dir, validate_audio_upload
from app.utils.file_hash import sha256_of_stream


class RecordingService:
    """录音相关业务方法集合。"""

    @staticmethod
    async def create_or_reuse(
        db: AsyncSession,
        upload: UploadFile,
        upload_dir: str,
        max_size_mb: int,
        allowed_exts: tuple[str, ...],
    ) -> tuple[Recording, bool]:
        """创建新录音记录；若同 hash 已存在则复用。

        参数:
            db: 异步数据库会话
            upload: FastAPI UploadFile 对象
            upload_dir: 磁盘保存目录
            max_size_mb: 单文件上限 MB
            allowed_exts: 允许的扩展名元组

        返回:
            (Recording 实例, 是否为幂等复用)

        异常:
            InvalidAudioError: 扩展名或大小不合法
        """
        # 功能说明：对 UploadFile 做完整校验（扩展名 + 大小）
        metadata = await validate_audio_upload(upload, allowed_exts, max_size_mb)
        # 功能说明：先按 hash 查重，若命中则直接复用（避免重复算 hash 和写盘）
        #           注：这里先算 hash 再查重，因为 hash 是幂等判断的唯一依据
        file_hash = await sha256_of_stream(upload.file)
        existing = await RecordingService.find_by_hash(db, file_hash)
        if existing is not None:
            return existing, True
        # 功能说明：未命中幂等则落盘，使用 UUID 避免文件名冲突
        ensure_upload_dir(upload_dir)
        ext = metadata["ext"]
        saved_filename = f"{uuid.uuid4()}{ext}"
        saved_path = os.path.join(upload_dir, saved_filename)
        # 功能说明：将 UploadFile 内容写入磁盘（seek(0) 重置读取指针，因为 sha256_of_stream 已消费过）
        upload.file.seek(0)
        with open(saved_path, "wb") as f:
            while chunk := upload.file.read(1024 * 1024):
                f.write(chunk)
        # 功能说明：构造 Recording 对象并持久化
        recording = Recording(
            filename=upload.filename or saved_filename,
            file_path=saved_path,
            file_size=metadata["size"],
            file_hash=file_hash,
            mime_type=metadata["mime_type"],
        )
        db.add(recording)
        await db.flush()
        await db.refresh(recording)
        return recording, False

    @staticmethod
    async def list_paginated(
        db: AsyncSession, page: int, page_size: int
    ) -> tuple[list[Recording], int]:
        """分页查询录音列表（按创建时间倒序）。

        参数:
            db: 异步数据库会话
            page: 页码，从 1 开始
            page_size: 每页条数

        返回:
            (录音列表, 总条数)
        """
        # 功能说明：构造 SELECT，关联预加载最新 task（仅取一条），按创建时间倒序
        offset = (page - 1) * page_size
        stmt = (
            select(Recording)
            .options(selectinload(Recording.tasks))
            .order_by(Recording.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await db.execute(stmt)
        recordings = list(result.scalars().all())
        # 功能说明：单独查 count() 获取总条数（不带分页的简单 count）
        count_stmt = select(func.count()).select_from(Recording)
        total = (await db.execute(count_stmt)).scalar() or 0
        return recordings, total

    @staticmethod
    async def get_with_latest_task(db: AsyncSession, recording_id: str) -> Recording:
        """获取录音详情，预加载最新任务。

        参数:
            db: 异步数据库会话
            recording_id: 录音 UUID

        返回:
            包含 tasks 列表的 Recording 实例

        异常:
            RecordingNotFoundError: 录音不存在
        """
        stmt = (
            select(Recording)
            .options(selectinload(Recording.tasks))
            .where(Recording.id == recording_id)
        )
        result = await db.execute(stmt)
        recording = result.scalar_one_or_none()
        if recording is None:
            raise RecordingNotFoundError(recording_id)
        return recording

    @staticmethod
    async def delete_cascade(db: AsyncSession, recording_id: str) -> None:
        """删除录音（含磁盘文件与关联任务）。

        参数:
            db: 异步数据库会话
            recording_id: 录音 UUID

        异常:
            RecordingNotFoundError: 录音不存在
        """
        # 功能说明：先查录音获取磁盘路径，再删文件
        recording = await RecordingService.get_with_latest_task(db, recording_id)
        file_path = recording.file_path
        RecordingService.remove_file_safely(file_path)
        # 功能说明：删除数据库行，外键 CASCADE 会自动删除关联 task
        await db.delete(recording)
        await db.commit()

    @staticmethod
    async def find_by_hash(db: AsyncSession, file_hash: str) -> Recording | None:
        """按 SHA256 查找录音。"""
        stmt = select(Recording).where(Recording.file_hash == file_hash)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def remove_file_safely(path: str) -> None:
        """静默删除磁盘文件，文件不存在不报错。"""
        try:
            os.remove(path)
        except FileNotFoundError:
            # 功能说明：文件不存在不影响业务逻辑，静默忽略
            pass
