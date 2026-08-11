"""应用配置 — 基于 pydantic-settings 从环境变量读取。"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
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

    # --- 本地文件存储（不装 Docker 后替代 MinIO） ---
    # 媒体文件根目录，默认 <仓库根>/data/storage
    LOCAL_STORAGE_DIR: str = Field(
        default_factory=lambda: str(
            Path(__file__).resolve().parents[3] / "data" / "storage"
        )
    )
    # 生成给前端/本地引擎的媒体 URL 前缀（后端自身地址）
    PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"

    # --- 本地内部工具：本机免登录 ---
    LOCAL_AUTO_LOGIN: bool = True
    LOCAL_ADMIN_EMAIL: str = "local@aistro.local"
    LOCAL_ADMIN_NAME: str = "本地管理员"

    # --- 视频 API（设置页可配置，预留） ---
    VIDEO_API_KEY: str = ""
    VIDEO_API_BASE_URL: str = ""
    VIDEO_API_MODEL: str = ""

    # --- AI：DeepSeek LLM + 豆包生图 ---
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    VOLCENGINE_API_KEY: str = ""
    VOLCENGINE_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    VOLCENGINE_IMAGE_MODEL: str = "doubao-seedream-5-0-260128"
    VOLCENGINE_VISION_MODEL: str = "doubao-seed-2-1-pro-260628"

    # --- 本地数字人引擎（形象同步 / 自动重启用；留空则不自动重启引擎） ---
    LIVE_ENGINE_WORKDIR: str = ""
    LIVE_ENGINE_VENV: str = ""

    # --- 高德地图 MCP ---
    # 高德开放平台 Web 服务 Key：https://lbs.amap.com/
    AMAP_MAPS_API_KEY: str = ""
    # MCP 服务地址。留空时默认走高德官方 Streamable HTTP：
    #   https://mcp.amap.com/mcp?key=<AMAP_MAPS_API_KEY>
    # 也可填 ModelScope MCP 广场生成的 SSE 地址，例如：
    #   https://mcp.api-inference.modelscope.net/<your-id>/sse
    AMAP_MCP_URL: str = ""
    # 可选：连接 ModelScope 等代理时需要的鉴权 Token（如 MODELSCOPE_API_KEY）
    AMAP_MCP_AUTH_TOKEN: str = ""

    # --- 高德 Web API（商圈分析产品功能） ---
    AMAP_WEB_API_KEY: str = ""
    AMAP_JS_KEY: str = ""
    AMAP_SECURITY_JS_CODE: str = ""
    # 账号级日配额熔断阈值（默认 8000 次/日，按 Asia/Shanghai 自然日）
    AMAP_DAILY_QUOTA_LIMIT: int = 8000

    # --- 站大爷隧道代理（小红书爬虫） ---
    XHS_TUNNEL_USERNAME: str = ""
    XHS_TUNNEL_PASSWORD: str = ""
    XHS_TUNNEL_HOST: str = ""
    XHS_TUNNEL_HTTP_PORT: str = ""
    XHS_TUNNEL_BACKUP_HOST: str = ""
    XHS_TUNNEL_BACKUP_HTTP_PORT: str = ""
    XHS_TUNNEL_PERIOD: str = "60"
    XHS_TUNNEL_POOL: str = "enh"
    XHS_TUNNEL_REGION: str = ""
    XHS_TUNNEL_SID: str = ""

    # --- JustOneAPI（小红书蒲公英平台历史涨粉数据） ---
    # Token 在 JustOneAPI 控制台获取；留空时分析任务自动回退到本地订阅快照
    JUST_ONE_API_TOKEN: str = ""
    JUST_ONE_API_BASE_URL: str = "https://api.justoneapi.com"
    # 平台接口官方建议超时 60~120 秒，这里默认 60 秒
    JUST_ONE_API_TIMEOUT_SECONDS: int = 60

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()












