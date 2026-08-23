"""Topic Classification Engine (Phase 4I.2).

Classifies educational text content into one of 22 supported categories using a hybrid
approach: high-precision rule-based keyword & pattern scoring combined with LLM fallback
classification.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.ai.factory import get_ai_provider
from app.ai.models import AIRequest
from app.core.logging import get_logger
from app.schemas.visual_intelligence import CategoryClassification, TopicCategory
from app.services.visual_prompts import CLASSIFICATION_SYSTEM_PROMPT

logger = get_logger(__name__)

# Category Keyword Scoring Rules (High-precision domain indicators)
CATEGORY_PATTERNS: dict[TopicCategory, list[str]] = {
    TopicCategory.ALGORITHM: [
        r"\balgorithm\b", r"\bcomplexity\b", r"\bbig-o\b", r"\bquicksort\b", r"\bmergesort\b",
        r"\brecursiv\w*\b", r"\bloop\b", r"\biteration\b", r"\bpointer\b", r"\bsort\w*\b",
    ],
    TopicCategory.SYSTEM_ARCHITECTURE: [
        r"\barchitecture\b", r"\bsubsystem\b", r"\bcomponent\b", r"\bmodule\b", r"\binterface\b",
        r"\bbus\b", r"\bcpu\b", r"\balu\b", r"\bram\b", r"\bcache\b", r"\bregister\b",
    ],
    TopicCategory.PROCESS: [
        r"\bprocess\b", r"\bstep 1\b", r"\bfirst\b", r"\bthen\b", r"\bnext\b", r"\bfinally\b",
        r"\bstage\b", r"\bprocedure\b", r"\bsequence\b",
    ],
    TopicCategory.WORKFLOW: [
        r"\bworkflow\b", r"\bswimlane\b", r"\bapproval\b", r"\bhandoff\b", r"\btask flow\b",
        r"\brole\b", r"\bassignee\b",
    ],
    TopicCategory.TIMELINE: [
        r"\btimeline\b", r"\bchronological\b", r"\bcentury\b", r"\bera\b", r"\bhistory\b",
        r"\b19\d\d\b", r"\b20\d\d\b", r"\bdate\b", r"\bperiod\b",
    ],
    TopicCategory.COMPARISON: [
        r"\bvs\.?\b", r"\bversus\b", r"\bcompared to\b", r"\bcomparison\b", r"\bdifference\b",
        r"\btradeoff\b", r"\bpros and cons\b", r"\badvantages\b",
    ],
    TopicCategory.HIERARCHY: [
        r"\bhierarchy\b", r"\btaxonomy\b", r"\btree\b", r"\bparent\b", r"\bchild\b",
        r"\bcategory\b", r"\bsubcategory\b", r"\brank\b",
    ],
    TopicCategory.MIND_MAP: [
        r"\bmind map\b", r"\bradial\b", r"\bcentral topic\b", r"\bbranch\b", r"\bcluster\b",
    ],
    TopicCategory.NETWORK: [
        r"\bnetwork\b", r"\btopology\b", r"\brouter\b", r"\bswitch\b", r"\bip address\b",
        r"\bpacket\b", r"\bnode\b", r"\bconnection\b",
    ],
    TopicCategory.LIFECYCLE: [
        r"\blifecycle\b", r"\blife cycle\b", r"\bcreation\b", r"\bdestruction\b",
        r"\bgarbage collect\w*\b", r"\bbirth\b", r"\bdeath\b",
    ],
    TopicCategory.CAUSE_AND_EFFECT: [
        r"\bcause\b", r"\beffect\b", r"\btrigger\b", r"\bconsequence\b", r"\bimpact\b",
        r"\broot cause\b", r"\bfishbone\b", r"\bled to\b",
    ],
    TopicCategory.PROGRAMMING_CONCEPT: [
        r"\bprogramming\b", r"\bvariable\b", r"\bfunction\b", r"\bclass\b", r"\bobject\b",
        r"\bscope\b", r"\bstack\b", r"\bheap\b", r"\bcode\b", r"\bparameter\b",
    ],
    TopicCategory.MATHEMATICAL_CONCEPT: [
        r"\bequation\b", r"\bformula\b", r"\bcalculus\b", r"\balgebra\b", r"\bgeometry\b",
        r"\btheorem\b", r"\bproof\b", r"\bmatrix\b", r"\bvector\b",
    ],
    TopicCategory.SCIENTIFIC_CYCLE: [
        r"\bcycle\b", r"\bwater cycle\b", r"\bkrebs cycle\b", r"\bcarbon cycle\b", r"\bfeedback loop\b",
    ],
    TopicCategory.BIOLOGY: [
        r"\bbiology\b", r"\bcell\b", r"\borgan\b", r"\bheart\b", r"\blood\b", r"\bmitosis\b",
        r"\bdna\b", r"\brna\b", r"\bprotein\b", r"\btissue\b",
    ],
    TopicCategory.CHEMISTRY: [
        r"\bchemistry\b", r"\breaction\b", r"\bmolecule\b", r"\batom\b", r"\bbond\b",
        r"\bcatalyst\b", r"\breactant\b", r"\bproduct\b",
    ],
    TopicCategory.PHYSICS: [
        r"\bphysics\b", r"\bforce\b", r"\bvelocity\b", r"\bacceleration\b", r"\benergy\b",
        r"\bmass\b", r"\bgravity\b", r"\bmotion\b", r"\bthermodynamics\b",
        r"\bquantum\b", r"\bqubit\b", r"\bsuperposition\b", r"\bentanglement\b",
        r"\bwave\b", r"\bparticle\b", r"\bphoton\b", r"\belectron\b", r"\batom\w*\b",
        r"\belectromagnetic\b", r"\bnuclear\b", r"\brelativity\b", r"\bspin\b",
        r"\bprobability amplitude\b", r"\binterference\b", r"\bmeasurement\b",
    ],
    TopicCategory.ECONOMICS: [
        r"\beconomics\b", r"\bsupply\b", r"\bdemand\b", r"\binflation\b", r"\bmarket\b",
        r"\bprice\b", r"\bGDP\b", r"\belasticity\b",
    ],
    TopicCategory.BUSINESS_PROCESS: [
        r"\bbusiness\b", r"\bvalue chain\b", r"\bswot\b", r"\bfunnel\b", r"\bstrategy\b",
        r"\bmarket share\b", r"\brevenue\b",
    ],
    TopicCategory.DECISION_TREE: [
        r"\bdecision tree\b", r"\bif-else\b", r"\bdecision node\b", r"\bbranching\b", r"\bcondition\b",
    ],
    TopicCategory.DATA_FLOW: [
        r"\bdata flow\b", r"\bpipeline\b", r"\bstream\b", r"\btransformation\b", r"\bsink\b",
        r"\betl\b", r"\bingestion\b",
    ],
    TopicCategory.CONCEPT_RELATIONSHIP: [
        r"\bconcept\b", r"\brelationship\b", r"\bsemantic\b", r"\blink\b", r"\binterconnected\b",
    ],
}


class VisualClassifierService:

    async def classify_topic(
        self,
        content: str,
        title: str | None = None,
    ) -> CategoryClassification:
        """Classify educational content into one of 22 TopicCategory values."""
        text_to_analyze = f"{title or ''}\n{content}".strip()

        # Step 1: Rule-based keyword matching evaluation
        scores: dict[TopicCategory, float] = {}
        matched_indicators: dict[TopicCategory, list[str]] = {}

        for category, patterns in CATEGORY_PATTERNS.items():
            count = 0
            matches: list[str] = []
            for pattern in patterns:
                found = re.findall(pattern, text_to_analyze, flags=re.IGNORECASE)
                if found:
                    count += len(found)
                    matches.extend(found)
            if count > 0:
                scores[category] = float(count)
                matched_indicators[category] = list(set(matches[:5]))

        if scores:
            sorted_categories = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            top_category, top_score = sorted_categories[0]
            confidence = min(0.95, 0.50 + (top_score * 0.10))

            secondary: TopicCategory | None = None
            if len(sorted_categories) > 1 and sorted_categories[1][1] >= 2:
                secondary = sorted_categories[1][0]

            logger.info(
                "topic_classified_by_rules",
                category=top_category.value,
                confidence=confidence,
                score=top_score,
            )
            return CategoryClassification(
                primary_category=top_category,
                secondary_category=secondary,
                confidence_score=round(confidence, 2),
                reasoning_metadata={
                    "matched_indicators": matched_indicators.get(top_category, []),
                    "method": "rule_based_matching",
                    "scores": {k.value: v for k, v in scores.items()},
                },
            )

        # Step 2: Fallback to LLM AI Provider classification
        try:
            ai_provider = get_ai_provider()
            prompt = f"Title: {title or 'N/A'}\n\nContent:\n{content[:4000]}"
            req = AIRequest(system_prompt=CLASSIFICATION_SYSTEM_PROMPT, user_prompt=prompt, temperature=0.2)
            res = await ai_provider.generate(req)

            data = json.loads(res.text)
            primary_str = data.get("primary_category", "Process")
            sec_str = data.get("secondary_category")
            conf = float(data.get("confidence_score", 0.75))

            primary_cat = self._match_enum(primary_str, TopicCategory.PROCESS)
            sec_cat = self._match_enum(sec_str, None) if sec_str else None

            logger.info("topic_classified_by_ai", category=primary_cat.value, confidence=conf)
            return CategoryClassification(
                primary_category=primary_cat,
                secondary_category=sec_cat,
                confidence_score=conf,
                reasoning_metadata=data.get("reasoning_metadata", {"method": "ai_llm_classification"}),
            )
        except Exception as exc:
            logger.warning("topic_classification_llm_failed_using_default", error=str(exc))
            return CategoryClassification(
                primary_category=TopicCategory.PROCESS,
                confidence_score=0.50,
                reasoning_metadata={"method": "default_fallback", "error": str(exc)},
            )

    @staticmethod
    def _match_enum(val: str, default: Any) -> Any:
        for cat in TopicCategory:
            if cat.value.lower() == val.lower() or cat.name.lower() == val.lower():
                return cat
        return default
