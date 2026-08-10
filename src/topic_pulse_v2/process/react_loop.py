"""ReAct-style agent business loop.

The loop follows this shape:

1. Build a prompt with user input, known tools, session context, and memories.
2. Ask the LLM what to do next.
3. If the LLM returns an action, execute the tool and append an observation.
4. Repeat until the LLM returns a final answer or max steps is reached.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from topic_pulse_v2.context_trim import (
    ContextTrimRequest,
    ContextTrimmer,
    PassthroughContextTrimmer,
)
from topic_pulse_v2.trace import log_event
from topic_pulse_v2.llm_call import LLMClient, Message
from topic_pulse_v2.memory import MemoryStore
from topic_pulse_v2.session import SessionManager, SessionStatus
from topic_pulse_v2.tool_call import ToolCallRequest, ToolCallResult, ToolExecutor
from topic_pulse_v2.tool_register import ToolRegistry


@dataclass(slots=True)
class ReActConfig:
    """Runtime options for the ReAct loop."""

    max_steps: int = 6
    memory_limit: int = 5
    session_history_limit: int = 12
    save_user_input_to_memory: bool = False
    save_final_answer_to_memory: bool = False
    trace_log_path: str | None = "logs/react_trace.jsonl"
    system_prompt: str = (

        "# 角色与目标\n"
        "你是一个基于 ReAct 流程运行的热点信息跟踪智能体。你的任务是围绕用户关心的新闻话题、热点话题或长期关注话题，结合联网搜索结果、本地话题记忆和会话历史，给出准确、结构化、可追溯的回答。\n\n"
        
        "# 输入上下文\n"
        "你会收到：用户本次输入、最近会话历史、相关记忆、可用工具列表、以及工具执行后的观察结果。\n"
        "会话历史只用于理解指代关系和上下文，不代表最新事实；涉及最新进展时必须优先使用联网搜索结果。\n\n"
        
        "# 基础判断规则\n"
        "1. 如果用户输入不是明确话题，或无法识别具体查询对象，不要编造回答，应引导用户补充具体话题。\n"
        "2. 当用户使用“最近”“近期”“最新进展”“现在怎么样了”等模糊时间表达时，默认转换为最近6个月。\n"
        "3. 如果任务涉及最新新闻、价格、政策、人物动态、公司动态、技术进展等可能变化的信息，必须调用 doubao_search 联网查询。\n\n"
        
        "# 工具调用输出格式\n"
        "当你需要调用一个工具时，只返回一个 JSON 对象，不要输出 Markdown、解释文字或额外文本：\n"
        '{"thought": "简短说明为什么调用工具", "action": "工具英文name", "arguments": {"参数名": "参数值"}}\n'
        "action 必须严格使用可用工具列表中的英文 name 字段，例如 doubao_search、topic_markdown_read_summary、topic_markdown_read_detail、topic_markdown_store。\n"
        "禁止使用中文展示名作为 action，例如“豆包搜索工具”“话题记忆存储”。\n"
        "只要决定使用工具，就必须输出带 action 的 JSON；禁止只在 thought 中描述打算使用工具。\n\n"
        
        "# 关键工具参数要求\n"
        "1. 调用 doubao_search 时，arguments 必须包含 query，query 应是补全时间范围后的具体搜索词。例如：{\"query\": \"内存条价格走势 最近6个月 最新消息\"}。\n"
        "2. 调用 topic_markdown_read_summary 时，arguments 必须包含 query，用于匹配本地已关注话题。\n"
        "3. 调用 topic_markdown_read_detail 时，arguments 必须包含 topic_name 或 path，且必须来自 topic_markdown_read_summary 返回的候选结果。\n"
        "4. 调用 topic_markdown_store 时，arguments 必须包含 topic_name、summary、latest_content 或 timeline_items；已有话题使用 operation=update，新话题使用 operation=create 或 auto。\n"
        "5. topic_markdown_store 的 timeline_items 必须是提炼后的具体条目，条目应尽量包含 date、title、summary、source、url；source 优先使用搜索结果中的 site_name，url 使用搜索结果中的 url。\n\n"
        
        "# 长期关注话题决策流程\n"
        "1. 如果用户明确表达“帮我关注”“持续关注”“长期跟踪”“记录下来”“保存到本地”“维护时间线”等意图，必须进入 Markdown 话题记忆流程。\n"
        "2. 系统消息中的“本地已关注话题候选”是强约束：只要候选 topics 非空且与用户本次问题相关，即使用户没有再次说“持续关注”，也必须按已关注话题处理。\n"
        "3. 如果用户没有明确长期关注意图，但输入中包含“上次”“之前”“关注过”“那个话题”“怎么样了”“更新一下”“走势”“最近”“最新”等表达，必须调用 topic_markdown_read_summary 判断是否存在本地相关话题。\n"
        "4. 如果 topic_markdown_read_summary 返回相关候选，或系统消息中的“本地已关注话题候选”已经给出相关候选，必须调用 topic_markdown_read_detail 读取完整 Markdown 内容，再结合 doubao_search 的最新结果进行更新。\n"
        "5. 如果 topic_markdown_read_summary 没有返回相关候选，并且用户也没有明确关注、记录、保存意图，则只进行普通查询和回答，禁止调用 topic_markdown_store。\n"
        "6. 如果用户只是查询、了解、分析、总结一个从未存储过的普通话题，本次会话直接回答用户即可，禁止写入 Markdown 记忆。\n\n"
        
        "# Markdown 话题记忆写入流程\n"
        "当需要创建或更新本地 Markdown 话题记忆时，按以下顺序执行：\n"
        "1. 调用 topic_markdown_read_summary 判断是否已有相关本地话题。\n"
        "2. 调用 doubao_search 获取最新联网内容。\n"
        "3. 如果发现相关本地话题，调用 topic_markdown_read_detail 读取完整旧内容。\n"
        "4. 综合本地旧内容和联网新内容，提炼出完整、去重、按时间倒序排列的内容。\n"
        "5. 最后调用 topic_markdown_store 写入。已有话题使用 operation=update，新话题使用 operation=create 或 auto。\n\n"
        
        "# 内容质量约束\n"
        "1. 禁止在任何工具参数中使用 {\"...\": null}、省略号、占位符或空壳条目。\n"
        "2. 如果搜索结果很长，必须先提炼为具体条目后再写入或回答，不能把未处理的大段结果原样塞进结构化字段。\n"
        "3. 不得编造来源、链接、发布时间；没有来源或链接时，应明确为空或说明未获得，但不能伪造。\n"
        "4. 写入 Markdown 的时间线必须按时间倒序排列。\n\n"
        
        "# 最终回答输出格式\n"
        "当你已经完成任务并准备回答用户时，只返回一个 JSON 对象，不要输出 Markdown、解释文字或额外文本：\n"
        '{"thought": "简短说明已经完成", "final_answer": "{\\"summary\\":\\"给用户的结构化摘要\\",\\"items\\":[],\\"next_action\\":\\"可选的后续建议\\",\\"query_key\\":\\"查询关键词\\",\\"reference_data\\":[{\\"title\\":\\"参考资料标题\\",\\"url\\":\\"https://example.com\\"}]}"}\n'
        "final_answer 的值必须是一个合法 JSON 字符串；也就是说，外层是 ReAct JSON，内层 final_answer 是经过转义的 JSON 字符串。\n"
        "final_answer 内层 JSON 的 summary 必须是面向用户的自然语言或 Markdown 正文，禁止把另一段 JSON、final_answer、items、reference_data 或 <think> 内容塞进 summary。\n"
        "如果本次流程调用过 doubao_search，final_answer 内层 JSON 必须包含 query_key 和 reference_data。query_key 是实际搜索关键词；reference_data 是参考资料对象数组，每个对象必须只包含 title 和 url 两个英文 key，禁止使用中文 key。\n"
        "如果本次流程调用过 topic_markdown_store，final_answer 内层 JSON 必须包含 topic_update，用于标识本次话题记忆更新的新旧信息；topic_update 必须包含 topic_name、status、new_count、existing_count、new_items、existing_items。\n"
        "最终回答必须使用中文，并且必须是结构化数据。\n"
    )


@dataclass(slots=True)
class ReActStep:
    """One model/tool iteration in a ReAct run."""

    index: int
    thought: str = ""
    action: str | None = None
    tool_call_id: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    observation: Any = None
    final_answer: str | None = None
    raw_response: str = ""
    tool_result: ToolCallResult | None = None
    tool_results: list[ToolCallResult] = field(default_factory=list)


@dataclass(slots=True)
class ReActResult:
    """Final result returned by the ReAct loop."""

    answer: str
    session_id: str | None
    steps: list[ReActStep]
    completed: bool
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ReActStreamEvent:
    """Event yielded by the streaming ReAct loop."""

    type: Literal[
        "status",
        "llm_delta",
        "tool_start",
        "tool_end",
        "step_end",
        "result",
        "error",
    ]
    content: str = ""
    session_id: str | None = None
    step_index: int | None = None
    data: dict[str, Any] = field(default_factory=dict)
    result: ReActResult | None = None


class ReActAgent:
    """A small ReAct agent process built on the scaffold modules."""

    def __init__(
        self,
        *,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        memory_store: MemoryStore | None = None,
        session_manager: SessionManager | None = None,
        context_trimmer: ContextTrimmer | None = None,
        config: ReActConfig | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._tool_registry = tool_registry
        self._tool_executor = ToolExecutor(tool_registry)
        self._memory_store = memory_store
        self._session_manager = session_manager
        self._context_trimmer = context_trimmer or PassthroughContextTrimmer()
        self._config = config or ReActConfig()

    def run(
        self,
        *,
        user_id: str,
        query: str,
        session_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ReActResult:
        if not user_id:
            raise ValueError("user_id cannot be empty.")
        if not query:
            raise ValueError("query cannot be empty.")

        session_id = self._ensure_session(session_id, user_id)
        if self._memory_store and self._config.save_user_input_to_memory:
            self._memory_store.save(user_id, query, metadata={"type": "user_input"})

        messages = self._build_initial_messages(user_id, query, session_id)

        steps: list[ReActStep] = []
        answer = ""
        completed = False
        tool_observations: dict[str, Any] = {}
        tools = self._tool_registry.as_llm_tools()

        for index in range(1, self._config.max_steps + 1):
            context = self._context_trimmer.trim(
                ContextTrimRequest(
                    messages=messages,
                    tools=tools,
                    session_id=session_id,
                    user_id=user_id,
                    query=query,
                    step_index=index,
                    metadata=metadata or {},
                )
            )
            llm_messages = context.messages
            log_event(
                self._config.trace_log_path,
                "llm_request",
                session_id=session_id,
                step_index=index,
                data={
                    "provider": provider,
                    "model": model,
                    "messages": [self._message_to_dict(message) for message in llm_messages],
                    "tools": tools,
                    "context_trim": context.metadata,
                    "metadata": metadata or {},
                },
            )
            response = self._llm_client.call(
                llm_messages,
                provider=provider,
                model=model,
                tools=tools,
                metadata=metadata,
            )
            log_event(
                self._config.trace_log_path,
                "llm_response",
                session_id=session_id,
                step_index=index,
                data={
                    "content": response.content,
                    "tool_calls": response.tool_calls,
                    "usage": response.usage,
                    "metadata": response.metadata,
                    "model": response.model,
                },
            )
            parsed = self._parse_response(response.content, response.tool_calls)
            step_tool_calls = self._parsed_tool_calls(
                parsed,
                session_id,
                index,
                query,
                tool_observations,
            )
            first_tool_call = step_tool_calls[0] if step_tool_calls else {}
            step = ReActStep(
                index=index,
                thought=parsed.get("thought", ""),
                action=first_tool_call.get("name"),
                tool_call_id=first_tool_call.get("id"),
                arguments=first_tool_call.get("args", {}),
                tool_calls=step_tool_calls,
                final_answer=parsed.get("final_answer"),
                raw_response=response.content,
            )
            steps.append(step)
            messages.append(
                Message(
                    role="assistant",
                    content=response.content,
                    metadata={
                        "tool_calls": self._assistant_tool_calls(
                            step.tool_calls,
                        )
                    },
                )
            )

            if step.final_answer is not None:
                answer = step.final_answer
                completed = True
                break

            if step.tool_calls:
                for tool_call in step.tool_calls:
                    tool_request = ToolCallRequest(
                        name=tool_call["name"],
                        arguments=tool_call.get("args", {}),
                        call_id=tool_call.get("id"),
                    )
                    log_event(
                        self._config.trace_log_path,
                        "tool_request",
                        session_id=session_id,
                        step_index=index,
                        data={
                            "name": tool_request.name,
                            "arguments": tool_request.arguments,
                            "call_id": tool_request.call_id,
                            "metadata": tool_request.metadata,
                        },
                    )
                    tool_result = self._tool_executor.call_request(tool_request)
                    log_event(
                        self._config.trace_log_path,
                        "tool_response",
                        session_id=session_id,
                        step_index=index,
                        data={
                            "name": tool_result.name,
                            "success": tool_result.success,
                            "result": tool_result.result,
                            "error": tool_result.error,
                            "call_id": tool_result.call_id,
                            "elapsed_ms": tool_result.elapsed_ms,
                            "metadata": tool_result.metadata,
                        },
                    )
                    step.tool_results.append(tool_result)
                    if step.tool_result is None:
                        step.tool_result = tool_result
                    if tool_result.success:
                        self._remember_tool_observation(tool_observations, tool_result)
                    messages.append(
                        Message(
                            role="tool",
                            name=tool_result.name,
                            tool_call_id=tool_result.call_id,
                            content=self._format_observation(tool_result),
                        )
                    )
                step.observation = [
                    result.result if result.success else result.error
                    for result in step.tool_results
                ]
                if len(step.observation) == 1:
                    step.observation = step.observation[0]
                continue

            answer = response.content
            completed = True
            break

        if not completed:
            answer = "智能体已停止，因为达到了最大执行步数。"

        answer = self._augment_answer_with_search_references(
            answer,
            query,
            tool_observations.get("doubao_search"),
        )
        answer = self._augment_answer_with_topic_update(
            answer,
            tool_observations.get("topic_markdown_store"),
        )

        if self._memory_store and self._config.save_final_answer_to_memory:
            self._memory_store.save(user_id, answer, metadata={"type": "final_answer"})
        self._save_session_history(session_id, query, answer, completed)
        self._finish_session(session_id, completed)
        log_event(
            self._config.trace_log_path,
            "agent_finish",
            session_id=session_id,
            step_index=None,
            data={
                "answer": answer,
                "completed": completed,
                "max_steps": self._config.max_steps,
            },
        )

        return ReActResult(
            answer=answer,
            session_id=session_id,
            steps=steps,
            completed=completed,
            metadata={"max_steps": self._config.max_steps},
        )

    def stream(
        self,
        *,
        user_id: str,
        query: str,
        session_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[ReActStreamEvent]:
        if not user_id:
            raise ValueError("user_id cannot be empty.")
        if not query:
            raise ValueError("query cannot be empty.")

        session_id = self._ensure_session(session_id, user_id)
        yield ReActStreamEvent(type="status", session_id=session_id, data={"stage": "session_ready"})

        if self._memory_store and self._config.save_user_input_to_memory:
            self._memory_store.save(user_id, query, metadata={"type": "user_input"})

        messages = self._build_initial_messages(user_id, query, session_id)
        steps: list[ReActStep] = []
        answer = ""
        completed = False
        tool_observations: dict[str, Any] = {}
        tools = self._tool_registry.as_llm_tools()

        for index in range(1, self._config.max_steps + 1):
            yield ReActStreamEvent(
                type="status",
                session_id=session_id,
                step_index=index,
                data={"stage": "llm_start"},
            )
            context = self._context_trimmer.trim(
                ContextTrimRequest(
                    messages=messages,
                    tools=tools,
                    session_id=session_id,
                    user_id=user_id,
                    query=query,
                    step_index=index,
                    metadata=metadata or {},
                )
            )
            llm_messages = context.messages
            log_event(
                self._config.trace_log_path,
                "llm_request",
                session_id=session_id,
                step_index=index,
                data={
                    "provider": provider,
                    "model": model,
                    "messages": [self._message_to_dict(message) for message in llm_messages],
                    "tools": tools,
                    "context_trim": context.metadata,
                    "metadata": metadata or {},
                    "stream": True,
                },
            )

            response = None
            content_parts: list[str] = []
            for event in self._llm_client.stream(
                llm_messages,
                provider=provider,
                model=model,
                tools=tools,
                metadata=metadata,
            ):
                if event.type == "delta":
                    content_parts.append(event.content)
                    yield ReActStreamEvent(
                        type="llm_delta",
                        content=event.content,
                        session_id=session_id,
                        step_index=index,
                        data=event.metadata,
                    )
                    continue
                if event.type == "done":
                    response = event.response
                    continue
                if event.type == "error":
                    yield ReActStreamEvent(
                        type="error",
                        content=event.content,
                        session_id=session_id,
                        step_index=index,
                        data=event.metadata,
                    )

            if response is None:
                response = self._llm_client.call(
                    llm_messages,
                    provider=provider,
                    model=model,
                    tools=tools,
                    metadata=metadata,
                )
            if not response.content and content_parts:
                response.content = "".join(content_parts)

            log_event(
                self._config.trace_log_path,
                "llm_response",
                session_id=session_id,
                step_index=index,
                data={
                    "content": response.content,
                    "tool_calls": response.tool_calls,
                    "usage": response.usage,
                    "metadata": response.metadata,
                    "model": response.model,
                    "stream": True,
                },
            )
            parsed = self._parse_response(response.content, response.tool_calls)
            step_tool_calls = self._parsed_tool_calls(
                parsed,
                session_id,
                index,
                query,
                tool_observations,
            )
            first_tool_call = step_tool_calls[0] if step_tool_calls else {}
            step = ReActStep(
                index=index,
                thought=parsed.get("thought", ""),
                action=first_tool_call.get("name"),
                tool_call_id=first_tool_call.get("id"),
                arguments=first_tool_call.get("args", {}),
                tool_calls=step_tool_calls,
                final_answer=parsed.get("final_answer"),
                raw_response=response.content,
            )
            steps.append(step)
            messages.append(
                Message(
                    role="assistant",
                    content=response.content,
                    metadata={"tool_calls": self._assistant_tool_calls(step.tool_calls)},
                )
            )

            if step.final_answer is not None:
                answer = step.final_answer
                completed = True
                yield ReActStreamEvent(
                    type="step_end",
                    session_id=session_id,
                    step_index=index,
                    data={"completed": True, "thought": step.thought},
                )
                break

            if step.tool_calls:
                for tool_call in step.tool_calls:
                    tool_request = ToolCallRequest(
                        name=tool_call["name"],
                        arguments=tool_call.get("args", {}),
                        call_id=tool_call.get("id"),
                    )
                    yield ReActStreamEvent(
                        type="tool_start",
                        session_id=session_id,
                        step_index=index,
                        data={
                            "name": tool_request.name,
                            "arguments": tool_request.arguments,
                            "call_id": tool_request.call_id,
                        },
                    )
                    log_event(
                        self._config.trace_log_path,
                        "tool_request",
                        session_id=session_id,
                        step_index=index,
                        data={
                            "name": tool_request.name,
                            "arguments": tool_request.arguments,
                            "call_id": tool_request.call_id,
                            "metadata": tool_request.metadata,
                        },
                    )
                    tool_result = self._tool_executor.call_request(tool_request)
                    log_event(
                        self._config.trace_log_path,
                        "tool_response",
                        session_id=session_id,
                        step_index=index,
                        data={
                            "name": tool_result.name,
                            "success": tool_result.success,
                            "result": tool_result.result,
                            "error": tool_result.error,
                            "call_id": tool_result.call_id,
                            "elapsed_ms": tool_result.elapsed_ms,
                            "metadata": tool_result.metadata,
                        },
                    )
                    step.tool_results.append(tool_result)
                    if step.tool_result is None:
                        step.tool_result = tool_result
                    if tool_result.success:
                        self._remember_tool_observation(tool_observations, tool_result)
                    messages.append(
                        Message(
                            role="tool",
                            name=tool_result.name,
                            tool_call_id=tool_result.call_id,
                            content=self._format_observation(tool_result),
                        )
                    )
                    yield ReActStreamEvent(
                        type="tool_end",
                        session_id=session_id,
                        step_index=index,
                        data={
                            "name": tool_result.name,
                            "success": tool_result.success,
                            "result": tool_result.result,
                            "error": tool_result.error,
                            "call_id": tool_result.call_id,
                            "elapsed_ms": tool_result.elapsed_ms,
                        },
                    )
                step.observation = [
                    result.result if result.success else result.error
                    for result in step.tool_results
                ]
                if len(step.observation) == 1:
                    step.observation = step.observation[0]
                yield ReActStreamEvent(
                    type="step_end",
                    session_id=session_id,
                    step_index=index,
                    data={"completed": False, "thought": step.thought},
                )
                continue

            answer = response.content
            completed = True
            yield ReActStreamEvent(
                type="step_end",
                session_id=session_id,
                step_index=index,
                data={"completed": True, "thought": step.thought},
            )
            break

        if not completed:
            answer = "智能体已停止，因为达到最大执行步数。"

        answer = self._augment_answer_with_search_references(
            answer,
            query,
            tool_observations.get("doubao_search"),
        )
        answer = self._augment_answer_with_topic_update(
            answer,
            tool_observations.get("topic_markdown_store"),
        )
        if self._memory_store and self._config.save_final_answer_to_memory:
            self._memory_store.save(user_id, answer, metadata={"type": "final_answer"})
        self._save_session_history(session_id, query, answer, completed)
        self._finish_session(session_id, completed)
        log_event(
            self._config.trace_log_path,
            "agent_finish",
            session_id=session_id,
            step_index=None,
            data={
                "answer": answer,
                "completed": completed,
                "max_steps": self._config.max_steps,
                "stream": True,
            },
        )

        result = ReActResult(
            answer=answer,
            session_id=session_id,
            steps=steps,
            completed=completed,
            metadata={"max_steps": self._config.max_steps, "stream": True},
        )
        yield ReActStreamEvent(
            type="result",
            session_id=session_id,
            data={"completed": completed},
            result=result,
        )

    def _ensure_session(self, session_id: str | None, user_id: str) -> str | None:
        if not self._session_manager:
            return session_id
        if session_id:
            session = self._session_manager.ensure(
                session_id,
                context={"user_id": user_id},
            )
            if session.status in {
                SessionStatus.COMPLETED,
                SessionStatus.FAILED,
                SessionStatus.PAUSED,
            }:
                self._session_manager.transition(session_id, SessionStatus.ACTIVE)
            self._session_manager.set_context(session_id, "user_id", user_id)
            return session_id
        session = self._session_manager.create(context={"user_id": user_id})
        return session.id

    def _finish_session(self, session_id: str | None, completed: bool) -> None:
        if not self._session_manager or not session_id:
            return
        status = SessionStatus.COMPLETED if completed else SessionStatus.FAILED
        self._session_manager.transition(session_id, status)

    def _build_initial_messages(
        self,
        user_id: str,
        query: str,
        session_id: str | None,
    ) -> list[Message]:
        tool_text = self._format_tools()
        memory_text = self._format_memories(user_id, query)
        session_text = self._format_session(session_id)
        local_topic_text = self._format_local_topic_candidates(query)
        history_messages = self._session_history_messages(session_id)
        current_time = datetime.now().isoformat(timespec="seconds")

        return [
            Message(
                role="system",
                content=(
                    f"{self._config.system_prompt}\n\n"
                    f"当前系统时间：{current_time}\n\n"
                    f"可用工具：\n{tool_text}\n\n"
                    f"相关记忆：\n{memory_text}\n\n"
                    f"本地已关注话题候选：\n{local_topic_text}\n\n"
                    f"会话上下文：\n{session_text}"
                ),
            ),
            *history_messages,
            Message(role="user", content=query),
        ]

    def _session_history_messages(self, session_id: str | None) -> list[Message]:
        if not self._session_manager or not session_id:
            return []
        history = self._session_manager.get_history(
            session_id,
            limit=self._config.session_history_limit,
        )
        messages: list[Message] = []
        for item in history:
            if item.role not in {"user", "assistant"}:
                continue
            if not item.content:
                continue
            messages.append(Message(role=item.role, content=item.content))
        return messages

    def _save_session_history(
        self,
        session_id: str | None,
        query: str,
        answer: str,
        completed: bool,
    ) -> None:
        if not self._session_manager or not session_id:
            return
        self._session_manager.append_history(
            session_id,
            "user",
            query,
            metadata={"type": "user_input"},
        )
        self._session_manager.append_history(
            session_id,
            "assistant",
            answer,
            metadata={"type": "final_answer", "completed": completed},
        )

    @staticmethod
    def _format_prompt_for_debug(messages: list[Message]) -> str:
        return "\n\n".join(
            f"[{message.role}]\n{message.content}"
            for message in messages
        )

    def _format_tools(self) -> str:
        specs = self._tool_registry.list()
        if not specs:
            return "未注册任何工具。"
        return "\n".join(
            f"- {spec.name}: {spec.description or '暂无描述。'}"
            for spec in specs
        )

    def _format_memories(self, user_id: str, query: str) -> str:
        if not self._memory_store:
            return "未配置记忆存储。"
        memories = self._memory_store.search(
            user_id,
            query,
            limit=self._config.memory_limit,
        )
        if not memories:
            return "没有相关记忆。"
        return "\n".join(f"- {record.content}" for record in memories)

    def _format_local_topic_candidates(self, query: str) -> str:
        if not self._tool_registry.has("topic_markdown_read_summary"):
            return "未注册本地话题摘要读取工具。"
        try:
            result = self._tool_registry.get("topic_markdown_read_summary").handler(
                query=query,
                limit=5,
            )
        except Exception as exc:
            return f"读取本地话题候选失败：{exc}"
        topics = result.get("topics") if isinstance(result, dict) else None
        if not isinstance(topics, list) or not topics:
            return "没有命中的本地已关注话题。"
        matched_topics = [
            topic for topic in topics
            if isinstance(topic, dict) and int(topic.get("match_score") or 0) > 0
        ]
        if not matched_topics:
            return "没有命中的本地已关注话题。"
        return json.dumps(
            {
                "说明": (
                    "如果用户本次问题与下列候选话题相关，即使用户没有再次说“持续关注”，"
                    "也必须按已关注话题更新流程处理：读取详情、联网搜索、合并更新、返回新旧信息标识。"
                ),
                "topics": matched_topics,
            },
            ensure_ascii=False,
            default=str,
        )

    def _format_session(self, session_id: str | None) -> str:
        if not self._session_manager or not session_id:
            return "没有会话上下文。"
        session = self._session_manager.get(session_id)
        return json.dumps(
            {"id": session.id, "status": str(session.status), "context": session.context},
            ensure_ascii=False,
        )

    @staticmethod
    def _message_to_dict(message: Message) -> dict[str, Any]:
        return {
            "role": message.role,
            "content": message.content,
            "name": message.name,
            "tool_call_id": message.tool_call_id,
            "metadata": message.metadata,
        }

    @classmethod
    def _parse_response(
        cls,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if tool_calls:
            normalized_calls = [cls._normalize_tool_call(call) for call in tool_calls]
            first_call = normalized_calls[0]
            return {
                "thought": tool_calls[0].get("thought", ""),
                "action": first_call.get("name"),
                "arguments": first_call.get("args", {}),
                "tool_call_id": first_call.get("id"),
                "tool_calls": normalized_calls,
            }

        payload = cls._extract_json_object(content)
        if payload is not None:
            return payload

        final_answer_value = cls._extract_json_string_value(content, "final_answer")
        if final_answer_value is not None:
            return {"final_answer": final_answer_value}

        final_answer_match = re.search(
            r"final\s*answer\s*:\s*(?P<answer>.+)",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if final_answer_match:
            return {"final_answer": final_answer_match.group("answer").strip()}

        return {"final_answer": content.strip()}

    @staticmethod
    def _extract_json_string_value(content: str, key: str) -> str | None:
        key_match = re.search(rf'"{re.escape(key)}"\s*:\s*"', content)
        if not key_match:
            return None

        start = key_match.end()
        escaped = False
        value_chars: list[str] = []
        for char in content[start:]:
            if escaped:
                value_chars.append("\\" + char)
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                try:
                    return json.loads(f'"{"".join(value_chars)}"')
                except json.JSONDecodeError:
                    return "".join(value_chars)
            value_chars.append(char)
        return None

    @staticmethod
    def _normalize_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
        function = tool_call.get("function", tool_call)
        arguments = (
            function.get("arguments")
            or function.get("args")
            or tool_call.get("args")
            or {}
        )
        if isinstance(arguments, str):
            arguments = json.loads(arguments or "{}")
        return {
            "id": tool_call.get("id") or function.get("id"),
            "name": function.get("name") or tool_call.get("name"),
            "args": arguments,
            "type": tool_call.get("type") or "tool_call",
        }

    @classmethod
    def _parsed_tool_calls(
        cls,
        parsed: dict[str, Any],
        session_id: str | None,
        step_index: int,
        query: str,
        tool_observations: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        raw_calls = parsed.get("tool_calls")
        if raw_calls:
            calls = [cls._normalize_tool_call(call) for call in raw_calls]
        elif parsed.get("action"):
            calls = [
                {
                    "id": parsed.get("tool_call_id"),
                    "name": parsed.get("action"),
                    "args": parsed.get("arguments", {}) or {},
                    "type": "tool_call",
                }
            ]
        else:
            return []

        normalized_calls: list[dict[str, Any]] = []
        for call_index, call in enumerate(calls, start=1):
            action = call.get("name")
            call_id = (
                call.get("id")
                or f"call_{session_id or uuid4()}_{step_index}_{call_index}"
            )
            normalized_calls.append(
                {
                    "id": call_id,
                    "name": action,
                    "args": cls._repair_tool_arguments(
                        action,
                        call.get("args", {}) or {},
                        query,
                        tool_observations,
                    ),
                    "type": call.get("type") or "tool_call",
                }
            )
        return normalized_calls

    @staticmethod
    def _assistant_tool_calls(
        tool_calls: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        return list(tool_calls or [])

    @staticmethod
    def _tool_call_id(
        parsed: dict[str, Any],
        session_id: str | None,
        step_index: int,
    ) -> str | None:
        if not parsed.get("action"):
            return None
        return parsed.get("tool_call_id") or f"call_{session_id or uuid4()}_{step_index}"

    @staticmethod
    def _repair_tool_arguments(
        action: str | None,
        arguments: dict[str, Any],
        query: str,
        tool_observations: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not action:
            return arguments
        repaired = dict(arguments)
        if action == "doubao_search" and not repaired.get("query"):
            repaired["query"] = query
        if action == "topic_markdown_read_summary" and not repaired.get("query"):
            repaired["query"] = query
        if action == "topic_markdown_read_detail" and not repaired.get("topic_name") and not repaired.get("path"):
            repaired["topic_name"] = query
        if action == "topic_markdown_store" and not repaired.get("topic_name"):
            repaired["topic_name"] = query
        if action == "topic_markdown_store":
            search_result = (tool_observations or {}).get("doubao_search")
            if search_result is not None and ReActAgent._latest_content_needs_search_result(
                repaired.get("latest_content")
            ):
                repaired["latest_content"] = ReActAgent._merge_latest_content_with_search_result(
                    repaired.get("latest_content"),
                    search_result,
                )
        return repaired

    @staticmethod
    def _remember_tool_observation(
        tool_observations: dict[str, Any],
        tool_result: ToolCallResult,
    ) -> None:
        if tool_result.name != "doubao_search":
            tool_observations[tool_result.name] = tool_result.result
            return
        previous = tool_observations.get(tool_result.name)
        if previous is None:
            tool_observations[tool_result.name] = tool_result.result
            return
        tool_observations[tool_result.name] = ReActAgent._merge_search_observations(
            previous,
            tool_result.result,
        )

    @staticmethod
    def _merge_search_observations(previous: Any, current: Any) -> dict[str, Any]:
        previous_items = ReActAgent._search_items_from_result(previous)
        current_items = ReActAgent._search_items_from_result(current)
        merged_items: list[Any] = []
        seen: set[tuple[str, str]] = set()
        for item in [*previous_items, *current_items]:
            if not isinstance(item, dict):
                merged_items.append(item)
                continue
            key = (
                str(item.get("url") or item.get("Url") or item.get("title") or item.get("Title") or ""),
                str(item.get("publish_time") or item.get("PublishTime") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            merged_items.append(item)

        base = dict(current) if isinstance(current, dict) else {}
        if isinstance(previous, dict):
            base.setdefault("queries", [])
            base["queries"] = [
                item
                for item in [
                    previous.get("query"),
                    current.get("query") if isinstance(current, dict) else None,
                ]
                if item
            ]
            base.setdefault("search_results", [])
            base["search_results"] = [previous, current]
        base["web_results"] = merged_items
        base["result_count"] = len(merged_items)
        return base

    @staticmethod
    def _search_items_from_result(result: Any) -> list[Any]:
        if isinstance(result, list):
            return result
        if not isinstance(result, dict):
            return []
        if isinstance(result.get("web_results"), list):
            return result["web_results"]
        if isinstance(result.get("items"), list):
            return result["items"]
        nested = result.get("result")
        if isinstance(nested, dict):
            return ReActAgent._search_items_from_result(nested)
        return []

    @staticmethod
    def _latest_content_needs_search_result(value: Any) -> bool:
        if value is None:
            return True
        if ReActAgent._contains_placeholder(value):
            return True
        if not isinstance(value, dict):
            return True
        web_results = value.get("web_results")
        if isinstance(web_results, list):
            return not ReActAgent._has_usable_search_items(web_results)
        if isinstance(web_results, dict):
            return not ReActAgent._has_usable_search_items(web_results.get("item"))
        return True

    @staticmethod
    def _contains_placeholder(value: Any) -> bool:
        if isinstance(value, dict):
            if "..." in value:
                return True
            return any(
                key == "..." or ReActAgent._contains_placeholder(item)
                for key, item in value.items()
            )
        if isinstance(value, list):
            return any(ReActAgent._contains_placeholder(item) for item in value)
        return False

    @staticmethod
    def _has_usable_search_items(value: Any) -> bool:
        if not isinstance(value, list):
            return False
        for item in value:
            if not isinstance(item, dict):
                continue
            if item.get("title") or item.get("Title"):
                return True
        return False

    @staticmethod
    def _merge_latest_content_with_search_result(
        latest_content: Any,
        search_result: Any,
    ) -> dict[str, Any]:
        merged = dict(latest_content) if isinstance(latest_content, dict) else {}
        if isinstance(search_result, dict):
            for key in ("query", "search_type", "result_count", "request_id"):
                if key in search_result and key not in merged:
                    merged[key] = search_result[key]
            if isinstance(search_result.get("web_results"), list):
                merged["web_results"] = search_result["web_results"]
            elif isinstance(search_result.get("items"), list):
                merged["web_results"] = search_result["items"]
            elif isinstance(search_result.get("result"), dict):
                result = search_result["result"]
                if isinstance(result.get("web_results"), list):
                    merged["web_results"] = result["web_results"]
                elif isinstance(result.get("items"), list):
                    merged["web_results"] = result["items"]
            merged["doubao_search_result"] = search_result
            return merged
        if isinstance(search_result, list):
            merged["web_results"] = search_result
            return merged
        merged["summary"] = merged.get("summary") or str(search_result)
        return merged

    @classmethod
    def _augment_answer_with_search_references(
        cls,
        answer: str,
        fallback_query: str,
        search_result: Any,
    ) -> str:
        if search_result is None:
            return answer

        payload = cls._answer_payload(answer)
        if payload is None:
            payload = {"summary": answer}

        payload.setdefault("query_key", cls._query_key_from_search_result(search_result, fallback_query))
        references = cls._reference_data_from_search_result(search_result)
        if references:
            existing = payload.get("reference_data")
            if not cls._has_usable_reference_data(existing):
                payload["reference_data"] = references

        return json.dumps(payload, ensure_ascii=False, default=str)

    @classmethod
    def _answer_payload(cls, answer: str) -> dict[str, Any] | None:
        stripped = answer.strip()
        if not stripped:
            return None
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = cls._extract_json_object(stripped)
        if not isinstance(payload, dict):
            return None

        final_answer = payload.get("final_answer")
        if isinstance(final_answer, str):
            return cls._answer_payload(final_answer)
        summary = payload.get("summary")
        if isinstance(summary, str):
            nested_payload = cls._answer_payload(summary)
            if nested_payload and nested_payload.get("summary"):
                merged = dict(nested_payload)
                for key in ("query_key", "reference_data", "topic_update"):
                    if key not in merged and payload.get(key):
                        merged[key] = payload[key]
                return merged
        return payload

    @classmethod
    def _augment_answer_with_topic_update(
        cls,
        answer: str,
        store_result: Any,
    ) -> str:
        topic_update = cls._topic_update_from_store_result(store_result)
        if not topic_update:
            return answer

        payload = cls._answer_payload(answer)
        if payload is None:
            payload = {"summary": answer}
        payload.setdefault("topic_update", topic_update)
        return json.dumps(payload, ensure_ascii=False, default=str)

    @staticmethod
    def _topic_update_from_store_result(store_result: Any) -> dict[str, Any] | None:
        if not isinstance(store_result, dict):
            return None
        topic_name = str(store_result.get("topic_name") or "").strip()
        if not topic_name:
            return None
        new_items = store_result.get("new_items")
        if not isinstance(new_items, list):
            new_items = store_result.get("appended_items")
        existing_items = store_result.get("existing_items")
        if not isinstance(existing_items, list):
            existing_items = []
        new_count = int(store_result.get("new_count") or store_result.get("appended_count") or 0)
        existing_count = int(store_result.get("existing_count") or 0)
        return {
            "topic_name": topic_name,
            "operation": store_result.get("operation") or "",
            "status": store_result.get("update_status") or ("updated_with_new_items" if new_count else "no_new_items"),
            "new_count": new_count,
            "existing_count": existing_count,
            "new_items": ReActAgent._compact_topic_items(new_items if isinstance(new_items, list) else []),
            "existing_items": ReActAgent._compact_topic_items(existing_items),
        }

    @staticmethod
    def _compact_topic_items(items: list[Any], *, limit: int = 8) -> list[dict[str, str]]:
        compacted: list[dict[str, str]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            compacted.append(
                {
                    "date": str(item.get("date") or "").strip(),
                    "title": title,
                    "source": str(item.get("source") or "").strip(),
                    "url": str(item.get("url") or "").strip(),
                    "summary": str(item.get("summary") or "").strip(),
                }
            )
            if len(compacted) >= limit:
                break
        return compacted

    @staticmethod
    def _query_key_from_search_result(search_result: Any, fallback_query: str) -> str:
        if isinstance(search_result, dict):
            for key in ("query", "Query"):
                value = search_result.get(key)
                if value:
                    return str(value)
            queries = search_result.get("queries")
            if isinstance(queries, list) and queries:
                return "；".join(str(item) for item in queries if item)
        return fallback_query

    @classmethod
    def _reference_data_from_search_result(cls, search_result: Any) -> list[dict[str, str]]:
        references: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for item in cls._search_items_from_result(search_result):
            if not isinstance(item, dict):
                continue
            raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
            title = (
                item.get("title")
                or item.get("Title")
                or raw.get("Title")
                or raw.get("title")
            )
            url = (
                item.get("url")
                or item.get("Url")
                or raw.get("Url")
                or raw.get("url")
            )
            if not title or not url:
                continue
            url_text = str(url)
            if url_text in seen_urls:
                continue
            seen_urls.add(url_text)
            references.append(
                {
                    "title": str(title),
                    "url": url_text,
                }
            )
        return references

    @staticmethod
    def _has_usable_reference_data(value: Any) -> bool:
        if not isinstance(value, list):
            return False
        for item in value:
            if not isinstance(item, dict):
                continue
            if item.get("title") and item.get("url"):
                return True
        return False

    @staticmethod
    def _extract_json_object(content: str) -> dict[str, Any] | None:
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
            stripped = re.sub(r"```$", "", stripped).strip()

        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            candidates = ReActAgent._extract_json_candidates(stripped)
            preferred = [
                item
                for item in candidates
                if isinstance(item, dict)
                and ("action" in item or "final_answer" in item)
            ]
            if preferred:
                return preferred[-1]
            if candidates and isinstance(candidates[-1], dict):
                return candidates[-1]
            return None

        if not isinstance(parsed, dict):
            return None
        return parsed

    @staticmethod
    def _extract_json_candidates(content: str) -> list[Any]:
        candidates: list[Any] = []
        start: int | None = None
        depth = 0
        in_string = False
        escaped = False
        for index, char in enumerate(content):
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char == "{":
                if depth == 0:
                    start = index
                depth += 1
                continue
            if char == "}":
                if depth == 0:
                    continue
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        candidates.append(json.loads(content[start : index + 1]))
                    except json.JSONDecodeError:
                        pass
                    start = None
        return candidates

    @staticmethod
    def _format_observation(tool_result: ToolCallResult) -> str:
        payload = {
            "tool": tool_result.name,
            "success": tool_result.success,
            "result": tool_result.result,
            "error": tool_result.error,
        }
        return f"观察结果：{json.dumps(payload, ensure_ascii=False, default=str)}"
