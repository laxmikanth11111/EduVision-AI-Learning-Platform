"""TrustedHost allow-list derivation.

``TrustedHostMiddleware`` matches the bare hostname from the ``Host`` header
(``host == pattern`` in ``starlette.middleware.trustedhost``), but the app used
to build its allow-list by appending ``APP_CORS_ORIGINS`` verbatim. Those are
full origins such as ``https://app.example.com``, which can never match a
hostname.

Local development kept working only because ``localhost``/``127.0.0.1`` were
hardcoded alongside them, so the defect was invisible until a real domain was
configured -- at which point every request would have returned
``400 Invalid host header``.
"""

from __future__ import annotations

from app.core.config import Settings, settings


def _settings(origins: str) -> Settings:
    return Settings(APP_CORS_ORIGINS=origins)  # type: ignore[call-arg]


def test_production_origin_hostname_is_allowed() -> None:
    hosts = _settings("https://app.example.com").trusted_hosts_list
    assert "app.example.com" in hosts
    assert "https://app.example.com" not in hosts


def test_localhost_origins_do_not_leak_into_allow_list() -> None:
    hosts = _settings("http://localhost:3000,http://localhost:8000").trusted_hosts_list
    assert "http://localhost:3000" not in hosts
    assert "localhost" in hosts
    assert hosts.count("localhost") == 1


def test_wildcard_origin_is_preserved() -> None:
    hosts = _settings("https://*.example.com").trusted_hosts_list
    assert "*.example.com" in hosts


def test_port_is_stripped_from_host() -> None:
    hosts = _settings("https://app.example.com:8443").trusted_hosts_list
    assert "app.example.com" in hosts
    assert "app.example.com:8443" not in hosts


def test_base_hosts_always_present() -> None:
    for expected in ("localhost", "127.0.0.1", "[::1]", "backend", "testserver"):
        assert expected in settings.trusted_hosts_list


def test_every_cors_origin_contributes_exactly_one_host() -> None:
    s = _settings("https://a.example.com,https://b.example.com,http://localhost:3000")
    hosts = s.trusted_hosts_list
    for expected in ("a.example.com", "b.example.com", "localhost"):
        assert hosts.count(expected) == 1


def test_cors_origins_list_is_unchanged() -> None:
    """CORS still needs full origins; only the host allow-list is reduced."""
    s = _settings("https://app.example.com,http://localhost:3000")
    assert s.cors_origins_list == ["https://app.example.com", "http://localhost:3000"]
