"""Unit tests for authentication hardening.

Covers the account lockout on repeated failed logins (Redis-first with
in-memory fallback) and refresh-token rotation with reuse detection. The Redis
pool is patched to raise so every path exercises the non-network fallback
deterministically and without waiting on connection timeouts.
"""

from __future__ import annotations

import pytest

import app.api.v1.auth as auth


@pytest.fixture(autouse=True)
def _redis_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the in-memory fallback for every Redis-backed auth helper."""

    async def _raise_pool():
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr("app.workers.redis_client.get_redis_pool", _raise_pool)
    monkeypatch.setattr(auth, "_revoked_refresh_jtis", set())
    monkeypatch.setattr(auth, "_login_failure_counts", {})
    monkeypatch.setattr(auth, "_login_failure_deadlines", {})


class TestLoginFailureLockout:
    @pytest.mark.asyncio
    async def test_below_limit_is_not_locked(self) -> None:
        assert await auth._is_login_locked("learner@example.com") is False
        await auth._record_login_failure("learner@example.com")
        await auth._record_login_failure("learner@example.com")
        assert await auth._is_login_locked("learner@example.com") is False

    @pytest.mark.asyncio
    async def test_limit_reached_locks_and_clear_resets(self) -> None:
        for _ in range(auth.settings.MAX_LOGIN_ATTEMPTS):
            await auth._record_login_failure("locked@example.com")
        assert await auth._is_login_locked("locked@example.com") is True

        await auth._clear_login_failures("locked@example.com")
        assert await auth._is_login_locked("locked@example.com") is False

    @pytest.mark.asyncio
    async def test_expired_window_unlocks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auth, "_login_failure_deadlines", {"stale@example.com": 1.0})
        monkeypatch.setattr(auth, "_login_failure_counts", {"stale@example.com": 99})
        assert await auth._is_login_locked("stale@example.com") is False

    @pytest.mark.asyncio
    async def test_lockout_is_per_account(self) -> None:
        for _ in range(auth.settings.MAX_LOGIN_ATTEMPTS):
            await auth._record_login_failure("one@example.com")
        assert await auth._is_login_locked("one@example.com") is True
        assert await auth._is_login_locked("two@example.com") is False

    @pytest.mark.asyncio
    async def test_login_endpoint_locks_after_repeated_failures(
        self, client: object
    ) -> None:
        # A fresh account; wrong password MAX_LOGIN_ATTEMPTS times -> 429.
        email = "lockout@example.com"
        reg = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Str0ng!pass", "name": "Lock"},
        )
        assert reg.status_code == 201

        for _ in range(auth.settings.MAX_LOGIN_ATTEMPTS):
            bad = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "wrong-password"},
            )
            assert bad.status_code == 401

        blocked = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "Str0ng!pass"},
        )
        assert blocked.status_code == 429

    @pytest.mark.asyncio
    async def test_successful_login_clears_failures(self) -> None:
        email = "recover@example.com"
        for _ in range(auth.settings.MAX_LOGIN_ATTEMPTS - 1):
            await auth._record_login_failure(email)
        assert await auth._is_login_locked(email) is False

        # Simulate the endpoint doing its clear on success.
        await auth._clear_login_failures(email)
        assert await auth._is_login_locked(email) is False
        await auth._record_login_failure(email)
        assert await auth._is_login_locked(email) is False


class TestRefreshTokenRotation:
    @pytest.mark.asyncio
    async def test_refresh_rotates_presented_token(
        self, client: object
    ) -> None:
        email = "rotate@example.com"
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Str0ng!pass", "name": "Rotate"},
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "Str0ng!pass"},
        )
        assert login.status_code == 200
        body = login.json()
        old_refresh = body["tokens"]["refresh_token"]
        old_jti = auth.decode_refresh_token(old_refresh)["jti"]

        refreshed = await client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": old_refresh},
        )
        assert refreshed.status_code == 200
        # The presented token must be revoked the moment a new one is issued.
        assert await auth._is_refresh_jti_revoked(old_jti) is True

    @pytest.mark.asyncio
    async def test_reusing_rotated_token_is_rejected(
        self, client: object
    ) -> None:
        email = "reuse@example.com"
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Str0ng!pass", "name": "Reuse"},
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "Str0ng!pass"},
        )
        old_refresh = login.json()["tokens"]["refresh_token"]

        first = await client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": old_refresh},
        )
        assert first.status_code == 200

        replay = await client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": old_refresh},
        )
        assert replay.status_code == 401

    @pytest.mark.asyncio
    async def test_no_cookie_returns_401(self, client: object) -> None:
        resp = await client.post("/api/v1/auth/refresh")
        assert resp.status_code == 401
