# P3 Study Design & Pilot Protocol

**Date:** 2026-08-20
**Status:** Documentation — no code changes

---

## P3.2 — Measurable Outcomes

### Classification Key

Every metric is classified as one of:

- **A — Learning outcome:** Measures change in assessed knowledge. Can only be
  interpreted as evidence of learning if the study design supports causal claims.
  The software calculates these correctly; it does NOT prove learning occurred.

- **B — Behavioral/product metric:** Measures what the user did, not what they
  learned. Useful for understanding engagement and usage patterns.

- **C — User-experience metric:** Measures how the user felt. Subjective.
  Correlation with actual learning is unknown without external validation.

---

### Primary Outcome

#### Absolute Learning Gain (Classification: A)

```
absolute_gain = post_test_score - baseline_score
```

**What it measures:** The difference between a participant's post-test score and
their baseline (pre-test) score on the same or equivalent assessment.

**What it does NOT measure:** Whether the participant actually learned,
understood, or retained the material. Score changes can result from test
familiarity, guessing, motivation, difficulty differences, or actual learning.

**System field:** `EffectivenessAssessment.absolute_gain`

**Range:** -100 to +100 (theoretically). Negative values are valid measurements.

---

### Secondary Outcomes

#### 1. Normalized Learning Gain (Classification: A)

```
normalized_gain = absolute_gain / (100 - baseline_score)
```

**What it measures:** The fraction of potential improvement achieved. A
normalized gain of 0.4 means the participant improved by 40% of the maximum
possible improvement from their baseline.

**Why it matters:** A 20-point gain from a 30 baseline is more impressive than
a 20-point gain from an 80 baseline. Normalized gain accounts for this.

**System field:** `EffectivenessAssessment.normalized_gain`

**Range:** -∞ to 1.0 (1.0 = perfect improvement from baseline to 100).

---

#### 2. Retention Score (Classification: A)

```
retention_score = score on delayed post-test
```

**What it measures:** The participant's score on a delayed follow-up assessment,
administered after a configurable delay (typically 24–72 hours).

**What it does NOT measure:** Whether the participant "retained" knowledge.
The score ratio is a mathematical measurement, not a cognitive assessment.

**System field:** `EffectivenessAssessment.retention_score`

---

#### 3. Retention Change (Classification: A)

```
retention_loss = post_score - retention_score
retention_pct = retention_score / post_score × 100
```

**What it measures:** How much the score changed between post-test and retention
test. `retention_pct` is the fraction of the post-test score maintained.

**What it does NOT measure:** Memory, forgetting rate, or long-term knowledge
retention. These require psychometrically validated instruments.

**System fields:** `EffectivenessAssessment.retention_loss`, `retention_pct`

---

#### 4. Concept Mastery Improvement (Classification: A)

Per-concept score changes from baseline to post-test.

**What it measures:** Which specific concepts improved and by how much, based
on quiz question scoring.

**What it does NOT measure:** Whether the participant actually mastered the
concept. Quiz performance ≠ concept mastery.

**System fields:** `EffectivenessAssessment.baseline_concept_scores`,
`post_concept_scores`, `concept_improvements` (computed in `_format_gain`)

---

#### 5. Learning Time (Classification: B — Behavioral)

```
total_learning_time_seconds = sum of durations between learning events
```

**What it measures:** Approximate time elapsed between recorded learning events
(lesson started, quiz started, AI tutor used, etc.). Computed from consecutive
event timestamps with a 2-hour maximum gap.

**What it does NOT measure:** Actual time spent learning. Participants may be
idle, multitasking, or step away from the screen.

**System field:** `EffectivenessAssessment.total_learning_time_seconds`

---

#### 6. Completion Rate (Classification: B — Behavioral)

```
status = "completed" if baseline AND post scores are recorded
       = "in_progress" if any score is recorded
       = "not_started" if no scores are recorded
```

**What it measures:** Whether the participant completed the assessment sequence.

**What it does NOT measure:** Quality of engagement or learning effort.

**System field:** `EffectivenessAssessment.status`

---

#### 7. User Understanding / Confidence (Classification: C — User Experience)

```
perceived_understanding: 1–5 Likert scale
confidence: 1–5 Likert scale
```

**What it measures:** How well the participant *thinks* they understood the
material and how confident they feel.

