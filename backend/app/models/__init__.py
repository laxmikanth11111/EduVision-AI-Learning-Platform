from app.database.base import Base
from app.models.ai_usage import AIUsageLog
from app.models.analytics import (
    CreatorAnalyticsSnapshot,
    LearningAnalyticsSnapshot,
    SystemAnalytics,
)
from app.models.answer_key import AnswerKey
from app.models.assistant_context_snapshot import AssistantContextSnapshot
from app.models.assistant_conversation import AssistantConversation
from app.models.assistant_message import AssistantMessage
from app.models.assistant_session import AssistantSession
from app.models.chunk_embedding import ChunkEmbedding
from app.models.chunk_relationship import ChunkRelationship
from app.models.chunk_section import ChunkSection
from app.models.concept import Concept
from app.models.content_block import ContentBlock
from app.models.content_unit import ContentUnit
from app.models.document_chunk import DocumentChunk
from app.models.educational_memory import EducationalMemoryRecord
from app.models.effectiveness_assessment import EffectivenessAssessment
from app.models.embedding_batch import EmbeddingBatch
from app.models.embedding_job import EmbeddingJob
from app.models.embedding_metadata import EmbeddingMetadata
from app.models.embedding_statistics import EmbeddingStatistics
from app.models.export_file import ExportFile
from app.models.export_job import ExportJob
from app.models.export_template import ExportTemplate
from app.models.generated_block import GeneratedBlock
from app.models.generated_lesson import GeneratedLesson
from app.models.generated_lesson_version import GeneratedLessonVersion
from app.models.learning_activity import LearningActivity
from app.models.learning_event import LearningEvent
from app.models.learning_session import LearningSession
from app.models.presentation import Presentation
from app.models.presentation_analytics import PresentationAnalytics
from app.models.presentation_audit_log import PresentationAuditLog
from app.models.presentation_folder import PresentationFolder
from app.models.presentation_tag import PresentationTag
from app.models.presentation_version import PresentationVersion
from app.models.question_attempt import QuestionAttempt
from app.models.question_explanation import QuestionExplanation
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.models.quiz_content import Question, QuestionOption
from app.models.quiz_version import QuizVersion
from app.models.score_summary import ScoreSummary
from app.models.topic_outline import TopicOutline
from app.models.user import User
from app.models.user_answer import UserAnswer
from app.models.user_feedback import UserFeedback
from app.models.vector_index import VectorIndex
from app.models.vector_index_version import VectorIndexVersion
from app.models.visual_knowledge_graph import (
    ComponentMetadata,
    LearningObjective,
    SimulationCandidate,
    VisualCanvas,
    VisualEdge,
    VisualLayout,
    VisualNode,
    VisualQuizBlueprint,
    VisualRelationship,
)

__all__ = [
    "Base",
    "LearningActivity",
    "Presentation",
    "PresentationFolder",
    "PresentationVersion",
    "PresentationAnalytics",
    "PresentationTag",
    "PresentationAuditLog",
    "ContentUnit",
    "ContentBlock",
    "AIUsageLog",
    "GeneratedLesson",
    "GeneratedLessonVersion",
    "GeneratedBlock",
    "TopicOutline",
    "DocumentChunk",
    "ChunkSection",
    "ChunkEmbedding",
    "ChunkRelationship",
    "EmbeddingJob",
    "EmbeddingBatch",
    "EmbeddingMetadata",
    "EmbeddingStatistics",
    "VectorIndex",
    "VectorIndexVersion",
    "ExportJob",
    "ExportFile",
    "ExportTemplate",
    "VisualCanvas",
    "VisualNode",
    "VisualEdge",
    "ComponentMetadata",
    "LearningObjective",
    "VisualRelationship",
    "VisualLayout",
    "SimulationCandidate",
    "VisualQuizBlueprint",
    "Quiz",
    "QuizVersion",
    "Question",
    "QuestionOption",
    "QuizAttempt",
    "QuestionAttempt",
    "UserAnswer",
    "AnswerKey",
    "QuestionExplanation",
    "ScoreSummary",
    "AssistantSession",
    "AssistantConversation",
    "AssistantMessage",
    "AssistantContextSnapshot",
    "EducationalMemoryRecord",
    "EffectivenessAssessment",
    "LearningEvent",
    "LearningSession",
    "Concept",
    "User",
    "UserFeedback",
]
