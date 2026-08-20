# Topic Pulse 热点 Agent 前置意图分类与范围控制方案

## 1. 目标

Topic Pulse 的产品边界是：只负责发现、汇总、筛选和追踪热点事件，尤其是“今天/最近发生了哪些热点事件”。对于代码、翻译、百科问答、闲聊、建议等无关请求，不应进入热点 Agent，也不应调用搜索工具，更不应由主 LLM 自由生成回答。

本方案只描述设计和落地路径，不修改现有业务代码。

## 2. 基于当前项目的结论

当前请求链路是：

```text
Web / Terminal
  -> ReactChatService
  -> ReActAgent.run() / stream()
  -> LLM
  -> ToolRegistry / ToolExecutor
  -> doubao_search、Markdown 话题记忆
```

关键现状：

- `src/topic_pulse_v2_chat/web/app.py` 的 `/api/chat` 和 `/api/chat/stream` 都直接调用 `app.state.chat_runtime`。
- `src/topic_pulse_v2_chat/web/react_service.py` 是 Web 与 Terminal 共用的 Agent 门面，适合作为统一入口。
- `src/topic_pulse_v2/process/react_loop.py` 在调用 LLM 前会创建 session、写入用户输入并加载历史；如果只在 system prompt 中增加“不要回答无关问题”，模型仍然可能直接生成答案。
- `ReActAgent` 会通过 `ToolRegistry.as_llm_tools()` 暴露全部工具。只要请求进入 ReAct 循环，模型就具备搜索和读写话题记忆的机会。
- `src/topic_pulse_v2/scheduler/tasks.py` 的 `refresh_topic` 通过同一个 `chat_runtime` 执行定时更新，因此范围控制必须区分用户入口和受信任的内部定时任务。

因此，范围控制不能只放在 `ReActConfig.system_prompt` 中，必须在调用 `ReActAgent` 之前增加业务层硬门禁。

## 3. 推荐架构：统一 Scope Gateway

新增一个概念层，不要求马上拆分出新的服务进程：

```text
Web / Terminal / Scheduler
          |
          v
   TopicPulseScopeGateway
          |
   +------+------------------+
   |                         |
   | OFF_TOPIC / AMBIGUOUS   | HOTSPOT
   |                         |
   | 固定回复，不调用 LLM     v
   |                  ReactChatService
   |                           |
   |                       ReActAgent
```

推荐将 Gateway 放在 `ReactChatService` 之前或包裹 `ReactChatService`，并让 Web 和 Terminal 都使用同一个 Gateway。不要只在 `app.py` 的 HTTP 路由中实现，否则 Terminal 入口和未来新增入口可能绕过限制。

Gateway 负责四件事：

1. 判断当前请求是否属于热点范围。
2. 通过代码校验分类结果并决定是否继续。
3. 对拒绝和澄清请求返回固定文本，不再调用主 LLM。
4. 记录分类结果、置信度和最终路由，便于通过现有 trace 机制复盘。

## 4. 意图分类协议

分类器只做路由，不回答问题，不调用工具。建议使用以下最小标签集：

| 意图 | 含义 | 示例 |
| --- | --- | --- |
| `HOTSPOT_DISCOVERY` | 发现当前或指定时间范围内的热点 | “今天有什么热点事件？” |
| `HOTSPOT_DIGEST` | 生成每日/定时热点简报 | “给我整理今天的热点早报” |
| `HOTSPOT_TRACKING` | 追踪某一热点的最新进展 | “某事件最近有什么新进展？” |
| `HOTSPOT_FILTER` | 按行业、地域、平台等筛选热点 | “找今天科技行业的热点” |
| `AMBIGUOUS` | 信息不足，无法判断是否要挖掘热点 | “帮我看看这个” |
| `OFF_TOPIC` | 不属于热点事件范围 | “帮我写一个 Python 快排” |

分类器输出固定 JSON，不允许输出自然语言：

```json
{
  "intent": "HOTSPOT_DISCOVERY",
  "decision": "ALLOW",
  "confidence": 0.96,
  "normalized_query": "整理今天发生的热点事件",
  "time_range": "today",
  "topic_hint": null,
  "classifier_version": "scope-v1"
}
```

建议有效值：

