from enum import Enum


class AppEnvironment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class UserRole(str, Enum):
    """Individual-user role.

    EduVision is an individual learning platform: every account is a single
    learner. There is no student/teacher split and no multi-role hierarchy.
    The value matches the ``role="user"`` claim issued on every JWT so
    existing access tokens remain valid.
    """

    USER = "user"


class ContentStatus(str, Enum):
    DRAFT = "draft"
    PROCESSING = "processing"
    READY = "ready"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    FAILED = "failed"


class LearningMode(str, Enum):
    SLIDE = "slide"
    READING = "reading"



class PresentationStatus(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    READY_TO_PUBLISH = "ready_to_publish"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class CollaboratorRole(str, Enum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class PresentationVisibility(str, Enum):
    PRIVATE = "private"
    PUBLIC = "public"
    UNLISTED = "unlisted"


class ExtractionStatus(str, Enum):
    NONE = "none"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ContentUnitType(str, Enum):
    SLIDE = "slide"
    PAGE = "page"
    SECTION = "section"
    DOCUMENT = "document"


class ContentBlockType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    CODE = "code"
    QUOTE = "quote"
    TABLE = "table"
    IMAGE = "image"
    NOTE = "note"


class GeneratedBlockType(str, Enum):
    PARAGRAPH = "paragraph"


class LessonStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class LessonVersionStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LessonDifficulty(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class LessonRetryState(str, Enum):
    NONE = "none"
    SCHEDULED = "scheduled"
    EXHAUSTED = "exhausted"



class QuestionAttemptStatus(str, Enum):
    UNANSWERED = "unanswered"
    ANSWERED = "answered"
    SKIPPED = "skipped"
    REVIEWED = "reviewed"


class QuestionType(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    MULTIPLE_SELECT = "multiple_select"
    TRUE_FALSE = "true_false"
    FILL_BLANK = "fill_blank"
    SHORT_ANSWER = "short_answer"
    MATCHING = "matching"
    ORDERING = "ordering"
    SCENARIO = "scenario"


class AnswerType(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    MULTIPLE_SELECT = "multiple_select"
    TRUE_FALSE = "true_false"
    FILL_BLANK = "fill_blank"
    SHORT_ANSWER = "short_answer"
    MATCHING = "matching"
    ORDERING = "ordering"


class BloomLevel(str, Enum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"


class QuizDifficulty(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class QuizRetryState(str, Enum):
    NONE = "none"
    SCHEDULED = "scheduled"
    EXHAUSTED = "exhausted"


class QuizOriginMode(str, Enum):
    AI_GENERATED = "ai_generated"
    MANUAL = "manual"
    FROM_TEMPLATE = "from_template"


class QuizExplanationTiming(str, Enum):
    AFTER_SUBMIT = "after_submit"
    REVIEW_MODE = "review_mode"
    IMMEDIATE = "immediate"


class QuestionStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class ScoringRule(str, Enum):
    EXACT = "exact"
    CONTAINS = "contains"
    REGEX = "regex"
    FUZZY = "fuzzy"
    AI_GRADED = "ai_graded"


class GradingStatus(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"
    PENDING = "pending"


class QuizValidationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    PASSED_WITH_WARNINGS = "passed_with_warnings"
    FAILED = "failed"
    REJECTED = "rejected"
    REQUIRES_REVIEW = "requires_review"


class PresentationAction(str, Enum):
    CREATED = "presentation.created"
    UPDATED = "presentation.updated"
    DELETED = "presentation.deleted"
    RESTORED = "presentation.restored"
    PUBLISHED = "presentation.published"
    UNPUBLISHED = "presentation.unpublished"
    ARCHIVED = "presentation.archived"
    VERSION_CREATED = "presentation.version_created"
    SHARED = "presentation.shared"
    COLLABORATOR_ADDED = "presentation.collaborator_added"
    COLLABORATOR_REMOVED = "presentation.collaborator_removed"
    COLLABORATOR_ROLE_CHANGED = "presentation.collaborator_role_changed"
    FOLDER_CREATED = "presentation.folder_created"
    FOLDER_UPDATED = "presentation.folder_updated"
    FOLDER_DELETED = "presentation.folder_deleted"
    FOLDER_CHANGED = "presentation.folder_changed"
    TAG_UPDATED = "presentation.tag_updated"
    DUPLICATED = "presentation.duplicated"
    VERSION_SAVED = "presentation.version_saved"
    VERSION_RESTORED = "presentation.version_restored"
    THUMBNAIL_UPDATED = "presentation.thumbnail_updated"
    THUMBNAIL_DELETED = "presentation.thumbnail_deleted"
    THUMBNAIL_REGENERATED = "presentation.thumbnail_regenerated"
    DRAFT_RECOVERED = "presentation.draft_recovered"
    VISIBILITY_CHANGED = "presentation.visibility_changed"
    VIEW_RECORDED = "presentation.view_recorded"
    LEARNING_SESSION_STARTED = "presentation.learning_session_started"


class AdaptiveRecommendationType(str, Enum):
    NEXT_LESSON = "next_lesson"
    REVIEW_LESSON = "review_lesson"
    EASIER_QUIZ = "easier_quiz"
    HARDER_QUIZ = "harder_quiz"
    FLASHCARDS = "flashcards"
    AI_TUTOR = "ai_tutor"
    REVISION_NOTES = "revision_notes"


class RecommendationStatus(str, Enum):
    ACTIVE = "active"
    DISMISSED = "dismissed"
    COMPLETED = "completed"
    EXPIRED = "expired"


class MasteryStatus(str, Enum):
    UNTESTED = "untested"
    WEAK = "weak"
    DEVELOPING = "developing"
    MASTERED = "mastered"


class ProgressPeriod(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class AdaptiveEventType(str, Enum):
    PROFILE_UPDATED = "profile_updated"
    MASTERY_CALCULATED = "mastery_calculated"
    RECOMMENDATIONS_CREATED = "recommendations_created"
    ADAPTIVE_QUIZ_GENERATED = "adaptive_quiz_generated"
    DIFFICULTY_ADJUSTED = "difficulty_adjusted"
    SNAPSHOT_RECORDED = "snapshot_recorded"


class AdaptiveQuizMode(str, Enum):
    WEAK = "weak"
    REVIEW = "review"
    PRACTICE = "practice"


class LearningSessionStatus(str, Enum):
    """Learning-session state machine states.

    Lifecycle: ``created -> started -> active -> (paused -> active)*`` then a
    terminal state of ``completed``, ``expired`` or ``cancelled``. Every
    transition is persisted as a ``LearningEvent``.
    """

    CREATED = "created"
    STARTED = "started"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class PlayerMode(str, Enum):
    """Slide-deck representation used for progress/completion tracking.

    ``source`` counts against the uploaded source slide deck; ``learning``
    counts against the AI teacher's concept/visual slide pair per topic. The
    visual and animation views render INTO the learning deck, so only these two
    values are accepted as completion modes (the client normalizes
    ``visual``/``animation`` to ``learning`` before saving a position).
    """

    SOURCE = "source"
    LEARNING = "learning"

    @classmethod
    def as_set(cls) -> frozenset[str]:
        return frozenset(item.value for item in cls)


class AnnotationLayerMode(str, Enum):
    """Per-slide annotation-layer identities (isolation across views).

    Each mode keeps its own annotation layers so strokes made in source mode
    never leak into the AI slides and vice-versa. ``visual`` and ``animation``
    annotate over the same underlying learning render but are still stored
    under their own layer ids so layers stay isolated per view.
    """

    SOURCE = "source"
    LEARNING = "learning"
    VISUAL = "visual"
    ANIMATION = "animation"

    @classmethod
    def as_set(cls) -> frozenset[str]:
        return frozenset(item.value for item in cls)


class LearningEventType(str, Enum):
    """Structured learning-session event names (append-only event stream)."""

    SESSION_CREATED = "session.created"
    SESSION_STARTED = "session.started"
    SESSION_RESUMED = "session.resumed"
    SESSION_PAUSED = "session.paused"
    SESSION_COMPLETED = "session.completed"
    SESSION_EXPIRED = "session.expired"
    SESSION_CANCELLED = "session.cancelled"
    RESUME_LOCATION_SET = "resume_location.set"
    PROGRESS_SAVED = "progress.saved"
    SLIDE_VIEWED = "slide.viewed"
    SLIDE_COMPLETED = "slide.completed"
    BLOCK_COMPLETED = "block.completed"
    ACTIVITY_COMPLETED = "activity.completed"
    QUIZ_COMPLETED = "quiz.completed"
    IDLE_DETECTED = "idle.detected"
    BOOKMARK_CREATED = "bookmark.created"
    BOOKMARK_UPDATED = "bookmark.updated"
    BOOKMARK_DELETED = "bookmark.deleted"
    NOTE_CREATED = "note.created"
    NOTE_UPDATED = "note.updated"
    NOTE_DELETED = "note.deleted"


class ProgressStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class BookmarkTargetType(str, Enum):
    LESSON = "lesson"
    SLIDE = "slide"
    SECTION = "section"
    BLOCK = "block"
    EXAMPLE = "example"
    PRACTICE = "practice"


class NoteTargetType(str, Enum):
    LESSON = "lesson"
    SLIDE = "slide"
    SECTION = "section"
    BLOCK = "block"


class CompletionKind(str, Enum):
    """What kind of work a completed block represents (player roles)."""

    READING = "reading"
    PRACTICE = "practice"
    QUIZ = "quiz"
    REFLECTION = "reflection"
    ACTIVITY = "activity"
    FLASHCARD = "flashcard"


class LearningActivityType(str, Enum):
    """Interactive activity kinds a lesson can embed (Phase 4D.4).

    Assessment activities carry a ``config`` block that the attempt evaluator
    consumes (options/correct answers/pairs/ordering/rubric). Non-assessed
    activities (reflection, confidence, self-assessment, ...) are recorded
    verbatim without a correctness verdict.
    """

    PRACTICE_QUESTION = "practice_question"
    MULTIPLE_CHOICE_PRACTICE = "multiple_choice_practice"
    TRUE_FALSE = "true_false"
    FILL_BLANK = "fill_blank"
    MATCHING = "matching"
    ORDERING = "ordering"
    SHORT_ANSWER = "short_answer"
    FLASHCARD = "flashcard"
    REFLECTION = "reflection"
    CONFIDENCE_RATING = "confidence_rating"
    SELF_ASSESSMENT = "self_assessment"
    NEED_MORE_EXPLANATION = "need_more_explanation"
    MARK_DIFFICULT = "mark_difficult"


class ActivityAttemptStatus(str, Enum):
    """Lifecycle of an interactive-activity attempt."""

    STARTED = "started"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    EVALUATED = "evaluated"
    FAILED = "failed"
    ABANDONED = "abandoned"


class ActivityOutcome(str, Enum):
    """Verdict for an evaluated (or unevaluated) activity attempt."""

    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIAL = "partial"
    UNEVALUATED = "unevaluated"
    NEUTRAL = "neutral"


class ActivityFeedbackType(str, Enum):
    """Classification of a learner's feedback on an activity."""

    RATING = "rating"
    DIFFICULTY = "difficulty"
    EXPLANATION_REQUEST = "explanation_request"
    NOTE = "note"


class MilestoneType(str, Enum):
    """Progress-engine milestone kinds (Phase 4D.3).

    ``scope_key`` on the milestone row distinguishes global milestones from
    per-lesson ones (e.g. ``lesson:<public_id>``) so the same type can be
    re-earned for every lesson.
    """

    LESSON_STARTED = "lesson_started"
    LESSON_COMPLETED = "lesson_completed"
    FIRST_ACTIVITY = "first_activity"
    ACTIVITIES_COMPLETED = "activities_completed"
    ACCURACY_THRESHOLD = "accuracy_threshold"
    TIME_SPENT = "time_spent"
    FLASHCARDS_REVIEWED = "flashcards_reviewed"
    CONFIDENCE_TRACKED = "confidence_tracked"
    SELF_ASSESSED = "self_assessed"
    STREAK_DAY = "streak_day"


class ActivityRecommendationType(str, Enum):
    """Why a learner should revisit a specific activity."""

    REVIEW_ACTIVITY = "review_activity"
    PRACTICE_MORE = "practice_more"
    NEXT_ACTIVITY = "next_activity"
    TARGETED_FLASHCARDS = "targeted_flashcards"
    TRY_AGAIN = "try_again"


class LearningPathStatus(str, Enum):
    """Lifecycle of a personalised learning path (Phase 4D.5)."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class LearningGoalType(str, Enum):
    """Kinds of goals a learner can track (Phase 4D.5)."""

    MASTERY_TARGET = "mastery_target"
    LESSON_COMPLETION = "lesson_completion"
    QUIZ_SCORE = "quiz_score"
    STUDY_TIME = "study_time"
    STREAK_DAYS = "streak_days"
    ACTIVITY_COUNT = "activity_count"


class LearningGoalStatus(str, Enum):
    """Lifecycle of a learner goal (Phase 4D.5)."""

    ACTIVE = "active"
    ACHIEVED = "achieved"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class StudyPlanStatus(str, Enum):
    """Lifecycle of a generated study plan (Phase 4D.5)."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class StudyPlanItemType(str, Enum):
    """Kinds of scheduled items inside a study plan."""

    LESSON = "lesson"
    REVIEW = "review"
    QUIZ = "quiz"
    ACTIVITY = "activity"
    FLASHCARDS = "flashcards"


class StudyPlanItemStatus(str, Enum):
    """Per-day completion status of a study-plan item."""

    PENDING = "pending"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class ReviewScheduleStatus(str, Enum):
    """Lifecycle of a spaced-repetition review item (Phase 4D.5)."""

    PENDING = "pending"
    DUE = "due"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class AssistantSessionStatus(str, Enum):
    """Lifecycle of an AI assistant session (Phase 4D.6)."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class AssistantMessageRole(str, Enum):
    """Roles of assistant conversation messages (Phase 4D.6)."""

    USER = "user"
    ASSISTANT = "assistant"


class AssistantMessageStatus(str, Enum):
    """Outcome of a single assistant message exchange."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    FILTERED = "filtered"
    TIMED_OUT = "timed_out"


class PersonalizationEventType(str, Enum):
    """Append-only event names for the personalised learning engine (4D.5)."""

    PATH_CREATED = "path.created"
    PATH_UPDATED = "path.updated"
    PATH_COMPLETED = "path.completed"
    GOAL_CREATED = "goal.created"
    GOAL_UPDATED = "goal.updated"
    GOAL_ACHIEVED = "goal.achieved"
    STUDY_PLAN_GENERATED = "study_plan.generated"
    STUDY_PLAN_ITEM_COMPLETED = "study_plan.item_completed"
    REVIEW_SCHEDULE_GENERATED = "review_schedule.generated"
    REVIEW_ITEM_COMPLETED = "review_item.completed"
    RECOMMENDATIONS_REFRESHED = "recommendations.refreshed"
    ASSISTANT_SESSION_CREATED = "assistant.session.created"
    ASSISTANT_MESSAGE_SENT = "assistant.message.sent"
    ASSISTANT_CONVERSATION_ARCHIVED = "assistant.conversation.archived"
    ASSISTANT_CONTEXT_REFRESHED = "assistant.context.refreshed"
    ASSISTANT_SUMMARY_CREATED = "assistant.summary.created"


class ChunkSource(str, Enum):
    """What kind of source document a chunk was built from (Phase 4E.1)."""

    PRESENTATION = "presentation"
    LESSON = "lesson"


class ChunkStatus(str, Enum):
    """Lifecycle of a document chunk in the RAG pipeline."""

    PENDING = "pending"
    PROCESSED = "processed"
    SKIPPED = "skipped"
    FAILED = "failed"


class ChunkingStrategy(str, Enum):
    """Chunking strategies the chunk builder supports (Phase 4E.1)."""

    SEMANTIC = "semantic"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    SLIDING = "sliding"


class EmbeddingProvider(str, Enum):
    """Supported embedding providers (Phase 4E.2)."""

    OPENAI = "openai"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    LOCAL = "local"


class EmbeddingRetryState(str, Enum):
    """Retry state shared by jobs, batches and chunks."""

    NONE = "none"
    SCHEDULED = "scheduled"
    EXHAUSTED = "exhausted"


class ChunkRetryState(str, Enum):
    """Retry state of a document chunk in the embedding pipeline."""

    NONE = "none"
    SCHEDULED = "scheduled"
    EXHAUSTED = "exhausted"


class EmbeddingJobStatus(str, Enum):
    """Lifecycle of an embedding background job (Phase 4E.2)."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EmbeddingJobType(str, Enum):
    """Kinds of embedding jobs the worker pool processes."""

    INDEX = "index"
    BATCH = "batch"
    REFRESH = "refresh"
    CLEANUP = "cleanup"


class EmbeddingBatchStatus(str, Enum):
    """Lifecycle of a single embedding batch."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class EmbeddingVersionStatus(str, Enum):
    """Lifecycle of a stored embedding version."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    FAILED = "failed"


class EmbeddingStatisticsPeriod(str, Enum):
    """Rollup granularity for embedding statistics rows."""

    TOTAL = "total"
    DAILY = "daily"


class VectorIndexType(str, Enum):
    """What scope a vector index covers (Phase 4E.1)."""

    PRESENTATION = "presentation"
    LESSON = "lesson"


class VectorIndexStatus(str, Enum):
    """Lifecycle of a vector index metadata record."""

    BUILDING = "building"
    READY = "ready"
    FAILED = "failed"
    REBUILDING = "rebuilding"


class ChunkRelationshipType(str, Enum):
    """Kinds of structural relationships between chunks."""

    PARENT = "parent"
    CHILD = "child"
    NEXT = "next"
    PREVIOUS = "previous"
    RELATED = "related"


class TutorSessionStatus(str, Enum):
    """Lifecycle of an AI tutor session (Phase 4E.3 + 4E.4)."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class TutorConversationStatus(str, Enum):
    """Lifecycle of an AI tutor conversation."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class TutorMessageStatus(str, Enum):
    """Outcome of a single tutor message exchange."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    FILTERED = "filtered"
    TIMED_OUT = "timed_out"


class TutorSearchType(str, Enum):
    """Retrieval strategies the hybrid search engine can run."""

    HYBRID = "hybrid"
    SEMANTIC = "semantic"
    KEYWORD = "keyword"


class TutorContextStatus(str, Enum):
    """Lifecycle of a frozen retrieval context snapshot."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"


class TutorCitationStatus(str, Enum):
    """Lifecycle of a citation attached to a tutor answer."""

    RETRIEVED = "retrieved"
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    REJECTED = "rejected"


class TutorRecommendationKind(str, Enum):
    """Kinds of recommendations the AI tutor can produce."""

    LESSON = "lesson"
    ACTIVITY = "activity"
    QUIZ = "quiz"
    REVIEW = "review"
    WEAK_TOPIC = "weak_topic"
    RESOURCE = "resource"


class TutorRecommendationStatus(str, Enum):
    """Lifecycle of a tutor recommendation."""

    ACTIVE = "active"
    DISMISSED = "dismissed"
    COMPLETED = "completed"
    EXPIRED = "expired"


class TutorMemoryKind(str, Enum):
    """Kinds of learner facts the tutor memory service extracts."""

    FACT = "fact"
    PREFERENCE = "preference"
    WEAK_TOPIC = "weak_topic"
    MISTAKE = "mistake"
    GOAL = "goal"


class TutorMemoryStatus(str, Enum):
    """Lifecycle of a stored tutor memory."""

    ACTIVE = "active"
    EXPIRED = "expired"


class TutorSummaryStatus(str, Enum):
    """Lifecycle of a rolling conversation summary."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class TutorAnalyticsPeriod(str, Enum):
    """Rollup granularity for tutor analytics rows."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    TOTAL = "total"


class TutorFeedbackType(str, Enum):
    """Classification of learner feedback on a tutor answer."""

    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"
    CORRECT = "correct"
    INCORRECT = "incorrect"
    CONFUSING = "confusing"


class TutorConfidenceLevel(str, Enum):
    """Confidence buckets for a tutor answer."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TutorSourceKind(str, Enum):
    """Provenance of a tutor answer (P8)."""

    RAG = "rag"
    DETERMINISTIC = "deterministic"


class TutorRetryState(str, Enum):
    """Retry state shared by every tutor row."""

    NONE = "none"
    SCHEDULED = "scheduled"
    EXHAUSTED = "exhausted"


class ExportFormat(str, Enum):
    """Supported output formats for content export (Phase 4F)."""

    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    MARKDOWN = "markdown"
    HTML = "html"
    FLASHCARDS = "flashcards"
    MINDMAP = "mindmap"
    ZIP = "zip"


class ExportKind(str, Enum):
    """Kinds of AI-generated content that can be exported (Phase 4F)."""

    NOTES = "notes"
    QUIZ = "quiz"
    SUMMARY = "summary"
    TUTOR_CONVERSATION = "tutor_conversation"
    PROGRESS_REPORT = "progress_report"
    STUDY_PLAN = "study_plan"
    ADAPTIVE_REPORT = "adaptive_report"
    BUNDLE = "bundle"


class ExportJobStatus(str, Enum):
    """Lifecycle state of an export job (Phase 4F)."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExportTemplateType(str, Enum):
    """Visual style/formatting templates for generated exports."""

    STANDARD = "standard"
    COMPACT = "compact"
    DENSE = "dense"
    MODERN = "modern"
    ELEGANT = "elegant"


class ExportRetryState(str, Enum):
    """Retry state shared by export job rows."""

    NONE = "none"
    RETRYING = "retrying"
    EXHAUSTED = "exhausted"


DIALECTS_SUPPORTED = [
    "ar",
    "bn",
    "de",
    "en",
    "es",
    "fr",
    "hi",
    "ja",
    "ko",
    "pa",
    "pt",
    "ru",
    "sw",
    "ta",
    "te",
    "th",
    "tr",
    "ur",
    "vi",
    "zh",
]

SUPPORTED_MIME_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}

MAX_FILE_SIZE_MB = 100
MAX_UPLOAD_FILES = 10
CHUNK_SIZE_MB = 5

