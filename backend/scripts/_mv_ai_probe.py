"""Isolated diagnostic: call AIContentService.generate() exactly as lesson
generation does, then validate the raw text against LessonPayload.

Prints ONLY safe diagnostics (no keys/secrets/headers).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.service import AIContentService  # noqa: E402
from app.schemas.generated_lesson import LessonPayload  # noqa: E402
from app.services.lesson_prompt_builder import (  # noqa: E402
    LessonPromptBuilder,
    SourceContext,
    SourceTopic,
    SourceUnit,
)


def trunc(s: str | None, n: int = 1200) -> str:
    if s is None:
        return "<None>"
    return s if len(s) <= n else s[:n] + f"... [truncated, total {len(s)} chars]"


async def main() -> int:
    builder = LessonPromptBuilder()
    units = [
        SourceUnit(
            position=1,
            title="Photosynthesis",
            blocks=[],
            raw_text=(
                "Photosynthesis is the process by which plants convert light "
                "energy into chemical energy. Chlorophyll in leaves absorbs "
                "sunlight, and the plant combines water and carbon dioxide "
                "to produce glucose and oxygen."
            ),
        )
    ]
    topics = [SourceTopic(title="Photosynthesis", slide_ranges=[1])]
    source_context = SourceContext(
        title="Photosynthesis Basics",
        units=units,
        total_chars=len(units[0].raw_text or ""),
        topics=topics,
    )

    request = builder.build_ai_request(
        mode="slide",
        difficulty=None,
        language=None,
        title_override="Probe Lesson",
        source_context=source_context,
        metadata={"resource_type": "diagnostic_probe"},
    )

    service = AIContentService()
    print(f"provider={service.provider.name}")
    print(f"model={service.provider.model}")

    try:
        response = await service.generate(request)
    except Exception as exc:
        print("generate_status=FAILED")
        print(f"exception_type={type(exc).__name__}")
        print(f"exception_message={trunc(str(exc), 500)}")
        return 2

    print("generate_status=OK")
    print(f"response_type={type(response).__name__}")
    print(f"finish_reason={getattr(response.finish_reason, 'value', response.finish_reason)}")
    print(
        "usage="
        f"in={response.usage.input_tokens} out={response.usage.output_tokens}"
    )
    print("--- response.text ---")
    print(trunc(response.text))
    print("--- end response.text ---")

    try:
        raw = json.loads(response.text)
        print(f"json_parse=OK top_level_keys={sorted(raw.keys())}")
        if isinstance(raw, dict):
            for k in ("topics", "blocks"):
                v = raw.get(k)
                if isinstance(v, list) and v:
                    print(f"field '{k}' list item keys={sorted(v[0].keys()) if isinstance(v[0], dict) else type(v[0]).__name__}")
    except json.JSONDecodeError as exc:
        print(f"json_parse=FAILED ({exc})")

    try:
        payload = LessonPayload.model_validate_json(response.text)
        print(f"lesson_payload_validation=OK topics={len(payload.topics)}")
    except Exception as exc:
        print("lesson_payload_validation=FAILED")
        print(trunc(str(exc), 800))

    await service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