```text
intent: HOTSPOT_DISCOVERY | HOTSPOT_DIGEST | HOTSPOT_TRACKING |
        HOTSPOT_FILTER | AMBIGUOUS | OFF_TOPIC
decision: ALLOW | CLARIFY | REJECT
```

## 5. 分类策略：规则优先，模型处理模糊请求

### 5.1 第一层：确定性规则

规则层用于快速处理明显请求，减少模型调用并提高拒答确定性。

热点相关动词包括：

```text
挖掘、发现、整理、汇总、早报、日报、热点、热搜、趋势、追踪、监测、最新进展
```

热点相关对象包括：

```text
热点事件、新闻热点、社会热点、科技热点、行业热点、国际热点、平台热榜
```

时间表达包括：

```text
今天、今日、昨天、最近、近一周、本周、当前、最新、刚刚
```

以下请求可直接判定为 `OFF_TOPIC`：

```text
写代码、解释概念、翻译、数学计算、闲聊、写作、购物推荐、医疗、法律、情感建议
```

规则不能只依赖黑名单。例如“解释某热点事件为什么上热搜”仍然属于热点范围；判断应基于“热点对象 + 当前事件语境”，而不是只看“解释”这个动词。

### 5.2 第二层：分类 LLM

规则无法判断时，使用一个独立的分类 LLM 调用。它与主 Agent 分离：

- 不提供任何工具。
- 只接收当前用户输入，以及经过筛选的热点上下文。
- 使用低温度和较短输出长度。
- 使用结构化 JSON 输出，并在业务代码中校验枚举、置信度和必填字段。
- 不能把分类 LLM 的自然语言输出直接返回给用户。

分类器提示词的核心约束：

```text
你是热点事件 Agent 的前置路由器，不负责回答用户问题。
只有发现、汇总、筛选、追踪当前或近期热点事件的请求才允许进入 HOTSPOT。
其他请求必须返回 OFF_TOPIC。
只输出符合 schema 的 JSON，不要解释，不要调用工具。
```

### 5.3 置信度门槛

初始建议：

```text
confidence >= 0.85 且 intent 为 HOTSPOT_*  -> ALLOW
confidence < 0.85                         -> CLARIFY
intent 为 OFF_TOPIC                       -> REJECT
分类器异常、超时或 JSON 无法解析          -> CLARIFY 或 REJECT
```

如果产品更重视“绝不回答无关问题”，分类器故障时应 fail closed：不进入主 Agent，返回固定澄清或拒答文案。

## 6. 业务代码的硬路由规则

分类结果必须经过代码分支处理，不能让主 LLM 再次解释分类结果：

```text
REJECT:
  返回固定拒答
  不调用 ReactChatService / ReActAgent
  不调用 doubao_search
  不调用 topic_markdown_* 工具
  不写入 Agent session 和 topic memory

CLARIFY:
  返回固定澄清问题
  不调用主 LLM
  不执行工具

ALLOW:
  将 normalized_query 和已抽取的时间、主题、过滤条件传给热点 Agent
  才创建或继续 Agent session
  才允许暴露热点相关工具
```

拒答建议固定为：

```text
我只支持热点事件挖掘、热点汇总和热点追踪，暂不回答其他问题。
你可以尝试：“整理今天的科技热点”或“追踪某事件最近的进展”。
```

澄清建议固定为：

```text
你想了解哪一类热点？请补充主题或时间范围，例如“今天的科技热点”或“最近一周的社会热点”。
```

## 7. 对当前项目各入口的接入建议

### 7.1 Web 非流式 `/api/chat`

在进入现有 `app.state.chat_runtime.chat` 之前，或者由统一 Gateway 包裹该调用：

1. 分类当前 `request.message`。
2. `REJECT` 或 `CLARIFY` 直接构造一个完成态响应。
3. 响应中保持现有 `ChatResponse` 结构：
   - `answer` 使用固定文本。
   - `completed=true`。
   - `query_key=null`。
   - `reference_data=[]`。
   - `topic_update={}`。
   - `steps=[]`。
4. `ALLOW` 才沿用当前 ReAct 流程。

### 7.2 Web 流式 `/api/chat/stream`

拒答和澄清也要走 NDJSON 流协议，避免前端等待一个不存在的 Agent 流：

