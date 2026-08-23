# P3.12 Real Analytics CSV Export — Final Report

**Date:** 2026-08-20
**Status:** COMPLETE

---

## 1. Files Created

| File | Purpose |
|---|---|
| `tests/integration/test_p3_12_export.py` | 17 tests: 10 service-level, 7 API-level |

## 2. Files Modified

| File | Change |
|---|---|
| `app/services/effectiveness_service.py` | Added `export_study_data()` method + `_sanitize_csv_text()` helper + `UserFeedback`/`func`/`hashlib` imports |
| `app/api/v1/effectiveness.py` | Added `GET /effectiveness/export` endpoint + `csv`/`io`/`datetime`/`StreamingResponse` imports |

## 3. Files Deleted

None. The old `export_presentation_analytics_csv()` method in `export_service.py` was left untouched — it's unreachable (no router registered) and serves as reference for future presentation-level export.

## 4. API Endpoint

```
GET /api/v1/effectiveness/export
```

- **Authentication:** Required (`Depends(get_current_user)`)
- **Query parameters:** `experiment_group` (optional, string, max 50 chars)
- **Response:** `text/csv; charset=utf-8` with `Content-Disposition: attachment`
- **Authorization:** Exports only the authenticated user's own assessment data

## 5. CSV Schema

| Column | Source | Null Handling |
|---|---|---|
| `participant_id` | SHA-256(user_id)[:16] | Always present |
| `experiment_group` | assessment.experiment_group | Empty string if NULL |
| `baseline_score` | assessment.baseline_score | Empty string if NULL |
| `post_score` | assessment.post_score | Empty string if NULL |
| `retention_score` | assessment.retention_score | Empty string if NULL |
| `absolute_gain` | Computed (post - baseline) | Empty string if NULL |
| `normalized_gain` | Computed (gain / (100 - baseline)) | Empty string if NULL |
| `retention_delay_hours` | assessment.retention_delay_hours | Empty string if NULL |
| `retention_loss` | Computed (post - retention) | Empty string if NULL |
| `retention_pct` | Computed (retention / post × 100) | Empty string if NULL |
| `learning_time_seconds` | assessment.total_learning_time_seconds | Empty string if NULL |
| `status` | assessment.status | Empty string if NULL |
| `completed_at` | assessment.completed_at (ISO 8601) | Empty string if NULL |
| `fb_perceived_understanding` | UserFeedback (max per assessment) | Empty string if NULL |
| `fb_confidence` | UserFeedback (max per assessment) | Empty string if NULL |
| `fb_usefulness` | UserFeedback (max per assessment) | Empty string if NULL |
| `fb_visual_usefulness` | UserFeedback (max per assessment) | Empty string if NULL |
| `fb_animation_usefulness` | UserFeedback (max per assessment) | Empty string if NULL |
| `fb_tutor_usefulness` | UserFeedback (max per assessment) | Empty string if NULL |
| `fb_recommendation_usefulness` | UserFeedback (max per assessment) | Empty string if NULL |
| `fb_overall_experience` | UserFeedback (max per assessment) | Empty string if NULL |
| `qualitative_feedback` | UserFeedback.qualitative_feedback | Empty string if NULL |

## 6. Database Queries Used

**Single query with LEFT JOIN subquery:**

1. Subquery: Aggregates `UserFeedback` per `assessment_id` using `GROUP BY` with `MAX()` on each rating field
2. Main query: `EffectivenessAssessment` LEFT JOIN subquery on `assessment_id`
3. Filter: `WHERE user_id = :authenticated_user_id`
4. Optional filter: `AND experiment_group = :group`
5. Order: `ORDER BY created_at`

No N+1 queries. Single query per export request.

## 7. Authorization Model

- All endpoints require JWT authentication via `Depends(get_current_user)`
- `export_study_data()` filters by `user_id = authenticated_user_id`
- User A cannot export User B's data — query is scoped to authenticated user
- No role-based access control needed (universal platform)

## 8. Data Isolation Verification

Tested in `test_does_not_expose_other_users_data`: creates assessment for OTHER_USER, verifies export for TEST_USER returns empty list.

## 9. Experiment-Group Support

- Optional `?experiment_group=eduvision` query parameter
- Filters assessments by stored `experiment_group` value
- No automatic labeling — exports actual stored value
- Tested in `test_filters_by_experiment_group` (service + API)

## 10. Empty/Edge-Case Handling

| Case | Handling |
|---|---|
| No assessments | Returns empty CSV (header only) |
| Only baseline (no post) | `post_score=""`, `absolute_gain=""` |
| Baseline without post-test | Same as above |
| Missing retention | `retention_score=""`, `retention_loss=""` |
| Missing feedback | All `fb_*` fields = `""` |
| Missing experiment group | `experiment_group=""` |
| Zero learning time | `learning_time_seconds=""` |
| Incomplete assessment | Status reflects actual state |
| NULL values | Rendered as empty string (not "None", not "0") |
| Multiple assessments | One row per assessment |
| No student/teacher relationship | Universal user_id terminology only |

