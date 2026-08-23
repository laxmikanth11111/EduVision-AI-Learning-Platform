from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.storage.s3_adapter import S3StorageBackend, _is_local_endpoint


class TestLocalEndpointDetection:
    @pytest.mark.parametrize(
        ("endpoint", "expected"),
        [
            ("http://localhost:9000", True),
            ("https://127.0.0.1:9000", True),
            ("http://0.0.0.0:9000", True),
            ("http://[::1]:9000", True),
            ("https://minio.internal:9000", True),
            ("http://minio:9000", True),
            ("https://s3.amazonaws.com", False),
            ("https://s3.us-east-1.amazonaws.com", False),
            ("https://mycompany-s3.example.com", False),
            (None, False),
        ],
    )
    def test_detection(self, endpoint: str | None, expected: bool) -> None:
        assert _is_local_endpoint(endpoint) is expected


class TestS3TLSVerification:
    @pytest.mark.parametrize(
        ("use_ssl", "endpoint", "expect_verify_disabled"),
        [
            (True, "https://s3.amazonaws.com", False),
            (True, "http://localhost:9000", False),
            (False, "http://localhost:9000", True),
            (False, "https://minio.internal:9000", True),
            (False, "https://s3.amazonaws.com", False),
            (False, "https://s3.us-east-1.amazonaws.com", False),
            (False, None, False),
        ],
    )
    async def test_verify_flag(
        self,
        use_ssl: bool,
        endpoint: str | None,
        expect_verify_disabled: bool,
    ) -> None:
        backend = S3StorageBackend()
        captured: dict[str, object] = {}

        def fake_client(**kwargs: object) -> MagicMock:
            captured.update(kwargs)
            return MagicMock()

        with (
            patch.object(settings, "S3_USE_SSL", use_ssl),
            patch.object(settings, "S3_ENDPOINT_URL", endpoint),
            patch("app.storage.s3_adapter.boto3.client", side_effect=fake_client),
        ):
            await backend.initialize()

        if expect_verify_disabled:
            assert captured["verify"] is False
        else:
            assert "verify" not in captured
