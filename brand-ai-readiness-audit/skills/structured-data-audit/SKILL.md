---
name: structured-data-audit
description: >
  Detect missing or too-generic JSON-LD / schema.org markup that leaves a
  machine nothing structured to extract, even when the page is readable
  prose: no application/ld+json blocks, or @type values that are only
  generic (Organization, WebSite) with no domain-specific type. Use when
  auditing why an assistant might fail to pull specific facts from an
  otherwise reachable site.
license: MIT
compatibility: >
  Requires Python 3.9+, requests, and beautifulsoup4. Outbound HTTP is limited
  to the audited origin (homepage and sampled pages).
allowed-tools: WebFetch Bash(python *)
---

# Structured Data Audit

Read-only. Do not modify the live site. This skill works standalone: given a
URL, it gathers pages itself if no site bundle is provided.

Detailed check-by-check rules: [references/checks.md](references/checks.md).

## When to use

Use when the pages are already reachable and readable, and the question
is whether they are **marked up so a machine can extract specific facts**
— not just prose. The strongest signal from the n=100+22 crawl pass: of
sites that have JSON-LD at all, **67% still use only generic
Organization/WebSite types**. Typical triggers: missing JSON-LD
(presence is roughly a coin flip: 56% / 44% among reachable sites), or
markup that is only generic chrome when the page implies something more
specific.

Do not use this skill for crawl/access problems, cross-web corroboration,
name collisions, or on-page messaging. Those are other skills.

## Inputs

- **Required:** a domain or URL (free-form). Normalize to an origin
  (`https://example.com`).
- **Optional — pre-fetched site bundle (preferred):** the homepage HTML plus
  the same sampled internal URLs/HTML that `crawl-render-audit` already
  fetched. Accept this bundle when the caller (or a later orchestrator)
  already gathered it. Do not re-crawl those URLs.
- **If no bundle is provided:** fetch the homepage yourself. For internal
  pages, pull **real** URLs from a declared/default sitemap only — never
  guess `/about` or `/product`. If there is no sitemap, run D7/D8 on the
  homepage only (`coverage` = `homepage_only`).

Dependencies for the helper scripts: `pip install requests beautifulsoup4`.

## Procedure (numbered, deterministic steps)

Run the helpers instead of eyeballing raw HTML. From this skill folder:

```bash
python scripts/run_audit.py https://example.com
python scripts/run_audit.py https://example.com --bundle site_bundle.json
```

Follow this order even if running checks by hand. Full pass/fail rules live in
[references/checks.md](references/checks.md).

1. **Resolve pages.** Prefer the site bundle's homepage + `sampled_pages`.
   Otherwise fetch the origin homepage, then sample real sitemap URLs only.
2. **Extract JSON-LD** on every scorable HTML page with
   `scripts/jsonld.py` — every `<script type="application/ld+json">` block,
   including `@graph` / array payloads. Record block count and every `@type`.
3. **D7 — JSON-LD absent.** If the homepage has **zero** blocks, record D7
   (`high`). If the homepage has blocks but a **key** subpage (product /
   pricing / about / equivalent path) has zero, record D7 (`medium`). Total
   absence on the homepage is the stronger finding; do not also invent a
   second absence finding for the same pages.
4. **Classify `@type`.** `scripts/jsonld.py` labels each type `generic`
   (`Organization`, `WebSite`, `WebPage`, breadcrumbs, and similar chrome)
   or `domain-specific` (anything else, including `LocalBusiness`, `Product`,
   `Article`, `NewsMediaOrganization`).
5. **D8 — generic-only or inconsistent.** Only if at least one page has a
   JSON-LD block. Fire when (a) every type on every checked page is
   generic, or (b) a page that has markup uses types that do not match
   that URL's evident purpose (see checks.md). This is type *quality*, not
   absence — missing blocks on key pages stay on D7. **Medium.**
6. **Emit** findings plus a per-page type table so a caller can reuse the
   extraction.

## Output

Standalone JSON from `scripts/run_audit.py` (stdout):

```json
{
  "skill": "structured-data-audit",
  "site": "example.com",
  "audited_at": "2026-09-20T14:32:00Z",
  "findings": [
    {
      "id": "D7",
      "title": "No JSON-LD structured data on the homepage",
      "severity": "high",
      "evidence": "0/1 JSON-LD blocks on https://example.com/; 0 blocks on 2 sampled internal pages.",
      "suggested_action": {
        "summary": "Add schema.org JSON-LD whose @type matches what this page actually is, not only a generic WebSite wrapper.",
        "priority": "high"
      }
    }
  ],
  "page_extractions": [],
  "coverage": {
    "pages": "homepage_and_internal",
    "skipped_checks": []
  }
}
```

Each finding must include `id`, `title`, `severity`, `evidence`,
`suggested_action` (`summary` + `priority`). Use check ids `D7`–`D8` here; a
later orchestrator may rewrite them to `F-00N`.

Omit a check from `findings` when it did not fire. If no HTML page could be
parsed, list `D7` / `D8` under `coverage.skipped_checks`.

## Guardrails

- Recommend-only. Never submit forms, log in, or change the site.
- Respect robots.txt when this skill fetches its own pages.
- Same-origin only. No third-party schema validators or APIs.
- Small sample, timeouts, and inter-request delay. Stay well under a
  5-minute budget.
- Patterns and counts only — no hardcoded domains or "this brand does X".
