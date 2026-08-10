# Agent 验收测试集

本测试集用于验证 Topic Pulse Agent 在联网查询、本地话题召回、Markdown 创建/更新、多轮对话、Web 展示数据和可观测性方面是否符合预期。

## 1. 正向集

### TC-P001 普通联网查询不写入 Markdown

输入：

```text
查一下内存条最近价格走势
```

前置条件：

- `data/topics` 为空，或不存在与“内存条价格走势”相关的话题。

期望工具链路：

- 必须调用 `doubao_search`。
- 可以调用 `topic_markdown_read_summary` 判断是否命中已有话题。
- 不调用 `topic_markdown_store`。

通过标准：

- 最终回答包含价格走势摘要。
- 最终回答包含 `query_key`。
- 最终回答包含 `reference_data`，且每项包含 `title/url`。
- `steps` 中没有 `topic_markdown_store`。
- `data/topics` 没有新增 Markdown。

### TC-P002 明确关注新话题时创建 Markdown

输入：

```text
帮我持续关注一下内存条最近价格走势
```

前置条件：

- `data/topics` 中不存在相关话题文件。

期望工具链路：

- 调用 `topic_markdown_read_summary`。
- 调用 `doubao_search`。
- 调用 `topic_markdown_store`。

通过标准：

- `topic_markdown_store.operation` 为 `create` 或 `auto`。
- 生成 `data/topics/*.md`。
- Markdown 包含标题、基本信息、摘要、时间线。
- 时间线不为空，且按时间倒序排列。
- 时间线条目包含 `date/title/source/url/summary`。
- 时间线不包含“备注”字段。
- 最终回答包含 `topic_update`。

### TC-P003 明确持续关注已有话题时更新 Markdown

输入：

```text
持续关注一下内存条价格走势，看看有没有新变化
```

前置条件：

- `data/topics/内存条价格走势*.md` 已存在。

期望工具链路：

- 调用 `topic_markdown_read_summary`。
- 调用 `topic_markdown_read_detail`。
- 调用 `doubao_search`。
- 调用 `topic_markdown_store`，且操作为更新。

通过标准：

- Markdown 文件被更新而不是新建重复话题。
- 新旧内容合并后时间线保持倒序。
- 重复 URL 或重复标题不会重复写入。
- 最终回答的 `topic_update.new_items` 标识新增信息。
- 最终回答的 `topic_update.existing_items` 标识已记录信息。

### TC-P004 未显式说“关注”但命中已有话题时更新

输入：

```text
上次关注的内存条价格怎么样了
```

前置条件：

- `data/topics/内存条价格走势*.md` 已存在。

期望工具链路：

- 调用 `topic_markdown_read_summary`。
- 命中已有话题后调用 `topic_markdown_read_detail`。
- 调用 `doubao_search`。
- 调用 `topic_markdown_store` 更新 Markdown。

通过标准：

- 不因用户本次没有说“持续关注”而跳过本地话题逻辑。
- 最终回答综合本地旧内容和联网新内容。
- Web 页面能显示新增/已记录信息区域。

### TC-P005 查询已有话题历史内容但不联网

输入：

```text
看看之前保存的韩红话题摘要
```

前置条件：

- `data/topics/韩红*.md` 已存在。

期望工具链路：

- 调用 `topic_markdown_read_summary`。
- 调用 `topic_markdown_read_detail`。
- 不调用 `doubao_search`。
- 不调用 `topic_markdown_store`。

通过标准：

- 回答基于 Markdown 旧内容。
- 不新增或更新 Markdown。
- 最终回答不声称已经查询最新进展。

### TC-P006 联网查询最终返回引用资料

输入：

```text
查一下最近 AI Agent 商业化有什么新进展
```

期望工具链路：

- 调用 `doubao_search`。

通过标准：

- 最终回答包含 `query_key`。
- 最终回答包含 `reference_data`。
- `reference_data` 中每项只有 `title/url` 两个核心展示字段。
- Web 页面能展示“搜索关键词”和“参考资料”折叠区域。

### TC-P007 已关注话题更新最终返回新旧信息标识

输入：

```text
更新一下之前关注的互联网大厂因 AI 裁员话题
```

前置条件：

- `data/topics/互联网大厂因AI裁员*.md` 已存在。

期望工具链路：

- 调用 `topic_markdown_read_summary`。
- 调用 `topic_markdown_read_detail`。
- 调用 `doubao_search`。
- 调用 `topic_markdown_store`。

