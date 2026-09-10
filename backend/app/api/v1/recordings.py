# ============================================
# 文件: backend/app/api/v1/recordings.py
# 功能: /v1/recordings 系列接口。
#      POST /v1/recordings       上传
#      GET  /v1/recordings       分页列表
#      GET  /v1/recordings/{id}  详情
#      DELETE /v1/recordings/{id} 删除
# ============================================
"""录音路由。"""
import json

from fastapi import APIRouter, File, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import DBDep
from app.clients.llm_client import LLMClient
from app.core.config import settings
from app.core.exceptions import InvalidAudioError
from app.core.logging import get_logger
from app.schemas.common import PageResponse, Pagination
from app.schemas.recording import (
    RecordingDetail,
    RecordingSummary,
    RecordingUploadResponse,
    TaskStatusInfo,
)
from app.services.recording_service import RecordingService
from app.services.task_service import TaskService
from app.workers.pipeline_worker import get_pipeline_worker

router = APIRouter(prefix="/recordings", tags=["recordings"])
logger = get_logger(__name__)


@router.post(
    "",
    response_model=RecordingUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="上传录音文件",
)
async def upload_recording(
    db: DBDep,
    file: UploadFile = File(..., description="音频文件"),
) -> RecordingUploadResponse:
    """上传录音并创建处理任务。

    命中幂等（SHA256 已存在）时，复用旧 recording 并返回其最新 task。
    """
    # 调用链：RecordingService.create_or_reuse
    #   └→ utils.audio.validate_audio_upload   (扩展名/大小校验)
    #   └→ utils.file_hash.sha256_of_stream   (分块算 SHA256)
    #   └→ RecordingService.find_by_hash       (幂等查重)
    #   └→ 落盘文件 → INSERT recording
    recording, reused = await RecordingService.create_or_reuse(
        db=db,
        upload=file,
        upload_dir=settings.UPLOAD_DIR,
        max_size_mb=settings.MAX_UPLOAD_SIZE_MB,
        allowed_exts=settings.ALLOWED_AUDIO_EXTS,
    )
    # 幂等命中：直接返回已有 recording 及其最新 task，不新建 task、不触发流水线。
    # 若该 task 历史上已经跑过转写，则顺手把 transcript 一起返回，避免客户端
    # 再调一次 /v1/tasks/{id} 才能拿到文本。
    if reused:
        task = await TaskService.get_latest_for_recording(db, recording.id)
        task_id = task.id if task else ""
        task_status = task.status if task else "pending"
        task_transcript = task.transcript if task else None
        logger.info(f"幂等命中，复用录音 {recording.id}，任务 {task_id}")
        return RecordingUploadResponse(
            recording_id=recording.id,
            task_id=task_id,
            status=task_status,
            idempotent_reused=True,
            transcript=task_transcript,
        )

    # 新建 recording：创建对应任务，立即入队，立即返回
    task = await TaskService.create_for_recording(db, recording)
    await db.commit()
    # 调用链：pipeline_worker.enqueue → asyncio.Queue.put
    worker = get_pipeline_worker()
    await worker.enqueue(task.id)
    logger.info(f"新建录音 {recording.id}，任务 {task.id} 已入队")
    return RecordingUploadResponse(
        recording_id=recording.id,
        task_id=task.id,
        status=task.status,
        idempotent_reused=False,
    )


