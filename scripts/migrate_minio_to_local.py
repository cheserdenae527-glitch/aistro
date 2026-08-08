"""一次性迁移脚本：把旧 MinIO 数据拷贝到本地文件存储。

用法（在仓库根目录）：
    python scripts/migrate_minio_to_local.py

要求：本机仍能连上旧 MinIO（Docker 容器或原服务），凭据读取 backend/.env 的
MINIO_*，目标目录读取 LOCAL_STORAGE_DIR（默认 <仓库根>/data/storage）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def _load_env() -> None:
    env_file = ROOT / "backend" / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    _load_env()
    from minio import Minio

    endpoint = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
    access = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
    secret = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
    bucket = os.environ.get("MINIO_BUCKET", "aistro")
    dest = Path(
        os.environ.get("LOCAL_STORAGE_DIR", str(ROOT / "data" / "storage"))
    ).resolve()

    client = Minio(endpoint, access_key=access, secret_key=secret, secure=False)
    if not client.bucket_exists(bucket):
        print(f"bucket {bucket} 不存在，无需迁移")
        return

    count = 0
    total_bytes = 0
    for obj in client.list_objects(bucket, recursive=True):
        target = (dest / obj.object_name).resolve()
        if not target.is_relative_to(dest):
            print(f"跳过非法对象名: {obj.object_name}")
            continue
        if target.exists():
            print(f"已存在，跳过: {obj.object_name}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            resp = client.get_object(bucket, obj.object_name)
            with target.open("wb") as f:
                for chunk in resp.stream(1024 * 1024):
                    f.write(chunk)
            resp.close()
            resp.release_conn()
            count += 1
            total_bytes += obj.size
            print(f"迁移: {obj.object_name} ({obj.size} B)")
        except Exception as exc:  # noqa: BLE001
            print(f"迁移失败: {obj.object_name}: {exc}")
    print(f"完成：迁移 {count} 个对象，共 {total_bytes / 1024 / 1024:.1f} MB -> {dest}")


if __name__ == "__main__":
    main()