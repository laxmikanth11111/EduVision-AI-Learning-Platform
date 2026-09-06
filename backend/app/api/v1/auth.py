"""Authentication endpoints: register, login, logout, Google OAuth."""

from __future__ import annotations

import secrets
import time
import urllib.parse
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.database.session import get_session
from app.models.user import User
from app.schemas.auth import AuthResponse, AuthTokens, LoginRequest, RegisterRequest, UserResponse

logger = get_logger(__name__)

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])

# In-memory revoked token JTI set (fallback when Redis is unavailable).
# Primary store is Redis so revocation is shared across app instances.
_revoked_refresh_jtis: set[str] = set()
_REVOKED_REFRESH_KEY_PREFIX = "eduvision:auth:revoked:refresh:"

# In-memory OAuth state store with TTL (fallback when Redis is unavailable;
# primary store is Redis so multiple app instances share state)
_oauth_states: dict[str, float] = {}
_OAUTH_STATE_TTL_SECONDS = 600  # 10 minutes
_OAUTH_STATE_KEY_PREFIX = "eduvision:oauth:state:"


def _revoked_refresh_ttl() -> int:
    """TTL for a revoked refresh token JTI (lifetime of a refresh token)."""
    return max(settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, 1)


async def _revoke_refresh_jti(jti: str) -> None:
    """Persist a revoked refresh token JTI (Redis with in-memory fallback)."""
    try:
        from redis.asyncio import Redis as AsyncRedis

        from app.workers.redis_client import get_redis_pool

        pool = await get_redis_pool()
        redis = AsyncRedis(connection_pool=pool)
        await redis.set(
            f"{_REVOKED_REFRESH_KEY_PREFIX}{jti}",
            "",
            ex=_revoked_refresh_ttl(),
        )
        return
    except Exception:
        from app.observability.metrics import metrics

        metrics.increment("redis_errors_total", operation="auth_revocation")
    _revoked_refresh_jtis.add(jti)


async def _is_refresh_jti_revoked(jti: str) -> bool:
    """Return True if a refresh token JTI has been revoked."""
    try:
        from redis.asyncio import Redis as AsyncRedis

        from app.workers.redis_client import get_redis_pool

        pool = await get_redis_pool()
        redis = AsyncRedis(connection_pool=pool)
        exists = await redis.exists(f"{_REVOKED_REFRESH_KEY_PREFIX}{jti}")
        return bool(exists)
    except Exception:
        from app.observability.metrics import metrics

        metrics.increment("redis_errors_total", operation="auth_revocation_check")
    return jti in _revoked_refresh_jtis


async def _store_oauth_state(state: str) -> None:
    try:
        from redis.asyncio import Redis as AsyncRedis

        from app.workers.redis_client import get_redis_pool

        pool = await get_redis_pool()
        redis = AsyncRedis(connection_pool=pool)
        await redis.set(
            f"{_OAUTH_STATE_KEY_PREFIX}{state}",
            repr(time.time()),
            ex=_OAUTH_STATE_TTL_SECONDS,
        )
        return
    except Exception:
        from app.observability.metrics import metrics

        metrics.increment("redis_errors_total", operation="oauth_state_store")
    _oauth_states[state] = time.time()


async def _consume_oauth_state(state: str) -> bool:
    """Validate and consume an OAuth state token atomically. Returns True if valid."""
    try:
        from redis.asyncio import Redis as AsyncRedis

        from app.workers.redis_client import get_redis_pool

        pool = await get_redis_pool()
        redis = AsyncRedis(connection_pool=pool)
        value = await redis.getdel(f"{_OAUTH_STATE_KEY_PREFIX}{state}")
        if value is not None:
            return (time.time() - float(value)) < _OAUTH_STATE_TTL_SECONDS
    except Exception:
        from app.observability.metrics import metrics

        metrics.increment("redis_errors_total", operation="oauth_state_consume")
    if state not in _oauth_states:
        return False
    created_at = _oauth_states.pop(state)
    return (time.time() - created_at) < _OAUTH_STATE_TTL_SECONDS


def _issue_tokens(user: User) -> AuthTokens:
    return AuthTokens(
        access_token=create_access_token(user.id, role="user"),
        refresh_token=create_refresh_token(user.id),
    )


def _user_response(user: User) -> UserResponse:
    return UserResponse(id=str(user.id), email=user.email, name=user.name)


def _set_auth_cookies(response: Response, tokens: AuthTokens) -> None:
    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAME_SITE,
        path=settings.COOKIE_PATH,
    )
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAME_SITE,
        path=settings.COOKIE_PATH,
    )


