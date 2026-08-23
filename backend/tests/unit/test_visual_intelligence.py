"""Comprehensive Unit & Regression Tests for Phase 4I.2 Visual Intelligence Backend Engine.
"""

from __future__ import annotations

import pytest

from app.schemas.visual_intelligence import (
    DifficultyLevel,
    DiscoveredComponent,
    RelationshipType,
    TopicCategory,
    VisualizationType,
)
from app.services.component_discovery_service import ComponentDiscoveryService
from app.services.learning_objective_service import LearningObjectiveService
from app.services.relationship_engine_service import RelationshipEngineService
from app.services.visual_classifier_service import VisualClassifierService
from app.services.visual_intelligence_service import VisualIntelligenceService
from app.services.visual_validation_service import VisualValidationService
from app.services.visualization_decision_service import VisualizationDecisionService


@pytest.mark.asyncio
async def test_topic_classification_all_22_categories():
    """Verify that classifier handles keywords for all 22 supported categories."""
    service = VisualClassifierService()

    category_samples: dict[TopicCategory, str] = {
        TopicCategory.ALGORITHM: "QuickSort algorithm recursion and partition logic with time complexity O(n log n).",
        TopicCategory.SYSTEM_ARCHITECTURE: "Central Processing Unit CPU registers ALU and system RAM bus architecture.",
        TopicCategory.PROCESS: "Step 1 first initialize, then execute procedure, next verify, finally finish stage.",
        TopicCategory.WORKFLOW: "Business task flow approval handoff swimlane roles and assignees.",
        TopicCategory.TIMELINE: "Historical timeline era century 1945 to 2026 chronological events.",
        TopicCategory.COMPARISON: "Comparison vs versus tradeoff pros and cons advantages compared to traditional.",
        TopicCategory.HIERARCHY: "Taxonomy tree hierarchy parent child subcategory rank structure.",
        TopicCategory.MIND_MAP: "Mind map radial central topic branch cluster overview.",
        TopicCategory.NETWORK: "Network topology router switch IP address packet routing nodes.",
        TopicCategory.LIFECYCLE: "State lifecycle birth creation destruction garbage collection cycle.",
        TopicCategory.CAUSE_AND_EFFECT: "Trigger cause effect consequence root cause fishbone led to failure.",
        TopicCategory.PROGRAMMING_CONCEPT: "Programming code variable function class object stack heap scope.",
        TopicCategory.MATHEMATICAL_CONCEPT: "Calculus algebra formula equation theorem matrix vector proof.",
        TopicCategory.SCIENTIFIC_CYCLE: "Ecological water cycle krebs cycle feedback loop continuous.",
        TopicCategory.BIOLOGY: "Biology cell organ heart blood mitosis DNA RNA tissue structure.",
        TopicCategory.CHEMISTRY: "Chemistry chemical reaction molecule atom covalent bond catalyst reactant product.",
        TopicCategory.PHYSICS: "Physics force velocity acceleration kinetic energy mass gravity thermodynamics.",
        TopicCategory.ECONOMICS: "Economics supply demand inflation market price GDP elasticity curve.",
        TopicCategory.BUSINESS_PROCESS: "Business strategy value chain SWOT analysis market funnel revenue.",
        TopicCategory.DECISION_TREE: "Decision tree if-else branching decision node conditional path.",
        TopicCategory.DATA_FLOW: "Data flow pipeline stream ETL ingestion transformation data sink.",
        TopicCategory.CONCEPT_RELATIONSHIP: "Interconnected semantic concept relationship web link.",
    }

    for expected_cat, sample_text in category_samples.items():
        res = await service.classify_topic(sample_text)
        assert res.primary_category == expected_cat, f"Expected {expected_cat}, got {res.primary_category}"
        assert res.confidence_score > 0.0


