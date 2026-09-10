import sys
import locale


def _decode_stdin(text: str) -> str:
    """修复 Windows 终端输入中文路径的编码问题。

    Windows PowerShell/CMD 默认用 GBK (cp936) 编码传给 stdin，
    但 Python 3.15+ 默认用 UTF-8 解码，导致中文乱码。
    此函数检测 stdin 实际编码，重新用正确编码解码。
    """
    # 尝试用 locale 偏好的编码重新解码（Windows 上通常是 cp936/GBK）
    preferred = locale.getpreferredencoding(False)
    if preferred.lower() in ("cp936", "gbk", "gb2312", "gb18030"):
        # text 是用错误编码（UTF-8）解码后的乱码 bytes
        # 把乱码 bytes 重新编码回原始字节，再按正确编码解码
        try:
            raw_bytes = text.encode("utf-8", errors="surrogateescape")
            return raw_bytes.decode(preferred, errors="replace")
        except (UnicodeDecodeError, UnicodeEncodeError):
            return text
    return text


class _StdinReader:
    """安全读取 stdin 输入，自动处理 Windows GBK 编码问题。"""

    @staticmethod
    def readline(prompt: str = "") -> str:
        raw = input(prompt)
        decoded = _decode_stdin(raw)
        return decoded
