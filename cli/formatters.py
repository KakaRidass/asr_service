# ============================================
# 文件: cli/formatters.py
# 功能: 把后端返回的 dict 格式化成可读的 CLI 输出。
#      所有函数都是纯函数，方便单测。
# ============================================
"""输出格式化工具。"""

from __future__ import annotations

import sys
from datetime import datetime
from typing import Any

# 状态 → 颜色码（ANSI）
_STATUS_COLOR = {
    "pending":      "\033[90m",   # 灰
    "transcribing": "\033[33m",   # 黄
    "summarizing":  "\033[36m",   # 青
    "done":         "\033[32m",   # 绿
    "failed":       "\033[31m",   # 红
}
_RESET = "\033[0m"


def colorize(text: str, status: str) -> str:
    """按状态着色，无匹配时返回原文本。"""
    color = _STATUS_COLOR.get(status, "")
    if not color:
        return text
    return f"{color}{text}{_RESET}"


def fmt_datetime(value: Any) -> str:
    """容错格式化时间：字符串、datetime 都接受。"""
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, str):
        # 兼容 ISO 字符串，去掉时区尾巴便于阅读
        return value.replace("T", " ")[:19]
    return str(value)


def fmt_size(num_bytes: int | None) -> str:
    """字节数 → 人类可读（KB/MB）。"""
    if num_bytes is None:
        return "-"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def print_health(data: dict) -> None:
    """打印健康检查结果。"""
    print(f"  服务状态: {data.get('status', '-')}")
    print(f"  数据库:   {data.get('database', '-')}")


def print_upload_response(data: dict) -> None:
    """打印上传响应。"""
    reused = data.get("idempotent_reused", False)
    tag = "（命中幂等）" if reused else "（新建）"
    print(f"  录音 ID:  {data.get('recording_id', '-')}")
    print(f"  任务 ID:  {data.get('task_id', '-')}")
    print(f"  状  态:   {colorize(data.get('status', '-'), data.get('status', ''))} {tag}")


def print_recording_summary(item: dict) -> None:
    """打印列表项。"""
    rid = item.get("id", "-")
    name = item.get("filename", "-")
    size = fmt_size(item.get("file_size"))
    created = fmt_datetime(item.get("created_at"))
    status = item.get("latest_task_status") or "-"
    print(f"  {rid}  {name}  {size}  {created}  {colorize(status, status)}")


def print_recording_list(data: dict) -> None:
    """打印分页列表。"""
    items = data.get("items", []) or []
    page = (data.get("pagination") or {}).get("page", 1)
    total = (data.get("pagination") or {}).get("total", 0)
    print(f"  共 {total} 条，当前第 {page} 页：")
    if not items:
        print("  （暂无录音）")
        return
    # 表头
    print(f"  {'ID':<38}  {'文件名':<24}  {'大小':<10}  {'创建时间':<19}  {'最新任务'}")
    print(f"  {'-'*38}  {'-'*24}  {'-'*10}  {'-'*19}  {'-'*12}")
    for it in items:
        print_recording_summary(it)


def print_recording_detail(data: dict) -> None:
    """打印录音详情，含任务与转写结果。"""
    print(f"  录音 ID:   {data.get('id', '-')}")
    print(f"  文件名:    {data.get('filename', '-')}")
    print(f"  文件路径:  {data.get('file_path', '-')}")
    print(f"  文件大小:  {fmt_size(data.get('file_size'))}")
    print(f"  MIME:      {data.get('mime_type') or '-'}")
    print(f"  创建时间:  {fmt_datetime(data.get('created_at'))}")

    task = data.get("latest_task")
    if not task:
        print("  关联任务:  （无）")
        return

    print("  ── 关联任务 ──")
    print(f"    任务 ID:    {task.get('id', '-')}")
    print(f"    状    态:   {colorize(task.get('status', '-'), task.get('status', ''))}")
    print(f"    当前阶段:  {task.get('current_stage') or '-'}")
    err = task.get("error_message")
    if err:
        print(f"    错误信息:  {err}")

    transcript = task.get("transcript")
    if transcript:
        print("  ── 转写文本 ──")
        # 长文本只显示前 800 字符，避免刷屏
        snippet = transcript if len(transcript) <= 800 else transcript[:800] + "\n  ...（已截断）"
        for line in snippet.splitlines():
            print(f"    {line}")

    summary = task.get("summary_json")
    if summary:
        print("  ── 摘要 JSON ──")
        import json
        print("    " + json.dumps(summary, ensure_ascii=False, indent=2).replace("\n", "\n    "))


def print_task(data: dict) -> None:
    """打印任务详情。"""
    print(f"  任务 ID:    {data.get('id', '-')}")
    print(f"  录音 ID:    {data.get('recording_id', '-')}")
    print(f"  状    态:   {colorize(data.get('status', '-'), data.get('status', ''))}")
    print(f"  当前阶段:  {data.get('current_stage') or '-'}")
    err = data.get("error_message")
    if err:
        print(f"  错误信息:  {err}")
    print(f"  重试次数:  {data.get('retry_count', 0)}")
    print(f"  创建时间:  {fmt_datetime(data.get('created_at'))}")
    print(f"  更新时间:  {fmt_datetime(data.get('updated_at'))}")


def print_retry(data: dict) -> None:
    """打印重试响应。"""
    print(f"  任务 ID:    {data.get('task_id', '-')}")
    print(f"  新状态:    {colorize(data.get('status', '-'), data.get('status', ''))}")
    print(f"  重试次数:  {data.get('retry_count', 0)}")


# ---------- 流式摘要渲染 ----------
# 风格：逐 token 即时打印（end=''+flush=True），避免输出被缓冲。

def print_streaming_header(recording_id: str) -> None:
    """打印流式摘要开头：录音 ID + 提示。"""
    print(f"\n  ── 流式摘要（录音 {recording_id}）──")
    print("  （正在生成…按 Ctrl+C 可中断）\n")
    sys.stdout.flush()


def print_streaming_footer(token_count: int, had_error: bool) -> None:
    """打印流式摘要结尾：统计 + 状态。"""
    print()  # 收尾换行
    if had_error:
        print(f"  \033[31m✗ 流式中断（已收到 {token_count} 个 token）\033[0m")
    else:
        print(f"  ✓ 接收完毕（共 {token_count} 个 token）")