**Important caveat:** Perceived understanding and actual competence are often
poorly correlated (Dunning-Kruger effect). High confidence does NOT indicate
effective learning.

**System field:** `UserFeedback.perceived_understanding`, `confidence`

---

#### 8. Visual Usefulness (Classification: C — User Experience)

```
visual_usefulness: 1–5 Likert scale
```

**What it measures:** How useful the participant found the visual explanations.

**What it does NOT measure:** Whether visuals actually improved learning.
Usefulness perception ≠ learning effectiveness.

**System field:** `UserFeedback.visual_usefulness`

---

#### 9. Animation/Simulation Usefulness (Classification: C — User Experience)

**Measurement:** Covered by `visual_usefulness` for visual components.
No separate animation-specific Likert scale exists.

**Assessment:** If animation-specific feedback is needed, `extra_json` on
`UserFeedback` can store additional fields without schema changes.

**System field:** `UserFeedback.visual_usefulness` (for visuals) or
`UserFeedback.extra_json` (for animation-specific)

---

#### 10. AI Tutor Usefulness (Classification: C — User Experience)

```
tutor_usefulness: 1–5 Likert scale
```

**What it measures:** How useful the participant found the AI tutor.

**What it does NOT measure:** Whether the AI tutor improved learning outcomes.

**System field:** `UserFeedback.tutor_usefulness`

---

#### 11. Overall User Satisfaction (Classification: C — User Experience)

```
overall_experience: 1–5 Likert scale
qualitative_feedback: free text (max 2000 chars)
```

**What it measures:** General satisfaction with the learning experience.

**What it does NOT measure:** Learning effectiveness. Satisfied users may or
may not have learned anything.

**System field:** `UserFeedback.overall_experience`, `qualitative_feedback`

---

### Outcome Summary Table

| # | Metric | Classification | System Field | Measures |
|---|---|---|---|---|
| 1 | Absolute gain | A — Learning outcome | `absolute_gain` | Score change |
| 2 | Normalized gain | A — Learning outcome | `normalized_gain` | Fractional improvement |
| 3 | Retention score | A — Learning outcome | `retention_score` | Delayed test score |
| 4 | Retention change | A — Learning outcome | `retention_loss`, `retention_pct` | Score decay |
| 5 | Concept improvement | A — Learning outcome | `concept_improvements` | Per-concept delta |
| 6 | Learning time | B — Behavioral | `total_learning_time_seconds` | Time elapsed |
| 7 | Completion | B — Behavioral | `status` | Sequence finished |
| 8 | Understanding/confidence | C — User experience | `perceived_understanding`, `confidence` | Self-report |
| 9 | Visual usefulness | C — User experience | `visual_usefulness` | Self-report |
| 10 | AI tutor usefulness | C — User experience | `tutor_usefulness` | Self-report |
| 11 | Overall satisfaction | C — User experience | `overall_experience` | Self-report |

---

## P3.3 — Pilot Protocol

### 1. Research Objective

**Objective:** Determine whether participants who learn with EduVision show
greater improvement from baseline to post-test compared to participants who
use alternative learning methods.

**Hypothesis (to be tested):** [Not pre-specified — this is exploratory.]

**Design:** Comparative, non-randomized pilot study with two groups.

**Important:** This protocol defines how data will be collected. It does NOT
predetermine outcomes. The purpose is to gather evidence; the interpretation
requires qualified researchers.

---

### 2. Participants

**Target participants:** [To be determined before recruitment.]

**Eligibility criteria:**
- Has basic familiarity with the learning topic (not complete novice, not expert)
- Willing to complete baseline assessment, learning session, post assessment,
  and retention assessment
- Consents to anonymous data collection for study purposes

**Exclusion criteria:**
- Subject-matter experts with ceiling-level baseline scores (>90%)
- Individuals unable to complete the assessment sequence

**No teacher/student role required.** Each participant interacts directly with
the system as a user.

---

### 3. Topic Selection

**Criteria for selecting learning topics:**

| Criterion | Rationale |
|---|---|
| Understandable to participants | Participants must be able to engage with the material |
| Measurable through assessment | Quiz questions can detect knowledge differences |
| Sufficient source material | At least one document/presentation to process |
| Suitable for visual explanation | Topic benefits from diagrams, flowcharts, or simulations |
| Suitable for quiz generation | Topic has factual/procedural content for quiz questions |
| Suitable for retention testing | Topic is distinct enough to test after a delay |

