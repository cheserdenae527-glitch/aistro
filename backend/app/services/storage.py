"""文件存储服务 — MinIO 客户端封装。"""
from __future__ import annotations

import io
import time
import uuid
from datetime import timedelta

import minio
import urllib3
from minio import Minio

from app.core.config import settings

_client: Minio | None = None
_storage_ok: bool | None = None
_storage_checked_at: float = 0.0
_STORAGE_CHECK_TTL = 5.0


def _get_client() -> Minio:
    global _client
    if _client is None:
        # MinIO 未启动时快速失败，避免每个请求等 30 秒超时重试。
        http_client = urllib3.PoolManager(
            retries=0,
            timeout=urllib3.Timeout(connect=0.5, read=2.0),
        )
        _client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=False,
            http_client=http_client,
        )
        # 确保 bucket 存在
        if not _client.bucket_exists(settings.MINIO_BUCKET):
            _client.make_bucket(settings.MINIO_BUCKET)
    return _client


def _storage_available() -> bool:
    """短周期探测 MinIO 可用性，避免每个图片 URL 都等一次连接超时。"""
    global _storage_ok, _storage_checked_at
    now = time.monotonic()
    if _storage_ok is not None and now - _storage_checked_at < _STORAGE_CHECK_TTL:
        return _storage_ok

    try:
        _get_client().bucket_exists(settings.MINIO_BUCKET)
        _storage_ok = True
    except Exception:
        _storage_ok = False
    _storage_checked_at = now
    return _storage_ok


def upload_bytes(data: bytes, content_type: str, folder: str = "profiles") -> str:
    """上传字节数据到 MinIO，返回 object 路径。"""
    client = _get_client()
    object_name = f"{folder}/{uuid.uuid4().hex}"
    client.put_object(
        settings.MINIO_BUCKET,
        object_name,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return object_name


def get_presigned_url(object_name: str, expires: int = 3600) -> str:
    """生成预签名下载 URL（1 小时有效期）。"""
    client = _get_client()
    return client.presigned_get_object(
        settings.MINIO_BUCKET, object_name, expires=timedelta(seconds=expires)
    )


def safe_get_presigned_url(object_name: str, expires: int = 3600) -> str | None:
    """读取历史图片 URL，MinIO 不可用时降级为 None 而不是阻塞请求。"""
    if not _storage_available():
        return None
    try:
        return get_presigned_url(object_name, expires)
    except Exception:
        return None


def get_object_bytes(object_name: str) -> bytes:
    """读取对象字节内容。"""
    client = _get_client()
    response = client.get_object(settings.MINIO_BUCKET, object_name)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def delete_object(object_name: str) -> None:
    """删除 MinIO 对象（不存在时静默忽略）。"""
    try:
        client = _get_client()
        client.remove_object(settings.MINIO_BUCKET, object_name)
    except Exception:
        pass
