from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.observability.metrics import init_default_metrics, metrics

EXPECTED_EMBEDDING_METRICS = {
    "embedding_tasks_started_total",
    "embedding_tasks_completed_total",
    "embedding_tasks_failed_total",
    "embedding_processing_seconds_total",
    "embedding_generation_jobs_total",
    "embedding_generation_batches_dispatched_total",
    "embedding_batches_processed_total",
    "embedding_batches_failed_total",
    "embedding_retries_total",
    "embedding_refresh_stale_total",
    "embedding_refresh_embedded_total",
    "embedding_cleanup_orphans_total",
    "embedding_cleanup_obsolete_total",
    "embedding_cleanup_batches_recovered_total",
    "embedding_cleanup_jobs_expired_total",
    "embedding_cleanup_metadata_total",
    "embedding_provider_usage_total",
    "embedding_versions_total",
    "embedding_storage_bytes",
    "embedding_dimension",
    "embedding_queue_backlog",
}


class TestEmbeddingSettings:
    def test_embedding_defaults(self) -> None:
        assert settings.EMBEDDING_BATCH_SIZE == 32
        assert settings.EMBEDDING_MAX_RETRIES == 2
        assert settings.EMBEDDING_CACHE_TTL == 86400
        assert settings.EMBEDDING_MAX_DIMENSION == 4096
        assert settings.EMBEDDING_CLEANUP_ORPHAN_DAYS == 30
        assert settings.EMBEDDING_REFRESH_STALE_DAYS == 7
        assert settings.MAX_EMBEDDING_QUEUE == 500
        assert settings.EMBEDDING_WORKER_CONCURRENCY == 4
        assert settings.EMBEDDING_REFRESH_INTERVAL == 900
        assert settings.EMBEDDING_CLEANUP_INTERVAL == 3600
        assert settings.EMBEDDING_BATCH_TIMEOUT == 300
        assert settings.EMBEDDING_JOB_STALE_SECONDS == 86400
        assert settings.EMBEDDING_MAINTENANCE_LIMIT == 200
        assert settings.EMBEDDING_OBSOLETE_VERSION_DAYS == 30
        assert settings.EMBEDDING_BATCH_MAX_RETRIES == 1

    def test_embedding_provider_falls_back_to_none(self) -> None:
        assert settings.EMBEDDING_PROVIDER is None or isinstance(
            settings.EMBEDDING_PROVIDER, str
        )
        assert settings.EMBEDDING_MODEL is None or isinstance(
            settings.EMBEDDING_MODEL, str
        )

    def test_env_example_documents_embedding_settings(self) -> None:
        p2 = Path(__file__).resolve().parents[2]
        p3 = Path(__file__).resolve().parents[3]
        env_example = p2 / ".env.example" if (p2 / ".env.example").exists() else p3 / ".env.example"
        content = env_example.read_text(encoding="utf-8")
        for field in ("EMBEDDING_PROVIDER", "EMBEDDING_BATCH_MAX_RETRIES"):
            assert f"EMBEDDING_{field}" in content or field in content


class TestEmbeddingMetricsRegistration:
    def test_all_embedding_metrics_registered(self) -> None:
        init_default_metrics()
        registered = set(metrics._help)
        missing = EXPECTED_EMBEDDING_METRICS - registered
        assert missing == set()

    def test_embedding_metrics_render_with_values(self) -> None:
        init_default_metrics()
        metrics.increment(
            "embedding_tasks_completed_total",
            task="eduvision.embedding.generate",
        )
        rendered = metrics.render()
        assert "embedding_tasks_completed_total" in rendered
