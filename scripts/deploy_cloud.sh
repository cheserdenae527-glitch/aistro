#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> 1/4 生成随机密钥"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-$(openssl rand -hex 16)}"
REDIS_PASSWORD="${REDIS_PASSWORD:-$(openssl rand -hex 16)}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-aistro-$(openssl rand -hex 4)}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-$(openssl rand -hex 24)}"
SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 32)}"

echo "==> 2/4 写入根目录 .env"
if [[ ! -f .env ]]; then
  cat > .env <<EOF
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
REDIS_PASSWORD=${REDIS_PASSWORD}
MINIO_ACCESS_KEY=${MINIO_ACCESS_KEY}
MINIO_SECRET_KEY=${MINIO_SECRET_KEY}
EOF
fi

echo "==> 3/4 写入 backend/.env"
if [[ ! -f backend/.env ]]; then
  cp backend/.env.example backend/.env
  sed -i "s/CHANGE_ME_STRONG_SECRET_KEY/${SECRET_KEY}/" backend/.env
  sed -i "s/CHANGE_ME_POSTGRES_PASSWORD/${POSTGRES_PASSWORD}/" backend/.env
  sed -i "s/CHANGE_ME_REDIS_PASSWORD/${REDIS_PASSWORD}/" backend/.env
  sed -i "s/CHANGE_ME_MINIO_ACCESS_KEY/${MINIO_ACCESS_KEY}/" backend/.env
  sed -i "s/CHANGE_ME_MINIO_SECRET_KEY/${MINIO_SECRET_KEY}/" backend/.env
fi

echo "==> 4/4 启动服务"
docker compose config --quiet
docker compose up -d --build
docker compose ps

echo ""
echo "部署完成。"
echo "如果 AI 功能需要调用火山引擎/DeepSeek，请编辑 backend/.env 里的 VOLCENGINE_API_KEY 和 DEEPSEEK_API_KEY，然后执行："
echo "  docker compose up -d"
