# 调度服务模块

`topic_pulse_v2.scheduler` 是内嵌在 FastAPI 后端中的调度服务模块。它负责管理定时任务定义、任务运行记录，以及到点触发任务执行。

当前设计中，APScheduler 只作为进程内的“触发引擎”；任务定义和运行历史由项目自己持久化到全局 SQLite 数据库：

```text
data/topic_pulse.sqlite3
```

不要为调度服务创建独立数据库。

## 目录结构

```text
src/topic_pulse_v2/scheduler/
  __init__.py      调度模块的统一导出入口
  models.py        调度任务和运行记录的数据模型
  registry.py      任务名称到 Python callable 的注册表
  service.py       基于 APScheduler 的 SchedulerService 门面
  store.py         SchedulerStore 接口和 SQLiteSchedulerStore 实现
  tasks.py         内置调度任务，例如 refresh_topic
  README.md        当前设计说明
```

## 核心概念

`ScheduledJob` 表示一条持久化的任务定义。

它记录：

```text
任务 ID
任务名称
触发器类型
触发器参数
任务参数
任务状态
任务元数据
创建时间
更新时间
```

`JobRun` 表示一次任务执行记录。

无论任务是被定时触发，还是被用户手动触发，都会写入一条运行记录。记录内容包括：

```text
运行 ID
任务 ID
任务名称
运行状态
开始时间
结束时间
耗时
错误信息
结果摘要
运行元数据
```

`ScheduledTaskRegistry` 是内存中的任务注册表。

它负责把字符串任务名映射到真正可执行的 Python 函数。例如：

```text
refresh_topic -> refresh_topic(...)
cleanup_trace_logs -> cleanup_trace_logs(...)
```

`SchedulerService` 是调度服务的主入口。

它负责：

```text
初始化存储
加载 active 状态的任务
启动 APScheduler
新增任务
暂停任务
恢复任务
手动运行任务
记录运行历史
关闭调度服务
```

`SQLiteSchedulerStore` 是调度模块当前的持久化实现。

它实现了 `SchedulerStore` 接口，并把调度数据写入全局 SQLite 数据库。

## FastAPI 启动链路

调度服务通过 FastAPI lifespan 接入。

整体启动链路如下：

```text
create_app()
  -> app.state.chat_runtime = chat_runtime or ReactChatService()
  -> lifespan startup
  -> _create_scheduler_service(app.state.chat_runtime)
  -> register_builtin_tasks(registry, chat_runtime=app.state.chat_runtime)
  -> SchedulerService.start()
  -> SQLiteSchedulerStore.initialize()
  -> 从 topic_pulse.sqlite3 读取 active 状态的 ScheduledJob
  -> APScheduler.add_job(...) 注册到调度引擎
  -> APScheduler.start()
```

这里需要区分两类“注册”：

```text
任务函数注册：把 refresh_topic 这样的 Python 函数注册到 ScheduledTaskRegistry
任务实例注册：把数据库中的 ScheduledJob 注册到 APScheduler，等待到点触发
```

任务函数注册发生在 `_create_scheduler_service(...)` 中：

```text
_create_scheduler_service(chat_runtime)
  -> registry = ScheduledTaskRegistry()
  -> register_builtin_tasks(registry, chat_runtime=chat_runtime)
```

任务实例注册发生在 `SchedulerService.start()` 中：

```text
SchedulerService.start()
  -> store.list_jobs()
  -> 找到 status == "active" 的任务
  -> _schedule_job(job)
  -> APScheduler.add_job(...)
```

## chat_runtime 的注入方式

`refresh_topic` 采用方案 A：复用现有的 `ReactChatService.chat()`。

`chat_runtime` 不是 `SchedulerService` 的字段，而是在注册任务函数时通过闭包捕获。

链路如下：

```text
create_app(chat_runtime)
  -> app.state.chat_runtime = chat_runtime or ReactChatService()
  -> _create_scheduler_service(app.state.chat_runtime)
  -> register_builtin_tasks(registry, chat_runtime=app.state.chat_runtime)
  -> registry.register("refresh_topic", lambda ...)
  -> lambda 闭包捕获 chat_runtime
  -> refresh_topic(..., chat_runtime=chat_runtime)
```

