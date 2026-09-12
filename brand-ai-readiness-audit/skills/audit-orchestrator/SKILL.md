---
name: audit-orchestrator
description: >
  Entry point for a full brand AI-readiness audit. Accepts a free-form
  request naming a URL or domain, gathers the site-fetch bundle and the
  brand-name search bundle once, invokes the five focused skills with that
  shared data, and emits one structured JSON report. Use when asked to
  audit a website for AI discoverability and on-site engagement.
license: MIT
compatibility: >
  Requires Python 3.9+, requests, beautifulsoup4, and ddgs. Outbound HTTP
  is the audited origin plus one keyless brand-name search.
allowed-tools: WebFetch Bash(python *)
---

# Audit Orchestrator

This is the marketplace entrypoint. It **composes**; it does not re-derive
D1–D15 / E1–E3. Read-only. Recommend-only.

Sibling skill contracts: each skill's `SKILL.md` Inputs / Output, plus
`references/checks.md` where present.

## When to use

Use when the user wants a **full** audit of an unseen site: crawl/access,
structured data, corroboration, identity, and on-page orientation in one
report. Do not use this skill to implement a single check — call the
owning skill instead.

## Inputs

A **free-form** audit request that names a URL or domain, for example:

- `https://example.com`
- `Audit example.com for AI readiness`
- `Why don't assistants cite https://www.example.com/?`

Not a fixed CLI flag schema. `scripts/run_audit.py` takes the remainder of
the command line as that request. Optional `--brand` overrides the name
used for search when the request does not contain one.

## Procedure (numbered, deterministic steps)

From this skill folder (or the marketplace root):

```bash
python skills/audit-orchestrator/scripts/run_audit.py Audit https://example.com
python skills/audit-orchestrator/scripts/run_audit.py example.com --brand "Example"
```

1. **Parse the request.** Extract the first URL/domain. Derive `origin`
   and `host`. Brand name = `--brand`, else a quoted name in the request,
   else homepage title (after fetch, and only if fetch-quality is
   usable), else the domain label. Never take a brand name from a 404
   stub or bot-challenge title.
2. **Site fetch bundle (once).** Use crawl-render-audit's
   `http_client.py`, `robots_parser.py`, and `sitemap_sampler.py` — do not
   reimplement fetching. Homepage first, then robots.txt, then declared
   or default sitemap, then a small sample of **real** sitemap URLs.
   Respect robots.txt after the homepage probe. Never guess paths.
3. **Brand-name search bundle (once).** Use freshness-corroboration's
   `web_search.py` / `source_classifier.py` (keyless DuckDuckGo, same
   pattern: keyless DuckDuckGo, no API key). Do not search again later.
4. **Invoke each skill's `run()`**, passing only what its Inputs section
   asks for:

   | Skill | What it receives |
   |---|---|
   | crawl-render-audit | origin + the site bundle (no second crawl) |
   | structured-data-audit | origin + homepage HTML + `sampled_pages` |
   | freshness-corroboration | brand, host, search bundle, homepage |
   | entity-clarity-audit | brand, host, **same** search bundle, self-description from the homepage extract |
   | engagement-audit | homepage HTML (same fetch) |

5. **Merge findings** in skill order (crawl → structured → freshness →
   entity → engagement). Assign stable ids `F-001`, `F-002`, … in that
   sequence. Keep each finding's `title`, `severity`, `evidence`,
   `suggested_action`.
6. **Summarize.** `total_findings`, `critical`, `high`, `medium`, `low`.
7. **Coverage (extra field).** Record what was sampled, homepage
   fetch-quality, preferred locale, and which checks were skipped so a
   zero-finding report is distinguishable from an under-sampled one.
8. **Validate** against [references/report_schema.md](references/report_schema.md)
   before printing. If validation fails, fix the report or raise — do not
   emit invalid JSON.

## Output

Exactly the context schema (extra fields allowed, these required):

```json
{
  "site": "example.com",
  "audited_at": "2026-09-20T14:32:00Z",
  "summary": {
    "total_findings": 6,
    "critical": 1,
    "high": 2,
    "medium": 3,
    "low": 0
  },
  "findings": [
    {
      "id": "F-001",
      "title": "…",
      "severity": "high",
      "evidence": "…",
      "suggested_action": {
        "summary": "…",
        "priority": "high"
      }
    }
  ]
}
```

`scripts/run_audit.py` prints that JSON on stdout. That is the Phase 8
dry-run entrypoint. An extra `coverage` object is always included
(sampled URLs, fetch-quality, skipped checks). Extra fields are allowed
by the schema.

## Guardrails

- Recommend-only. No writes, forms, logins, or authenticated areas.
- Respect robots.txt for every request after the homepage D3 probe.
- Same-origin site fetches. The only off-origin call is the keyless
  brand-name search.
- One site crawl, one search. Skills must not re-fetch when given bundles.
- Stay under 5 minutes. Small samples, timeouts, delays.
- Patterns and counts only — no hardcoded evaluation sites.
