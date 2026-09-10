# ============================================
# 文件: cli/cli.py
# 功能: 命令行交互客户端。
#      提供菜单式操作：上传 / 列表 / 详情 / 任务查询 / 重试 / 健康检查。
#
# 启动:
#   python -m cli.cli
#   或:
#   python cli/cli.py
#   自定义后端地址:
#     set RECORDING_API_BASE=http://127.0.0.1:8000  (Windows PowerShell: $env:RECORDING_API_BASE=...)
# ============================================
"""CLI 交互客户端入口。"""

from __future__ import annotations

import builtins
import locale
import os
import sys
from pathlib import Path

# 让 `python cli/cli.py` 也能 import 同目录的兄弟模块
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Windows 终端默认 GBK，强制切到 UTF-8 让中文与 emoji 正常显示
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# ---------- stdin 编码修复（Windows GBK → UTF-8 问题）----------
# 背景：Windows PowerShell/CMD 用 GBK(cp936) 发送输入，但 Python 按 UTF-8 解码，
# 导致 input() 读到的中文字符串乱码，Path.exists() 找不到文件。
# 修复：用 locale 偏好的编码重新解码。

_RAW_INPUT = builtins.input  # 保留原始 input 供内部使用


def _fixed_input(prompt: str = "") -> str:
    """兼容 Windows GBK 终端的 input() 替身。

    注意：不能无条件地把 raw 字符串按 surrogateescape 重新编码再按 GBK 解码，
    因为现代终端（Windows Terminal / VSCode 内置 / PowerShell 7+）默认就以
    UTF-8 传给 stdin，那种情况下再做一次"乱码修复"反而会把正确的路径破坏掉，
    导致 Path.exists() 误报"文件不存在"。

    策略：
      1. 优先尝试把 raw 当作 UTF-8 解码（终端传的是 UTF-8 bytes 时这是无损的）。
      2. 解码失败且 locale 偏好是 GBK 系列时，再用 GBK 重新解码。
      3. 都失败时回退到原 raw，不影响英文路径。
    """
    raw = _RAW_INPUT(prompt)
    if not raw:
        return raw

    # 情形 A：终端本来就是 UTF-8（如 Windows Terminal、PowerShell 7、VSCode 终端）
    # 此时 raw 已经是正确的 Unicode 字符串，按 UTF-8 编码再解码应该是恒等变换。
    try:
        roundtrip = raw.encode("utf-8").decode("utf-8")
        if roundtrip == raw:
            # 看起来是合法 UTF-8，原样返回最安全
            return raw
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass

    # 情形 B：raw 里包含 surrogateescape 标记（说明 Python 是按 UTF-8 解码 GBK 字节得到的乱码）
    preferred = locale.getpreferredencoding(False)
    if preferred.lower() in ("cp936", "gbk", "gb2312", "gb18030"):
        try:
            raw_bytes = raw.encode("utf-8", errors="surrogateescape")
            return raw_bytes.decode(preferred, errors="replace")
        except (UnicodeDecodeError, UnicodeEncodeError):
            return raw
    return raw


# 把全局 input 替换掉，后续所有 input() 自动走修复版本
builtins.input = _fixed_input

from api_client import APIClient  # noqa: E402
import formatters as F            # noqa: E402


# ---------- 配置 ----------

DEFAULT_BASE_URL = "http://127.0.0.1:8003"


def get_base_url() -> str:
    """从环境变量读取后端地址，未设置时使用默认。"""
    return os.environ.get("RECORDING_API_BASE", DEFAULT_BASE_URL).rstrip("/")


# ---------- 菜单渲染 ----------

MENU = """
╔════════════════════════════════════════╗
║        录音转写系统 · CLI 客户端       ║
╠════════════════════════════════════════╣
║  1. 健康检查                           ║
║  2. 上传录音                           ║
║  3. 查看录音列表（分页）               ║
║  4. 查看录音详情                       ║
║  5. 查询任务状态                       ║
║  6. 重试失败任务                       ║
║  7. 流式预览摘要（SSE）                ║
╠════════════════════════════════════════╣
║  0. 退出                               ║
╚════════════════════════════════════════╝
"""


def print_header(client: APIClient) -> None:
    """每次循环开头打印标题与当前后端地址。"""
    print(MENU)
    print(f"  后端地址: {client.base_url}")
    print()


def pause() -> None:
    """按回车继续，避免刷屏。"""
    input("\n  按回车键继续...")


def handle_failure(msg: str) -> None:
    """统一错误展示。"""
    print(f"\n  \033[31m✗ {msg}\033[0m")


# ---------- 菜单动作 ----------