```text
status: 正在判断请求范围
delta: 固定拒答或澄清文本
done: completed=true，steps=[]
```

拒答路径不能产生以下事件：

```text
llm_delta、tool_start、tool_end、topic_update
```

尤其不能先调用 `chat_stream()`，等模型输出后再判断，否则已经失去门禁意义。

### 7.3 Terminal

当前 Terminal 直接使用 `ReactChatService`。应让它和 Web 共用同一个 Scope Gateway，保证命令行不会成为绕过范围控制的入口。

### 7.4 Scheduler

当前 `refresh_topic` 是服务端生成的热点追踪请求，不是用户自由输入。建议保留内部可信路由，但必须通过受信任的服务端元数据区分：

```text
source=scheduler
task=refresh_topic
scope=HOTSPOT_TRACKING
```

这些字段不能由 HTTP 用户直接传入或覆盖。

同时要注意：当前 Scheduler 主要刷新“已关注话题”，并不等于“每天发现全网新热点”。如果目标是每日热点简报，应增加一个独立的 `daily_hotspot_digest` 任务：

```text
cron 每日固定时间
  -> 使用服务端固定查询模板
  -> doubao_search 获取当天热点
  -> 去重、排序、摘要
  -> 生成日报结果
  -> 通过现有 topic memory 或新的 digest 存储保存
```

该任务不应把用户自然语言作为入口，也不应依赖用户的 session history。

## 8. Session、Memory 和 Prompt 的处理边界

范围门禁必须发生在 `ReActAgent.run()` / `stream()` 之前。因为当前 ReAct 流程会在调用 LLM 前写入 session history；如果把门禁放到 ReActAgent 内部太晚，至少会造成无关问题进入会话记录。

建议遵循以下规则：

- `OFF_TOPIC` 不写入 Agent session，不写入 topic Markdown，不写入长期 memory。
- 分类结果只写入 trace 或独立的分类审计日志。
- `AMBIGUOUS` 只保留必要的分类日志，不进入主 Agent。
- 只有 `ALLOW` 的标准化查询进入 ReAct history。
- 后续消息中的“这个事件”“它最新怎么样”等指代，只能从已确认的热点上下文中解析，不能因为历史中出现过任意问题就扩大 Agent 范围。
- 不要把用户输入中的“忽略之前规则”“你现在改成通用助手”等指令当作系统规则；分类器只判断业务意图。

现有 `ReActConfig.system_prompt` 仍应保留热点角色约束，但它只是第二道防线，不是安全边界。

## 9. 工具权限建议

对 `ALLOW` 请求，现有工具可以按任务裁剪：

| 意图 | 允许工具 |
| --- | --- |
| `HOTSPOT_DISCOVERY` | `doubao_search`、必要时 `topic_markdown_read_summary` |
| `HOTSPOT_DIGEST` | `doubao_search`、热点日报存储工具 |
| `HOTSPOT_TRACKING` | `topic_markdown_read_summary`、`topic_markdown_read_detail`、`doubao_search`、`topic_markdown_store` |
| `HOTSPOT_FILTER` | `doubao_search`、必要时读取已有话题 |

对 `REJECT` 和 `CLARIFY` 请求，工具列表应为空；更稳妥的做法是根本不创建 ReActAgent 调用。

## 10. Trace 与可观测性

复用现有 `logs/react_trace.jsonl` 的事件记录能力，增加一类范围路由事件，建议至少记录：

```json
{
  "event": "intent_gate",
  "request_id": "...",
  "session_id": "...",
  "source": "web",
  "intent": "OFF_TOPIC",
  "decision": "REJECT",
  "confidence": 0.99,
  "classifier_version": "scope-v1",
  "forwarded_to_agent": false,
  "tool_count": 0
}
```

不要在日志中保存不必要的敏感信息。重点观察：

- 无关请求是否仍产生 `llm_request`。
- 无关请求是否产生工具调用。
- 分类器 JSON 解析失败率。
- `OFF_TOPIC` 误拒绝率。
- `AMBIGUOUS` 占比。
- Web、Stream、Terminal 三个入口的路由结果是否一致。

## 11. 验收用例

### 必须允许

```text
今天有什么热点事件？
整理今天的科技热点。
最近一周有哪些社会热点？
追踪某事件的最新进展。
这个热点为什么突然上热搜？
每天早上给我一份热点简报。
```