因此，数据库中的任务定义只需要保存：

```text
task_name = "refresh_topic"
kwargs = {"topic_name": "..."}
```

真正执行时，注册表中的 callable 会自动带上启动时捕获的 `chat_runtime`。

## 创建话题刷新任务

当前通过 Web API 为某个已关注话题创建定时刷新任务：

```text
POST /api/topics/{topic_id}/schedule
```

接口执行流程：

1. 根据 `topic_id` 定位 `data/topics/{topic_id}.md`。
2. 校验话题 Markdown 文件是否存在。
3. 查询已有任务，判断该话题是否已经有刷新任务。
4. 如果已存在，直接返回已有任务。
5. 如果不存在，创建新的 `ScheduledJob`。
6. 写入 SQLite 的 `scheduled_jobs` 表。
7. 如果调度服务已经启动且任务状态为 `active`，同步注册到 APScheduler。

为了保证“一个话题只有一个刷新任务”，任务通过 metadata 标识话题：

```json
{
  "type": "topic_refresh",
  "topic_id": "..."
}
```

创建出来的任务大致结构是：

```text
task_name = "refresh_topic"
kwargs = {"topic_name": topic.title}
metadata.type = "topic_refresh"
metadata.topic_id = topic.id
metadata.topic_title = topic.title
```

## 任务何时发生调度

任务执行有两条路径。

第一条是定时触发：

```text
APScheduler 到达触发时间
  -> SchedulerService._run_job(job)
```

第二条是手动触发：

```text
POST /api/scheduler/jobs/{job_id}/run
  -> SchedulerService.run_job_now(job_id)
  -> SchedulerService._run_job(job)
```

无论是定时触发还是手动触发，最终都会进入同一个 `_run_job(...)`。

## 任务执行链路

`SchedulerService._run_job(job)` 是统一执行入口。

执行过程：

```text
_run_job(job)
  -> 创建 JobRun(status="running")
  -> 写入 job_runs
  -> registry.get(job.task_name)
  -> task.handler(*job.args, **job.kwargs)
  -> 成功：JobRun(status="success", result_summary=...)
  -> 失败：JobRun(status="failed", error=...)
  -> 更新 job_runs
```

对于 `refresh_topic`，实际执行链路是：

```text
refresh_topic(topic_name)
  -> chat_runtime.chat(...)
  -> Agent 读取本地话题记忆
  -> Agent 搜索最新互联网信息
  -> Agent 去重、合并、写回 Markdown
  -> refresh_topic 提取 topic_update
  -> 返回结构化结果
```

调度任务模拟的用户输入大致是：

```text
请更新一下「某话题」这个已关注话题的最新动态，必须结合本地已有话题记忆和最新互联网信息，去重后写回本地 Markdown 话题记忆。
```

`refresh_topic` 会从 Agent 返回结果中提取：

```text
topic_name
new_count
existing_count
update_status
session_id
summary
```

这些内容会被 `SchedulerService._run_job(...)` 序列化后写入 `job_runs.result_summary`。

## 当前调度 API

```text
GET  /api/scheduler/jobs
POST /api/topics/{topic_id}/schedule
GET  /api/topics/{topic_id}/schedule
POST /api/scheduler/jobs/{job_id}/pause
POST /api/scheduler/jobs/{job_id}/resume
POST /api/scheduler/jobs/{job_id}/run
GET  /api/scheduler/jobs/{job_id}/runs
```

## 数据表

`scheduled_jobs` 保存任务定义。

主要字段：

```text
id
task_name
trigger
trigger_args
args
kwargs
status
name
description
metadata
created_at
updated_at
```

`job_runs` 保存运行历史。

主要字段：

```text
id
job_id
task_name
status
started_at
finished_at
duration_ms
error
result_summary
metadata
```

## 关闭链路

FastAPI 关闭时，会通过 lifespan 关闭调度服务：

```text
lifespan shutdown
  -> SchedulerService.shutdown(wait=False)
  -> APScheduler.shutdown(...)
  -> SQLiteSchedulerStore.close()
  -> SQLiteDatabase.close()
```

这样可以释放调度服务和 API 共享的 SQLite 连接。
