# ============================================
# 文件: backend/app/services/transcription_service.py
# 功能: 转写 + 摘要流水线的业务编排。
#      由 pipeline_worker 在后台协程中调用。
#      不直接对外暴露 HTTP 接口。
# ============================================
"""转写流水线编排服务。"""

import asyncio
import random

from app.clients.llm_client import LLMClient
from app.core.config import settings
from app.core.logging import get_logger
from app.models import TaskStatus
from app.services.task_service import TaskService

logger = get_logger(__name__)


class TranscriptionService:
    """编排"转写 → 摘要"两阶段流水线。

    该类的方法均在后台协程中执行，不应被 HTTP 路由直接调用。
    """

    def __init__(self, llm_client: LLMClient):
        """初始化流水线编排器。

        参数:
            llm_client: LLM 客户端实例（外部注入，便于测试替换）
        """
        self.llm_client = llm_client

    async def run_pipeline(
        self,
        db_factory,
        task_id: str,
    ) -> None:
        """执行完整的转写 + 摘要流水线。

        任何阶段失败都会被捕获并把 task 标为 failed，确保 worker 不会因
        未捕获异常而把任务永久卡在中间状态。

        参数:
            db_factory: 可调用的 Session 工厂（worker 注入，避免与请求会话耦合）
            task_id: 待处理的任务 UUID

        异常:
            不抛出异常；所有失败均写入 task.error_message
        """
        async with db_factory() as db:
            try:
                task = await TaskService.get(db, task_id)
            except Exception as exc:
                logger.error(f"任务 {task_id} 加载失败: {exc}", exc_info=True)
                return

            # ---------- 阶段 1：转写（mock）----------
            try:
                await TaskService.update_status(
                    db, task,
                    new_status=TaskStatus.TRANSCRIBING,
                    current_stage="转写中",
                )
                logger.info(f"任务 {task_id} 进入转写阶段")
                transcript = await self.mock_transcribe()
            except Exception as exc:
                logger.error(f"任务 {task_id} 转写失败: {exc}")
                await TaskService.mark_failed(db, task, f"转写失败: {exc}")
                return

            # ---------- 阶段 2：摘要（真实 LLM）----------
            try:
                await TaskService.update_status(
                    db, task,
                    new_status=TaskStatus.SUMMARIZING,
                    current_stage="摘要生成中",
                    transcript=transcript,
                )
                logger.info(f"任务 {task_id} 进入摘要阶段")
                summary_json = await self.summarize(transcript)
            except Exception as exc:
                logger.error(f"任务 {task_id} 摘要失败: {exc}")
                await TaskService.mark_failed(db, task, f"摘要失败: {exc}")
                return

            # ---------- 阶段 3：完成 ----------
            await TaskService.update_status(
                db, task,
                new_status=TaskStatus.DONE,
                current_stage="已完成",
                summary_json=summary_json,
            )
            logger.info(f"任务 {task_id} 处理完成（done）")

    async def mock_transcribe(self) -> str:
        """Mock 转写：随机耗时 5~15 秒，约 20% 概率失败。

        模拟真实 ASR 行为：
            - 每次 sleep 随机秒数（从 .env 配置读取区间）
            - 失败率 MOCK_TRANSCRIBE_FAIL_RATE，模拟识别失败
            - 成功时返回固定模板 + 随机噪声的 transcript

        返回:
            模拟产出的转写文本

        异常:
            RuntimeError: 模拟 ASR 失败
        """
        lo = max(0, settings.MOCK_TRANSCRIBE_MIN_SEC)
        hi = max(lo + 1, settings.MOCK_TRANSCRIBE_MAX_SEC)
        sleep_sec = random.uniform(lo, hi)
        logger.debug(f"mock 转写模拟耗时 {sleep_sec:.1f}s")
        await asyncio.sleep(sleep_sec)

        if random.random() < settings.MOCK_TRANSCRIBE_FAIL_RATE:
            raise RuntimeError("模拟 ASR 识别失败（mock）")

        # 固定模板 + 随机噪声，让每次结果略有不同
        noise = random.randint(1000, 9999)
        body = (
            "【mock 对话样本 编号 %d】\n"
            "（SPK_0） 喂，你好，能听到我说话吗？\n"
            "（SPK_1） 喂老师您好，能听到，很清楚。\n"
            "（SPK_0） 好嘞，我看到你的简历了，咱们直接一点哈，你现在的意向城市和薪资预期大概是多少？\n"
            "（SPK_1） 我主要想投北上广深，尤其优先北京和上海。薪资的话，因为我毕竟是 27 届的应届生嘛，我希望总包能在二十五万到三十万左右。\n"
            "（SPK_0） 二十五到三十？这个期望在技术岗里算是中等偏上，但也不是不可能。LeetCode 刷了多少道了？\n"
            "（SPK_1） 大概两百道左右，但是 hot 一百我刷了两遍。\n"
            "（SPK_0） 行，技术底子还可以。接下来两个星期，重点刷一下大厂的真题，尤其是字节和腾讯。\n"
        ) % noise
        return body

    async def summarize(self, transcript: str) -> dict:
        """调用 LLM 生成结构化摘要。

        参数:
            transcript: 转写文本

        返回:
            {"summary": str, "key_points": list[str], "todos": list[str]}

        异常:
            RuntimeError: LLM 调用失败（超时 / 网络错误 / HTTP 非 2xx / 空返回）
            ValueError: LLM 输出无法解析为 JSON 或字段缺失
        """
        prompt = self.build_summary_prompt(transcript)
        try:
            content = await self.llm_client.chat(
                prompt,
                system="你是一名严谨的会议助理，只输出合法 JSON，不输出任何额外文字。",
            )
        except RuntimeError:
            # 透传网络/超时错误，run_pipeline 会标 failed
            raise

        # 解析严格 JSON；解析失败抛 ValueError，由 run_pipeline 兜底
        return LLMClient.parse_summary_json(content)

    @staticmethod
    def build_summary_prompt(transcript: str) -> str:
        """构造摘要 prompt。

        参数:
            transcript: 转写文本

        返回:
            完整的 prompt 字符串
        """
        return (
            "请阅读以下会议/录音转写文本，并产出一段结构化摘要。\n"
            "要求严格输出一个 JSON 对象，键与类型如下：\n"
            '  - "summary":     string，一句话总结（<=80 字）\n'
            '  - "key_points":  string[]，2~5 条要点\n'
            '  - "todos":       string[]，0~5 条待办事项（无则输出空数组）\n'
            "不要输出除 JSON 之外的任何字符，不要使用 Markdown 代码块。\n\n"
            f"转写文本：\n{transcript}\n"
        )
