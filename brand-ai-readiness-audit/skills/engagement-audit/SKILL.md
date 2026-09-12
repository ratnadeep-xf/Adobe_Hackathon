---
name: engagement-audit
description: >
  Check whether a visitor who successfully lands on the homepage can tell
  what the entity concretely does: weak on-page orientation, a meta
  description that is long enough but names no offering, and missing or
  duplicate H1s. Use when auditing on-site clarity, not crawl access or
  off-site corroboration.
license: MIT
compatibility: >
  Requires Python 3.9+, requests, and beautifulsoup4. Reuses a pre-fetched
  homepage when provided.
allowed-tools: WebFetch Bash(python *)
---

# Engagement Audit

Read-only. Works standalone: fetches the homepage if no site bundle is given.

Detailed rules: [references/checks.md](references/checks.md).

## When to use

Use when the visitor **did land** and the question is whether the page is
clear and orienting. Typical triggers: slogan-only homepages, generic meta
descriptions, missing or competing H1s.

Do not use for robots/JS-shell, JSON-LD, or off-site search.

## Inputs

- **Required:** a domain or URL.
- **Optional — pre-fetched homepage (preferred):** `site_bundle.homepage`
  from `crawl-render-audit`. Do not re-fetch when present.
- **If no bundle:** fetch `{origin}/` only.

Dependencies: `pip install requests beautifulsoup4`.

## Procedure (numbered, deterministic steps)

```bash
python scripts/run_audit.py https://example.com
python scripts/run_audit.py https://example.com --bundle site_bundle.json
```

1. Extract title, meta description, H1 text(s), and the first visible
   paragraph with `scripts/page_signals.py`.
2. **E1 — orientation.** Combine those four strings. Fire `high` if no
   concrete offering/action is named (slogan/filler only).
3. **E2 — meta quality.** Not a length-only check. Fire `medium` when a
   meta description is present and long enough (≥ 40 characters) but still
   names no concrete offering distinct from marketing filler.
4. **E3 — H1 structure.** Fire if H1 count is 0 or ≥ 2. `low` alone;
   `medium` if E1 also fired.
5. Emit findings plus the extracted self-description (entity-clarity-audit
   uses the same fields).

## Output

Findings use ids `E1`–`E3`. `self_description` holds title, meta, h1s,
first paragraph, and combined text. Orchestrator may rewrite ids to `F-00N`.

## Guardrails

- Recommend-only. Homepage only unless a bundle already includes it.
- Same-origin fetch when this skill retrieves the page itself.
- E2 must stay qualitative (offering vs filler), never length-only.
