# Phase 3 — Skill Decomposition
**Adobe University Hackathon 2026 — Round 3, Agent Skill Marketplace**

Five focused skills + one entrypoint (6 total), built directly from the
Phase 2 checks table. The key design decision below is how the shared,
expensive steps (fetching pages, running a web search) are gathered once
and reused, rather than each skill independently re-fetching the same data —
this is what makes the decomposition "genuine separation of concerns" rather
than padding, per the rubric.

---

## The two shared raw-data steps

Two pieces of raw data are needed by more than one skill. Rather than each
skill re-fetching them independently, **the orchestrator gathers both once**
and passes the results to whichever skills need them:

1. **Site fetch bundle** — robots.txt, homepage, sitemap, and a small sample
   of real internal URLs pulled from the sitemap (never guessed paths — see
   D5's note in Phase 2). Needed by: crawl-render-audit, structured-data-audit,
   engagement-audit.
2. **Brand-name search bundle** — a keyless web search for the brand/entity's
   own name, returning distinct result domains. Needed by: freshness-corroboration,
   entity-clarity-audit.

Each downstream skill's SKILL.md documents this in its **Inputs** section:
"Accepts a pre-fetched site bundle (preferred) or fetches it directly if none
is provided" — so every skill still independently satisfies the agentskills.io
spec (self-contained, runnable on its own) while the orchestrator's smarter
composition avoids duplicate network calls when it runs the full marketplace.

---

## The five skills

### 1. `crawl-render-audit`
**Owns:** D1, D2, D3, D4, D5, D6
**Concern:** can an automated visitor even reach and read the content at all?
**Inputs:** domain/URL; optionally a pre-fetched site bundle
**Procedure shape:** fetch homepage → classify any hard block (D3) before
even checking robots.txt → parse robots.txt for general (D1) and named
AI-crawler (D2, split training/live-agent) rules → check sitemap presence
(D4) → sample real internal URLs from the sitemap and check each for
JS-shell content (D5) and auth walls (D6)
**Output:** findings for D1–D6, plus the sampled internal-URL list and raw
fetched content (handed back to the orchestrator for reuse by the two
skills below)

### 2. `structured-data-audit`
**Owns:** D7, D8
**Concern:** even where content is reachable and readable, is it marked up
so a machine can extract specific facts (not just prose)?
**Inputs:** homepage + the same sampled internal URLs from crawl-render-audit
(reuses that fetch rather than re-crawling)
**Procedure shape:** extract all JSON-LD blocks per page checked → note
absence (D7) → classify `@type` values as generic vs. domain-specific and
check consistency across pages (D8)
**Output:** findings for D7–D8

### 3. `freshness-corroboration`
**Owns:** D9, D10, D11, D12, D13
**Concern:** is what's said about this brand (on its own site and
elsewhere) current, agreed-upon, and repeated across independent sources?
**Inputs:** brand/entity name; domain (to check D10 against); optionally
the pre-fetched homepage (for D12's official-site facts and D13's copyright
check)
**Procedure shape:** run the brand-name search once (D9's raw material) →
count distinct domains and classify by source type for D9/D11 → check
whether the audited domain itself appears (D10) → extract 1-2 checkable
facts from the official site and compare against independent sources (D12)
→ check footer/header freshness signals (D13), explicitly capped at low
severity per the Phase 2 finding
**Output:** findings for D9–D13

### 4. `entity-clarity-audit`
**Owns:** D14, D15
**Concern:** is this brand's identity actually distinguishable from other
things that share its name, both in AI-generated answers and at the domain
level?
**Inputs:** brand/entity name; domain; the same brand-name search bundle as
freshness-corroboration (reused, not re-run); the site's own self-description
(title/meta/H1/opening text — same extraction engagement-audit uses)
**Procedure shape:** build an independent, search-grounded summary of the
brand's name → compare its subject matter against the site's own
self-description → flag material mismatch (D14) → if the domain doesn't
resolve or resolves to unrelated content, check whether the named business
still has independent presence in the search results anyway (D15)
**Output:** findings for D14–D15

### 5. `engagement-audit`
**Owns:** E1, E2, E3
**Concern:** for a visitor who does successfully land on the page, is it
actually clear and orienting?
**Inputs:** the pre-fetched homepage (reuses crawl-render-audit's fetch)
**Procedure shape:** extract title + meta description + H1(s) + first
visible paragraph → check for a concrete stated offering (E1) → check meta
description for genuine descriptiveness vs. generic filler (E2) → count and
flag H1 structure issues (E3)
**Output:** findings for E1–E3

---

## `audit-orchestrator` (the entrypoint)

**Responsibilities:**
1. Accept the audit request (a URL/domain — free-form, not a fixed CLI arg).
2. Run the two shared steps once: the site fetch bundle and the brand-name
   search bundle.
3. Invoke each of the five skills' logic, handing each the shared data it
   needs so nothing is re-fetched unnecessarily.
4. Merge all returned findings into one list, assign each a stable `F-00N`
   id, and compute the `summary` severity counts.
5. Emit the final report in the required schema (see `context.md` for the
   exact shape) — `site`, `audited_at`, `summary`, `findings[]`, each finding
   with `id`, `title`, `severity`, `evidence`, `suggested_action`.

**Not the orchestrator's job:** re-deriving any check logic itself — it
composes and reports, it doesn't duplicate what the five skills already do.

---

## Folder structure this maps to

```
brand-ai-readiness-audit/
  marketplace.json
  README.md
  skills/
    audit-orchestrator/        <- entrypoint
      SKILL.md
      scripts/
      references/
    crawl-render-audit/
      SKILL.md
      scripts/                 <- robots.txt parser, sitemap-based URL sampler, JS-shell heuristic
      references/
    structured-data-audit/
      SKILL.md
      scripts/                 <- JSON-LD extractor/classifier
    freshness-corroboration/
      SKILL.md
      scripts/                 <- keyless search wrapper, source-type classifier
    entity-clarity-audit/
      SKILL.md
    engagement-audit/
      SKILL.md
```

---

## Why this decomposition (for the rubric's "marketplace composition" criterion)

Each skill owns a genuinely distinct *kind* of question (access, machine-
readability, corroboration, identity, on-page clarity) rather than being
split by, say, industry vertical or arbitrarily divided check-by-check. The
two cross-skill dependencies (shared site-fetch, shared brand search) are
explicit and intentional, not accidental duplication — and each skill still
stands alone and satisfies the agentskills.io spec independently if invoked
on its own.
