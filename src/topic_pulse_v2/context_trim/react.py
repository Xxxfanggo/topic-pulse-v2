"""ReAct-specific context budget and history helpers."""

from __future__ import annotations

from dataclasses import dataclass

from topic_pulse_v2.llm_call import Message
from topic_pulse_v2.session import SessionMessage


@dataclass(slots=True)
class ReActContextBudget:
    """Budget settings used before ReAct initial prompt assembly."""

    system_prompt_token_budget: int = 10000
    memory_token_budget: int = 10000
    context_extra_token_budget: int = 50000
    session_history_token_budget: int = 80000
    session_history_recent_turns_on_over_budget: int = 5


class ReActContextManager:
    """Deterministic context shaping for ReAct prompts."""

    def __init__(self, budget: ReActContextBudget | None = None) -> None:
        self._budget = budget or ReActContextBudget()

    @property
    def budget(self) -> ReActContextBudget:
        return self._budget

    def trim_system_prompt(self, text: str) -> str:
        return self.trim_text_to_token_budget(
            text,
            self._budget.system_prompt_token_budget,
        )

    def trim_memory_text(self, text: str) -> str:
        return self.trim_text_to_token_budget(
            text,
            self._budget.memory_token_budget,
        )

    def trim_context_extra_text(self, text: str) -> str:
        return self.trim_text_to_token_budget(
            text,
            self._budget.context_extra_token_budget,
        )

    def session_history_messages(
        self,
        history: list[SessionMessage],
        *,
        current_query: str | None = None,
    ) -> list[Message]:
        restored = self.restore_session_messages(history)
        current_turn_message: Message | None = None
        if (
            current_query
            and restored
            and restored[-1].role == "user"
            and restored[-1].content == current_query
        ):
            current_turn_message = restored.pop()

        complete_history = self.complete_tool_history_messages(restored)
        if self.messages_token_count(complete_history) <= self._budget.session_history_token_budget:
            history_messages = complete_history
        else:
            history_messages = self.recent_turn_history_messages(
                complete_history,
                self._budget.session_history_recent_turns_on_over_budget,
            )
        if current_turn_message is not None:
            history_messages.append(current_turn_message)
        return history_messages

    @staticmethod
    def restore_session_messages(history: list[SessionMessage]) -> list[Message]:
        restored: list[Message] = []
        for item in history:
            if item.role not in {"user", "assistant", "tool"}:
                continue
            if not item.content and item.metadata.get("type") != "tool_call":
                continue
            restored.append(
                Message(
                    role=item.role,
                    content=item.content,
                    name=item.metadata.get("name"),
                    tool_call_id=item.metadata.get("tool_call_id"),
                    metadata=dict(item.metadata),
                )
            )
        return restored

    @classmethod
    def complete_tool_history_messages(cls, messages: list[Message]) -> list[Message]:
        completed: list[Message] = []
        index = 0
        while index < len(messages):
            message = messages[index]
            tool_calls = message.metadata.get("tool_calls") if message.role == "assistant" else None
            if not tool_calls:
                if message.role != "tool":
                    completed.append(message)
                index += 1
                continue

            expected_ids = [
                str(call.get("id"))
                for call in tool_calls
                if isinstance(call, dict) and call.get("id")
            ]
            if not expected_ids:
                index += 1
                continue

            block = [message]
            found_ids: set[str] = set()
            scan = index + 1
            while scan < len(messages) and messages[scan].role == "tool":
                tool_message = messages[scan]
                tool_call_id = str(tool_message.tool_call_id or "")
                if tool_call_id in expected_ids:
                    block.append(tool_message)
                    found_ids.add(tool_call_id)
                scan += 1

            if all(call_id in found_ids for call_id in expected_ids):
                completed.extend(block)
            index = scan
        return completed

    @classmethod
    def limit_history_messages(cls, messages: list[Message], limit: int | None) -> list[Message]:
        if limit is None or limit < 0 or len(messages) <= limit:
            return messages

        limited: list[Message] = []
        index = len(messages) - 1
        while index >= 0 and len(limited) < limit:
            message = messages[index]
            if message.role != "tool":
                limited.append(message)
                index -= 1
                continue

            block_end = index
            expected_ids: set[str] = set()
            while index >= 0 and messages[index].role == "tool":
                if messages[index].tool_call_id:
                    expected_ids.add(str(messages[index].tool_call_id))
                index -= 1
            if index < 0:
                continue
            assistant = messages[index]
            tool_calls = assistant.metadata.get("tool_calls") if assistant.role == "assistant" else None
            assistant_ids = {
                str(call.get("id"))
                for call in tool_calls or []
                if isinstance(call, dict) and call.get("id")
            }
            if assistant_ids and assistant_ids.issubset(expected_ids):
                block = messages[index : block_end + 1]
                if len(limited) + len(block) <= limit:
                    limited.extend(reversed(block))
            index -= 1

        return list(reversed(limited))

    @classmethod
    def recent_turn_history_messages(cls, messages: list[Message], turns: int) -> list[Message]:
        if turns <= 0:
            return []

        selected: list[Message] = []
        seen_user_turns = 0
        index = len(messages) - 1
        while index >= 0:
            block_start = index
            if messages[index].role == "tool":
                while block_start >= 0 and messages[block_start].role == "tool":
                    block_start -= 1
                if block_start >= 0 and messages[block_start].role == "assistant":
                    block = messages[block_start : index + 1]
                    selected.extend(reversed(block))
                    index = block_start - 1
                    continue

            message = messages[index]
            selected.append(message)
            if message.role == "user":
                seen_user_turns += 1
                if seen_user_turns >= turns:
                    break
            index -= 1

        return list(reversed(selected))

    @classmethod
    def messages_token_count(cls, messages: list[Message]) -> int:
        return sum(cls.approx_token_count(message.content) for message in messages)

    @classmethod
    def trim_text_to_token_budget(cls, text: str, token_budget: int) -> str:
        if token_budget <= 0:
            return ""
        if cls.approx_token_count(text) <= token_budget:
            return text
        char_budget = max(token_budget * 4, 0)
        trimmed = text[:char_budget].rstrip()
        return f"{trimmed}\n\n[content trimmed to fit budget]"

    @staticmethod
    def approx_token_count(text: str) -> int:
        if not text:
            return 0
        return max(1, (len(text) + 3) // 4)
