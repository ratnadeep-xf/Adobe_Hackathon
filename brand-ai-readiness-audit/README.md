# Brand AI-Readiness Audit

A marketplace of agent skills that audits an unseen website for two things: whether AI assistants can **find and correctly represent** the brand, and whether a visitor who lands can **tell what is offered**.

It is read-only and recommend-only. Nothing is written to the live site. One skill is the entrypoint; five focused skills do the checks.

**Run a full audit**

```bash
python skills/audit-orchestrator/scripts/run_audit.py https://example.com
python skills/audit-orchestrator/scripts/run_audit.py example.com --brand "Example"
```

Requires Python 3.9+, `requests`, `beautifulsoup4`, and `ddgs`. The report is JSON: `site`, `audited_at`, severity counts, and a `findings` list (`id`, `title`, `severity`, `evidence`, `suggested_action`). Extra coverage fields record what was sampled and which checks were skipped.

---

## The five focused skills

| Skill | What it answers |
|---|---|
| **crawl-render-audit** | Can an automated visitor *reach and read* the pages? robots.txt blocks (all crawlers vs named AI agents), WAF/403, missing or nested-empty sitemaps, JS-shell pages with almost no visible text, and login walls on sampled URLs. |
| **structured-data-audit** | Is there JSON-LD a machine can extract? Missing `ld+json` on the homepage or key subpages, or markup that is only generic (`Organization` / `WebSite`) when the page implies something more specific. |
| **freshness-corroboration** | Does the name show up consistently elsewhere? A keyless brand-name search: thin footprint, official domain missing from its own name results, one-note source types, and on-site facts that conflict with (or never appear in) those snippets. |
| **entity-clarity-audit** | Is this the right entity? The site’s own description vs the search-grounded picture of the same name (mistaken identity), or a dead/unreachable domain while the name still appears on independent sites. |
| **engagement-audit** | If someone *did* land, can they tell what is offered? Slogan-only homepages, meta descriptions that don’t name an offering, and missing or duplicate H1s. |

Each skill can run alone. In a full audit they reuse shared fetches instead of crawling again.

---

## How the entrypoint composes them

**audit-orchestrator** is the only `entrypoint` in `marketplace.json`. It does not re-implement the checks.

1. Parse a free-form request for a URL/domain (optional `--brand`).
2. Fetch the site **once** (homepage, robots.txt, declared sitemap, a small sample of real sitemap URLs). Classify the homepage as usable content vs a 404 stub / bot-check before anyone reasons about identity or copy.
3. Run **one** keyless brand-name search.
4. Call the five skills in order, passing those two bundles.
5. Merge findings as `F-001`, `F-002`, …, add a `coverage` trace (what was sampled, fetch quality, skip reasons), validate the schema, and print the report.

Typical runtime is well under five minutes. Fetches stay on the audited origin except for that one search. Patterns only — no hardcoded evaluation sites.
