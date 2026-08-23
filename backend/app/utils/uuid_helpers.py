from __future__ import annotations

import uuid


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def uuid_to_str(value: uuid.UUID) -> str:
    return str(value)


def str_to_uuid(value: str) -> uuid.UUID:
    return uuid.UUID(value)
