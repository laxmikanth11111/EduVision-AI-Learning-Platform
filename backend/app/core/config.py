from __future__ import annotations

from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__",
    )

    # ── Application ──────────────────────────────────────────────────────────
    APP_NAME: str = "EduVision AI"
    APP_VERSION: str = "1.0.0"
    APP_ENV: Annotated[str, Field(description="one of: development, staging, production, test")] = "development"
    APP_DEBUG: bool = True
    APP_SECRET_KEY: Annotated[str, Field(min_length=32)] = "CHANGE-ME-TO-A-RANDOM-SECRET-KEY-32CHARS"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_URL: str = "http://localhost:8000"
    APP_CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000,http://localhost:5173"

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://eduvision:eduvision@localhost:5432/eduvision"
    DATABASE_SYNC_URL: str = "postgresql://eduvision:eduvision@localhost:5432/eduvision"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_POOL_RECYCLE: int = 1800
    DATABASE_ECHO: bool = False

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL: int = 300
    REDIS_SOCKET_TIMEOUT: int = 10
    REDIS_RETRY_ATTEMPTS: int = 3
    REDIS_RETRY_DELAY: float = 0.5

    # ── Quiz read caching ─────────────────────────────────────────────────────
    # The published-version session payload is immutable for a given version,
    # so it is cached in Redis and shared across users. ``QUIZ_CACHE_ENABLED``
    # is an emergency kill-switch (stale graph risk: zero after invalidation);
    # ``QUIZ_CACHE_TTL`` bounds how long a payload lives without a publish
    # event bumping it.
    QUIZ_CACHE_ENABLED: bool = True
    QUIZ_CACHE_TTL: int = 300

    # ── Celery ────────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    CELERY_TASK_ALWAYS_EAGER: bool = False
    CELERY_TASK_EAGER_PROPAGATES: bool = False
    CELERY_WORKER_CONCURRENCY: int = 4
    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_RESULT_SERIALIZER: str = "json"
    CELERY_ACCEPT_CONTENT: list[str] = ["json"]
    CELERY_TASK_DEFAULT_QUEUE: str = "default"
    CELERY_TASK_DLQ_ENABLED: bool = False
    CELERY_TASK_MAX_RETRIES: int = 3
    CELERY_TASK_RETRY_DELAY: int = 60

    # ── Celery dispatch ─────────────────────────────────────────────────────
    # Bounded in-process retry used by safe_dispatch when enqueueing a task to
    # the broker fails (e.g. Redis momentarily unavailable). On exhaustion the
    # caller's on_failure hook runs and, if CELERY_TASK_DLQ_ENABLED, the task
    # is forwarded to the dead-letter queue.
    CELERY_DISPATCH_RETRY_ATTEMPTS: int = 2
    CELERY_DISPATCH_RETRY_DELAY: float = 0.1
    CELERY_DISPATCH_RETRY_MAX_DELAY: float = 1.0

    # ── Startup / lifespan ───────────────────────────────────────────────────
    # When True, a failure to run Alembic migrations at startup aborts app
    # startup (fail-fast) instead of continuing on a possibly-stale schema.
    AUTO_MIGRATE_ON_STARTUP: bool = True
    LIFESPAN_FAIL_FAST_ON_MIGRATION_ERROR: bool = False

    # ── Storage (S3-compatible) ───────────────────────────────────────────────
    STORAGE_PROVIDER: str = "s3"
    S3_ENDPOINT_URL: str | None = None
    S3_ACCESS_KEY_ID: str | None = None
    S3_SECRET_ACCESS_KEY: str | None = None
    S3_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "eduvision-content"
    S3_PUBLIC_BUCKET_NAME: str = "eduvision-public"
    S3_USE_SSL: bool = True
    LOCAL_STORAGE_PATH: str = "./storage-data"

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "DEBUG"
    LOG_FORMAT: str = "json"
    LOG_OUTPUT: str = "console"
    LOG_MASK_SENSITIVE: bool = True

    # ── AI / LLM Providers ─────────────────────────────────────────────────────
    # Provider selection is entirely configuration driven. Supported values:
    # "gemini", "openai", "local" (deterministic mock for development/tests).
    AI_PROVIDER: str | None = None
    AI_API_KEY: str | None = None
    AI_MODEL: str | None = None
    AI_BASE_URL: str | None = None
    AI_TEMPERATURE: float = 0.7
    AI_TOP_P: float = 0.9
    AI_MAX_TOKENS: int = 4096
    AI_MAX_INPUT_TOKENS: int = 100000
    AI_STREAMING_ENABLED: bool = True
    AI_DEFAULT_LANGUAGE: str | None = None
    AI_DEFAULT_DIFFICULTY: str | None = None

    # ── Text-To-Speech (TTS) Narration Engine (Phase 4K.1) ──────────────────────
    TTS_ENABLED: bool = True
    TTS_PROVIDER: str = "edge_tts"
    TTS_VOICE: str = "en-US-ChristopherNeural"
    TTS_LANGUAGE: str = "en"
    TTS_SPEECH_RATE: float = 1.0
    TTS_TIMEOUT_SECONDS: float = 10.0

    # AI timeouts (seconds). Connection/request apply to the underlying HTTP
    # client; the overall timeout bounds an entire generation (including retries).
    AI_TIMEOUT_CONNECT: float = 10.0
    AI_TIMEOUT_REQUEST: float = 60.0
    AI_TIMEOUT_OVERALL: float = 120.0

    # AI retry policy (bounded exponential backoff with jitter).
    AI_RETRY_COUNT: int = 3
    AI_RETRY_MIN_DELAY: float = 1.0
    AI_RETRY_MAX_DELAY: float = 30.0
    AI_RETRY_JITTER: float = 0.1

    # AI rate limit & cache.
    AI_RATE_LIMIT_RPM: int = 60
    AI_CACHE_ENABLED: bool = False
    AI_CACHE_TTL: int = 300

    # ── AI Lesson Generation ───────────────────────────────────────────────────
    AI_LESSON_MAX_SOURCE_UNITS: int = 50
    AI_LESSON_MAX_SOURCE_CHARS: int = 40000
    AI_LESSON_MAX_ATTEMPTS: int = 3
    AI_LESSON_SAFETY_VALIDATOR: str = "noop"

    # ── AI Quiz Generation ─────────────────────────────────────────────────────
    AI_QUIZ_MAX_SOURCE_UNITS: int = 50
    AI_QUIZ_MAX_SOURCE_CHARS: int = 40000
    AI_QUIZ_MAX_ATTEMPTS: int = 3
    AI_QUIZ_MAX_QUESTIONS: int = 50
    AI_QUIZ_SAFETY_VALIDATOR: str = "noop"
    QUIZ_MAX_ATTEMPTS_PER_USER_DEFAULT: int = 1

    # ── Adaptive Learning ─────────────────────────────────────────────────────
    MASTERY_VERSION: str = "1"
    MASTERY_MASTERED_THRESHOLD: float = 80.0
    MASTERY_DEVELOPING_THRESHOLD: float = 50.0
    MASTERY_OBJECTIVE_COMPLETE_THRESHOLD: float = 70.0
    MASTERY_RECALC_LIMIT: int = 300
    MASTERY_HALF_LIFE_DAYS: float = 14.0
    MASTERY_HIGH_ACCURACY: float = 0.85
    MASTERY_LOW_ACCURACY: float = 0.40
    ADAPTIVE_RECOMMENDATION_LIMIT: int = 25
    ADAPTIVE_QUIZ_MAX_QUESTIONS: int = 50

    # ── Learning Sessions ─────────────────────────────────────────────────────
    # Stale/non-terminal sessions are auto-expired when idle beyond
    # ``SESSION_IDLE_TIMEOUT_MINUTES``; the cleanup worker also expires any
    # session past its ``expires_at`` on a short cadence so timeboxed lessons
    # can never outlive their limit.
    SESSION_IDLE_TIMEOUT_MINUTES: int = 120
    SESSION_CLEANUP_LIMIT: int = 500
    SESSION_STATS_LOOKBACK_PERIODS: int = 12
    SESSION_ANALYTICS_ROLLUP_LIMIT: int = 500

    # ── Personalized Learning (Phase 4D.5) ────────────────────────────────────
    # ``PERSONALIZATION_CONTEXT_VERSION`` names the current personalization
    # schema so assistant context snapshots and learning-path revisions can
    # record which version generated them.
    PERSONALIZATION_CONTEXT_VERSION: str = "1"
    LEARNING_PATH_ITEM_LIMIT: int = 50
    STUDY_PLAN_DAYS: int = 7
    STUDY_PLAN_ITEMS_PER_DAY: int = 3
    REVIEW_SCHEDULE_WINDOW_DAYS: int = 14
    REVIEW_SCHEDULE_BATCH_LIMIT: int = 200
    STUDY_PLAN_BATCH_LIMIT: int = 200
    RECOMMENDATION_REFRESH_BATCH_LIMIT: int = 200

    # ── AI Learning Assistant (Phase 4D.6) ────────────────────────────────────
    # Bounds for the assistant so a single abusive client cannot exhaust AI
    # credits: maximum user message length, the depth of conversation history
    # sent to the model, the size of the assembled lesson/context and the max
    # tokens a single answer may produce.
    ASSISTANT_CONTEXT_VERSION: str = "1"
    ASSISTANT_MAX_MESSAGE_LENGTH: int = 4000
    ASSISTANT_MAX_HISTORY_MESSAGES: int = 20
    ASSISTANT_MAX_CONTEXT_CHARS: int = 24000
    ASSISTANT_MAX_RESPONSE_TOKENS: int = 1024
    ASSISTANT_CONVERSATION_PAGE_SIZE: int = 25
    ASSISTANT_CONTEXT_REFRESH_BATCH_LIMIT: int = 200
    ASSISTANT_SUMMARY_MIN_MESSAGES: int = 4

    # ── AI Tutor + Retrieval (Phase 4E.3 + 4E.4) ──────────────────────────────
    # Bounds for the retrieval engine and the grounded AI tutor. ``TUTOR_*``
    # settings mirror the assistant's safety posture (message length, history
    # depth, response tokens) and add retrieval-specific knobs: the similarity
    # floor, hybrid fusion depth, MMR diversity lambda, token budget for
    # assembled context and the number of citations surfaced per answer.
    TUTOR_CONTEXT_VERSION: str = "1"
    TUTOR_MAX_MESSAGE_LENGTH: int = 4000
    TUTOR_MAX_HISTORY_MESSAGES: int = 12
    TUTOR_MAX_RESPONSE_TOKENS: int = 1024
    TUTOR_CONVERSATION_PAGE_SIZE: int = 25
    TUTOR_SUMMARY_MIN_MESSAGES: int = 6
    TUTOR_SUMMARY_ROLLING_COUNT: int = 6
    TUTOR_MAX_CONTEXT_CHARS: int = 16000
    TUTOR_RETRIEVAL_TOP_K: int = 8
    TUTOR_RETRIEVAL_CANDIDATE_K: int = 40
    TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD: float = 0.3
    TUTOR_RETRIEVAL_MMR_LAMBDA: float = 0.7
    TUTOR_RETRIEVAL_RRF_K: int = 60
    TUTOR_RETRIEVAL_MAX_CHUNKS: int = 12
    TUTOR_CONTEXT_TOKEN_BUDGET: int = 3000
    TUTOR_CONTEXT_OVERLAP_WINDOW: int = 200
    TUTOR_EMBEDDING_SEARCH_LIMIT: int = 200
    TUTOR_MEMORY_MAX_ACTIVE: int = 50
    TUTOR_MEMORY_REFRESH_BATCH: int = 25
    TUTOR_ANALYTICS_ROLLUP_LIMIT: int = 500
    TUTOR_CITATION_VALIDATION_BATCH: int = 50
    TUTOR_CONVERSATION_CLEANUP_DAYS: int = 90
    TUTOR_SESSION_IDLE_DAYS: int = 30
    TUTOR_HALLUCINATION_OVERLAP_THRESHOLD: float = 0.25
    TUTOR_GROUNDED_SENTENCE_THRESHOLD: float = 0.6
    TUTOR_HIGH_CONFIDENCE_THRESHOLD: float = 0.75
    TUTOR_LOW_CONFIDENCE_THRESHOLD: float = 0.5
    TUTOR_INJECTION_FLAG_THRESHOLD: float = 0.6
    TUTOR_MAX_MESSAGE_QUERY_CHARS: int = 300

    # ── Video rendering runtime (P16) ────────────────────────────────────────
    # ``VIDEO_RENDER_EXECUTOR`` selects how a render job is executed:
    #   - ``inline`` (default): renders in a background asyncio task inside the
    #     same process so the request handler never blocks the event loop and no
    #     separate worker is required (single-process demo/dev deployments).
    #   - ``celery``: dispatches ``eduvision.videos.render_project`` through the
    #     broker for scale-out; requires a running Celery worker on the
    #     ``videos`` queue.
    # ``VIDEO_RENDER_BACKEND`` selects the renderer: ``real`` (FFmpeg/OpenCV
    # binary pipeline) or ``mock`` (deterministic, instant, no binaries — used
    # by the test suites via tests/conftest.py env defaults). ``TOPIC``/schema
    # bounds mirror the assistant's safety posture.
    VIDEO_RENDER_EXECUTOR: str = "inline"
    VIDEO_RENDER_BACKEND: str = "real"
    VIDEO_RENDER_MAX_CONCURRENT_PER_USER: int = 2
    VIDEO_RENDER_TIMEOUT_SECONDS: float = 1800.0
    VIDEO_RENDER_MAX_TOPIC_CHARS: int = 300
    VIDEO_RENDER_MAX_COMPONENTS: int = 50
    VIDEO_RENDER_PROGRESS_MILESTONES: int = 5

    # ── RAG / Embeddings (Phase 4E.1 + 4E.2) ─────────────────────────────────
    # Provider/model for the embedding pipeline. ``EMBEDDING_PROVIDER`` accepts
    # the same values as ``AI_PROVIDER`` plus ``openrouter``/``ollama``. When
    # unset the AI chat provider is used so a single credential serves both
    # paths; the local mock is deterministic and safe for tests.
    EMBEDDING_PROVIDER: str | None = None
    EMBEDDING_MODEL: str | None = None
    EMBEDDING_BATCH_SIZE: int = 32
    EMBEDDING_MAX_RETRIES: int = 2
    EMBEDDING_CACHE_TTL: int = 86400
    EMBEDDING_MAX_DIMENSION: int = 4096
    EMBEDDING_CLEANUP_ORPHAN_DAYS: int = 30
    EMBEDDING_REFRESH_STALE_DAYS: int = 7
    MAX_EMBEDDING_QUEUE: int = 500

    # Background worker pipeline (Phase 4E.1 + 4E.2, Checkpoint 5).
    # ``EMBEDDING_WORKER_CONCURRENCY`` bounds the number of embedding worker
    # processes; ``EMBEDDING_BATCH_TIMEOUT`` bounds a single provider call in a
    # batch worker (seconds). Refresh/cleanup run on the analytics queue on a
    # beat cadence; a batch worker re-runs failed batches after a crash.
    EMBEDDING_WORKER_CONCURRENCY: int = 4
    EMBEDDING_REFRESH_INTERVAL: int = 900
    EMBEDDING_CLEANUP_INTERVAL: int = 3600
    EMBEDDING_BATCH_TIMEOUT: int = 300
    # A job whose queued/processing state is untouched beyond this many seconds
    # is reclaimed by the cleanup worker (worker-restart recovery).
    EMBEDDING_JOB_STALE_SECONDS: int = 86400
    # How many indexes each refresh/cleanup/statistics run processes per beat.
    EMBEDDING_MAINTENANCE_LIMIT: int = 200
    # Superseded embedding versions older than this are removed by cleanup.
    EMBEDDING_OBSOLETE_VERSION_DAYS: int = 30
    # Failed batches are retried at most this many times by the recovery path.
    EMBEDDING_BATCH_MAX_RETRIES: int = 1

    # Chunking engine defaults (characters). Semantic/heading chunking aims for
    # ``CHUNK_SIZE`` characters with ``CHUNK_OVERLAP`` characters of overlap;
    # ``MAX_CHUNK_TOKENS`` bounds a single chunk after token estimation.
    CHUNK_SIZE: int = 1500
    CHUNK_OVERLAP: int = 150
    MAX_CHUNK_TOKENS: int = 1000
    MAX_CHUNK_CHARACTERS: int = 12000

    # ── RAG indexing trigger (F2-13 Phase 1) ─────────────────────────────────
    # When enabled, every successful source extraction and lesson generation
    # dispatches a background indexing job that chunks the content and enqueues
    # an embedding job, making the content retrievable by the AI tutor.
    RAG_INDEXING_ENABLED: bool = True
    # Chunking strategy used when building index metadata for a new scope.
    RAG_INDEXING_STRATEGY: str = "semantic"


    # ── Authentication ────────────────────────────────────────────────────────
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ALGORITHM: str = "HS256"
    JWT_AUDIENCE: str = "eduvision-api"
    JWT_ISSUER: str = "eduvision-auth"
    JWT_SECRET_KEY: str | None = None
    PASSWORD_HASH_ALGORITHM: str = "argon2"
    PASSWORD_MIN_LENGTH: int = 8
    MAX_LOGIN_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15
    VERIFICATION_TOKEN_EXPIRE_HOURS: int = 24
    RESET_TOKEN_EXPIRE_HOURS: int = 1

    # ── Google OAuth ──────────────────────────────────────────────────────────
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:3000/auth/callback"

    # ── Email ─────────────────────────────────────────────────────────────────
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_USE_TLS: bool = True
    EMAIL_FROM_NAME: str = "EduVision AI"
    EMAIL_FROM_ADDRESS: str = "noreply@eduvision.ai"
    EMAIL_VERIFICATION_REQUIRED: bool = False

    # ── CSRF ──────────────────────────────────────────────────────────────────
    CSRF_ENABLED: bool = True
    CSRF_SECRET: str = "CHANGE-ME-CSRF-SECRET"
    CSRF_COOKIE_NAME: str = "csrf_token"
    CSRF_HEADER_NAME: str = "X-CSRF-Token"

    # ── Cookie ────────────────────────────────────────────────────────────────
    COOKIE_DOMAIN: str | None = None
    COOKIE_SECURE: bool = True
    COOKIE_SAME_SITE: str = "lax"
    COOKIE_PATH: str = "/"

    # ── Upload ────────────────────────────────────────────────────────────────
    UPLOAD_DIR: str = "uploads"
    UPLOAD_MAX_FILE_SIZE: int = 104857600
    UPLOAD_ALLOWED_EXTENSIONS: str = ".pdf,.pptx,.docx,.txt,.jpg,.png,.mp4,.webm"
    UPLOAD_CHUNK_SIZE: int = 5242880

    # ── Content Extraction ─────────────────────────────────────────────────────
    EXTRACTION_MAX_UNITS: int = 200
    EXTRACTION_MAX_BLOCKS_PER_UNIT: int = 200
    EXTRACTION_MAX_BLOCK_CHARS: int = 20000

    # ── Observability ─────────────────────────────────────────────────────────
    OTEL_ENABLED: bool = False
    OTEL_SERVICE_NAME: str = "eduvision-backend"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4318"

    # ── Database Retry ─────────────────────────────────────────────────────────
    DATABASE_RETRY_ATTEMPTS: int = 3
    DATABASE_RETRY_BASE_DELAY: float = 0.1
    DATABASE_RETRY_MAX_DELAY: float = 2.0
    DATABASE_RETRY_JITTER: float = 0.1

    # ── Request Size Limiting ──────────────────────────────────────────────────
    REQUEST_SIZE_LIMIT_ENABLED: bool = True
    REQUEST_SIZE_LIMIT_DEFAULT: int = 104857600
    REQUEST_SIZE_LIMIT_ENDPOINTS: str = ""

    # ── Celery Idempotency ─────────────────────────────────────────────────────
    CELERY_IDEMPOTENCY_ENABLED: bool = True
    CELERY_IDEMPOTENCY_TTL: int = 86400

    # ── Rate Limiting ──────────────────────────────────────────────────────────
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT: int = 100
    RATE_LIMIT_WINDOW: int = 60
    RATE_LIMIT_TRUSTED_PROXIES: str = "127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    RATE_LIMIT_WHITELIST: str = ""
    RATE_LIMIT_BLACKLIST: str = ""
    # Per-path overrides: "PATH_REGEX=LIMIT/WINDOW,PATH_REGEX=LIMIT/WINDOW".
    # The quiz subsystem's expensive routes get tighter budgets than the
    # global 100/60s so an abusive client cannot burn AI credits or grading
    # CPU by hammering generation/submission.
    RATE_LIMIT_ROUTES: str = (
        r"^/api/v1/presentations/[^/]+/quizzes$=10/60,"
        r"^/api/v1/quizzes/[^/]+/attempts/[^/]+/submit$=30/60,"
        r"^/api/v1/users/me/adaptive-quiz$=30/60,"
        r"^/api/v1/quizzes/[^/]+/session$=240/60,"
        r"^/api/v1/assistant/messages$=20/60,"
        r"^/api/v1/assistant/summarize$=10/60,"
        r"^/api/v1/tutor/chat$=20/60,"
        r"^/api/v1/tutor/search$=40/60,"
        r"^/api/v1/tutor/summarize$=10/60"
    )

    # ── Derived Properties ────────────────────────────────────────────────────

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.APP_CORS_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_extensions_list(self) -> list[str]:
        return [e.strip() for e in self.UPLOAD_ALLOWED_EXTENSIONS.split(",") if e.strip()]

    @property
    def upload_path(self) -> Path:
        return Path(self.UPLOAD_DIR)

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_testing(self) -> bool:
        return self.APP_ENV == "test"

    @property
    def is_staging(self) -> bool:
        return self.APP_ENV == "staging"

    @staticmethod
    def _is_unauthenticated_localhost(url: str) -> bool:
        """True when a URL points at localhost loopback with no password.

        Production must never silently run against the default unauthenticated
        ``redis://localhost:6379`` style endpoints baked into the settings
        defaults (fail-fast guard). Password-protected loopback Redis is a
        legitimate single-box deployment, so it is allowed.
        """
        try:
            parts = urlsplit(url)
        except ValueError:
            return False
        return parts.hostname in {"localhost", "127.0.0.1", "::1"} and parts.password is None

    # ── Validators ────────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def validate_environment(self) -> Settings:
        valid_envs = {"development", "staging", "production", "test"}
        if self.APP_ENV not in valid_envs:
            msg = f"APP_ENV must be one of {valid_envs}, got '{self.APP_ENV}'"
            raise ValueError(msg)

        if self.is_production or self.is_staging:
            if self.APP_DEBUG:
                raise ValueError("APP_DEBUG must be False in production/staging environments")
            if self.APP_SECRET_KEY.startswith("CHANGE-ME") or len(self.APP_SECRET_KEY) < 32:
                raise ValueError("APP_SECRET_KEY must be configured with a secure 32+ char key in production/staging")
            if self.CSRF_SECRET.startswith("CHANGE-ME"):
                raise ValueError("CSRF_SECRET must be configured with a secure secret in production/staging")
            if "eduvision:eduvision@" in self.DATABASE_URL or "eduvision:eduvision@" in self.DATABASE_SYNC_URL:
                raise ValueError("Database credentials must be explicitly configured in production/staging; default 'eduvision:eduvision' password is not allowed.")
            if self.AI_PROVIDER and self.AI_PROVIDER != "local" and not self.AI_API_KEY:
                raise ValueError(f"AI_API_KEY is required when AI_PROVIDER is '{self.AI_PROVIDER}' in production/staging")
            if self.STORAGE_PROVIDER == "s3" and (
                not self.S3_ACCESS_KEY_ID or not self.S3_SECRET_ACCESS_KEY
            ):
                raise ValueError("S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY are required when STORAGE_PROVIDER is 's3' in production/staging")

        if self.is_production:
            if self.LOG_LEVEL.upper() == "DEBUG":
                raise ValueError("LOG_LEVEL must not be 'DEBUG' in production")
            if not self.JWT_SECRET_KEY:
                raise ValueError("JWT_SECRET_KEY must be explicitly configured in production")
            if len(self.JWT_SECRET_KEY) < 32:
                raise ValueError("JWT_SECRET_KEY must be at least 32 characters in production")
            if self.JWT_SECRET_KEY == self.APP_SECRET_KEY:
                raise ValueError("JWT_SECRET_KEY must differ from APP_SECRET_KEY in production")
            if not self.LIFESPAN_FAIL_FAST_ON_MIGRATION_ERROR:
                raise ValueError("LIFESPAN_FAIL_FAST_ON_MIGRATION_ERROR must be True in production")
            for name, url in (
                ("REDIS_URL", self.REDIS_URL),
                ("CELERY_BROKER_URL", self.CELERY_BROKER_URL),
                ("CELERY_RESULT_BACKEND", self.CELERY_RESULT_BACKEND),
            ):
                if self._is_unauthenticated_localhost(url):
                    raise ValueError(f"{name} must not use the default unauthenticated localhost URL in production")

        return self

    @model_validator(mode="after")
    def validate_storage_config(self) -> Settings:
        if self.STORAGE_PROVIDER == "s3" and not self.S3_ENDPOINT_URL and not self.is_testing:
            raise ValueError("S3_ENDPOINT_URL is required when STORAGE_PROVIDER is 's3'")
        return self


settings = Settings()

settings.upload_path.mkdir(parents=True, exist_ok=True)
