---
name: freshness-corroboration
description: >
  Check whether what is said about a brand on its own site and elsewhere is
  current, agreed-upon, and repeated across independent sources: thin search
  footprint, the official domain missing from its own name search, low-diversity
  corroboration, contradicted facts, and weak copyright/freshness signals.
  Use when auditing why assistants under-cite or misstate a brand.
license: MIT
compatibility: >
  Requires Python 3.9+, requests, beautifulsoup4, and ddgs (keyless search).
  Search is the brand-name query only; site fetches stay on the audited origin.
allowed-tools: WebFetch Bash(python *)
---

# Freshness & Corroboration

Read-only. Do not modify the live site. This skill works standalone: given a
brand name and domain, it runs its own keyless search if no search bundle is
provided.

Detailed check-by-check rules: [references/checks.md](references/checks.md).

## When to use

Use when the question is whether the brand is **current, agreed-upon, and
repeated across independent sources**. Typical triggers: thin organic
footprint, official domain absent from a name search, aggregator-only
sources, or stale on-site facts.

Do not use this skill for crawl/access, JSON-LD quality, name-collision
judgment (D14/D15), or on-page orientation.

## Inputs

- **Required:** brand/entity name and the audited domain (or a URL from which
  both can be derived).
- **Optional — pre-fetched brand-name search bundle (preferred):** the keyless
  search results for the exact brand name (titles, URLs, snippets, distinct
  domains, source-type buckets). Accept this when the caller already ran the
  search. Do not search again.
- **Optional — pre-fetched homepage** from the site bundle (for D12 official
  facts and D13 copyright / `Last-Modified`). Fetch the homepage yourself if
  none is provided.

Dependencies: `pip install requests beautifulsoup4 ddgs`.

## Procedure (numbered, deterministic steps)

```bash
python scripts/run_audit.py https://example.com
python scripts/run_audit.py https://example.com --brand "Example" --search-bundle search.json --bundle site_bundle.json
```

Full rules: [references/checks.md](references/checks.md).

1. **Resolve brand name** from `--brand`, the request, the homepage title, or
   the domain label — in that order.
2. **Search once** with `scripts/web_search.py` (keyless DuckDuckGo, no
   API key) unless a search bundle is provided. Do not take a brand name
   from a 404 stub or bot-challenge title.
3. **D9 — footprint.** Count distinct result domains. `high` if under 3;
   `medium` if under 5.
4. **D10 — own domain absent.** Compare registrable domain (eTLD+1), so a
   subdomain of the audited site counts. If other results exist and none
   share that eTLD+1: `critical`.
5. **D11 — source diversity.** `scripts/source_classifier.py` buckets each
   domain (reference, press, review/directory, social, official, other). If
   two or more results exist and only one bucket is represented: `medium`.
6. **D12 — facts.** Extract 1–2 checkable official-site facts (founding year,
   HQ-style location). Compare to search snippets. `high` if contradicted;
   `low` if merely unconfirmed.
7. **D13 — copyright / Last-Modified.** Regex for `©`/`copyright` + year;
   read `Last-Modified` if present. **Severity is hard-capped at `low` in
   the script — never raise it.** Absence of a year does not fire (noisy:
   41% of n=100+22 sites had no year, confirming the Phase 2 Low cap).
   A year two or more years behind the current calendar year may fire, still
   `low` only.
8. **Emit** findings plus the search bundle for reuse by entity-clarity-audit.

## Output

Standalone JSON from `scripts/run_audit.py`. Findings use ids `D9`–`D13`.
`search_bundle` is the reusable search (query, results, distinct domains,
buckets). A later orchestrator may rewrite ids to `F-00N`.

## Guardrails

- Recommend-only. No writes, no login, no authenticated areas.
- Keyless search for the brand name only. No paid APIs.
- Homepage fetch is same-origin when this skill fetches it itself.
- **D13 can never be anything but `low`.** That cap is in the procedure and
  in `scripts/run_audit.py`, not a footnote.
- Patterns and counts only — no hardcoded brands.
- D9–D15 can vary run-to-run: they depend on live keyless search hits, not only fetched page content.
