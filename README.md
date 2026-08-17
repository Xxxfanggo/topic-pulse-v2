<p align="center">
  <h1 align="center">⚡ Topic Pulse V2</h1>
</p>

<p align="center">
  <strong>面向热点新闻与长期关注话题的 local-first Agent Runtime</strong>
</p>

<p align="center">
  <a href="https://github.com/zhangxiaoxiao9527/topic-pulse-v2/stargazers">
    <img alt="GitHub stars" src="https://img.shields.io/github/stars/zhangxiaoxiao9527/topic-pulse-v2?style=flat-square">
  </a>
  <img alt="Version" src="https://img.shields.io/badge/version-0.1.0-111827?style=flat-square">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=flat-square&logo=fastapi&logoColor=white">
  <img alt="React" src="https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=111827">
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a>
  ·
  <a href="#architecture">Architecture</a>
  ·
  <a href="#developer-guide">Developer Guide</a>
  ·
  <a href="#project-layout">Project Layout</a>
</p>

Topic Pulse V2 不是一个一次性搜索脚本，也不是一个普通聊天机器人。它是一套围绕“热点信息持续追踪”设计的 Agent 工程骨架：把联网搜索、多轮会话、本地 Markdown 记忆、后台热点沉淀、工具调用、上下文管理和 JSONL 可观测日志组织成一个可扩展、可调试、可测试的运行时。

当用户只是查询一个普通话题时，Agent 会联网检索并直接返回结构化结果；当用户明确表达“持续关注”“长期跟踪”“记录下来”时，Agent 会把搜索结果沉淀为本地 Markdown 话题记忆，并在后续会话中持续合并更新。

同时，系统内置了一个平台级热点沉淀链路：后端启动时会自动创建微博热搜每小时刷新任务，定时抓取今日热点、归并相似条目、提炼摘要、计算今日热点排行，并在新对话首页展示 Top 10。用户点击某个热点后，热点会回填到聊天输入框，方便继续分析。

## 🖥️ Preview

<p align="center">
  <img src="README/web交互介绍图-1.png" alt="Topic Pulse Web Chat" width="92%">
</p>

<p align="center">
  <img src="README/web交互介绍图-2.png" alt="Topic Pulse Topic Workspace" width="92%">
</p>

<p align="center">
  <img src="README/web交互介绍图-3.png" alt="Topic Pulse Memory Detail" width="92%">
</p>
<p align="center">
  <img src="README/web交互介绍图-4.png" alt="Topic Pulse Memory Detail" width="92%">
</p>

## ✨ Highlights

| Capability | What it means |
| --- | --- |
| ReAct Agent Runtime | 支持模型推理、工具选择、工具观察、最终结构化回答的完整闭环。 |
| Local Tool Registry | 本地 Python 工具自动注册，并导出为 LLM 可调用的 tool schema。 |
| Markdown Topic Memory | 将长期关注话题保存为可读、可审计、可手动维护的 Markdown 时间线。 |
| HotspotAgent Pipeline | 平台级后台 Agent 定时沉淀今日热点，生成小时级观测和日排行。 |
| Weibo Hot Provider | `information_search` 中提供微博热搜 Provider，可继续扩展其他热点源。 |
| Session-managed History | Web / CLI 不维护历史，由 session 层根据 `session_id` 统一读写多轮对话。 |
| Context Trim Boundary | LLM 调用前统一经过 `context_trim`，为后续裁剪、压缩、摘要预留扩展点。 |
| JSONL Observability | LLM 请求、响应、工具参数、工具结果全部写入 trace 文件，方便复盘。 |

## 🚀 Quick Start

### 1. Install

```powershell
git clone https://github.com/zhangxiaoxiao9527/topic-pulse-v2.git
cd topic-pulse-v2
.\.venv\Scripts\python -m pip install -r requirements.txt
```

If you are not using the checked-in virtual environment, create one first:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Start Backend

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python -m uvicorn topic_pulse_v2_chat.web:app --host 127.0.0.1 --port 8000 --reload
```

Health check:

```text
http://127.0.0.1:8000/api/health
```

### 3. Start Frontend

```powershell
cd src/topic_pulse_v2_chat/web/frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173/
```

### 4. Or Use Terminal Chat

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python -m topic_pulse_v2_chat.terminal --user-id user-1
```

Minimal interaction:

```text
你> 查一下内存条最近价格走势
AI> ...

你> 持续关注一下内存条价格走势，看看有没有新变化
AI> ...
```

## 🐳 Docker Deployment

Docker 镜像采用前后端一体部署：构建阶段先用 Node 执行 `npm run build` 生成 React 静态资源，再把 `frontend/dist` 复制进 Python 镜像。运行时只启动一个 FastAPI/Uvicorn 服务，FastAPI 会自动托管前端页面、`/assets` 静态资源和 `/api` 后端接口。

### 1. Prepare Environment

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

### 2. Prepare Docker Network

`docker-compose.yml` 默认要求加入一个外部网络，供独立启动的 nginx / phddns-nginx 容器反向代理访问：

```powershell
docker network create nginx-proxy
```