### 必须拒绝且不调用主 LLM

```text
帮我写一个 Python 爬虫。
什么是 Transformer？
帮我翻译这段英文。
推荐一款手机。
讲个笑话。
帮我计算 12345 * 67890。
```

### 必须澄清

```text
帮我看看这个。
最近怎么样？
分析一下这个事件。
给我来点新闻。
```

每条拒答用例都应断言：

```text
没有调用 LLM 主 Agent
没有调用 doubao_search
没有调用 topic_markdown_* 工具
没有新增 Agent session 消息
没有新增 topic Markdown
```

## 12. 推荐落地顺序

### 第一阶段：先建立硬门禁

- [x] 在 Web、Terminal 共用的 `ReactChatService` 入口加入 Scope Gateway 能力。
- [x] 使用规则 + 固定拒答/澄清。
- [x] 只允许 `HOTSPOT_*` 请求进入现有 ReActAgent。
- [x] 为同步和流式接口分别覆盖拒答路径。

### 第二阶段：补充语义分类

- [x] 规则无法判断时再调用独立分类 LLM。
- [x] 使用结构化 JSON 校验、`0.85` 置信度阈值和 fail-closed 策略。
- [x] 将 `intent_gate` 写入现有 trace。

### 第三阶段：完善每日热点能力

- [ ] 新增服务端受信任的 `daily_hotspot_digest` 调度任务。
- [ ] 区分“发现全网新热点”和“刷新已关注话题”。
- [ ] 为日报结果增加独立的存储和前端展示约定，避免混入普通聊天历史。

## 13. 最终建议

本项目最适合的方案不是继续堆叠 system prompt，而是：

```text
统一入口 Gateway
  -> 规则初筛
  -> 独立分类 LLM（仅处理模糊请求）
  -> 代码硬路由
  -> 热点专用 ReActAgent
```

最关键的验收标准是：

> 对无关问题，系统在调用主 LLM、创建 Agent session、暴露工具之前就已经返回固定拒答。

## 14. 实施变更记录

### 2026-08-20：完成阶段一、阶段二

本次实施前，先将工作区中原有的已跟踪文件改动恢复到 Git HEAD；随后只保留本次范围控制功能相关的新增和修改。

已完成的修改动作：

1. 新增 `src/topic_pulse_v2/scope/` 包，定义 `IntentGate` 和 `IntentDecision`。
2. 增加规则分类：明确热点请求直接允许，明确无关请求直接拒绝，无法判断的请求进入语义分类或澄清。
3. 在 `ReactChatService.chat()` 和 `chat_stream()` 前置执行范围判断。
4. 对 `OFF_TOPIC` 返回固定拒答，对 `AMBIGUOUS` 返回固定澄清；两条路径均不进入 ReActAgent，不创建新的 Agent session，不调用工具。
5. 为模糊请求接入独立分类 LLM 调用，分类请求不携带工具，仅允许输出分类 JSON。
6. 增加意图枚举、置信度范围、JSON 解析和置信度阈值校验；分类失败时按 fail-closed 策略澄清。
7. 对 `refresh_topic` 等服务端 Scheduler 请求增加受信任路由，避免定时刷新被用户范围门禁误拦截。
8. 为流式拒答增加 `scope_gate` 状态和兼容现有 `result` 事件的返回路径。
9. 将分类意图、决策、置信度、来源和版本写入现有 `intent_gate` trace 事件。
10. 新增 `tests/test_intent_gate.py`，覆盖规则分类、分类 LLM、低置信度、非法 JSON、Scheduler 信任路由及同步/流式门禁行为。

本次涉及文件：

```text
src/topic_pulse_v2/scope/__init__.py
src/topic_pulse_v2/scope/intent_gate.py
src/topic_pulse_v2_chat/web/react_service.py
src/topic_pulse_v2_chat/web/app.py
tests/test_intent_gate.py
```

验证结果：新增及相关回归测试共 21 项通过，4 项 Web service 测试因当前环境缺少 FastAPI 被跳过；完整测试集仍需要安装 `fastapi`、`langchain-core` 和 `langchain-openai` 后再执行。

阶段三尚未实施。本次没有新增每日主动热点发现任务、日报存储或通知推送能力。
