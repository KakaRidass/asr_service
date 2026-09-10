# ============================================
# 文件: backend/app/utils/file_hash.py
# 功能: 大文件分块 SHA256 计算。
#      避免一次性 read() 把 50MB 文件读入内存。
# ============================================
"""文件哈希工具。"""

import asyncio
import hashlib
from pathlib import Path
from typing import IO

CHUNK_SIZE = 1024 * 1024  # 1 MB


async def sha256_of_file(file_path: str | Path) -> str:
    """异步计算文件的 SHA256 哈希值。

    参数:
        file_path: 文件路径

    返回:
        64 位十六进制小写字符串
    """
    # 功能说明：以二进制模式分块读取，协程内为同步 IO，需用 run_in_executor 避免阻塞事件循环
    loop = asyncio.get_running_loop()
    path_obj = Path(file_path)

    async def _sync_hash() -> str:
        hasher = hashlib.sha256()
        with path_obj.open("rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                hasher.update(chunk)
        return hasher.hexdigest()

    return await loop.run_in_executor(None, _sync_hash)


async def sha256_of_stream(file_obj: IO[bytes]) -> str:
    """从已打开的文件对象流式计算 SHA256（用于 UploadFile）。

    参数:
        file_obj: 任意带 read() 方法的对象（UploadFile.file / SpooledTemporaryFile）

    返回:
        64 位十六进制小写字符串
    """
    # 功能说明：seek(0) 重置指针，分块读取，每次 update 后清空缓冲区
    # 注意：必须是普通 def，不能是 async def，run_in_executor 只接受同步函数
    loop = asyncio.get_running_loop()

    def _sync_stream_hash() -> str:
        hasher = hashlib.sha256()
        file_obj.seek(0)
        while chunk := file_obj.read(CHUNK_SIZE):
            hasher.update(chunk)
        return hasher.hexdigest()

    return await loop.run_in_executor(None, _sync_stream_hash)
