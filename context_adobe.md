# Project: Brand AI-Readiness Audit — Agent Skill Marketplace
**Adobe University Hackathon 2026 — Round 3**

## What this project is

We are building a package of AI agent "skills" (in the agentskills.io SKILL.md format) that, together, let a general AI agent audit any website automatically for:

1. **Off-site discoverability problems** — why AI assistants (ChatGPT, Perplexity, etc.) don't find, cite, or correctly represent this brand.
2. **On-site engagement problems** — why visitors who do land on the site don't stay or convert.

The package is called a **marketplace**: a folder containing one or more skills, a manifest file (`marketplace.json`) declaring exactly one of them as the **entrypoint**, and a README. The entrypoint skill is the one actually invoked — given a URL, it runs (or composes) the checks and emits a single structured JSON audit report.

This is Round 3 of a multi-round hackathon. Round 2 was a written reasoning exercise about *why* brands go invisible/stale/uncited in AI tools. Round 3 requires turning that reasoning into deterministic, reusable, generalizable agent skills.

## Critical constraint — read this first

**We will not be given example/test sites, and none of the sites we personally study are used in grading.** The marketplace will be run against **unseen websites** at evaluation time.

This means:
- Every check, threshold, and piece of logic must be a **general, repeatable pattern** (e.g. "flag pages where visible text is less than X% of raw HTML" ), never a fact about a specific brand or domain.
- Any field research we do (testing real sites) is purely to **discover patterns to encode** — it is not itself a deliverable, and nothing about specific sites we tested should leak into the skill logic, examples, or hardcoded lists.
- "Generalization" is an explicit rubric line. Overfitting to our own test sites actively hurts the score.

## Required output schema (entrypoint's final report)

This is a floor — extra fields are fine, but these are mandatory:

```json
{
  "site": "example.com",
  "audited_at": "2026-09-20T14:32:00Z",
  "summary": {
    "total_findings": 6,
    "critical": 1,
    "high": 2,
    "medium": 3
  },
  "findings": [
    {
      "id": "F-001",
      "title": "No JSON-LD structured data on product pages",
      "severity": "high",
      "evidence": "Crawled 12 product pages; 0/12 contain schema.org markup.",
      "suggested_action": {
        "summary": "Add Product/Offer JSON-LD to every product page.",
        "priority": "high"
      }
    }
  ]
}
```

Required per finding: `id`, `title`, `severity`, `evidence`, `suggested_action`.
Required summary fields: `site`, `audited_at`, counts by severity.

## Marketplace structure

```
brand-ai-readiness-audit/          <- marketplace root (this is what gets zipped)
  marketplace.json                 <- manifest: lists all skills + marks the entrypoint
  README.md                        <- what each skill does + how entrypoint composes them
  skills/
    audit-orchestrator/            <- ENTRYPOINT: receives request, composes others, emits report
      SKILL.md
      scripts/
      references/
    crawl-render-audit/            <- example skill: bot access, JS-render gaps, sitemap
      SKILL.md
    structured-data-audit/         <- example skill: JSON-LD / schema.org presence & validity
      SKILL.md
    freshness-corroboration/       <- example skill: staleness, cross-web fact agreement
      SKILL.md
    entity-clarity-audit/          <- example skill: name collisions / disambiguation
      SKILL.md
    engagement-audit/              <- example skill: on-page orientation, content clarity
      SKILL.md
```

A single-skill marketplace is a valid floor submission. Splitting into multiple focused skills (one concern each) is rewarded **only if the decomposition is genuine** — not padding.

## `marketplace.json` format

```json
{
  "name": "brand-ai-readiness-audit",
  "version": "1.0.0",
  "skills": [
    { "id": "audit-orchestrator", "path": "skills/audit-orchestrator", "entrypoint": true },
    { "id": "crawl-render-audit", "path": "skills/crawl-render-audit" },
    { "id": "structured-data-audit", "path": "skills/structured-data-audit" },
    { "id": "freshness-corroboration", "path": "skills/freshness-corroboration" },
    { "id": "entity-clarity-audit", "path": "skills/entity-clarity-audit" },
    { "id": "engagement-audit", "path": "skills/engagement-audit" }
  ]
}
```

Exactly one skill must have `"entrypoint": true`.

## `SKILL.md` format (per skill, agentskills.io spec)

```markdown
---
name: crawl-render-audit
description: >
  Detect crawlability and JS-render gaps that prevent AI assistants and search
  crawlers from reading a site's content: robots.txt blocks, missing/broken
  sitemap, and content that only appears after JavaScript execution (a
  "JS-shell" page whose visible text is a small fraction of what a browser
  would render). Use when auditing why a brand's pages might be technically
  invisible to non-browser-executing crawlers.
license: MIT
---

# Crawl & Render Audit

## When to use
...

## Inputs
...

## Procedure (numbered, deterministic steps)
...

## Output
(conforms to the shared finding schema — see audit-orchestrator)
```

Rules:
- Keep SKILL.md itself lean — push detailed checklists to `references/` and executable logic to `scripts/` (progressive disclosure).
- Declare any `allowed-tools` the skill needs.
- Every skill folder must independently validate against the agentskills.io spec.

## Hard guardrails (non-negotiable, must show up in every skill's logic)

- **Recommend-only.** No skill ever modifies a live site. Read-only, sandboxed.
- No destructive actions, no authenticated-area access, no rate-abusive crawling.
- **Respect robots.txt always.**
- No external services required to resolve the marketplace — self-contained.
- Zip size ≤ 50MB, no pretrained model weights.
- Full audit runtime < 5 minutes on a typical website.
- Design for *patterns*, not memorized examples.

## Round 2 background theory (why these problems exist — not a checklist)

- **A. Crawl basics** — a page must be (1) accessible to the crawler, (2) readable, (3) parseable for the specific fact — in that order. Fail any step and the page is functionally invisible to the machine even if a human sees it fine.
- **B. How assistants use sources** — many AI assistants search/fetch live rather than answer from memory. What gets cited is what's easy to reach, read, and quote a clear fact from.
- **C. How machines read pages** — JS-assembled or non-textual content can be invisible to simple parsers even though a human sees it. Explicit plain-text facts get extracted correctly far more often than implied/buried ones.
- **D. Agreement across the web** — facts repeated consistently across independent sources are trusted more than a fact living in one place. Name collisions cause mistaken identity unless something disambiguates.
- **E. Personalization** — assistants weight answers by conversation context, so two users asking the same thing can get different results; not something a site can fully control but relevant framing.
- **F. Email/summary drop-off** — same root cause as C, applied to inbox summarizers: unreadable or filler-buried substance disappears from AI summaries.

Our checks should trace back to these mechanisms, not to specific sites we happened to test.

## Working style / role for Cursor

- We already have a rough roadmap (10 phases) for building this. Cursor's job is to help write the actual `SKILL.md` files, helper scripts, `marketplace.json`, and README — not to re-derive strategy from scratch.
- The person driving this will paste in phase-specific prompts one at a time, in order. Don't jump ahead to later phases unless asked.
- Keep every skill's logic domain-general (works on an arbitrary unseen site), evidence-based (every finding must cite what was actually observed, e.g. a count or a missing element), and testable.
