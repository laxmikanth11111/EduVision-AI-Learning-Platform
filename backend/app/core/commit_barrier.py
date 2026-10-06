"""Commit-before-response barrier for request-scoped database sessions.

Why this exists
---------------
FastAPI executes the exit code of a ``yield`` dependency only *after* the
response has been handed to the ASGI server. In
``fastapi.routing.request_response`` the ordering is::

    async with AsyncExitStack() as request_stack:   # owns the dependencies
        response = await f(request)                 # endpoint runs
        await response(scope, receive, send)        # <-- response leaves here
    # request_stack unwinds only now -> dependency teardown -> COMMIT

A request-scoped transaction that commits in that teardown is therefore still
open when the client is told the request succeeded. A client that immediately
follows up on another connection sees the pre-commit snapshot, which for a
freshly created resource means::

    POST -> 201 Created
    immediate GET -> 404 Not Found
    (a moment later) -> the resource exists

How this fixes it
-----------------
The ASGI ``send`` channel is the exact moment a client first learns the outcome
of a request, so that is where the commit belongs.
:class:`CommitBarrierMiddleware` sits just inside the other middleware and, on
the response head of a successful reply, commits the request's transaction
before forwarding that head upstream. A dependency publishes its commit callable
into the request scope with :func:`publish_commit_hook`.

Safety properties:

* Only successful replies (``status < 400``) trigger a commit. A handler that
  raises unwinds its own dependency stack first -- rolling back and clearing the
  hook -- so the error path is untouched.
* The second commit that dependency teardown still performs is free: with
  nothing invoked on the session since the previous ``commit()``, SQLAlchemy
  opens an internal-only "logical" transaction that never reaches the database.
* A request that published no hook (Celery, dependency overrides in tests,
  unmounted paths) behaves exactly as before.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request

# Key under which a request-scoped dependency publishes its commit callable.
COMMIT_HOOK_SCOPE_KEY = "eduvision.commit_hook"

CommitHook = Callable[[], Awaitable[None]]

# Responses at or above this status are treated as unsuccessful: their handler
# did not complete, so its transaction must roll back rather than commit.
_SUCCESS_CEILING = 400


def publish_commit_hook(request: Request, commit: CommitHook) -> None:
    """Register ``commit`` as the request's pre-response commit hook."""
    request.scope[COMMIT_HOOK_SCOPE_KEY] = commit


def clear_commit_hook(request: Request) -> None:
    """Remove a previously published commit hook from the request scope."""
    request.scope.pop(COMMIT_HOOK_SCOPE_KEY, None)


class CommitBarrierMiddleware:
    """Commit the request transaction before the client observes success."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, object],
        receive: Callable[..., Awaitable[dict[str, object]]],
        send: Callable[..., Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_commit_barrier(message: dict[str, object]) -> None:
            if message.get("type") == "http.response.start":
                status = int(message.get("status", 0))  # type: ignore[call-overload]
                if status < _SUCCESS_CEILING:
                    commit_hook = scope.get(COMMIT_HOOK_SCOPE_KEY)
                    if commit_hook is not None:
                        await commit_hook()  # type: ignore[misc]
            await send(message)

        await self.app(scope, receive, send_with_commit_barrier)