"""运行时设置 — 持久化到 data/settings.json，保存后实时生效。

不依赖数据库，本地内部工具专用：文件存明文密钥（本机私有），GET 接口做脱敏展示。
"""
from __future__ import annotations

import json
from pathlib import Path

from app.core.config import settings

SETTINGS_FILE = Path(__file__).resolve().parents[3] / "data" / "settings.json"

# 运行时 key -> 启动配置属性名
_CONFIG_MAP = {
    "deepseek_api_key": "DEEPSEEK_API_KEY",
    "deepseek_base_url": "DEEPSEEK_BASE_URL",
    "deepseek_model": "DEEPSEEK_MODEL",
    "volcengine_api_key": "VOLCENGINE_API_KEY",
    "volcengine_base_url": "VOLCENGINE_BASE_URL",
    "volcengine_image_model": "VOLCENGINE_IMAGE_MODEL",
    "volcengine_vision_model": "VOLCENGINE_VISION_MODEL",
    "video_api_key": "VIDEO_API_KEY",
    "video_api_base_url": "VIDEO_API_BASE_URL",
    "video_api_model": "VIDEO_API_MODEL",
}

_cache: dict | None = None


def _env_seed() -> dict:
    """把 .env / 启动配置里已有的值作为初始种子，避免重复填写。"""
    return {
        "deepseek_api_key": settings.DEEPSEEK_API_KEY,
        "deepseek_base_url": settings.DEEPSEEK_BASE_URL,
        "deepseek_model": settings.DEEPSEEK_MODEL,
        "volcengine_api_key": settings.VOLCENGINE_API_KEY,
        "volcengine_base_url": settings.VOLCENGINE_BASE_URL,
        "volcengine_image_model": settings.VOLCENGINE_IMAGE_MODEL,
        "volcengine_vision_model": settings.VOLCENGINE_VISION_MODEL,
        "video_api_key": settings.VIDEO_API_KEY,
        "video_api_base_url": settings.VIDEO_API_BASE_URL,
        "video_api_model": settings.VIDEO_API_MODEL,
        "storage_dirs": [],
    }


def get() -> dict:
    global _cache
    if _cache is None:
        data = _env_seed()
        if SETTINGS_FILE.exists():
            try:
                data.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass
        _cache = data
    return _cache


def save(patch: dict) -> dict:
    data = get()
    if "storage_dir" in patch:
        raw = (patch.get("storage_dir") or "").strip()
        if not raw:
            new_dir = _env_seed()["storage_dirs"][0] if _env_seed()["storage_dirs"] else settings.LOCAL_STORAGE_DIR
        else:
            new_dir = str(Path(raw).expanduser().resolve())
        dirs = list(data.get("storage_dirs") or [])
        current = settings.LOCAL_STORAGE_DIR
        if current and current not in dirs:
            dirs.insert(0, current)
        if new_dir and new_dir not in dirs:
            dirs.insert(0, new_dir)
        data["storage_dirs"] = dirs
        if new_dir:
            settings.LOCAL_STORAGE_DIR = new_dir
    for key, value in patch.items():
        if key in _CONFIG_MAP and value is not None:
            data[key] = value
    _apply_to_live()
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data


def _apply_to_live() -> None:
    data = get()
    for key, attr in _CONFIG_MAP.items():
        setattr(settings, attr, data.get(key, ""))
    dirs = data.get("storage_dirs") or []
    if dirs:
        settings.LOCAL_STORAGE_DIR = dirs[0]
    # 重置模块级缓存的 AI 客户端，使新密钥立即生效
    try:
        from app.ai import design_prompt

        design_prompt._client = None
    except Exception:  # noqa: BLE001
        pass


def reset() -> None:
    """清空进程内缓存（测试用）。"""
    global _cache
    _cache = None