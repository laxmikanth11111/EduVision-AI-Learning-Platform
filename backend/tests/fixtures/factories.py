from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone

import factory


class BaseFactory(factory.Factory):
    class Meta:
        abstract = True

    id = factory.LazyFunction(uuid.uuid4)
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))
