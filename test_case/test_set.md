# Agent 测试集

本测试集用于验证 Agent 在联网查询、本地话题记忆召回、Markdown 创建与更新方面的行为是否符合预期。

## 一、正向集

### TC-P001 普通联网查询不写入 Markdown

输入：

```text
查一下内存条最近价格走势
```

预期行为：

- 调用 `doubao_search`。
- 可以调用 `topic_markdown_read_summary` 判断是否已有关注话题。
- 如果本地没有命中已有关注话题，不调用 `topic_markdown_store`。
- 最终直接回答价格走势。

通过标准：

- 最终回答包含价格走势摘要。
- `steps` 中没有 `topic_markdown_store`。

### TC-P002 明确关注新话题时创建 Markdown

输入：

```text
帮我关注一下内存条最近价格走势
```

预期行为：

- 调用 `doubao_search`。
- 调用 `topic_markdown_read_summary`。
- 如果没有命中已有话题，调用 `topic_markdown_store` 创建文件。

通过标准：

- `topic_markdown_store.operation` 为 `create` 或 `auto`。
- 生成 `data/topics/*.md`。
- 时间线非空。
- 时间线包含来源和链接。

### TC-P003 明确持续关注已有话题时更新 Markdown

前置条件：

- `data/topics/内存条价格走势.md` 已存在。

输入：

```text
持续关注一下内存条价格走势，看看有没有新变化
```

预期行为：

- 调用 `topic_markdown_read_summary`。
- 命中已有话题。
- 调用 `topic_markdown_read_detail`。
- 调用 `doubao_search`。
- 调用 `topic_markdown_store` 更新文件。

通过标准：

- `topic_markdown_store.operation` 为 `update`。
- 时间线保持倒序。
- 重复新闻不会重复追加。

### TC-P004 无关注关键词但命中已有话题时更新

前置条件：

- `data/topics/内存条价格走势.md` 已存在。

输入：

```text
上次关注的内存条价格怎么样了
```

预期行为：

- 调用 `topic_markdown_read_summary`。
- 根据本地摘要命中“内存条价格走势”。
- 调用 `topic_markdown_read_detail`。
- 调用 `doubao_search`。
- 调用 `topic_markdown_store` 更新 Markdown。

通过标准：

- 不因为输入中缺少“持续关注”而跳过本地话题逻辑。
- 最终回答包含本地旧内容和最新搜索内容的合并结果。

### TC-P005 查询已有话题历史内容但不联网

前置条件：

- `data/topics/韩红近期热点.md` 已存在。

输入：

```text
看看之前保存的韩红话题摘要
```

预期行为：

- 调用 `topic_markdown_read_summary`。
- 调用 `topic_markdown_read_detail`。
- 不调用 `doubao_search`，除非用户要求“最新”。
- 不调用 `topic_markdown_store`。

通过标准：

- 回答基于 Markdown 内容。
- 没有新增或更新文件。

## 二、边界集

### TC-B001 本地 topics 目录为空

输入：

```text
上次关注的内存条价格怎么样了
```

预期行为：

- 调用 `topic_markdown_read_summary`。
- 返回 `topics: []`。
- 可提示用户当前没有本地关注记录。
- 如果用户没有明确要求新建关注，不调用 `topic_markdown_store`。

### TC-B002 用户普通查询但本地存在近似话题

前置条件：

- `data/topics/内存条价格走势.md` 已存在。

输入：

```text
查一下 DDR5 现在贵不贵
```

预期行为：

- 可调用 `topic_markdown_read_summary` 判断是否相关。
- 如果判断为同一关注话题，可进入已有话题更新路径。
- 如果只是宽泛相关但不是同一话题，应只回答，不更新 Markdown。

通过标准：

- 不把弱相关话题强行合并。

### TC-B003 搜索结果缺少发布时间

输入：

```text
帮我关注一下某个没有明确发布时间的话题
```

预期行为：

- 创建或更新时，如果搜索结果没有发布时间，可以使用当前日期作为兜底。
- 回答中应说明部分条目发布时间不完整。

通过标准：

- 不因缺少发布时间导致流程失败。
- 时间线仍可排序。

### TC-B004 搜索结果缺少来源或链接

输入：

```text
帮我关注一下某个来源信息不完整的话题
```

预期行为：

- 优先从 `site_name/raw.SiteName` 取来源。
- 优先从 `url/raw.Url` 取链接。
- 如果仍然缺失，应避免写入不可靠条目，或在回答中说明条目来源不完整。

通过标准：

- Markdown 中不应大量出现空来源或空链接。

### TC-B005 已有 Markdown 文件内容不完整

前置条件：

- 某个 Markdown 文件缺少摘要或时间线章节。

输入：

```text
更新一下之前关注的这个话题
```

预期行为：

- 尽量读取已有内容。
- 更新时补齐缺失章节。
- 不覆盖用户已有文本。

通过标准：

- 文件仍是合法 Markdown。
- 原有内容未被无故删除。

## 三、干扰集

### TC-D001 用户提到“关注”但不是长期关注意图

输入：

```text
这个新闻为什么受到关注？
```

预期行为：

- 不应因为出现“关注”两个字就创建 Markdown。
- 应按普通查询或普通回答处理。

通过标准：

- 不调用 `topic_markdown_store`。

### TC-D002 用户要求不要保存

输入：

```text
查一下韩红最近新闻，但不要保存到本地
```

预期行为：

- 调用 `doubao_search`。
- 不调用 `topic_markdown_store`。

通过标准：

- 严格遵守“不要保存”约束。

### TC-D003 用户输入模糊代词但本地多个候选

前置条件：

- `data/topics/内存条价格走势.md` 已存在。
- `data/topics/内存条架构走势.md` 已存在。

输入：

```text
上次那个内存条话题怎么样了
```

预期行为：

- 调用 `topic_markdown_read_summary`。
- 如果候选不唯一，应读取候选摘要后向用户澄清，或在最终回答中列出候选让用户选择。
- 不应随意更新其中一个文件。

通过标准：

- 不误写错误 Markdown 文件。

### TC-D004 搜索结果中存在大量重复新闻

输入：

```text
持续关注一下互联网大厂因 AI 裁员
```

预期行为：

- 搜索结果去重。
- 同一 URL 不重复写入。
- 同一标题高度相似时不重复写入。

通过标准：

- Markdown 时间线没有明显重复条目。

### TC-D005 大模型输出省略占位参数

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

预期行为：

- ReAct 参数修复逻辑应使用上一次 `doubao_search` 的真实结果补齐。
- 不应把 `{ "...": null }` 写入 Markdown。

通过标准：

- Markdown 中没有 `...` 占位内容。
- 时间线条目来自真实搜索结果。

### TC-D006 用户要求删除或覆盖本地记忆

输入：

```text
把之前关注的韩红话题删掉
```

预期行为：

- 当前版本不应直接执行删除。
- 应说明当前工具只支持读取、创建、更新，不支持删除。

通过标准：

- 不删除文件。
- 不清空 Markdown 内容。

