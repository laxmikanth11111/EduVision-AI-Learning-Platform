"""Backward-compatible alias — prefer ``app.models.user_answer.UserAnswer``."""

from app.models.user_answer import UserAnswer as StudentAnswer  # noqa: F401

__all__ = ["StudentAnswer"]