通过标准：

- 最终回答包含 `topic_update`。
- `topic_update.new_count` 和 `topic_update.existing_count` 可解析。
- `topic_update.new_items` 展示新增信息。
- `topic_update.existing_items` 展示已记录信息。
- Web 页面能明显区分“新增”和“已记录”。

## 2. 边界集

### TC-B001 本地 topics 目录为空

输入：

```text
上次关注的内存条价格怎么样了
```

前置条件：

- `data/topics` 为空。

期望工具链路：

- 调用 `topic_markdown_read_summary`。
- 返回 `topics: []`。
- 不调用 `topic_markdown_store`，除非用户明确要求新建关注。

通过标准：

- 回答说明当前没有命中的本地关注记录。
- 可以引导用户使用“帮我持续关注...”创建新话题。

### TC-B002 普通查询但本地存在弱相关话题

输入：

```text
查一下 DDR5 现在贵不贵
```

前置条件：

- `data/topics/内存条价格走势*.md` 已存在。

期望工具链路：

- 可以调用 `topic_markdown_read_summary`。
- 必须调用 `doubao_search`。
- 只有明确判断为同一已关注话题时才更新 Markdown。

通过标准：

- 不把弱相关话题强行合并。
- 如果没有进入已关注话题路径，不调用 `topic_markdown_store`。

### TC-B003 搜索结果缺少发布时间

输入：

```text
帮我持续关注一个发布时间不完整的话题
```

期望行为：

- 可以创建或更新 Markdown。
- 缺少发布时间时，允许使用检索日期或当前日期兜底。
- 回答中说明部分条目发布时间不完整。

通过标准：

- 流程不中断。
- 时间线仍可排序。
- 不编造精确发布时间。

### TC-B004 搜索结果缺少来源或链接

输入：

```text
帮我关注一个来源信息不完整的话题
```

期望行为：

- `source` 优先取 `site_name/raw.SiteName`。
- `url` 优先取 `url/raw.Url`。
- 无法补齐时，应避免写入不可靠条目，或在回答中说明信息不完整。

通过标准：

- Markdown 中不应大量出现空来源或空链接。
- 不伪造来源或链接。

### TC-B005 已有 Markdown 内容不完整

输入：

```text
更新一下之前关注的这个话题
```

前置条件：

- 某个 Markdown 文件缺少摘要或时间线章节。

期望行为：

- 尽量读取已有内容。
- 更新时补齐缺失章节。
- 不覆盖用户已有文本。

通过标准：

- 文件仍是合法 Markdown。
- 原有内容没有被无故删除。

### TC-B006 多轮会话中省略主语

输入轮次：

```text
第一轮：帮我关注一下内存条价格走势
第二轮：这个现在有什么新变化
```

期望行为：

- 第二轮通过 `session_id` 读取历史对话。
- 能识别“这个”指代“内存条价格走势”。
- 进入已关注话题更新路径。

通过标准：

- CLI 和 Web 都能保持同一会话上下文。
- 不依赖前端自行拼接历史消息。

### TC-B007 工具响应很大时流程仍能结束

输入：

```text
持续关注一下内存条价格走势，看看有没有新变化
```

前置条件：

- `doubao_search` 返回大量正文、raw 字段和多条搜索结果。

期望行为：

- trace 日志可以记录完整工具响应。
- 进入下一轮 LLM 的 observation 被压缩。
- Agent 能继续生成最终回答。

通过标准：

- 日志中出现 `agent_finish` 或 Web 流式返回 `done`。
- 前端不会一直停留在思考中。
- 下一轮 LLM prompt 不包含大段 `content/raw` 原文。

## 3. 干扰集

### TC-D001 用户提到“关注”但不是长期关注意图

输入：

```text
这个新闻为什么受到关注？
```

期望工具链路：

- 可按普通查询调用 `doubao_search`。
- 不调用 `topic_markdown_store`。

通过标准：

- 不因为出现“关注”两个字就创建 Markdown。

### TC-D002 用户明确要求不要保存

输入：

```text
查一下韩红最近新闻，但不要保存到本地
```

期望工具链路：

- 调用 `doubao_search`。
- 不调用 `topic_markdown_store`。

通过标准：

- 严格遵守“不保存”约束。
- 不生成 Markdown。

### TC-D003 模糊指代命中多个本地候选

输入：

```text
上次那个内存条话题怎么样了
```

前置条件：