def action_health(client: APIClient) -> None:
    """1. 健康检查。"""
    print("  ── 健康检查 ──")
    ok, data, msg = client.health()
    if not ok:
        handle_failure(msg)
        return
    F.print_health(data)


def action_upload(client: APIClient) -> None:
    """2. 上传录音。"""
    print("  ── 上传录音 ──")
    # 不 strip()，保留路径原样（Windows 路径中可能有意义的首尾空格）
    path = input("  请输入音频文件路径（拖入文件也可）> ").strip()
    if not path:
        print("  已取消（路径为空）")
        return
    # 去掉 PowerShell 自动加的双引号（拖拽文件时常有）
    if path.startswith('"') and path.endswith('"'):
        path = path[1:-1]
    print(f"  正在上传: {path}")
    ok, data, msg = client.upload_recording(path)
    if not ok:
        handle_failure(msg)
        return
    F.print_upload_response(data)


def action_list(client: APIClient) -> None:
    """3. 分页列表。"""
    print("  ── 录音列表 ──")
    raw_page = input("  页码（默认 1）> ").strip()
    raw_size = input("  每页大小（默认 20，最大 100）> ").strip()
    try:
        page = int(raw_page) if raw_page else 1
        page_size = int(raw_size) if raw_size else 20
    except ValueError:
        handle_failure("页码和大小必须是整数")
        return
    if page < 1 or page_size < 1 or page_size > 100:
        handle_failure("范围错误：page>=1，1<=page_size<=100")
        return

    ok, data, msg = client.list_recordings(page=page, page_size=page_size)
    if not ok:
        handle_failure(msg)
        return
    F.print_recording_list(data)


def action_recording_detail(client: APIClient) -> None:
    """4. 录音详情。"""
    print("  ── 录音详情 ──")
    rid = input("  请输入录音 ID> ").strip()
    if not rid:
        print("  已取消")
        return
    ok, data, msg = client.get_recording(rid)
    if not ok:
        handle_failure(msg)
        return
    F.print_recording_detail(data)


def action_task_status(client: APIClient) -> None:
    """5. 任务状态。"""
    print("  ── 任务状态 ──")
    tid = input("  请输入任务 ID> ").strip()
    if not tid:
        print("  已取消")
        return
    ok, data, msg = client.get_task(tid)
    if not ok:
        handle_failure(msg)
        return
    F.print_task(data)


def action_retry(client: APIClient) -> None:
    """6. 重试任务。"""
    print("  ── 重试任务（仅 failed 状态可重试）──")
    tid = input("  请输入任务 ID> ").strip()
    if not tid:
        print("  已取消")
        return
    confirm = input(f"  确认重试任务 {tid}？(y/N)> ").strip().lower()
    if confirm != "y":
        print("  已取消")
        return
    ok, data, msg = client.retry_task(tid)
    if not ok:
        handle_failure(msg)
        return
    F.print_retry(data)


def action_stream_summary(client: APIClient) -> None:
    """7. 流式预览摘要（SSE）。

    主动调后端 SSE 端点，按 token 实时打印，不存库；用于在拿到完整 summary_json
    之前就能看到生成过程。
    """
    print("  ── 流式预览摘要（SSE）──")
    rid = input("  请输入录音 ID> ").strip()
    if not rid:
        print("  已取消")
        return
    F.print_streaming_header(rid)
    token_count = 0
    had_error = False
    try:
        for kind, payload in client.stream_summary(rid):
            if kind == "token":
                print(payload, end="", flush=True)
                token_count += 1
            elif kind == "error":
                had_error = True
                print(f"\n  \033[31m[服务端错误] {payload}\033[0m", flush=True)
                break
            elif kind == "done":
                break
    except KeyboardInterrupt:
        # 用户中途按 Ctrl+C：服务端可能还在跑，标记为中断即可
        had_error = True
        print("\n  （已中断）")
    F.print_streaming_footer(token_count, had_error)


# ---------- 主循环 ----------

ACTIONS = {
    "1": action_health,
    "2": action_upload,
    "3": action_list,
    "4": action_recording_detail,
    "5": action_task_status,
    "6": action_retry,
    "7": action_stream_summary,
}


def main() -> int:
    """CLI 入口。"""
    base_url = get_base_url()
    client = APIClient(base_url=base_url)
    try:
        while True:
            print()
            print("=" * 50)
            print_header(client)
            choice = input("  请选择操作 [0-7]> ").strip()
            if choice == "0":
                print("\n  再见 👋")
                return 0
            action = ACTIONS.get(choice)
            if not action:
                print("  无效选项，请重新输入")
                continue
            try:
                action(client)
            except KeyboardInterrupt:
                # Ctrl+C 跳过当前操作，回到菜单
                print("\n  （已中断当前操作）")
                continue
            pause()
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
