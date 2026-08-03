# Topic Pulse V2

Topic Pulse V2 是一个用于热点新闻话题追踪的 Agent 项目脚手架。

## Core Modules

```text
src/topic_pulse_v2/
  llm_call/        # 大模型调用模块
  tool_register/   # 工具注册与 LLM tool schema 导出
  tool_call/       # 本地工具执行
  memory/          # 记忆存储与查询
  session/         # 会话状态管理
  process/         # Agent 业务流程，包含 ReAct loop
  trace.py         # JSONL 调用观测日志

src/topic_pulse_v2_chat/
  web/             # 面向用户交互的 Web 后端与前端
```

## Install Dependencies

```powershell
pip install -r requirements.txt
```

## Run Tests

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests
```

## Run Web Backend

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python -m uvicorn topic_pulse_v2_chat.web:app --host 127.0.0.1 --port 8000 --reload
```
