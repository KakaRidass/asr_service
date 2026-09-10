# ============================================
# 文件: backend/app/core/config.py
# 功能: 应用统一配置加载。
#      从 .env 读取敏感配置（如数据库连接串、DeepSeek API Key），
#      通过 pydantic-settings 提供类型安全的 Settings 对象。
#      应用启动时调用 settings.validate() 进行 fail-fast 校验。
# ============================================
"""应用配置模块。

提供单例 `settings` 对象。所有需要读取配置的模块都应从此处导入，
避免在业务代码中散落 `os.getenv(...)` 调用。
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置类。

    配置优先级：环境变量 > .env 文件 > 字段默认值。
    """

    # ----- 服务基础配置 -----
    APP_NAME: str = "recording-transcription-service"
    APP_ENV: Literal["dev", "test", "prod"] = "dev"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True

    # ----- 数据库配置 -----
    # 支持两种驱动：
    #   - MySQL: mysql+aiomysql://user:pass@host:3306/dbname
    #   - SQLite: sqlite+aiosqlite:///./data/recording.db（无 Docker 时使用）
    DATABASE_URL: str = Field(default="", description="数据库异步连接串")
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False

    # ----- 文件存储 -----
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_AUDIO_EXTS: tuple[str, ...] = (".wav", ".mp3", ".m4a", ".aac")

    # ----- DeepSeek LLM 配置 -----
    DEEPSEEK_API_KEY: str = Field(default="", description="DeepSeek API Key")
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    LLM_TIMEOUT_SECONDS: int = 60

    # ----- 异步流水线配置 -----
    MAX_CONCURRENT_TASKS: int = 3  # 并发闸：同时处理的最多任务数
    MOCK_TRANSCRIBE_MIN_SEC: int = 5
    MOCK_TRANSCRIBE_MAX_SEC: int = 15
    MOCK_TRANSCRIBE_FAIL_RATE: float = 0.2  # 模拟 ASR 20% 失败率

    # ----- 日志 -----
    LOG_LEVEL: Literal["debug", "info", "warning", "error"] = "info"
    LOG_FILE: str = "./logs/app.log"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    def validate(self) -> None:
        """启动时校验必填配置。

        Raises:
            ValueError: 关键配置缺失或非法。
        """
        # 功能说明：数据库连接串必须配置；根据 scheme 分别校验驱动前缀
        if not self.DATABASE_URL:
            raise ValueError("DATABASE_URL 必须配置，请设置 .env 中的 DATABASE_URL")
        url = self.DATABASE_URL.lower()
        # 功能说明：SQLite 路径（无 Docker 时本地启动用）
        if url.startswith("sqlite"):
            if "+aiosqlite" not in url:
                raise ValueError(
                    "DATABASE_URL 使用 SQLite 时必须搭配 aiosqlite 驱动，"
                    "格式如: sqlite+aiosqlite:///./data/recording.db"
                )
        elif url.startswith("mysql"):
            # 功能说明：MySQL 路径（生产 / Docker 部署用）
            if "+aiomysql" not in url:
                raise ValueError(
                    "DATABASE_URL 使用 MySQL 时必须搭配 aiomysql 异步驱动，"
                    "格式如: mysql+aiomysql://user:pass@host:3306/dbname"
                )
        else:
            raise ValueError(
                "DATABASE_URL 仅支持 sqlite+aiosqlite 或 mysql+aiomysql，"
                f"当前: {self.DATABASE_URL}"
            )
        # 功能说明：DeepSeek API Key 必须配置（即使不实现 LLM 也要占位）
        if not self.DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY 必须配置，请到 https://platform.deepseek.com/ 申请")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """获取缓存的 Settings 单例。

    使用 lru_cache 保证全应用只构造一次配置对象。
    """
    settings = Settings()
    # 功能说明：应用启动时立即进行 fail-fast 校验，提前暴露配置问题
    settings.validate()
    return settings


# 全局快捷访问
settings: Settings = get_settings()
