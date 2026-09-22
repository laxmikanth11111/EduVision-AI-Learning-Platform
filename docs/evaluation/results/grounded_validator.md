# Grounded safety validator — recorded result

Module: `app/services/lesson_safety.py`
Default: `grounded` (`AI_LESSON_SAFETY_VALIDATOR` for lesson + quiz generation;
also the default when unset).
Tests: `tests/unit/test_lesson_prompt_builder.py` (33), `tests/unit/test_lesson_generation_service.py` (30)
(63 combined, including new grounded-validator coverage)

Commands:

```
.venv\Scripts\python.exe -m pytest tests/unit/test_lesson_prompt_builder.py tests/unit/test_lesson_generation_service.py -q --no-header --tb=short
.venv\Scripts\python.exe -m pytest tests/unit/test_lesson_generation_service.py tests/unit/test_topic_outline_service.py -q --no-header --tb=short
```

- Date: 2026-09-15
- **Result: all pass**

## Semantics

- Replaces the previous dead-config no-op: the configured name now maps through
  `build_safety_validator(name)` to `GroundedLessonSafetyValidator` ("grounded")
  or `NoopLessonSafetyValidator` ("noop"/None); unknown names raise
  `ConfigurationError` instead of silently degrading.
- **Input validation**: non-empty text required; prompt-injection scan
  (`is_reliably_flagged`) → `LessonSafetyError`.
- **Output validation**: rejects outputs with no topics; records a
  `source_coverage` estimate computed from the RAG context (stopword-normalized
  lexical overlap between context and generated content).
- `validate_output` returns the engineered lesson plus a
  `LessonSafetyReport` (validator name, topic count, source-coverage estimate).
- `_text_of(source_context)` handles `to_text()`, `units`, and single content
  unit forms so coverage works across slide/unit shapes.
- `local` deterministic provider + `grounded` validator combination means the
  full input→(RAG)→schema→safety loop is exercised without paid APIs in tests.