**Recommended topic characteristics:**
- Concrete (not abstract philosophy)
- Multi-concept (allows concept-level analysis)
- Moderate difficulty (avoids ceiling/floor effects)

**Source material:** One or more uploaded documents (PDF, DOCX, PPTX, TXT).

---

### 4. Baseline Assessment

**Procedure:**
1. Participant uploads or is provided with source material
2. System generates quiz from source material
3. Participant completes quiz (baseline assessment)
4. System records: `baseline_score`, `baseline_concept_scores`
5. Assessment is tagged with `experiment_group`

**API flow:**
```
POST /effectiveness/assessments/start
  { presentation_id, assessment_type: "baseline", experiment_group: "reference"|"eduvision" }

→ Participant takes quiz
→ QuizAttempt.percent_score is recorded

POST /effectiveness/assessments/{id}/record-score?assessment_type=baseline
  { quiz_attempt_id, concept_scores }
```

**Purpose:** Establishes each participant's starting knowledge before any
learning intervention.

---

### 5. Learning Intervention

#### EduVision Group

Full pipeline:
```
Source document
  → Content understanding (parsing, chunking)
  → Concept extraction
  → Lesson generation (AI-powered with fallback)
  → Visual generation (intelligence pipeline, animation, simulation)
  → Quiz generation
  → Mastery tracking
  → Recommendations
  → AI tutor access
```

**This is the existing production flow.** No separate learning pipeline is needed.

**Learning events recorded:**
- `lesson_started` — when the participant begins the lesson
- `lesson_completed` — when the participant finishes the lesson
- `ai_tutor_used` — when the participant interacts with the AI tutor
- `quiz_completed` — when the participant completes a practice quiz
- `concept_reviewed` — when the participant reviews a specific concept

**Learning time tracked:** Approximate duration from first to last learning
event.

#### Reference Group

Uses alternative learning method (e.g., reading the source document directly,
or a non-EduVision tool). The specific reference method is defined by the
study administrator, not by this system.

**The system does not enforce how the reference group learns.** It only measures
their scores for comparison.

---

### 6. Post Assessment

**Procedure:**
1. After completing the learning session, participant takes a post-test
2. System records: `post_score`, `post_concept_scores`
3. System computes: `absolute_gain`, `normalized_gain`
4. Assessment status updated to `completed`

**Timing:** Immediately after the learning session (same session).

**API flow:**
```
POST /effectiveness/assessments/start
  { presentation_id, assessment_type: "post" }

→ Participant takes post-quiz
→ POST /effectiveness/assessments/{id}/record-score?assessment_type=post
  { quiz_attempt_id, concept_scores }
```

**Important:** Post-test gains measure score change, not learning. The
distinction must be maintained in all reporting.

---

### 7. Retention Assessment

**Procedure:**
1. After a configurable delay (recommended: 24–72 hours), participant is
   invited back for a retention assessment
2. System records: `retention_score`, `retention_delay_hours`
3. System computes: `retention_loss`, `retention_pct`

**Configurable delay:** The `retention_delay_hours` field allows study
administrators to set the appropriate delay for their topic and population.

**API flow:**
```
POST /effectiveness/assessments/start
  { presentation_id, assessment_type: "retention", retention_delay_hours: 48 }

→ Participant takes retention-quiz
→ POST /effectiveness/assessments/{id}/record-score?assessment_type=retention
  { quiz_attempt_id }
```

**Non-response handling:** If a participant does not return for the retention
assessment, their retention fields remain `null`. This is expected attrition.

---

### 8. Feedback Collection

**Procedure:**
After completing all assessments, participant optionally submits feedback.

**Dimensions measured (all 1–5 Likert scale):**

| Dimension | Field | What It Captures |
|---|---|---|
| Ease of understanding | `perceived_understanding` | How well participant thinks they understood |
| Confidence | `confidence` | How confident participant feels about the material |
| Visual usefulness | `visual_usefulness` | Value of visual explanations |
| AI tutor usefulness | `tutor_usefulness` | Value of AI tutor interactions |
| Recommendation usefulness | `recommendation_usefulness` | Value of suggested next steps |
| Overall satisfaction | `overall_experience` | General experience rating |
| Qualitative feedback | `qualitative_feedback` | Open-ended comments (max 2000 chars) |

**API flow:**
```
POST /effectiveness/feedback
  { presentation_id, perceived_understanding: 4, confidence: 3, ... }
```