@pytest.mark.asyncio
async def test_learning_objective_detection():
    """Verify learning objective detector extracts main goals and outcomes."""
    service = LearningObjectiveService()
    content = "HTTP Request and Response lifecycle in web development. Understand client-server model."

    objectives = await service.detect_objectives(content, title="HTTP Cycle")
    assert objectives.main_goal is not None
    assert len(objectives.learning_objectives) > 0
    assert len(objectives.expected_outcomes) > 0


@pytest.mark.asyncio
async def test_component_discovery_and_metadata():
    """Verify component discovery engine extracts components with rich metadata."""
    service = ComponentDiscoveryService()
    content = "The Central Processing Unit CPU fetches data from RAM, passes instructions to ALU, and writes to Cache."

    components = await service.discover_components(content, title="CPU Architecture")
    assert len(components) > 0
    c1 = components[0]
    assert c1.component_id is not None
    assert c1.name is not None
    assert c1.short_description is not None
    assert c1.difficulty_level in [DifficultyLevel.BEGINNER, DifficultyLevel.INTERMEDIATE, DifficultyLevel.ADVANCED]


@pytest.mark.asyncio
async def test_relationship_engine_and_graph_layout():
    """Verify relationship detection and layout graph coordinate generation."""
    service = RelationshipEngineService()
    components = [
        DiscoveredComponent(
            component_id="comp_cpu",
            name="CPU",
            short_description="Processor",
            detailed_working="Executes instructions",
        ),
        DiscoveredComponent(
            component_id="comp_ram",
            name="RAM",
            short_description="Memory",
            detailed_working="Stores data",
        ),
    ]

    relationships = await service.detect_relationships(components, "CPU fetches from RAM")
    assert len(relationships) > 0

    nodes, edges, layout = service.build_graph_layout(components, relationships, layout_direction="horizontal")
    assert len(nodes) == 2
    assert len(edges) == 1
    assert nodes[0].position.x < nodes[1].position.x
    assert layout.layout_direction == "horizontal"


@pytest.mark.asyncio
async def test_visualization_decision_matrix():
    """Verify visualization decision engine rules."""
    service = VisualizationDecisionService()
    classifier = VisualClassifierService()

    class_res = await classifier.classify_topic("QuickSort algorithm partition time complexity O(n log n)")
    decision = await service.decide_visualization(class_res, [], "QuickSort Algorithm")

    assert decision.visualization_type == VisualizationType.ALGORITHM_STEPS
    assert decision.fallback_type == VisualizationType.FLOWCHART
    assert decision.confidence > 0.0


def test_visual_validation_layer():
    """Verify visual validation service edge cases."""
    validator = VisualValidationService()

    res_empty = validator.validate_content("   ")
    assert res_empty.is_valid is False
    assert res_empty.errors[0].code == "EMPTY_CONTENT"

    res_short = validator.validate_content("Short")
    assert res_short.is_valid is False
    assert res_short.errors[0].code == "CONTENT_TOO_SHORT"

    res_valid = validator.validate_content("This is a valid long text content describing how a database index scan works.")
    assert res_valid.is_valid is True


@pytest.mark.asyncio
async def test_full_visual_intelligence_pipeline_and_caching():
    """Verify complete end-to-end visual intelligence pipeline generation and caching."""
    service = VisualIntelligenceService()

    content = "CPU Von Neumann Architecture consisting of Control Unit, ALU, Registers, and System RAM Memory."
    title = "CPU Von Neumann Architecture"

    model1 = await service.generate_visual_learning_model(content, title=title, use_cache=True)
    assert model1.topic == title
    assert model1.classification.primary_category == TopicCategory.SYSTEM_ARCHITECTURE
    assert len(model1.components) > 0
    assert len(model1.visual_nodes) > 0
    assert len(model1.visual_edges) > 0
    assert len(model1.future_simulation_candidates) > 0

    # Test Caching
    model2 = await service.generate_visual_learning_model(content, title=title, use_cache=True)
    assert model1 is model2  # Cached instance returned
