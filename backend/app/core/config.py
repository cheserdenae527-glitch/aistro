"""应用配置 — 基于 pydantic-settings 从环境变量读取。"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- 应用 ---
    APP_NAME: str = "AiRestro API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # --- 数据库 ---
    DATABASE_URL: str = (
        "postgresql+asyncpg://aistro:aistro@localhost:5432/aistro"
    )

    # --- JWT ---
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24h

    # --- CORS ---
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- MinIO (S3) ---
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "aistro"

    # --- AI：DeepSeek LLM + 豆包生图 ---
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    VOLCENGINE_API_KEY: str = ""
    VOLCENGINE_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    VOLCENGINE_IMAGE_MODEL: str = "doubao-seedream-5-0-260128"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()