如果你的反向代理网络不是 `nginx-proxy`，启动前设置：

```powershell
$env:DOCKER_PROXY_NETWORK="你的网络名"
```

### 3. Build And Start

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

### 4. Runtime Data

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

### 5. Image Sources

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

### 6. Reverse Proxy

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

## 🧭 How It Works

Topic Pulse V2 的核心链路很短，但每一层都有清晰边界：

```text
User Input
  -> Web / Terminal
  -> ReActAgent
  -> Session History
  -> Context Trim
  -> LLM
  -> Tool Registry
  -> Local Tools
  -> Markdown Topic Memory
  -> Structured Answer
```

普通查询路径：

```text
用户提问
  -> 判断需要最新信息
  -> doubao_search
  -> 汇总搜索结果
  -> 返回结构化回答
```

长期关注路径：

```text
用户要求持续关注
  -> topic_markdown_read_summary
  -> doubao_search
  -> topic_markdown_read_detail
  -> topic_markdown_store
  -> 返回更新结果
```

平台热点沉淀路径：

```text
FastAPI 启动
  -> 自动确保 refresh_hotspots(provider="weibo") 每小时任务存在
  -> SchedulerService 定时触发
  -> WeiboHotNewsProvider 拉取微博热搜
  -> HotspotAgent 固定 pipeline 清洗、归并、总结、沉淀
  -> SQLite 保存快照、主题、观测、日排行
  -> Web 首页读取 /api/hotspots/today 展示 Top 10
```

## 🏗️ Architecture

<p align="center">
  <img src="README/系统架构图.png" alt="Topic Pulse Architecture" width="92%">
</p>

```text
topic_pulse_v2_chat
  |
  |-- web / terminal
  |
  v
topic_pulse_v2.process.ReActAgent
  |
  |-- llm_call          # model provider abstraction
  |-- tool_register     # local tool discovery and schema export
  |-- tool_call         # tool execution boundary
  |-- session           # state and markdown conversation history
  |-- memory            # lightweight user memory
  |-- context_trim      # context management boundary
  |-- trace.py          # jsonl observability

topic_pulse_v2.process.HotspotAgent
  |
  |-- information_search.hot_news  # hot news providers, currently Weibo
  |-- SQLiteHotspotStore           # snapshots, topics, observations, rankings
  |-- llm_call                     # optional semantic merge and summarization
  |-- scheduler.refresh_hotspots   # hourly background refresh task
```

Design principles:

- **Local-first**：长期话题和会话历史优先落在本地 Markdown。
- **Tool-native**：业务能力以工具形式暴露给模型，而不是隐藏在不可见逻辑中。
- **Interface-oriented**：LLM、Session、Memory、Context Trim 均保留替换边界。
- **Observable by default**：每次模型和工具调用都有 JSONL trace。
- **Testable Agent Flow**：工具选择、响应解析、多轮会话、上下文链路都有测试覆盖。

## 🧩 Core Concepts

### ReActAgent

`ReActAgent` 是主流程编排器，负责构建 prompt、调用上下文管理、请求大模型、解析工具调用、执行工具、写 trace、维护 session history，并最终返回 `ReActResult`。

### HotspotAgent

`HotspotAgent` 是后台固定 pipeline Agent，位于：

```text
src/topic_pulse_v2/process/hotspot_agent.py
```

它不采用开放式 ReAct 工具循环，而是按固定步骤执行：

```text
fetch_hot_news
  -> normalize_items
  -> save_snapshots
  -> load_today_context
  -> llm_merge_and_summarize 或 deterministic fallback
  -> persist_analysis
  -> recalculate_daily_ranking
```

LLM 只负责语义归并和摘要生成；最终数据校验、落库、排序和任务状态由确定性代码完成。如果没有配置 LLM，或 LLM 输出不可解析，流程会走规则 fallback，保证后台任务不会因为模型不可用而中断。

### Hot News Providers

热点外部数据源放在：

```text
src/topic_pulse_v2/information_search/hot_news.py
```

当前内置：

| Provider | Purpose |
| --- | --- |
| `EmptyHotNewsProvider` | 空实现，用于安全占位和测试。 |
| `WeiboHotNewsProvider` | 抓取微博实时热搜页并转换为统一 `HotNewsItem`。 |

Provider 统一输出：

```text
HotNewsItem(title, summary, url, source, rank, heat, category, raw)
```

后续扩展其他热点接口时，实现同样的 `fetch_hot_news()` 边界即可。

### Local Tools

当前核心工具：

| Tool | Purpose |
| --- | --- |
| `doubao_search` | 联网查询任意话题内容。 |
| `topic_markdown_read_summary` | 读取本地话题摘要，判断是否命中已关注话题。 |
| `topic_markdown_read_detail` | 读取某个 Markdown 话题的完整内容。 |
| `topic_markdown_store` | 创建或更新本地话题 Markdown 记忆。 |

热点沉淀暂时不通过聊天工具暴露给 LLM。后台刷新链路由 `HotspotAgent` 直接调用 Provider / Store / LLMClient；Web 首页通过只读 API 获取今日排行。

