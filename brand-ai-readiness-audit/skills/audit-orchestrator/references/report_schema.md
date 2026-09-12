# Final report schema

Mandatory floor from `context_adobe.md`. Extra fields are allowed.
`scripts/validate_report.py` rejects a report that is missing any of these.

## Root

| Field | Type | Rule |
|---|---|---|
| `site` | string | Non-empty host (no scheme required) |
| `audited_at` | string | ISO-8601 UTC timestamp |
| `summary` | object | See below |
| `findings` | array | Zero or more finding objects |

## `summary`

| Field | Type | Rule |
|---|---|---|
| `total_findings` | int | Must equal `len(findings)` |
| `critical` | int | Count of findings with severity `critical` |
| `high` | int | Count of severity `high` |
| `medium` | int | Count of severity `medium` |
| `low` | int | Optional but emitted; count of severity `low` |

## Each finding

| Field | Type | Rule |
|---|---|---|
| `id` | string | `F-001`, `F-002`, … stable, sequential, 3-digit |
| `title` | string | Non-empty |
| `severity` | string | `critical` \| `high` \| `medium` \| `low` |
| `evidence` | string | Non-empty; must cite something observed |
| `suggested_action` | object | `summary` (string) and `priority` (string) |

Severity counts must match the findings array. Ids must be unique.

## Extra: `coverage` (emitted by the orchestrator)

Not required by the schema floor. Always included so a clean report can
be told apart from an under-sampled or interstitial fetch.

Typical keys: `homepage_fetch_quality`, `preferred_locale`,
`sampled_internal_urls`, `sampled_page_count`, `path_classes`,
`check_notes`, `skipped_checks`, `skills`, `brand_used`.

`skipped_checks` lists only checks that **could not run** (unusable
fetch, no search results, no sample). Checks that ran and did not fire
are recorded in `check_notes` with `status` `clear` or `no_signal`, not
as skips.

`check_notes` values: `{status, reason, skill}` where status is
`skipped` | `no_signal` | `clear` | `fired`.
