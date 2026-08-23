# P2 Real-World Learning Effectiveness — Real-User Readiness Assessment

**Date:** 2026-08-20
**Status:** READY FOR REAL-USER PILOT (with caveats)

---

## What This Assessment Covers

This document evaluates whether the EduVision AI effectiveness measurement
infrastructure is ready to be used with real human users in a pilot study.

It does NOT claim that EduVision causes learning. It assesses whether the
software correctly implements the measurement tools needed to COLLECT DATA
for a future effectiveness study.

---

## Infrastructure Checklist

### Data Collection ✅

- [x] **Baseline assessment** — Users can take a pre-test before learning
- [x] **Post assessment** — Users can take a post-test after learning
- [x] **Retention assessment** — Users can take a delayed follow-up test
- [x] **Learning events** — System records lesson_started, lesson_completed,
      quiz_started, quiz_completed, ai_tutor_used, concept_reviewed
- [x] **User feedback** — Subjective ratings (perceived understanding,
      confidence, usefulness, experience) with optional qualitative text
- [x] **Concept-level scores** — Per-concept breakdowns for granular analysis
- [x] **Experiment groups** — Users can be assigned to control/treatment groups

### Data Storage ✅

- [x] EffectivenessAssessment model with all required fields
- [x] LearningEvent model with event tracking
- [x] UserFeedback model with rating aggregation
- [x] SQLite/PostgreSQL compatible (async SQLAlchemy)
- [x] Database migration (0023_learning_effectiveness) for schema changes
- [x] JSONB fields for flexible metadata storage

### Calculation ✅

- [x] Absolute gain = post_score - baseline_score
- [x] Normalized gain = absolute_gain / (100 - baseline_score)
- [x] Retention loss = post_score - retention_score
- [x] Retention percentage = retention_score / post_score * 100
- [x] Concept improvement tracking (pre/post/retention per concept)
- [x] Weak concept identification (post < 50%)
- [x] Strong concept identification (improvement + post >= 80%)

### API Endpoints ✅

- [x] `POST /effectiveness/events` — Record learning event
- [x] `GET /effectiveness/events` — List user's events
- [x] `POST /effectiveness/assessments/start` — Start assessment
- [x] `POST /effectiveness/assessments/{id}/record-score` — Record score
- [x] `GET /effectiveness/assessments/{presentation_id}` — Get assessment
- [x] `GET /effectiveness/learning-gain/{presentation_id}` — Get gain
- [x] `GET /effectiveness/summary` — User summary
- [x] `GET /effectiveness/report/{presentation_id}` — Full report
- [x] `POST /effectiveness/feedback` — Submit feedback
- [x] `GET /effectiveness/feedback/summary/{id}` — Feedback aggregation
- [x] `GET /effectiveness/comparison?group_a=...&group_b=...` — Group comparison

### Testing ✅

- [x] 65+ unit tests (effectiveness, events, feedback, groups)
- [x] 14 validation tests (boundary between software and learning claims)
- [x] 2 E2E integration tests (full chain + retention)
- [x] 816+ total tests passing across the project (0 failures)

---

## What the Pilot CAN Measure

With real users, the system can correctly answer:

1. "What were the user's baseline scores on this quiz?"
2. "What were the user's post-test scores?"
3. "How much did the score change (absolute and normalized gain)?"
4. "What concepts improved, and which are still weak?"
5. "How much time did the user spend learning?"
6. "What events occurred during the learning session?"
7. "How did two groups compare in average score changes?"

These are factual measurements. They are useful for descriptive analytics.

---

## What the Pilot CANNOT Measure

Even with real users, the system cannot answer:

1. **"Did users actually learn?"** — Score gains could be from test
   familiarity, guessing, or easier questions. Learning requires expert
   assessment beyond quiz scores.

2. **"Did EduVision cause better outcomes?"** — Without randomized
   controlled trial design, selection bias and confounders make causal
   claims impossible. The system provides comparison data; it does not
   design or validate experiments.

3. **"Is the difference statistically significant?"** — The system
   computes group averages. It does NOT perform hypothesis testing,
   compute p-values, confidence intervals, or effect sizes. External
   statistical analysis is required.

4. **"Do users retain knowledge long-term?"** — retention_pct measures
   a score ratio, not cognitive memory. True retention assessment
   requires validated instruments (e.g., delayed recall tests designed
   by psychometricians).

5. **"Are users satisfied because the tool works?"** — User feedback
   reflects perception. The Dunning-Kruger effect means perceived
   understanding and actual competence are often poorly correlated.

---

## Requirements for a Valid Pilot Study

To actually measure learning effectiveness, a pilot would need:

### Study Design (NOT provided by this system)
- [ ] Randomized assignment to control/treatment groups
- [ ] Matched groups on prior knowledge, motivation, demographics
- [ ] Control for time-on-task, instructor quality, content quality
- [ ] Pre-registration of hypotheses and analysis plan

### Instruments (NOT validated by this system)
- [ ] Psychometrically validated assessments (not just quizzes)
- [ ] Test-retest reliability for baseline/post instruments
- [ ] Equivalent difficulty between baseline and post quizzes
- [ ] Appropriate difficulty range (not ceiling/floor effects)

### Analysis (NOT performed by this system)
- [ ] Sample size calculation (statistical power analysis)
- [ ] Appropriate statistical tests (t-test, ANOVA, mixed-effects)
- [ ] Effect size reporting (Cohen's d, eta-squared)
- [ ] Confidence intervals for all comparisons
- [ ] Multiple comparison correction (Bonferroni, FDR)
- [ ] Handling of missing data and attrition

### Expertise (NOT provided by this system)
- [ ] Educational researchers to interpret results
- [ ] Psychometricians to validate instruments
- [ ] Statisticians to design analysis
- [ ] IRB approval for human subjects research

---

## Recommendation

**The system is READY for a data-collection pilot.** The measurement
infrastructure is correct, tested, and functional. It will collect
accurate data about score changes, learning events, and user feedback.

**The system is NOT ready to claim learning effectiveness.** That
requires a properly designed study with the elements listed above,
conducted by qualified researchers, with external analysis.

Use the system to collect data. Use qualified experts to interpret it.