## 11. CSV Injection/Security Handling

`_sanitize_csv_text()` prefixes text starting with `=`, `+`, `-`, `@`, `\t`, or `\r` with a single quote `'`. This prevents spreadsheet formula interpretation while keeping text readable.

`csv.DictWriter` handles structural CSV escaping (quoting, delimiters).

## 12. Migration Status

**No database migration required.** The export queries existing `effectiveness_assessments` and `user_feedback` tables. No new columns or tables needed.

## 13. Tests Added

**17 tests** in `tests/integration/test_p3_12_export.py`:

| # | Test | Proves |
|---|---|---|
| 1 | `test_returns_real_db_data` | Real DB → real query → correct values |
| 2 | `test_returns_multiple_assessments` | Multiple rows rendered correctly |
| 3 | `test_filters_by_experiment_group` | Group filter works (service) |
| 4 | `test_empty_dataset_returns_empty_list` | Empty case handled |
| 5 | `test_includes_feedback_when_present` | Feedback JOIN works |
| 6 | `test_missing_feedback_shows_empty_strings` | Missing feedback = "" |
| 7 | `test_pseudonymized_participant_id` | user_id not exposed |
| 8 | `test_does_not_expose_other_users_data` | Isolation verified |
| 9 | `test_csv_injection_prefix` | Injection prevention works |
| 10 | `test_null_scores_rendered_as_empty` | NULL ≠ 0 |
| 11 | `test_endpoint_returns_csv` | Full API flow: auth → DB → CSV |
| 12 | `test_endpoint_requires_authentication` | 401 without token |
| 13 | `test_filters_by_experiment_group` (API) | Group filter via HTTP |
| 14 | `test_empty_dataset_returns_header_only` | Empty CSV via API |
| 15 | `test_no_sensitive_data_exposed` | No passwords/tokens in CSV |
| 16 | `test_csv_headers_are_correct` | 22 columns match schema |
| 17 | `test_no_hardcoded_sample_data` | No 92.5/88.0/usr_ values |

## 14. Full Regression Result

```
837 passed, 1 xfailed, 0 failures
```

Baseline: 820 passed + 17 new = 837 passed. No regressions.

## 15. Ruff Result

```
All checks passed!
```

## 16. Before vs After Comparison

| Aspect | Before | After |
|---|---|---|
| CSV export data | 2 hardcoded fake rows | Real DB records |
| Participant IDs | Random UUID per call | SHA-256 pseudonymized |
| Scores | Fixed 92.5/88.0 | Actual DB values |
| API endpoint | Not registered (source deleted) | `GET /effectiveness/export` |
| Authentication | N/A (unreachable) | Required JWT |
| Authorization | None | user_id scoped |
| Feedback data | Not included | LEFT JOIN with ratings |
| Experiment group | N/A | Filterable |
| Tests | 0 (endpoint didn't exist) | 17 integration tests |
| Hardcoded data in production | Yes | No |

## 17. Remaining Limitations

1. **Old hardcoded export code untouched:** `export_presentation_analytics_csv()` in `export_service.py` still contains fake data but is unreachable (no router registered). Left as-is to avoid breaking unrelated export infrastructure.

2. **One row per assessment, not per participant:** The export produces one CSV row per effectiveness assessment. A participant with 5 presentations gets 5 rows. This is intentional for study analysis.

3. **Feedback aggregation uses MAX():** When multiple feedback records exist per assessment, MAX() picks the highest value. This is a simplification; a future improvement could use the most recent feedback.

4. **No CSV streaming for large datasets:** Current implementation builds entire CSV in memory. Acceptable for pilot scale (hundreds of participants); would need streaming for thousands.

5. **qualitative_feedback CSV injection:** Only prefixes dangerous characters at the start of the string. Mid-string formula injection is not a concern for CSV (only affects the first character of a cell).

## 18. Pilot Readiness

**Yes — the export is genuinely ready for pilot use.**

The endpoint:
- Returns real database data with no hardcoded values
- Requires authentication
- Is scoped to the authenticated user's own data
- Handles all edge cases (empty data, missing fields, null values)
- Prevents CSV injection
- Has 17 integration tests proving the complete flow
- Passes full regression (837 passed, 0 failures)

## 19. Student/Teacher Relationship Confirmation

**NO student/teacher relationship was introduced.** All terminology uses:
- `user_id` / `participant_id`
- `experiment_group`
- `assessment_type`
- `baseline_score` / `post_score` / `retention_score`
- `learning_time_seconds`

No `student_id`, `teacher_id`, `classroom`, `assignment`, or role-based restrictions were added.
