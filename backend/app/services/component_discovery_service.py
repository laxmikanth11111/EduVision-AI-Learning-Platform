"""Component Discovery Engine (Phase 4I.2).

Discovers discrete entities, actors, modules, hardware/software blocks, and process steps
from educational text, populating rich metadata (inputs, outputs, analogies, importance).
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.ai.models import AIRequest
from app.ai.service import get_ai_content_service
from app.core.logging import get_logger
from app.schemas.visual_intelligence import (
    DifficultyLevel,
    DiscoveredComponent,
    InputDescriptor,
    OutputDescriptor,
)
from app.services.visual_prompts import COMPONENT_DISCOVERY_SYSTEM_PROMPT

logger = get_logger(__name__)


class ComponentDiscoveryService:

    async def discover_components(
        self,
        content: str,
        title: str | None = None,
    ) -> list[DiscoveredComponent]:
        """Discover components and extract rich metadata from educational text."""
        if not content.strip():
            return []

        try:
            ai_service = get_ai_content_service()
            prompt = f"Topic Title: {title or 'Topic'}\n\nContent:\n{content[:4000]}"
            req = AIRequest(system_prompt=COMPONENT_DISCOVERY_SYSTEM_PROMPT, user_prompt=prompt, temperature=0.3, scan_for_injection=True)
            res = await ai_service.generate(req)

            data = json.loads(res.text)
            raw_comps = data.get("components", [])
            results: list[DiscoveredComponent] = []

            for comp in raw_comps:
                results.append(
                    DiscoveredComponent(
                        component_id=comp.get("component_id", f"comp_{len(results)+1}"),
                        name=comp.get("name", "Component"),
                        category=comp.get("category", "core"),
                        short_description=comp.get("short_description", "System component"),
                        detailed_working=comp.get("detailed_working", "Operates within the topic workflow."),
                        inputs=[InputDescriptor(**i) if isinstance(i, dict) else InputDescriptor(name=str(i)) for i in comp.get("inputs", [])],
                        outputs=[OutputDescriptor(**o) if isinstance(o, dict) else OutputDescriptor(name=str(o)) for o in comp.get("outputs", [])],
                        dependencies=comp.get("dependencies", []),
                        real_world_analogy=comp.get("real_world_analogy"),
                        importance_weight=float(comp.get("importance_weight", 0.5)),
                        difficulty_level=self._match_difficulty(comp.get("difficulty_level")),
                    )
                )

            if results:
                return results
        except Exception as exc:
            logger.warning("component_discovery_llm_failed_using_heuristic", error=str(exc))

        return self._heuristic_discovery(content, title)

    def _heuristic_discovery(self, content: str, title: str | None) -> list[DiscoveredComponent]:
        """Heuristic fallback component discovery when LLM is offline.

        Uses frequency-across-sentences analysis to find genuine domain concepts
        (terms that appear in multiple sentences) and filters out sentence-starters
        that only appear capitalized once at the beginning of a sentence.
        """
        sentences = [s.strip() for s in re.split(r"[.!?\n]+\s*", content) if s.strip()]
        if not sentences:
            unique_names = [f"{title or 'Topic'} Step {i}" for i in range(1, 4)]
            return self._build_components(unique_names, content, title)

        # Step 1: Extract all capitalized terms per sentence
        sentence_terms: list[set[str]] = []
        for sent in sentences:
            terms = set()
            for match in re.finditer(
                r"\b([A-Z][A-Za-z0-9_\-']*(?:\s+[A-Z][A-Za-z0-9_\-']*)*)\b",
                sent,
            ):
                term = match.group(1).strip()
                if len(term) >= 3 and not self._is_structural_label(term):
                    terms.add(term)
            sentence_terms.append(terms)

        # Step 2: Count how many *different sentences* each term appears in
        term_freq: dict[str, int] = {}
        for terms in sentence_terms:
            for term in terms:
                term_freq[term] = term_freq.get(term, 0) + 1

        # Step 3: Also extract title noun phrase as an anchor
        title_terms = []
        if title:
            # Words to exclude from title extraction (question words, articles, prepositions)
            title_excludes = {
                "what", "how", "why", "when", "where", "which", "who",
                "the", "a", "an", "is", "are", "was", "were", "be",
                "do", "does", "did", "to", "of", "in", "on", "at",
                "for", "with", "by", "from", "into", "about", "between",
            }
            for match in re.finditer(
                r"\b([A-Z][A-Za-z0-9_\-']*(?:\s+[A-Z][A-Za-z0-9_\-']*)*)\b",
                title,
            ):
                t = match.group(1).strip()
                if len(t) >= 2 and t.lower() not in title_excludes and not self._is_structural_label(t):
                    title_terms.append(t)

        # Step 4: Merge multi-word terms — if "Quantum Computing" appears,
        # don't also keep "Quantum" and "Computing" separately
        merged = self._merge_multiword_terms(term_freq)

        # Step 5: Score and rank — title terms get a boost
        scored: list[tuple[str, float]] = []
        for term, freq in merged.items():
            title_boost = 2.0 if any(
                term.lower() == tt.lower() or term.lower() in tt.lower() or tt.lower() in term.lower()
                for tt in title_terms
            ) else 1.0
            score = freq * title_boost
            scored.append((term, score))

        # Also include title terms that didn't appear in content (topic might be mentioned only in title)
        existing = {t.lower() for t in merged}
        for tt in title_terms:
            if not any(tt.lower() == e or tt.lower() in e or e in tt.lower() for e in existing):
                scored.append((tt, 3.0))  # High score since it's the topic itself

        scored.sort(key=lambda x: x[1], reverse=True)

        # Step 6: Take top concepts, filter sentence-starters that only appear once
        filter_starters = {
            "unlike", "when", "however", "therefore", "furthermore", "moreover",
            "additionally", "consequently", "meanwhile", "alternatively", "similarly",
            "otherwise", "nevertheless", "thus", "hence", "since", "although",
            "while", "after", "before", "during", "above", "below", "between",
            "according", "first", "second", "third", "next", "then", "also",
            "here", "there", "this", "that", "these", "those", "another",
            "each", "every", "both", "few", "many", "such", "some", "most",
            "only", "just", "still", "even", "now", "new", "old", "all",
        }

        unique_names: list[str] = []
        seen_lower: set[str] = set()
        for term, _score in scored:
            lower = term.lower()
            if lower in seen_lower:
                continue
            # Filter: if it only appears in 1 sentence AND it's a sentence-starter, skip it
            freq = term_freq.get(term, 1)
            if freq <= 1 and lower in filter_starters:
                continue
            # Also skip very short terms that are likely not real concepts
            if len(term) < 3:
                continue
            seen_lower.add(lower)
            unique_names.append(term)
            if len(unique_names) >= 6:
                break

        if not unique_names:
            unique_names = [f"{title or 'Topic'} Step 1", f"{title or 'Topic'} Step 2", f"{title or 'Topic'} Step 3"]

        return self._build_components(unique_names, content, title)

    def _build_components(
        self, names: list[str], content: str, title: str | None,
    ) -> list[DiscoveredComponent]:
        """Build DiscoveredComponent objects from a list of concept names."""
        components: list[DiscoveredComponent] = []

        for idx, name in enumerate(names, start=1):
            cid = f"comp_{idx}_{re.sub(r'[^a-z0-9]', '_', name.lower())}"
            freq = content.lower().count(name.lower())
            importance = min(1.0, 0.4 + (freq * 0.08))

            # Extract a context sentence for this component
            context = self._find_context_sentence(name, content)

            components.append(
                DiscoveredComponent(
                    component_id=cid,
                    name=name,
                    category=self._categorize_by_position(idx, importance),
                    short_description=context or f"Key concept: {name}.",
                    detailed_working=f"{name} is a fundamental element in {title or 'this topic'}.",
                    inputs=[InputDescriptor(name="Input Data", type="signal")],
                    outputs=[OutputDescriptor(name="Output State", type="result")],
                    dependencies=[components[idx - 2].component_id] if idx > 1 else [],
                    real_world_analogy=self._generate_analogy(name, idx),
                    importance_weight=round(importance, 2),
                    difficulty_level=DifficultyLevel.INTERMEDIATE,
                )
            )

        return components

    @staticmethod
    def _find_context_sentence(name: str, content: str) -> str:
        """Find the most informative sentence containing this concept."""
        sentences = [s.strip() for s in re.split(r"[.!?\n]+\s*", content) if s.strip()]
        # Prefer longer sentences (more context) that contain the term
        matches = [s for s in sentences if name.lower() in s.lower()]
        if matches:
            # Pick the longest match for most context
            best = max(matches, key=len)
            # Truncate to reasonable length
            if len(best) > 120:
                best = best[:120].rsplit(" ", 1)[0] + "..."
            return best
        return ""

    @staticmethod
    def _merge_multiword_terms(term_freq: dict[str, int]) -> dict[str, int]:
        """When 'Quantum Computing' (freq=5) and 'Quantum' (freq=3) both exist,
        keep only 'Quantum Computing' to avoid double-counting fragments."""
        sorted_terms = sorted(term_freq.keys(), key=lambda t: -len(t))
        merged: dict[str, int] = {}
        absorbed: set[str] = set()

        for term in sorted_terms:
            if term in absorbed:
                continue
            merged[term] = term_freq[term]
            # Absorb shorter terms that are substrings of this term
            for other in list(term_freq.keys()):
                if other != term and other.lower() in term.lower() and other not in absorbed:
                    merged[term] += term_freq[other]
                    absorbed.add(other)

        return merged

    @staticmethod
    def _categorize_by_position(idx: int, importance: float) -> str:
        if idx <= 2 or importance >= 0.8:
            return "core"
        if idx <= 4 or importance >= 0.5:
            return "supporting"
        return "peripheral"

    @staticmethod
    def _generate_analogy(name: str, idx: int) -> str:
        analogies = [
            f"Like the foundation of a building — {name} provides the base structure.",
            f"Similar to the engine in a car — {name} drives the core functionality.",
            f"Like the navigation system — {name} guides how information flows.",
            f"Similar to a translator — {name} converts between different formats.",
            f"Like the quality inspector — {name} verifies correctness at each stage.",
            f"Similar to the connective tissue — {name} links other elements together.",
        ]
        return analogies[(idx - 1) % len(analogies)]

    @staticmethod
    def _is_structural_label(name: str) -> bool:
        """True when a candidate is a generic section heading / structural label.

        These are page furniture, not real concepts, and must never become nodes
        (matches the granularity rules in the LLM prompt).
        """
        structural = {
            "course objectives", "learning objectives", "introduction", "abstract",
            "conclusion", "summary", "overview", "objectives", "references",
            "appendix", "bibliography", "literature survey", "literature review",
            "proposed methodology", "methodology", "requirements",
            "hardware and software requirements", "learn", "understand",
            "learn and understand", "project", "about", "key terms",
            "key probability terms", "what you will learn", "takeaways",
            "exercise", "homework", "quiz", "background", "definitions",
            "glossary", "index", "preface", "acknowledgments", "dedication",
        }
        return name.strip().lower() in structural

    @staticmethod
    def _match_difficulty(val: Any) -> DifficultyLevel:
        if not val or not isinstance(val, str):
            return DifficultyLevel.INTERMEDIATE
        v = val.lower()
        if "begin" in v:
            return DifficultyLevel.BEGINNER
        if "adv" in v:
            return DifficultyLevel.ADVANCED
        return DifficultyLevel.INTERMEDIATE
