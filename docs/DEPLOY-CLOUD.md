# 云主机上线配置

本文档针对单台 Linux 云主机 + Docker Compose 部署。核心原则：所有密码在 `.env` 里生成，不写入代码；防火墙只暴露前端 `3000`。

## 1. 生成强随机值

在服务器或本机执行，生成后保存到安全位置：

```bash
# SECRET_KEY（JWT 签名，建议 64 字节）
openssl rand -hex 32

# 数据库 / Redis / MinIO 密码，建议至少 16 位
openssl rand -base64 18
```

Windows PowerShell 等价命令：

```powershell
[Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(48))
```

## 2. 配置仓库根目录 `.env`

Compose 里的 Postgres、Redis、MinIO 会从仓库根目录 `.env` 读取这些变量：

```dotenv
POSTGRES_PASSWORD=上面生成的数据库密码
REDIS_PASSWORD=上面生成的Redis密码
MINIO_ACCESS_KEY=上面生成的MinIO用户名
MINIO_SECRET_KEY=上面生成的MinIO密码
```

执行前确认：

```bash
docker compose config --quiet
```

不要把这个文件提交进 Git。

## 3. 配置 `backend/.env`

Docker 后端容器会读取这个文件，至少覆盖这些值：

```dotenv
DEBUG=false
SECRET_KEY=第 1 步生成的 JWT 密钥
DATABASE_URL=postgresql+asyncpg://aistro:POSTGRES_PASSWORD@127.0.0.1:5433/aistro
REDIS_URL=redis://:REDIS_PASSWORD@127.0.0.1:6379/0
MINIO_ACCESS_KEY=与根目录 .env 一致
MINIO_SECRET_KEY=与根目录 .env 一致
MINIO_BUCKET=aistro
VOLCENGINE_API_KEY=火山引擎真实 Key
DEEPSEEK_API_KEY=DeepSeek 真实 Key
```

注意：

- `POSTGRES_PASSWORD`、`REDIS_PASSWORD` 要和根目录 `.env` 完全一致。
- 容器内实际连接串由 `docker-compose.yml` 覆盖为 `postgres` / `redis` 服务名，`backend/.env` 里的 `DATABASE_URL` / `REDIS_URL` 主要用于本机开发和排查。
- `SECRET_KEY` 必须换成强随机值，不要使用 `change-me-in-production`。

## 4. 构建并启动

```bash
cd /path/to/aistro
cp backend/.env.example backend/.env   # 然后按上一步替换真实值
docker compose up -d --build
```

查看健康状态：

```bash
docker compose ps
docker compose logs -f backend
```

## 5. 防火墙：只开放 3000

Ubuntu 自带 UFW 示例：

```bash
sudo ufw default deny incoming
sudo ufw allow OpenSSH        # 或只允许你的管理 IP：sudo ufw allow from <你的IP> to any port 22
sudo ufw allow 3000/tcp
sudo ufw enable
```

云厂商安全组/防火墙规则只放行：

```text
TCP 3000   -> 公网
TCP 22     -> 仅你的管理 IP（可选）
```

不要放行这些端口：

```text
8000 后端 API
5432 PostgreSQL
6379 Redis
9000 / 9001 MinIO
```

## 6. 上线后验证

查看监听地址，只有 `3000` 应该是 `0.0.0.0` 或 `::`，其余应只监听 `127.0.0.1`：

```bash
ss -tlnp | grep -E ':3000|:8000|:5432|:6379|:9000'
```

从外部访问：

```bash
curl -I http://<云主机公网IP>:3000
```

后端不应从公网访问：

```bash
curl -m 3 http://<云主机公网IP>:8000/ping   # 应超时或拒绝
```

## 7. 额外建议

- 使用云厂商密钥管理服务保存 `.env`，不要放到公开仓库或聊天记录。
- 定期轮换 AI Key 和 Cookie。
- 升级时先备份 `backend/.env` 和根目录 `.env`。


## 阿里云 ECS 安全组配置

如果你的服务器是阿里云 ECS，除了主机防火墙，还要在阿里云控制台的安全组里放行端口。两个地方都要改。

### 控制台操作

1. 登录阿里云控制台，进入 `云服务器 ECS`。
2. 选择 `实例`，找到你的 ECS 实例，点击实例 ID。
3. 进入 `安全组` 页签，点击该安全组的 `管理规则`。
4. 打开 `入方向`，按以下规则配置：

```text
协议    端口范围      授权对象                说明
TCP     3000/3000    0.0.0.0/0 或你的固定IP    前端访问
TCP     22/22        你的管理IP                SSH（建议只放行你的 IP）
```

5. 删除或拒绝任何对以下端口的入方向规则：

```text
8000 后端 API
5432 PostgreSQL
6379 Redis
9000 9001 MinIO
```

6. 如果实例绑定了多块网卡或多个安全组，记得检查所有关联安全组。

### 主机防火墙

阿里云系统镜像默认可能没有启用 UFW，按需执行：

```bash
sudo ufw default deny incoming
sudo ufw allow OpenSSH
sudo ufw allow 3000/tcp
sudo ufw enable
```

如果系统提示 `ufw not found`，先安装：

```bash
sudo apt-get update
sudo apt-get install -y ufw
```

### 阿里云常见坑

- 安全组放行了 `3000`，但实例上如果之前启用了 `firewalld` 或 `iptables`，需要同步放行：
  ```bash
  sudo firewall-cmd --permanent --add-port=3000/tcp
  sudo firewall-cmd --reload
  ```
- 如果使用弹性公网 IP（EIP），安全组规则对 EIP 同样生效。
- 上线后先 `curl http://<公网IP>:3000`，再检查 `curl -m 3 http://<公网IP>:8000/ping` 是否超时。
