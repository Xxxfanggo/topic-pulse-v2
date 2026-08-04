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
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

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
    save_user_input_to_memory: bool = False
    save_final_answer_to_memory: bool = False
    trace_log_path: str | None = "logs/react_trace.jsonl"
    system_prompt: str = (
        "你是一个 ReAct逻辑的 智能体。请通过推理解决用户任务，必要时使用工具，"
        "并给出最终回答。\n\n"
        "你的主要职责是‘热点信息跟踪’，针对用户想要了解的新闻话题，结合网络搜索、本地记忆的内容进行回复，帮助用户更加全面地了解新闻话题。\n\n"
        
        "当你需要使用工具时，只返回 JSON：\n"
        '{"thought": "简短推理", "action": "工具名称", "arguments": {}}\n\n'
        "action 必须使用可用工具列表中的英文 name 字段，例如 doubao_search 或 topic_markdown_store；"
        "不要使用“豆包搜索工具”“话题记忆存储”等中文展示名。"
        "只要决定使用工具，就必须输出带 action 的 JSON，不能只在 thought 中描述打算使用工具。\n\n"
        "当你已经完成任务时，只返回 JSON：\n"
        '{"thought": "简短推理", "final_answer": "给用户的回答"}\n\n'
        "最终回答必须是结构化数据。请把结构化结果作为 final_answer 的内容返回，final_answer 本身必须是合法 JSON 字符串。\n"
        
        f"当前系统时间是 {datetime.now()}\n\n"
        "当用户描述词是'最近'、'近期'这类模糊时间，把时间转换成最近2个月。\n\n"
        
        "如果需要联网查询，请使用 doubao_search。\n"
        "如果针对某一具体新闻话题进行联网搜索之后，需要使用 topic_markdown_store "
        "记录该新闻话题的内容到本地记忆。\n"
        "每次联网搜索到最新内容之后，需要使用 topic_markdown_store "
        "将最新内容与本地已存储的记忆进行合并更新，保障存储记忆中的内容持续更新并且正确。\n\n"
    )


@dataclass(slots=True)
class ReActStep:
    """One model/tool iteration in a ReAct run."""

    index: int
    thought: str = ""
    action: str | None = None
    tool_call_id: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    observation: Any = None
    final_answer: str | None = None
    raw_response: str = ""
    tool_result: ToolCallResult | None = None


@dataclass(slots=True)
class ReActResult:
    """Final result returned by the ReAct loop."""

    answer: str
    session_id: str | None
    steps: list[ReActStep]
    completed: bool
    metadata: dict[str, Any] = field(default_factory=dict)


class ReActAgent:
    """A small ReAct agent process built on the scaffold modules."""

    def __init__(
        self,
        *,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        memory_store: MemoryStore | None = None,
        session_manager: SessionManager | None = None,
        config: ReActConfig | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._tool_registry = tool_registry
        self._tool_executor = ToolExecutor(tool_registry)
        self._memory_store = memory_store
        self._session_manager = session_manager
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

        for index in range(1, self._config.max_steps + 1):
            tools = self._tool_registry.as_llm_tools()
            log_event(
                self._config.trace_log_path,
                "llm_request",
                session_id=session_id,
                step_index=index,
                data={
                    "provider": provider,
                    "model": model,
                    "messages": [self._message_to_dict(message) for message in messages],
                    "tools": tools,
                    "metadata": metadata or {},
                },
            )
            response = self._llm_client.call(
                messages,
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
            tool_call_id = self._tool_call_id(parsed, session_id, index)
            step = ReActStep(
                index=index,
                thought=parsed.get("thought", ""),
                action=parsed.get("action"),
                tool_call_id=tool_call_id,
                arguments=self._repair_tool_arguments(
                    parsed.get("action"),
                    parsed.get("arguments", {}) or {},
                    query,
                ),
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
                            response.tool_calls,
                            step.action,
                            step.arguments,
                            tool_call_id,
                        )
                    },
                )
            )

            if step.final_answer is not None:
                answer = step.final_answer
                completed = True
                break

            if step.action:
                tool_request = ToolCallRequest(
                    name=step.action,
                    arguments=step.arguments,
                    call_id=step.tool_call_id,
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
                tool_result = self._tool_executor.call_request(
                    tool_request
                )
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
                step.tool_result = tool_result
                step.observation = (
                    tool_result.result if tool_result.success else tool_result.error
                )
                messages.append(
                    Message(
                        role="tool",
                        name=step.action,
                        tool_call_id=step.tool_call_id,
                        content=self._format_observation(tool_result),
                    )
                )
                continue

            answer = response.content
            completed = True
            break

        if not completed:
            answer = "智能体已停止，因为达到了最大执行步数。"

        if self._memory_store and self._config.save_final_answer_to_memory:
            self._memory_store.save(user_id, answer, metadata={"type": "final_answer"})
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

    def _ensure_session(self, session_id: str | None, user_id: str) -> str | None:
        if not self._session_manager:
            return session_id
        if session_id:
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

        return [
            Message(
                role="system",
                content=(
                    f"{self._config.system_prompt}\n\n"
                    f"可用工具：\n{tool_text}\n\n"
                    f"相关记忆：\n{memory_text}\n\n"
                    f"会话上下文：\n{session_text}"
                ),
            ),
            Message(role="user", content=query),
        ]

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
            first_call = tool_calls[0]
            function = first_call.get("function", first_call)
            arguments = (
                function.get("arguments")
                or function.get("args")
                or first_call.get("args")
                or {}
            )
            if isinstance(arguments, str):
                arguments = json.loads(arguments or "{}")
            return {
                "thought": first_call.get("thought", ""),
                "action": function.get("name") or first_call.get("name"),
                "arguments": arguments,
                "tool_call_id": first_call.get("id") or function.get("id"),
            }

        payload = cls._extract_json_object(content)
        if payload is not None:
            return payload

        final_answer_match = re.search(
            r"final\s*answer\s*:\s*(?P<answer>.+)",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if final_answer_match:
            return {"final_answer": final_answer_match.group("answer").strip()}

        return {"final_answer": content.strip()}

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
    def _assistant_tool_calls(
        response_tool_calls: list[dict[str, Any]] | None,
        action: str | None,
        arguments: dict[str, Any],
        tool_call_id: str | None,
    ) -> list[dict[str, Any]]:
        if response_tool_calls:
            return response_tool_calls
        if not action or not tool_call_id:
            return []
        return [
            {
                "id": tool_call_id,
                "name": action,
                "args": arguments,
                "type": "tool_call",
            }
        ]

    @staticmethod
    def _repair_tool_arguments(
        action: str | None,
        arguments: dict[str, Any],
        query: str,
    ) -> dict[str, Any]:
        if not action:
            return arguments
        repaired = dict(arguments)
        if action == "doubao_search" and not repaired.get("query"):
            repaired["query"] = query
        if action == "topic_markdown_store" and not repaired.get("topic_name"):
            repaired["topic_name"] = query
        return repaired

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
