"""Versioned prompt construction for the AI learning assistant (Phase 4D.6).

Owns the system behaviour, the conversation formatting rules and the
deterministic ``prompt_hash`` used to pin the exact context/prompt revision a
turn was answered from. Bumping ``PROMPT_VERSION`` or ``CONTEXT_SCHEMA_VERSION``
records provenance on every turn without requiring a migration. Raw prompt
content is never logged.
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.ai.models import AIMessage, AIRequest, AIResponseFormat

PROMPT_VERSION = "1"
CONTEXT_SCHEMA_VERSION = "1"

SYSTEM_BEHAVIOR = (
    "You are the AI learning assistant inside EduVision AI, helping a learner "
    "understand a lesson they are currently studying. You answer in clear, "
    "well-structured markdown. You only ever use the context provided below; "
    "you never invent facts, URLs, citations or lesson content that is not in "
    "the context. When the context is missing a detail, say so plainly. Keep "
    "answers concise and focused on the learner's question. Never repeat the "
    "same point more than once. Do not answer questions unrelated to the "
    "learner's learning material."
)


class AssistantPromptBuilder:
    @staticmethod
    def format_history(history: list[AIMessage]) -> str:
        if not history:
            return "(no previous messages)"
        return "\n".join(f"[{msg.role}] {msg.content}" for msg in history)

    def build_ai_request(
        self,
        *,
        context_text: str,
        history: list[AIMessage],
        user_message: str,
        metadata: dict[str, Any],
        max_tokens: int,
        model_override: str | None = None,
    ) -> AIRequest:
        system_prompt = "\n".join(
            [
                SYSTEM_BEHAVIOR,
                f"Prompt version: {PROMPT_VERSION}.",
                f"Context schema version: {CONTEXT_SCHEMA_VERSION}.",
                "--- CONTEXT (frozen, do not infer anything outside it) ---",
                context_text or "(empty context)",
                "--- END CONTEXT ---",
            ]
        )
        user_prompt = "\n".join(
            [
                "--- CONVERSATION SO FAR ---",
                self.format_history(history),
                "--- END CONVERSATION ---",
                "",
                "Learner question:",
                user_message,
            ]
        )
        return AIRequest(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            messages=history,
            response_format=AIResponseFormat.MARKDOWN,
            max_tokens=max_tokens,
            metadata=metadata,
            model_override=model_override,
        )

    def prompt_hash(
        self,
        *,
        context_text: str,
        history_count: int,
        user_message: str,
    ) -> str:
        payload = "\n".join(
            [
                PROMPT_VERSION,
                CONTEXT_SCHEMA_VERSION,
                context_text,
                str(history_count),
                user_message,
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
