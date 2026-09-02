from __future__ import annotations

from app.observability.metrics import DEFAULT_HISTOGRAM_BUCKETS, MetricsRegistry


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

    def test_histogram_observe_populates_buckets_sum_count(self) -> None:
        registry = MetricsRegistry()
        registry.register("http_requests_duration_seconds", "HTTP request duration histogram.")
        registry.set_histogram_buckets("http_requests_duration_seconds", DEFAULT_HISTOGRAM_BUCKETS)
        registry.observe("http_requests_duration_seconds", 0.05, method="GET")
        registry.observe("http_requests_duration_seconds", 1.5, method="GET")
        rendered = registry.render()
        assert "# TYPE http_requests_duration_seconds histogram" in rendered
        assert 'http_requests_duration_seconds_bucket{le="0.05",method="GET"} 1' in rendered
        assert 'http_requests_duration_seconds_bucket{le="0.1",method="GET"} 1' in rendered
        assert 'http_requests_duration_seconds_bucket{le="0.25",method="GET"} 1' in rendered
        assert 'http_requests_duration_seconds_bucket{le="2.5",method="GET"} 2' in rendered
        assert 'http_requests_duration_seconds_bucket{le="+Inf",method="GET"} 2' in rendered
        assert 'http_requests_duration_seconds_sum{method="GET"} 1.55' in rendered
        assert 'http_requests_duration_seconds_count{method="GET"} 2' in rendered

    def test_histogram_clamps_negative_values(self) -> None:
        registry = MetricsRegistry()
        registry.register("http_requests_duration_seconds", "Histogram.")
        registry.observe("http_requests_duration_seconds", -3.0)
        rendered = registry.render()
        assert 'http_requests_duration_seconds_bucket{le="0.005"} 1' in rendered
        assert 'http_requests_duration_seconds_bucket{le="+Inf"} 1' in rendered
        assert "http_requests_duration_seconds_sum 0" in rendered
        assert "http_requests_duration_seconds_count 1" in rendered

    def test_histogram_without_explicit_buckets_uses_defaults(self) -> None:
        registry = MetricsRegistry()
        registry.register("latency", "Default buckets.")
        registry.observe("latency", 0.001)
        rendered = registry.render()
        assert 'latency_bucket{le="0.005"} 1' in rendered
        assert 'latency_bucket{le="+Inf"} 1' in rendered

    def test_histogram_multiple_label_series_are_independent(self) -> None:
        registry = MetricsRegistry()
        registry.register("task_duration", "Per-task duration.")
        registry.observe("task_duration", 0.5, task_name="a")
        registry.observe("task_duration", 2.0, task_name="b")
        rendered = registry.render()
        assert 'task_duration_bucket{le="0.5",task_name="a"} 1' in rendered
        assert 'task_duration_bucket{le="1.0",task_name="a"} 1' in rendered
        assert 'task_duration_bucket{le="1.0",task_name="b"} 0' in rendered
        assert 'task_duration_bucket{le="2.5",task_name="b"} 1' in rendered
