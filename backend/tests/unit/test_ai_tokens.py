from __future__ import annotations

from app.ai.tokens import estimate_request_tokens, estimate_tokens


class TestEstimateTokens:
    def test_empty_text_is_zero(self) -> None:
        assert estimate_tokens("") == 0
        assert estimate_tokens("   ") == 0

    def test_single_word(self) -> None:
        assert estimate_tokens("hello") == 2

    def test_two_words(self) -> None:
        assert estimate_tokens("hello world") == 3

    def test_punctuation_counts(self) -> None:
        assert estimate_tokens("hello world.") == 4

    def test_deterministic(self) -> None:
        assert estimate_tokens("The quick brown fox jumps over the lazy dog") == (
            estimate_tokens("The quick brown fox jumps over the lazy dog")
        )

    def test_never_zero_for_nonempty(self) -> None:
        assert estimate_tokens("a") >= 1


class TestEstimateRequestTokens:
    def test_user_only(self) -> None:
        user_tokens = estimate_tokens("explain gravity")
        assert estimate_request_tokens("explain gravity") == user_tokens

    def test_system_and_user(self) -> None:
        expected = estimate_tokens("you are a tutor") + estimate_tokens("explain gravity")
        assert estimate_request_tokens("explain gravity", system_prompt="you are a tutor") == expected

    def test_messages_summed(self) -> None:
        expected = estimate_tokens("final") + estimate_tokens("prior")
        assert estimate_request_tokens(
            "final", messages=[{"role": "user", "content": "prior"}]
        ) == expected