- `data/topics/内存条价格走势*.md` 已存在。

期望行为：

- 调用 `topic_markdown_read_summary`。
- 如果候选不唯一，应澄清或列出候选让用户选择。
- 不应随意更新其中一个文件。

通过标准：

- 不误写错误 Markdown。
- 最终回答说明需要用户确认具体话题。

### TC-D004 搜索结果中存在大量重复新闻

输入：

```text
持续关注一下互联网大厂因 AI 裁员
```

期望行为：

- 对搜索结果去重。
- 同一 URL 不重复写入。
- 标题高度相似且内容相同的条目不重复写入。

通过标准：

- Markdown 时间线没有明显重复条目。
- `topic_update.existing_items` 能体现已记录内容。

### TC-D005 LLM 工具参数出现省略占位符

模拟工具参数：

```json
{
  "topic_name": "内存条价格走势",
  "latest_content": {
    "web_results": {
      "item": [
        {
          "...": null
        }
      ]
    }
  }
}
```

期望行为：

- ReAct 参数修复逻辑使用上一轮 `doubao_search` 的真实结果补齐。
- 不把 `{ "...": null }` 写入 Markdown。

通过标准：

- Markdown 中没有 `...` 占位内容。
- 时间线条目来自真实搜索结果。

### TC-D006 用户要求删除本地记忆

输入：

```text
把之前关注的韩红话题删掉
```

期望行为：

- 当前版本不直接删除文件。
- 回答说明当前工具只支持读取、创建、更新。

通过标准：

- 不删除 Markdown 文件。
- 不清空 Markdown 内容。

### TC-D007 工具选择出现思考正确但 action 为空

输入：

```text
查一下韩红最近的热点新闻
```

异常表现：

- LLM 在 `<think>` 中说要使用 `doubao_search`。
- 但输出没有合法 `action`，或 `arguments` 缺少 `query`。

期望行为：

- Parser 能识别 LangChain tool_calls。
- 参数修复逻辑能为 `doubao_search` 补齐 `query`。
- Prompt 要求工具调用时必须返回合法 JSON 或 tool_call。

通过标准：

- `steps.action` 为 `doubao_search`。
- `arguments.query` 非空。
- 不出现连续多轮 `TypeError: missing a required argument: 'query'`。

## 4. Web/CLI 交互集

### TC-W001 Web 普通查询完整收尾

输入：

```text
查一下最近 AI Agent 商业化有什么新进展
```

通过标准：

- 前端显示思考/工具执行过程后能收到最终回答。
- 前端收到 `done` 事件。
- 回答区域展示引用资料。
- 后端日志包含 `agent_finish`。

### TC-W002 Web 已关注话题更新展示新旧信息

输入：

```text
更新一下之前关注的内存条价格走势
```

通过标准：

- 前端展示 `topic_update` 面板。
- 新增信息和已记录信息有明显标识。
- 引用资料区域可以展开查看。

### TC-W003 CLI 多轮对话

输入轮次：

```text
第一轮：帮我关注一下内存条价格走势
第二轮：上次这个话题有新变化吗
```

通过标准：

- CLI 第二轮复用同一个 `session_id`。
- 不出现 session 状态非法转换错误。
- 第二轮能读取历史并进入已关注话题路径。

## 5. 可观测检查集

### TC-O001 trace 记录 LLM 输入输出

通过标准：

- 每次 LLM 调用前记录 `llm_request`。
- 每次 LLM 返回后记录 `llm_response`。
- `llm_request` 中可以看到完整 messages。

### TC-O002 trace 记录工具输入输出

通过标准：

- 每次工具调用前记录 `tool_request`。
- 每次工具返回后记录 `tool_response`。
- 记录工具名、参数、响应、耗时、成功状态、错误信息。

### TC-O003 中断定位

通过标准：

- 如果日志最后只有 `llm_request`，没有 `llm_response`，优先检查模型调用超时、上下文过大或 provider 异常。
- 如果日志最后只有 `tool_request`，没有 `tool_response`，优先检查工具内部阻塞或异常。
- 如果有 `tool_response` 但前端无展示，优先检查 Web stream 事件映射。

### TC-O004 工具 observation 压缩

通过标准：

- `doubao_search` 原始响应可以很大，但进入下一轮 LLM 的 observation 应只保留精简字段。
- observation 中不应包含大段 `content` 或完整 `raw`。
- 大搜索结果场景下 Agent 仍能完成最终回答。
