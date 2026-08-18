"""Background extraction flow for user preference memories."""

from __future__ import annotations

import json
import re
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from topic_pulse_v2.llm_call import LLMClient, Message
from topic_pulse_v2.memory import MemoryRecord, MemoryStore


PREFERENCE_MEMORY_TYPE = "preference"


@dataclass(slots=True)
class PreferenceMemoryExtractionRequest:
    """One completed chat turn that may contain reusable user preferences."""

    user_id: str
    user_message: str
    assistant_answer: str
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExtractedPreference:
    """A normalized preference candidate returned by the extractor."""

    content: str
    category: str = "other"
    confidence: float = 0.0
    importance: float = 0.0
    evidence: str = ""


@dataclass(slots=True)
class PreferenceMemoryExtractionResult:
    """Extraction result for one chat turn."""

    should_extract: bool
    saved: list[MemoryRecord] = field(default_factory=list)
    skipped: list[ExtractedPreference] = field(default_factory=list)
    reason: str = ""


class PreferenceMemoryExtractionProcess:
    """Extract stable user preferences after a ReAct turn finishes.

    This MVP focuses on preference memories only. It runs as a fire-and-forget
    background job from the chat loop, while keeping a synchronous `extract`
    method for tests and CLI diagnostics.
    """

    _INTENT_PATTERNS = (
        "记住",
        "以后",
        "下次",
        "默认",
        "偏好",
        "喜欢",
        "不喜欢",
        "不要",
        "别再",
        "习惯",
        "格式",
        "风格",
        "简洁",
        "详细",
        "表格",
        "时间线",
        "来源",
        "链接",
        "中文",
        "英文",
    )

    def __init__(
        self,
        *,
        llm_client: LLMClient,
        memory_store: MemoryStore,
        provider: str | None = None,
        model: str | None = None,
        max_workers: int = 1,
        min_confidence: float = 0.7,
        min_importance: float = 0.5,
    ) -> None:
        self._llm_client = llm_client
        self._memory_store = memory_store
        self._provider = provider
        self._model = model
        self._min_confidence = min_confidence
        self._min_importance = min_importance
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, max_workers),
            thread_name_prefix="preference-memory",
        )

    def schedule_after_turn(
        self,
        request: PreferenceMemoryExtractionRequest,
    ) -> Future[PreferenceMemoryExtractionResult]:
        """Run extraction in the background after a completed chat turn."""

        return self._executor.submit(self.extract, request)

    def extract(
        self,
        request: PreferenceMemoryExtractionRequest,
    ) -> PreferenceMemoryExtractionResult:
        """Synchronously extract and persist preference memories."""

        if not request.user_id:
            raise ValueError("user_id cannot be empty.")
        gate = self.should_extract(request)
        if not gate.should_extract:
            return gate

        existing = self._existing_preferences(request.user_id, request.user_message)
        candidates = self._extract_candidates(request, existing)
        saved: list[MemoryRecord] = []
        skipped: list[ExtractedPreference] = []
        seen = {self._normalize_memory_key(record.content) for record in existing}

        for candidate in candidates:
            key = self._normalize_memory_key(candidate.content)
            if (
                not candidate.content
                or candidate.confidence < self._min_confidence
                or candidate.importance < self._min_importance
                or key in seen
            ):
                skipped.append(candidate)
                continue
            seen.add(key)
            saved.append(
                self._memory_store.save(
                    request.user_id,
                    candidate.content,
                    metadata={
                        "type": PREFERENCE_MEMORY_TYPE,
                        "category": candidate.category,
                        "confidence": candidate.confidence,
                        "importance": candidate.importance,
                        "source": "preference_memory_extraction",
                        "source_session_id": request.session_id,
                        "evidence": candidate.evidence,
                    },
                )
            )

        return PreferenceMemoryExtractionResult(
            should_extract=True,
            saved=saved,
            skipped=skipped,
            reason="extracted_preferences",
        )

    def should_extract(
        self,
        request: PreferenceMemoryExtractionRequest,
    ) -> PreferenceMemoryExtractionResult:
        """Fast gate before spending an LLM call."""

        user_text = str(request.user_message or "").strip()
        if len(user_text) < 4:
            return PreferenceMemoryExtractionResult(False, reason="message_too_short")
        if _looks_sensitive(user_text) and not _has_explicit_memory_intent(user_text):
            return PreferenceMemoryExtractionResult(False, reason="sensitive_without_explicit_intent")
        if any(pattern in user_text for pattern in self._INTENT_PATTERNS):
            return PreferenceMemoryExtractionResult(True, reason="preference_intent_keyword")
        return PreferenceMemoryExtractionResult(False, reason="no_preference_signal")

    def _existing_preferences(self, user_id: str, query: str) -> list[MemoryRecord]:
        return self._memory_store.search(
            user_id,
            query,
            limit=20,
            metadata_filter={"type": PREFERENCE_MEMORY_TYPE},
        )

    def _extract_candidates(
        self,
        request: PreferenceMemoryExtractionRequest,
        existing: list[MemoryRecord],
    ) -> list[ExtractedPreference]:
        response = self._llm_client.call(
            [
                Message(
                    role="system",
                    content=(
                        "你是用户偏好记忆提取器。只提取未来对该用户有帮助、稳定、明确的偏好或约束。"
                        "不要提取一次性问题、普通新闻事实、寒暄、模型推测或敏感信息。"
                        "只输出 JSON 对象，格式为："
                        "{\"memories\":[{\"content\":\"...\",\"category\":\"style|source|topic_interest|workflow|constraint|other\","
                        "\"confidence\":0.0,\"importance\":0.0,\"evidence\":\"...\"}]}"
                    ),
                ),
                Message(
                    role="user",
                    content=json.dumps(
                        {
                            "user_message": request.user_message,
                            "assistant_answer": request.assistant_answer,
                            "existing_preferences": [
                                {
                                    "id": item.id,
                                    "content": item.content,
                                    "metadata": item.metadata,
                                }
                                for item in existing
                            ],
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                ),
            ],
            provider=self._provider,
            model=self._model,
            temperature=0,
            max_tokens=800,
            metadata={
                "task": "preference_memory_extraction",
                "session_id": request.session_id,
                **request.metadata,
            },
        )
        payload = _extract_json_object(response.content)
        items = payload.get("memories") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return []
        return [_preference_from_payload(item) for item in items if isinstance(item, dict)]

    @staticmethod
    def _normalize_memory_key(content: str) -> str:
        return re.sub(r"\s+", "", content).lower()


def _preference_from_payload(item: dict[str, Any]) -> ExtractedPreference:
    return ExtractedPreference(
        content=str(item.get("content") or "").strip(),
        category=str(item.get("category") or "other").strip() or "other",
        confidence=_float_between_zero_and_one(item.get("confidence")),
        importance=_float_between_zero_and_one(item.get("importance")),
        evidence=str(item.get("evidence") or "").strip(),
    )


def _float_between_zero_and_one(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, number))


def _extract_json_object(content: str) -> dict[str, Any] | None:
    stripped = str(content or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _has_explicit_memory_intent(text: str) -> bool:
    return any(pattern in text for pattern in ("记住", "保存", "记录", "以后", "默认"))


def _looks_sensitive(text: str) -> bool:
    return any(
        pattern in text
        for pattern in (
            "身份证",
            "银行卡",
            "密码",
            "手机号",
            "住址",
            "家庭地址",
            "病历",
            "诊断",
        )
    )
