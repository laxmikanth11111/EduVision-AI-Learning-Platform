from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
    argon2__time_cost=3,
    argon2__memory_cost=65536,
    argon2__parallelism=4,
    argon2__type="ID",
)


def hash_password(password: str) -> str:
    hashed: str = pwd_context.hash(password)
    return hashed


def verify_password(plain_password: str, hashed_password: str) -> bool:
    valid: bool = pwd_context.verify(plain_password, hashed_password)
    return valid


def _jwt_secret() -> str:
    return settings.JWT_SECRET_KEY or settings.APP_SECRET_KEY


def create_access_token(
    user_id: uuid.UUID,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))

    claims = {
        "sub": str(user_id),
        "role": role,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "nbf": now,
        "exp": expire,
        "aud": settings.JWT_AUDIENCE,
        "iss": settings.JWT_ISSUER,
        "type": "access",
    }
    token: str = jwt.encode(
        claims,
        _jwt_secret(),
        algorithm=settings.JWT_ALGORITHM,
    )
    return token


def create_refresh_token(
    user_id: uuid.UUID,
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))

    claims = {
        "sub": str(user_id),
        "jti": str(uuid.uuid4()),
        "iat": now,
        "nbf": now,
        "exp": expire,
        "aud": settings.JWT_AUDIENCE,
        "iss": settings.JWT_ISSUER,
        "type": "refresh",
    }
    token: str = jwt.encode(
        claims,
        _jwt_secret(),
        algorithm=settings.JWT_ALGORITHM,
    )
    return token


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
            options={"require": ["sub", "role", "type", "jti"]},
        )
        if payload.get("type") != "access":
            raise JWTError("Invalid token type")
        return payload
    except JWTError as e:
        logger.warning("access_token_decode_failed", error=str(e))
        raise


def decode_refresh_token(token: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
            options={"require": ["sub", "jti", "type"]},
        )
        if payload.get("type") != "refresh":
            raise JWTError("Invalid token type")
        return payload
    except JWTError as e:
        logger.warning("refresh_token_decode_failed", error=str(e))
        raise


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_verification_token() -> str:
    return secrets.token_urlsafe(48)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def validate_csrf_token(cookie_token: str, header_token: str) -> bool:
    return hmac.compare_digest(cookie_token, header_token)
