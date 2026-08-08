"""文件存储服务 — 本地文件系统实现（替代 MinIO，不依赖 Docker）。

对外接口保持与原 MinIO 封装一致：
- upload_bytes / upload_fileobj 返回 object_name（如 "profiles/<hex>"）
- get_presigned_url / safe_get_presigned_url 返回后端媒体 URL
- get_object_bytes / delete_object / safe_delete_object 读写本地文件
- local_path 返回本地绝对路径，供数字人引擎等本地程序直接使用

保存位置可通过设置页修改；历史目录保留，读取时按"当前目录 -> 历史目录"查找。
历史 MinIO 数据迁移：python scripts/migrate_minio_to_local.py
"""
from __future__ import annotations

import uuid
from pathlib import Path

from app.core.config import settings
from app.services import runtime_settings


def _storage_roots() -> list[Path]:
    roots: list[Path] = []
    current = Path(settings.LOCAL_STORAGE_DIR).expanduser().resolve()
    roots.append(current)
    for raw in (runtime_settings.get().get("storage_dirs") or []):
        p = Path(str(raw)).expanduser().resolve()
        if p not in roots:
            roots.append(p)
    roots[0].mkdir(parents=True, exist_ok=True)
    return roots


def _normalize(object_name: str) -> str:
    name = object_name.replace("\\", "/").strip("/")
    if not name or ".." in name.split("/"):
        raise ValueError("invalid object name")
    return name


def write_path(object_name: str) -> Path:
    """新文件写入路径（当前保存目录）。"""
    name = _normalize(object_name)
    root = _storage_roots()[0]
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        raise ValueError("invalid object name")
    return path


def find_path(object_name: str) -> Path:
    """查找已有文件：当前目录优先，其次历史目录；找不到时返回当前目录路径。"""
    name = _normalize(object_name)
    for root in _storage_roots():
        path = (root / name).resolve()
        if path.is_relative_to(root) and path.is_file():
            return path
    return write_path(object_name)


def resolve_object(object_name: str) -> Path:
    """读取场景使用：返回实际存在的文件路径（不存在时返回当前目录路径，由调用方报 404）。"""
    return find_path(object_name)


def upload_bytes(data: bytes, content_type: str, folder: str = "profiles") -> str:
    """上传字节数据到本地存储，返回 object 路径。"""
    object_name = f"{folder}/{uuid.uuid4().hex}"
    path = write_path(object_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return object_name


def upload_fileobj(fileobj, content_type: str, folder: str = "live_avatars") -> str:
    """流式上传文件对象到本地存储，避免整文件读入内存。"""
    object_name = f"{folder}/{uuid.uuid4().hex}"
    path = write_path(object_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    fileobj.seek(0)
    with path.open("wb") as out:
        while True:
            chunk = fileobj.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    return object_name


def get_presigned_url(object_name: str, expires: int = 3600) -> str:
    """返回后端媒体 URL（本地文件无需签名，expires 参数保留兼容）。"""
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/api/v1/media/{object_name}"


def safe_get_presigned_url(object_name: str, expires: int = 3600) -> str | None:
    """读取历史图片 URL，文件不存在时降级为 None 而不是报错。"""
    if not object_name:
        return None
    try:
        path = find_path(object_name)
    except ValueError:
        return None
    if not path.is_file():
        return None
    return get_presigned_url(object_name, expires)


def safe_delete_object(object_name: str) -> None:
    """尽力删除对象，失败或不存在时静默跳过，不影响业务。"""
    if not object_name:
        return
    try:
        path = find_path(object_name)
    except ValueError:
        return
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def get_object_bytes(object_name: str) -> bytes:
    """读取对象字节内容。"""
    return find_path(object_name).read_bytes()


def delete_object(object_name: str) -> None:
    """删除本地对象（不存在时静默忽略）。"""
    try:
        path = find_path(object_name)
        if path.is_file():
            path.unlink()
    except (ValueError, OSError):
        pass


def local_path(object_name: str) -> Path:
    """返回本地绝对路径（供数字人引擎等本地程序直接使用）。"""
    return find_path(object_name)