**Note:** Animation/simulation usefulness is not a separate field. If needed,
it can be captured via `extra_json` or by asking in `qualitative_feedback`.

---

### 9. Comparison Methodology

**Groups:**
- **reference** — Uses alternative learning method (defined by study admin)
- **eduvision** — Uses full EduVision pipeline

**Comparison endpoint:**
```
GET /effectiveness/comparison?group_a=reference&group_b=eduvision
```

**Returns:**
- Participant count per group
- Average baseline score per group
- Average post-test score per group
- Average absolute gain per group
- Average normalized gain per group
- Number of completed assessments per group

**Statistical analysis:** Not performed by the system. Raw averages are exported
for external analysis by qualified researchers.

**Important:** Observed differences in averages do NOT prove that one group
learned more. Confounders (motivation, prior knowledge, time-of-day, sample
size) must be accounted for by the study design and statistical analysis.

---

### 10. Data Collected

**Per participant, per presentation:**

| Data Point | Source | Purpose |
|---|---|---|
| User ID | Authentication | Participant identification (pseudonymous) |
| Experiment group | Admin assignment | Group membership |
| Baseline score | Baseline quiz | Starting knowledge |
| Baseline concept scores | Baseline quiz | Per-concept starting knowledge |
| Post-test score | Post quiz | Ending knowledge |
| Post concept scores | Post quiz | Per-concept ending knowledge |
| Absolute gain | Computed | Score change |
| Normalized gain | Computed | Fractional improvement |
| Retention score | Retention quiz | Delayed knowledge |
| Retention delay | Admin-configured | Delay duration |
| Learning time | Event timestamps | Approximate engagement time |
| Learning events | Event recording | Activity log |
| Completion status | Assessment lifecycle | Whether sequence was finished |
| Feedback (7 ratings) | Participant submission | Subjective experience |
| Qualitative feedback | Participant submission | Open comments |

**Data NOT collected:** Name, email, IP address, demographic information,
browsing history, or any personally identifiable information beyond the
pseudonymous user ID.

---

### 11. Analysis Plan

**Phase 1 — Descriptive statistics (performed by system):**
- Mean, median, range of baseline scores per group
- Mean, median, range of post-test scores per group
- Mean absolute and normalized gain per group
- Retention scores and loss per group
- Completion rates per group
- Feedback averages per group

**Phase 2 — Comparative analysis (performed externally):**
- Appropriate statistical tests (t-test, Mann-Whitney, ANOVA)
- Effect size calculation (Cohen's d)
- Confidence intervals
- Handling of missing data (attrition)

**Phase 3 — Interpretation (performed by researchers):**
- Contextual factors
- Confounding variables
- Practical significance
- Recommendations for future studies

---

### 12. Limitations

**Study design limitations:**
- Non-randomized groups (selection bias possible)
- No blinding (participants know their group)
- Single-topic assessment (generalizability unclear)
- Self-selected participation (volunteer bias)

**Measurement limitations:**
- Quiz scores ≠ learning (test familiarity, guessing, difficulty)
- Self-reported feedback ≠ objective effectiveness
- Learning time ≈ approximate (not precise)
- Retention score ≠ long-term memory

**System limitations:**
- No statistical inference (raw averages only)
- No validated assessment instruments (quizzes, not psychometric tests)
- No control for time-on-task (reference group may spend more/less time)
- No mechanism for blinding group assignment

---

## Appendix: Pipeline Verification

The learning intervention pipeline (P3.4) has been verified as production-ready:

```
Source document
  → DocumentParser (PDF/DOCX/PPTX/TXT)
  → ContentExtractionService (structural extraction)
  → ChunkingService (4 strategies, 12+ languages)
  → ConceptService (concept creation/management)
  → LessonGenerationService (AI + heuristic fallback, 790 lines)
  → VisualIntelligenceService (11-step pipeline, 22 categories)
  → AnimationPlannerService (scene/timeline planning)
  → SimulationEngineService (stateful sessions)
  → QuizGenerationService (AI-powered, 7 question types)
  → QuizAttemptService (delivery, 853 lines)
  → EducationalMemoryService (mastery tracking)
  → RecommendationEngine (threshold-based, 288 lines)
  → LearningAssistantService (AI tutor, 589 lines)
```

All services are tested. No separate pipeline is needed for the pilot.