@router.get(
    "",
    response_model=PageResponse[RecordingSummary],
    summary="分页查询录音列表",
)
async def list_recordings(
    db: DBDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PageResponse[RecordingSummary]:
    """按创建时间倒序分页返回录音列表。"""
    # 调用链：RecordingService.list_paginated
    #   └→ SELECT recordings ORDER BY created_at DESC
    #   └→ func.count() 查总数
    recordings, total = await RecordingService.list_paginated(db, page, page_size)
    items = []
    for rec in recordings:
        # tasks 已通过 selectinload 预加载（且 Recording.tasks 关系已加 order_by），
        # 此处再按 created_at 显式排序、取最新一条，作为防御性二次校验。
        latest_task = max(rec.tasks, key=lambda t: t.created_at, default=None)
        latest_status = latest_task.status if latest_task else None
        items.append(RecordingSummary(
            id=rec.id,
            filename=rec.filename,
            file_size=rec.file_size,
            created_at=rec.created_at,
            latest_task_status=latest_status,
        ))
    return PageResponse(
        items=items,
        pagination=Pagination(page=page, page_size=page_size, total=total),
    )


@router.get(
    "/{recording_id}",
    response_model=RecordingDetail,
    summary="录音详情",
)
async def get_recording(
    db: DBDep,
    recording_id: str,
) -> RecordingDetail:
    """返回录音详情与最新任务状态、转写文本、摘要。"""
    # 调用链：RecordingService.get_with_latest_task
    #   └→ SELECT recordings WHERE id=? OPTIONS (selectinload tasks)
    #   └→ RecordingNotFoundError (404)
    recording = await RecordingService.get_with_latest_task(db, recording_id)
    latest_task = max(recording.tasks, key=lambda t: t.created_at, default=None)
    task_info = None
    if latest_task:
        task_info = TaskStatusInfo(
            id=latest_task.id,
            status=latest_task.status,
            current_stage=latest_task.current_stage,
            error_message=latest_task.error_message,
            transcript=latest_task.transcript,
            summary_json=latest_task.summary_json,
        )
    return RecordingDetail(
        id=recording.id,
        filename=recording.filename,
        file_path=recording.file_path,
        file_size=recording.file_size,
        mime_type=recording.mime_type,
        created_at=recording.created_at,
        latest_task=task_info,
    )


@router.get(
    "/{recording_id}/summary/stream",
    summary="流式获取录音摘要（SSE）",
    response_class=StreamingResponse,
)
async def stream_summary(
    db: DBDep,
    request: Request,
    recording_id: str,
) -> StreamingResponse:
    """SSE 流式返回摘要生成过程。

    数据格式遵循 .cursor/rules.md：
      - 每个 token 事件：data: {"token": "..."}\\n\\n
      - 结束事件：data: [DONE]\\n\\n
      - 错误事件：data: {"error": "..."}\\n\\n

    注：本端点会重新调用 LLM（不读取 pipeline 写好的 summary_json），
    每次都会消耗 token；用于实时预览 / 调试。
    """
    # 1) 拿录音（不存在直接 404，由 service 抛 RecordingNotFoundError）
    recording = await RecordingService.get_with_latest_task(db, recording_id)
    latest_task = max(recording.tasks, key=lambda t: t.created_at, default=None)
    # 2) 防御式：转写未完成时拒绝流式
    transcript = latest_task.transcript if latest_task else None
    if not transcript:
        raise InvalidAudioError("转写尚未完成，无法生成摘要")
    # 3) 取 LLMClient 单例；main.py:54 startup 注入，shutdown 关闭
    llm: LLMClient = request.app.state.llm_client
    # 4) 返回 SSE；SSE 协议：每条消息以 data: 起头、以 \n\n 结尾
    return StreamingResponse(
        _summary_event_source(llm=llm, transcript=transcript, recording_id=recording_id),
        media_type="text/event-stream",
    )


@router.delete(
    "/{recording_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除录音",
)
async def delete_recording(
    db: DBDep,
    recording_id: str,
) -> None:
    """删除录音文件、数据库行与关联任务。"""
    # 调用链：RecordingService.delete_cascade
    #   └→ RecordingService.get_with_latest_task (验证存在)
    #   └→ os.remove(file_path)
    #   └→ db.delete(recording) → CASCADE 删除 tasks
    await RecordingService.delete_cascade(db, recording_id)
    logger.info(f"录音 {recording_id} 及其关联任务已删除")


# ============================================
# 以下：SSE 流式摘要的事件源生成器
# ============================================
async def _summary_event_source(llm: LLMClient, transcript: str, recording_id: str):
    """产出 SSE 事件流：每个 token 一行 data，最终一行结束标记。

    客户端用 EventSource 接收。生成器内部不假设客户端是否断连，
    每次 next() 都 try-yield。
    """
    # SSE 双换行作为帧分隔：把帧分隔符抽成常量，规避编辑器对 \n\n 的高亮 bug
    NEW = chr(10) + chr(10)
    DATA_PREFIX = "data: "
    # 防御式：避免外部传空 transcript 触发空 prompt
    if not transcript or not transcript.strip():
        yield DATA_PREFIX + '{"error": "transcript is empty"}' + NEW
        return
    # 与 pipeline_worker 保持一致的 system prompt，便于自测稳定
    system_prompt = "你是一个助理。请根据用户提供的录音转写文本，生成结构化摘要。"
    prompt = f"请对以下转写文本生成摘要，要求给出 summary / key_points / todos：\n\n{transcript}"
    try:
        async for piece in llm.chat_stream(prompt, system=system_prompt):
            # 转 JSON 单引号包裹，SSE data 帧
            payload = '{"token": ' + json.dumps(piece, ensure_ascii=False) + '}'
            yield DATA_PREFIX + payload + NEW
        # 结尾帧（项目约定的结束标记）
        yield DATA_PREFIX + "[DONE]" + NEW
    except Exception as exc:
        # 异常帧：保证客户端永远会看到一个收尾事件，而不是挂在半路
        msg = str(exc).replace(chr(34), "'")  # 防止内嵌引号破坏 JSON
        yield DATA_PREFIX + '{"error": ' + json.dumps(msg, ensure_ascii=False) + '}' + NEW
        # 任务级日志，便于后端定位
        logger.error(f"SSE 流式摘要异常 recording={recording_id}: {exc}")