### Scheduler

调度服务使用 APScheduler 作为进程内触发器，并把任务定义与运行记录持久化到 SQLite。

当前内置任务：

| Task | Purpose |
| --- | --- |
| `refresh_topic` | 定时刷新某个用户已关注 Markdown 话题。 |
| `refresh_hotspots` | 平台级定时刷新今日热点排行。 |

后端启动时会自动确保存在一条默认微博热点任务：

```text
id = hotspot-refresh-weibo-hourly
task_name = refresh_hotspots
trigger = interval
trigger_args = {"hours": 1}
kwargs = {"provider": "weibo"}
metadata.type = hotspot_refresh
metadata.provider = weibo
```

这条任务是平台级共享任务，不属于某个用户。

### Markdown Memory

长期话题存储在：

```text
data/topics/
```

会话历史存储在：

```text
data/session/
```

这种设计让 Agent 的“记忆”既能被程序读取，也能被人直接打开审阅。

### Trace Log

默认 trace 文件：

```text
data/logs/react_trace/YYYY-MM-DD.log
```

热点分析 Agent 的 LLM prompt 日志默认写入：

```text
data/logs/hotspot_agent_trace/YYYY-MM-DD.log
```

你可以用它观察：

- 发给 LLM 的完整 messages
- LLM 返回的原始 content / tool calls
- 工具调用参数
- 工具响应结果
- context trim 元信息
- Agent 完成状态

## 👤 User Guide

### 普通查询

适合一次性了解某个话题：

```text
查一下内存条最近价格走势
```

Agent 应该联网搜索并直接回答，不写入 Markdown 记忆。

### 长期关注

适合将一个具体新闻话题纳入本地记忆：

```text
持续关注一下内存条价格走势，看看有没有新变化
```

Agent 会读取本地话题、联网搜索最新内容，并创建或更新 Markdown 时间线。

### 继续追问

适合多轮会话：

```text
上次关注的内存条价格怎么样了？
```

历史由 session 层维护，Web 和 CLI 只需要持续传递同一个 `session_id`。

### 今日热点排行

新对话首页会读取本地沉淀的今日热点 Top 10：

```text
GET /api/hotspots/today?limit=10
```

热点榜来自后台 `refresh_hotspots` 定时任务，而不是页面临时联网搜索。点击某个热点不会立即发送消息，只会把分析提示填入聊天输入框，用户可以继续修改后再发送。

## 🛠️ Developer Guide

### Run Tests

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python -m unittest discover -s tests
```

### Run Focused Agent Tests

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python -m unittest tests.test_react_response_parser tests.test_react_multi_tool_calls tests.test_react_session_history tests.test_context_trim
```

### Build Frontend

```powershell
cd src/topic_pulse_v2_chat/web/frontend
npm run build
```

### Debug With Terminal

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python -m topic_pulse_v2_chat.terminal --user-id debug-user
```

Terminal 模式适合给 `ReActAgent.run()`、工具执行器、搜索工具、Markdown store 打断点。

## 📁 Project Layout

```text
src/topic_pulse_v2/
  context_trim/          # context assembly, trimming and compression boundary
  information_search/    # web search and hot news provider integrations
  llm_call/              # LLM client and provider abstraction
  memory/                # lightweight user memory
  process/               # ReActAgent, HotspotAgent and business orchestration
  scheduler/             # persisted scheduled jobs and APScheduler facade
  session/               # session state and markdown conversation history
  tool_call/             # tool execution runtime
  tool_register/         # local tool registry and auto-discovery
  trace.py               # jsonl trace logging

src/topic_pulse_v2_chat/
  terminal/              # terminal chat client
  web/                   # FastAPI backend and React frontend

data/topics/             # long-term topic markdown memory
data/session/            # conversation session markdown history
data/topic_pulse.sqlite3 # auth, scheduler, hotspot, topic and session index data
data/logs/react_trace/YYYY-MM-DD.log   # date-partitioned runtime trace log
data/logs/hotspot_agent_trace/YYYY-MM-DD.log # hotspot LLM prompt trace log
tests/                   # unit and flow tests
test_case/               # functional spec and agent test cases
README/                  # README screenshots and architecture images
```

## 🗺️ Roadmap

- Context trim strategies for long-running sessions
- Better topic matching and alias resolution
- Markdown diff, conflict resolution and provenance tracking
- SQLite / PostgreSQL backed session and topic stores
- Dedicated hotspot detail page and cross-source trend visualization
- Topic graph and timeline visualization in Web UI
- More hot news providers beyond Weibo
- More formal Agent evaluation cases

## ⭐ Star History

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=zhangxiaoxiao9527/topic-pulse-v2&type=Date&theme=dark">
  <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=zhangxiaoxiao9527/topic-pulse-v2&type=Date">
  <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=zhangxiaoxiao9527/topic-pulse-v2&type=Date">
</picture>

## 📌 Status

Topic Pulse V2 is under active development. The goal is not to build a universal Agent, but to evolve a precise, observable and durable runtime for turning moving information into local memory.
