# Docker Deployment

Docker 镜像采用前后端一体部署：构建阶段先用 Node 执行 `npm run build` 生成 React 静态资源，再把 `frontend/dist` 复制进 Python 镜像。运行时只启动一个 FastAPI/Uvicorn 服务，FastAPI 会自动托管前端页面、`/assets` 静态资源和 `/api` 后端接口。

## 1. Prepare Environment

复制生产环境变量模板：

```powershell
Copy-Item .env.production.example .env.production
```

按需填写：

```env
MINIMAX_API_KEY=
DOUBAO_SEARCH_API_KEY=
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_FROM_NAME=Topic Pulse
SMTP_USE_TLS=false
SMTP_USE_SSL=true
```

真实的 `.env.production` 会被 `.gitignore` 忽略，不会提交到仓库。

## 2. Prepare Docker Network

`docker-compose.yml` 默认要求加入一个外部网络，供独立启动的 nginx / phddns-nginx 容器反向代理访问：

```powershell
docker network create nginx-proxy
```

如果你的反向代理网络不是 `nginx-proxy`，启动前设置：

```powershell
$env:DOCKER_PROXY_NETWORK="你的网络名"
```

## 3. Build And Start

在项目根目录执行：

```powershell
docker compose build
docker compose up -d
```

默认镜像名：

```text
topic-pulse-v2:local
```

访问：

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/api/health
```

常用命令：

```powershell
docker compose ps
docker compose logs -f topic-pulse-v2
docker compose restart topic-pulse-v2
docker compose down
```

## 4. Runtime Data

容器内统一使用：

```text
/app/data
```

并通过 compose 映射到项目目录：

```yaml
volumes:
  - ./data:/app/data
```

所以 Docker 运行期数据会保存在：

```text
data/topic_pulse.sqlite3
data/topics/
data/session/
data/logs/
```

迁移或备份时保留 `data/` 即可。

## 5. Image Sources

为了减少 Docker Hub 拉取失败，`Dockerfile` 默认使用镜像代理：

```text
docker.m.daocloud.io/library/node:22-bookworm
docker.m.daocloud.io/library/python:3.10-slim
```

如果你的环境可以直接访问 Docker Hub，可临时切回官方镜像：

```powershell
$env:NODE_IMAGE="node:22-bookworm"
$env:PYTHON_IMAGE="python:3.10-slim"
docker compose build
```

## 6. Reverse Proxy

当 nginx 容器和 `topic-pulse-v2` 容器加入同一个 Docker network 后，nginx 可以直接反向代理到：

```text
http://topic-pulse-v2:8000
```

建议 nginx 将整站 `/` 转发到该地址，因为当前服务同时提供前端和后端：

```text
/        -> frontend index.html
/assets  -> frontend static assets
/api     -> FastAPI API
```

流式聊天接口需要关闭代理缓冲：

```nginx
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 300s;
```
