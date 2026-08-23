from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from jose import JWTError, jwt

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    generate_csrf_token,
    generate_verification_token,
    hash_password,
    hash_token,
    validate_csrf_token,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify(self) -> None:
        password = "TestPass123"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed) is True

    def test_verify_wrong_password(self) -> None:
        hashed = hash_password("TestPass123")
        assert verify_password("WrongPass123", hashed) is False

    def test_hash_is_deterministically_different(self) -> None:
        password = "TestPass123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True

    def test_empty_password(self) -> None:
        hashed = hash_password("")
        assert verify_password("", hashed) is True

    def test_argon2_backend_available(self) -> None:
        from app.core.security import pwd_context

        assert "argon2" in pwd_context.schemes()
        hashed = pwd_context.hash("TestPass123", scheme="argon2")
        assert hashed.startswith("$argon2")
        assert pwd_context.verify("TestPass123", hashed)


class TestRuntimeDependencyDeclared:
    """Guard against the undeclared argon2-cffi runtime dependency (HIGH)."""

    def _project_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def test_argon2_cffi_declared_in_requirements(self) -> None:
        content = (self._project_root() / "requirements.txt").read_text(encoding="utf-8")
        assert re.search(
            r"^\s*argon2-cffi\b", content, re.MULTILINE
        ), "argon2-cffi must be declared in backend/requirements.txt"

    def test_argon2_cffi_declared_in_pyproject(self) -> None:
        content = (self._project_root() / "pyproject.toml").read_text(encoding="utf-8")
        assert re.search(
            r"argon2-cffi", content
        ), "argon2-cffi must be declared in backend/pyproject.toml"


class TestJWT:
    def test_create_and_decode_access_token(self) -> None:
        user_id = uuid.uuid4()
        token = create_access_token(user_id, "user")
        payload = decode_access_token(token)
        assert payload["sub"] == str(user_id)
        assert payload["role"] == "user"
        assert payload["type"] == "access"
        assert "jti" in payload
        assert "iat" in payload
        assert "nbf" in payload
        assert "exp" in payload
        assert payload["aud"] == settings.JWT_AUDIENCE
        assert payload["iss"] == settings.JWT_ISSUER

    def test_create_and_decode_refresh_token(self) -> None:
        user_id = uuid.uuid4()
        token = create_refresh_token(user_id)
        payload = decode_refresh_token(token)
        assert payload["sub"] == str(user_id)
        assert payload["type"] == "refresh"
        assert "jti" in payload

    def test_access_token_rejects_refresh_token(self) -> None:
        user_id = uuid.uuid4()
        token = create_refresh_token(user_id)
        with pytest.raises(JWTError):
            decode_access_token(token)

    def test_refresh_token_rejects_access_token(self) -> None:
        user_id = uuid.uuid4()
        token = create_access_token(user_id, "creator")
        with pytest.raises(JWTError):
            decode_refresh_token(token)

    def test_access_token_expired(self) -> None:
        user_id = uuid.uuid4()
        with patch.object(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", -1):
            token = create_access_token(user_id, "user")
        with pytest.raises(JWTError):
            decode_access_token(token)

    def test_access_token_different_jti(self) -> None:
        user_id = uuid.uuid4()
        token1 = create_access_token(user_id, "user")
        token2 = create_access_token(user_id, "user")
        payload1 = decode_access_token(token1)
        payload2 = decode_access_token(token2)
        assert payload1["jti"] != payload2["jti"]

    def test_custom_expiry(self) -> None:
        user_id = uuid.uuid4()
        token = create_access_token(user_id, "admin", timedelta(hours=1))
        payload = decode_access_token(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        assert exp > datetime.now(UTC) + timedelta(minutes=59)

    def test_tampered_token(self) -> None:
        user_id = uuid.uuid4()
        token = create_access_token(user_id, "user")
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(JWTError):
            decode_access_token(tampered)


class TestTokenHashing:
    def test_hash_token(self) -> None:
        token = "some-secret-token-value"
        hashed = hash_token(token)
        assert isinstance(hashed, str)
        assert len(hashed) == 64
        assert hash_token(token) == hashed

    def test_hash_token_different(self) -> None:
        assert hash_token("token-a") != hash_token("token-b")

    def test_generate_verification_token(self) -> None:
        token = generate_verification_token()
        assert len(token) > 32
        assert generate_verification_token() != token


class TestCSRF:
    def test_generate_csrf_token(self) -> None:
        token = generate_csrf_token()
        assert len(token) > 10
        assert isinstance(token, str)

    def test_validate_csrf_token(self) -> None:
        token = generate_csrf_token()
        assert validate_csrf_token(token, token) is True

    def test_validate_csrf_token_mismatch(self) -> None:
        token1 = generate_csrf_token()
        token2 = generate_csrf_token()
        assert validate_csrf_token(token1, token2) is False

    def test_validate_csrf_token_empty(self) -> None:
        token = generate_csrf_token()
        assert validate_csrf_token(token, "") is False
        assert validate_csrf_token("", token) is False
