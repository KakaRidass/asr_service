# ============================================
# 文件: cli/api_client.py
# 功能: 封装对 FastAPI 后端的 HTTP 调用。
#      所有方法返回 dict 或 None，不抛异常给上层（统一返回 (ok, data, msg)）。
# ============================================
"""后端 API 客户端。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx


class APIClient:
    """薄封装 httpx，提供面向用户的辅助方法。"""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        # 去掉末尾斜杠，避免 URL 拼接出 //v1
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # 共享一个 Client，复用连接池
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        """关闭底层 httpx 客户端。"""
        self._client.close()

    # ---------- 通用请求辅助 ----------

    def _request(self, method: str, path: str, **kwargs) -> tuple[bool, Any, str]:
        """统一错误处理，返回 (成功, 数据, 错误信息)。

        成功: 2xx 响应，data 为解析后的 JSON（GET）或 None（DELETE）。
        失败: 包含错误描述的字符串，data 为 None。
        """
        url = f"{self.base_url}{path}"
        try:
            resp = self._client.request(method, url, **kwargs)
        except httpx.ConnectError:
            return False, None, f"无法连接后端 {url}，请确认服务已启动"
        except httpx.TimeoutException:
            return False, None, f"请求超时（{self.timeout}s）: {method} {path}"
        except httpx.HTTPError as e:
            return False, None, f"网络错误: {e}"

        if resp.status_code == 204:
            # DELETE 无内容
            return True, None, ""

        # 尝试解析 JSON；非 JSON 时给出原始文本
        try:
            data = resp.json()
        except ValueError:
            data = resp.text

        if 200 <= resp.status_code < 300:
            return True, data, ""

        # 错误响应：FastAPI 默认 {"detail": "..."}
        detail = data.get("detail") if isinstance(data, dict) else None
        msg = f"HTTP {resp.status_code}: {detail or data}"
        return False, None, msg

    # ---------- 业务接口 ----------

    def health(self) -> tuple[bool, Any, str]:
        """健康检查。"""
        return self._request("GET", "/v1/health")

    def upload_recording(self, file_path: str) -> tuple[bool, Any, str]:
        """上传录音文件，返回 recording_id / task_id。"""
        # 先按原字符串判断是否存在 —— 不依赖 Path.resolve() 的"按字面回退"
        # 行为，避免对 Windows 中文/带空格路径产生误判。
        import os
        abs_path = os.path.abspath(file_path)
        if not (os.path.isfile(abs_path) or os.path.isfile(file_path)):
            return False, None, (
                f"文件不存在: {file_path}\n"
                f"  解析后路径: {abs_path}\n"
                f"  提示: 请确认文件实际存在；如路径含中文/空格，建议用 `dir \"{file_path}\"`"
                " 在 CMD 先验证"
            )
        # 用 Path 仅用于读取，名字用 basename 避免 multipart filename 包含目录
        path = Path(abs_path)
        try:
            with path.open("rb") as f:
                files = {"file": (path.name, f)}
                return self._request("POST", "/v1/recordings", files=files)
        except OSError as e:
            return False, None, f"读取文件失败: {e}"

    def list_recordings(self, page: int = 1, page_size: int = 20) -> tuple[bool, Any, str]:
        """分页查询录音列表。"""
        params = {"page": page, "page_size": page_size}
        return self._request("GET", "/v1/recordings", params=params)

    def get_recording(self, recording_id: str) -> tuple[bool, Any, str]:
        """查询录音详情。"""
        return self._request("GET", f"/v1/recordings/{recording_id}")

    def get_task(self, task_id: str) -> tuple[bool, Any, str]:
        """查询任务状态。"""
        return self._request("GET", f"/v1/tasks/{task_id}")

    def retry_task(self, task_id: str) -> tuple[bool, Any, str]:
        """重试失败任务。"""
        return self._request("POST", f"/v1/tasks/{task_id}/retry")

    def stream_summary(self, recording_id: str) -> Any:
        """调用 SSE 端点，逐帧产出 (kind, payload)。

        kind 取值：
          - "token"：payload 为字符串片段（来自 {"token": "..."}）
          - "error"：payload 为错误信息（网络/HTTP/服务端 {"error": "..."}）
          - "done" ：payload 为空字符串（服务端哨兵 [DONE]）

        本方法不抛异常，所有失败都转为 ("error", msg) 让上层统一处理。
        """
        path = f"/v1/recordings/{recording_id}/summary/stream"
        url = f"{self.base_url}{path}"
        # 流式请求单独设置超时：连接 5s、读 120s、写 5s、空闲 30s，
        # httpx 要求四参数都显式给定（不能只给部分字段）。
        stream_timeout = httpx.Timeout(connect=5.0, read=120.0, write=5.0, pool=30.0)
        with self._client.stream("GET", url, timeout=stream_timeout) as resp:
            if not (200 <= resp.status_code < 300):
                body = resp.read().decode("utf-8", errors="replace")[:200]
                yield ("error", f"HTTP {resp.status_code}: {body}")
                return
            buffer = ""
            for chunk in resp.iter_text():
                buffer += chunk
                # SSE 帧以空行分隔；用 split 切，未切完的留到下一轮
                while "\n\n" in buffer:
                    frame, buffer = buffer.split("\n\n", 1)
                    line = frame.strip()
                    if not line.startswith("data: "):
                        continue
                    payload = line[len("data: "):]
                    if payload == "[DONE]":
                        yield ("done", "")
                        return
                    try:
                        obj = json.loads(payload)
                    except ValueError:
                        continue
                    if "token" in obj:
                        yield ("token", str(obj["token"]))
                    elif "error" in obj:
                        yield ("error", str(obj["error"]))
