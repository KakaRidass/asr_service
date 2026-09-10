# ============================================
# 文件: backend/app/clients/llm_client.py
# 功能: DeepSeek API 客户端封装。
#      - 基于 httpx 异步调用（不引入 openai SDK，减少依赖体积）
#      - 处理超时、非 JSON 返回
#      - 提供 chat() 单次接口
# ============================================
"""DeepSeek LLM 客户端。

DeepSeek 兼容 OpenAI Chat Completions 协议，因此 endpoint 与请求体
均按 OpenAI 格式构造。
"""

import json
import re
from typing import Any, AsyncIterator

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLMClient:
    """DeepSeek API 异步客户端。"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: int = 60,
    ):
        """初始化客户端。

        参数:
            api_key: DeepSeek API Key
            base_url: DeepSeek API base URL
            model: 模型名（如 deepseek-chat）
            timeout_seconds: 单次请求超时秒数
        """
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    async def chat(self, prompt: str, *, system: str | None = None) -> str:
        """调用 DeepSeek Chat Completions 接口。

        参数:
            prompt: 用户 prompt
            system: 可选 system prompt

        返回:
            LLM 返回的文本内容（已剥离 message 包装）

        异常:
            RuntimeError: 网络错误、超时、HTTP 非 2xx、内容为空
        """
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }

        try:
            resp = await self._client.post("/v1/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"DeepSeek 请求超时: {exc}") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"DeepSeek 网络错误: {exc}") from exc

        if resp.status_code >= 400:
            # 不打印完整 body 避免泄露敏感字段，只截取前 200 字符
            snippet = resp.text[:200] if resp.text else "(empty)"
            raise RuntimeError(
                f"DeepSeek 返回 HTTP {resp.status_code}: {snippet}"
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"DeepSeek 返回非 JSON: {exc}") from exc

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"DeepSeek 返回无 choices: {data}")
        content = (choices[0] or {}).get("message", {}).get("content")
        if not content:
            raise RuntimeError(f"DeepSeek 返回空 content: {data}")
        return content

    async def chat_stream(
        self, prompt: str, *, system: str | None = None
    ) -> AsyncIterator[str]:
        """流式调用 DeepSeek，逐 chunk 产出文本片段。

        参数:
            prompt: 用户 prompt
            system: 可选 system prompt

        返回:
            异步迭代器，每次 yield 一段文本（已剥离 SSE / JSON 包装）

        异常:
            RuntimeError: 网络错误、超时、HTTP 非 2xx
        """
        # 组装消息：system 可选，user 必填
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        # 关键开关：stream=True 让 DeepSeek 走 SSE
        payload = {"model": self._model, "messages": messages, "stream": True}

        # 使用 httpx 流式上下文，按行读取，不一次性下载整 body
        try:
            async with self._client.stream(
                "POST", "/v1/chat/completions", json=payload
            ) as resp:
                if resp.status_code >= 400:
                    # 非 2xx：尝试读取首块错误体，避免泄露完整 body
                    snippet = (await resp.aread()).decode("utf-8", "ignore")[:200]
                    raise RuntimeError(
                        f"DeepSeek 流式返回 HTTP {resp.status_code}: {snippet}"
                    )
                # 按 SSE 行迭代：每行形如 "data: {...}" 或 "data: [DONE]"
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[len("data: "):].strip()
                    if not data_str or data_str == "[DONE]":
                        if data_str == "[DONE]":
                            break
                        continue
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        # 单个 chunk 解析失败不影响后续 chunk，跳过即可
                        continue
                    # 取 delta.content（流式响应没有 message，只有增量）
                    delta = ((chunk.get("choices") or [{}])[0]).get("delta", {})
                    piece = delta.get("content")
                    if piece:
                        yield piece
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"DeepSeek 流式请求超时: {exc}") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"DeepSeek 流式网络错误: {exc}") from exc

    @staticmethod
    def parse_summary_json(content: str) -> dict[str, Any]:
        """从 LLM 输出中解析出 summary / key_points / todos 字典。

        兼容 LLM 把 JSON 包在 ```json ... ``` 代码块里的情况。

        参数:
            content: LLM 原始输出文本

        返回:
            包含 summary、key_points、todos 三个字段的字典

        异常:
            ValueError: 解析失败或字段缺失
        """
        # 尝试直接解析
        text = content.strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # 尝试剥离 ```json ... ``` 代码块
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
            if not m:
                raise ValueError("LLM 输出无法解析为 JSON") from None
            data = json.loads(m.group(1))

        # 字段完整性检查
        required = {"summary", "key_points", "todos"}
        missing = required - set(data.keys())
        if missing:
            raise ValueError(f"LLM 输出缺少字段: {missing}")
        return {
            "summary": str(data["summary"]),
            "key_points": list(data["key_points"]),
            "todos": list(data["todos"]),
        }

    async def close(self) -> None:
        """关闭底层 httpx 客户端。"""
        await self._client.aclose()
