 # AiRestro 🍜
 
 餐饮商家 AI 运营工作台 — 面向中小餐饮商家代运营服务商的一站式 SaaS 平台。
 
 ## 项目结构
 
 ```
 docs/    设计文档（SPEC.md）
 backend/   FastAPI 后端
 frontend/  React 前端
 ```
 ## 快速开始（本地内部工具模式，不需要 Docker）
 
 前置：本机已安装并运行 PostgreSQL（默认 localhost:5432，账号/密码见 backend/.env）。
 
 1. 安装后端依赖：`cd backend && pip install -r requirements.txt`
 2. 安装前端依赖：`cd frontend && npm install`
 3. 启动：仓库根目录执行 `python start_services.py`
 4. 打开 http://localhost:3000（前端）与 http://localhost:8000/docs（后端）
 
 如果之前用 MinIO 存过图片/视频，先迁移旧数据：`python scripts/migrate_minio_to_local.py` 
 ## 开发流程
 
 1. 主分支 main — 稳定版本
 2. 开发分支 dev — 日常开发
 3. 功能分支 feature/xxx — 具体功能实现
 
 详见 [docs/SPEC.md](docs/SPEC.md)
