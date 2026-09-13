# Brand AI-Readiness Audit

A marketplace of agent skills that audits an unseen website for two things: whether AI assistants can **find and correctly represent** the brand, and whether a visitor who lands can **tell what is offered**.

It is read-only and recommend-only. Nothing is written to the live site. One skill is the entrypoint; five focused skills do the checks.

**Run a full audit**

```bash
python skills/audit-orchestrator/scripts/run_audit.py https://example.com
python skills/audit-orchestrator/scripts/run_audit.py example.com --brand "Example"
```

Requires Python 3.9+, `requests`, `beautifulsoup4`, and `ddgs`. The report is JSON: `site`, `audited_at`, severity counts, and a `findings` list (`id`, `title`, `severity`, `evidence`, `suggested_action`). Extra coverage fields record what was sampled, the fetch-quality classification, and which checks were skipped and why.

---

## The five focused skills

| Skill | What it answers |
|---|---|
| **crawl-render-audit** | Can an automated visitor *reach and read* the pages? robots.txt blocks (all crawlers vs named AI agents, split into training-crawler vs live-agent access), infrastructure-level blocks classified by cause (WAF/403, rate-limited/429 after a failed retry, homepage-level auth/401, empty-202 bot-challenge, 405, timeout), missing or nested-empty sitemaps, JS-shell pages with almost no visible text, and login walls on sampled URLs. Internal pages that just echo the homepage are detected and excluded rather than scored as their own finding. |
| **structured-data-audit** | Is there JSON-LD a machine can extract? Missing `ld+json` on the homepage or key subpages, or markup that is only generic (`Organization` / `WebSite`) when the page implies something more specific. The homepage check runs on its own merits even when no internal pages could be sampled from the sitemap. |
| **freshness-corroboration** | Does the name show up consistently elsewhere? A keyless brand-name search: thin footprint, official domain missing from its own name results (matched by registrable domain, not exact string, so subdomains still count), one-note source types, on-site facts that conflict with (or never appear in) those snippets, and a copyright-year check that's deliberately capped at low severity — real-world testing showed it's too unreliable to weight any higher. |
| **entity-clarity-audit** | Is this the right entity? The site’s own description vs the search-grounded picture of the same name (mistaken identity) — only compared once the homepage fetch is confirmed to be real content, not a bot-check or error page — or a dead/unreachable domain while the name still appears on independent sites. |
| **engagement-audit** | If someone *did* land, can they tell what is offered? Slogan-only homepages, meta descriptions that don’t name an offering, and missing or duplicate H1s. |

Each skill can run alone. In a full audit they reuse shared fetches instead of crawling again.

---

## How the entrypoint composes them

**audit-orchestrator** is the only `entrypoint` in `marketplace.json`. It does not re-implement the checks.

1. Parse a free-form request for a URL/domain (optional `--brand`).
2. Fetch the site **once** (homepage, robots.txt, declared sitemap, a small sample of real sitemap URLs). Classify the homepage as usable content vs a 404 stub / bot-check / empty-response challenge *before* any other skill reasons about its identity or copy.
3. Run **one** keyless brand-name search.
4. Call the five skills in order, passing those two bundles.
5. Merge findings as `F-001`, `F-002`, …, add a `coverage` trace (what was sampled, fetch-quality classification, and a reason for every skipped check — not just its id), validate the schema, and print the report.

Typical runtime is well under five minutes. Fetches stay on the audited origin except for that one search. Patterns only — no hardcoded evaluation sites.

---

## Evidence sourcing

D1–D8 (crawl, structured data, and the on-site half of freshness that
does not need search) are backed by the original n=22 Phase 2 sample
**plus** a later 100-site validation pass. That 100-site pass had **no
web-search step**, so it says nothing about D9–D15. Those checks remain
backed by the n=22 sample only. That split is expected, not an oversight.

D9–D15 can also vary from run to run on the same site: they depend on
live keyless search results, not only fetched page content.