@auth_router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    request: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    existing = await session.execute(
        select(User).where(User.email == request.email.lower())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=request.email.lower(),
        password_hash=hash_password(request.password),
        name=request.name,
    )
    session.add(user)
    await session.flush()
    # Commit before issuing tokens: the response can reach the client before
    # get_session's teardown commit runs, and an immediate authenticated call
    # would then race the INSERT and fail with 401 "User not found.".
    await session.commit()
    logger.info("user_registered", user_id=str(user.id), email=user.email)

    tokens = _issue_tokens(user)
    return AuthResponse(user=_user_response(user), tokens=tokens)


@auth_router.post(
    "/login",
    response_model=AuthResponse,
)
async def login(
    request: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    result = await session.execute(
        select(User).where(User.email == request.email.lower())
    )
    user = result.scalar_one_or_none()
    if not user or not user.password_hash or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    tokens = _issue_tokens(user)
    _set_auth_cookies(response, tokens)
    logger.info("user_logged_in", user_id=str(user.id))
    return AuthResponse(user=_user_response(user), tokens=tokens)


@auth_router.post("/logout")
async def logout(
    response: Response,
    request: Request,
) -> dict[str, str]:
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        try:
            payload = decode_refresh_token(refresh_token)
            await _revoke_refresh_jti(payload["jti"])
        except Exception:
            pass

    response.delete_cookie("access_token", path=settings.COOKIE_PATH)
    response.delete_cookie("refresh_token", path=settings.COOKIE_PATH)
    return {"message": "Logged out successfully."}


@auth_router.get("/providers")
async def auth_providers() -> dict[str, bool]:
    """Public list of enabled sign-in providers so the UI can hide unconfigured ones."""
    return {"google": bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)}


@auth_router.get("/google")
async def google_login() -> RedirectResponse:
    if not settings.GOOGLE_CLIENT_ID:
        # Friendly in-app notice instead of a raw JSON error page.
        return RedirectResponse(
            url="/frontend/signin.html?google_error=not_configured",
            status_code=status.HTTP_302_FOUND,
        )

    state = secrets.token_urlsafe(32)
    await _store_oauth_state(state)
    params = urllib.parse.urlencode({
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    })
    return RedirectResponse(
        url=f"https://accounts.google.com/o/oauth2/v2/auth?{params}",
        status_code=status.HTTP_302_FOUND,
    )


@auth_router.get("/google/callback")
async def google_callback(
    code: str = Query(...),
    state: str | None = Query(None),
    error: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Google OAuth error: {error}")

    if not state or not await _consume_oauth_state(state):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or expired OAuth state parameter.")

    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured.",
        )

    import httpx

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to exchange Google authorization code.",
            )
        tokens_data = token_resp.json()

        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tokens_data['access_token']}"},
        )
        if userinfo_resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to fetch Google user info.",
            )
        google_user = userinfo_resp.json()

    google_id = google_user["id"]
    email = google_user.get("email", "").lower()
    name = google_user.get("name", email.split("@")[0])

    result = await session.execute(
        select(User).where((User.google_id == google_id) | (User.email == email))
    )
    user = result.scalar_one_or_none()

    if user:
        if not user.google_id:
            user.google_id = google_id
        if not user.name:
            user.name = name
    else:
        user = User(
            email=email,
            google_id=google_id,
            name=name,
        )
        session.add(user)

    await session.flush()
    # Commit before redirecting: upload.html authenticates immediately and
    # would otherwise race this INSERT (same race as /auth/register).
    await session.commit()
    logger.info("google_oauth_success", user_id=str(user.id), email=email)

    tokens = _issue_tokens(user)

    redirect_url = "/frontend/upload.html"
    redirect_response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    # Cookies MUST go on the returned RedirectResponse: FastAPI discards the
    # injected Response when the handler returns its own Response object.
    _set_auth_cookies(redirect_response, tokens)
    return redirect_response


@auth_router.get("/me", response_model=UserResponse)
async def get_me(
    user: User = Depends(get_current_user),
) -> UserResponse:
    return _user_response(user)


@auth_router.post("/refresh", response_model=AuthTokens)
async def refresh_tokens(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AuthTokens:
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token provided.",
        )

    try:
        payload = decode_refresh_token(refresh_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

    if await _is_refresh_jti_revoked(payload["jti"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked.",
        )

    user_id = uuid.UUID(payload["sub"])
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")

    new_tokens = _issue_tokens(user)
    _set_auth_cookies(response, new_tokens)
    return new_tokens
