from __future__ import annotations

from app.observability.metrics import MetricsRegistry


class TestMetricsRegistry:
    def test_counter_accumulates_with_labels(self) -> None:
        registry = MetricsRegistry()
        registry.increment("http_requests_total", method="GET", path="/x")
        registry.increment("http_requests_total", method="GET", path="/x")
        registry.increment("http_requests_total", method="POST", path="/x")
        rendered = registry.render()
        assert 'http_requests_total{method="GET",path="/x"} 2' in rendered
        assert 'http_requests_total{method="POST",path="/x"} 1' in rendered

    def test_gauge_set(self) -> None:
        registry = MetricsRegistry()
        registry.set_gauge("active_connections", 3)
        registry.set_gauge("active_connections", 5)
        rendered = registry.render()
        assert "active_connections 5" in rendered

    def test_help_and_type_lines(self) -> None:
        registry = MetricsRegistry()
        registry.register("http_requests_total", "Total HTTP requests.")
        registry.increment("http_requests_total", path="/health")
        rendered = registry.render()
        assert "# HELP http_requests_total Total HTTP requests." in rendered
        assert "# TYPE http_requests_total counter" in rendered

    def test_empty_registry_renders_empty(self) -> None:
        registry = MetricsRegistry()
        assert registry.render() == ""
