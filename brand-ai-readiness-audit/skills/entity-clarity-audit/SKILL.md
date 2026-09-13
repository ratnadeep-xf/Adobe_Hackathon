---
name: entity-clarity-audit
description: >
  Check whether a brand's identity is distinguishable from other things that
  share its name: material mismatch between the site's self-description and
  a search-grounded summary of the same name, or a dead/parked domain while
  the named business still appears elsewhere. Use when auditing mistaken
  identity in AI answers.
license: MIT
compatibility: >
  Requires Python 3.9+ and beautifulsoup4. Reuses the freshness search
  bundle and the homepage / self-description extract — does not re-search.
allowed-tools: WebFetch Bash(python *)
---

# Entity Clarity Audit

Read-only. Standalone if needed, but designed to reuse the search bundle
and homepage already gathered for freshness-corroboration and engagement.

Detailed rules: [references/checks.md](references/checks.md).

## When to use

Use when the question is **identity**: does a name search describe *this*
entity, and does the domain still belong to that business?

Do not use for crawl blocks, JSON-LD, footprint size, or on-page slogans
except as the self-description input.

## Inputs

- **Required:** brand/entity name and audited domain.
- **Optional — brand-name search bundle (preferred):** the same bundle
  freshness-corroboration produced. **Do not re-run the search.**
- **Optional — site self-description (preferred):** title + meta + H1s +
  opening text — the same extraction `engagement-audit` uses. If missing,
  extract it from the site-bundle homepage.
- **If no search bundle:** this skill may call freshness-corroboration's
  `web_search.py` once. Prefer being passed the bundle.

## Why there is no comparison “oracle” script

D14 is a **subject-matter mismatch** judgment: two short descriptions,
side by side. An LLM reading those strings is the right tool when a
human/agent is in the loop. The marketplace must also run without a
paid model, so `scripts/run_audit.py` applies a conservative lexical
overlap check (content tokens, not slogans) and always returns both
descriptions so an agent can override a miss. The script never invents
an entity from memory — it only compares the site text to the search
bundle that was passed in.

## Procedure (numbered, deterministic steps)

```bash
python scripts/run_audit.py https://example.com --search-bundle search.json --bundle site_bundle.json
```

1. Take the search bundle as-is. Build a search-grounded summary by
   concatenating result titles + snippets (no extra API).
2. Take the site self-description (or extract it from homepage HTML).
3. **D14.** Compare subject matter. Fire `critical` on a material
   mismatch (script: near-zero overlap of content tokens while both
   sides have substance). Quote both descriptions.
4. **D15.** Fire `critical` only when the homepage fetch itself failed
   (hard block / no HTTP response) **and** the search bundle still shows
   independent presence. A short or error-page body is not enough.
   **No finding** if the business also looks defunct (no independent
   results). Skip D14 when fetch-quality is not usable.
5. Emit findings plus both descriptions.

## Output

Findings use ids `D14`–`D15`. Extra fields: `site_description`,
`search_summary`. Orchestrator may rewrite ids to `F-00N`.

## Guardrails

- Do not re-search when a bundle is provided.
- Recommend-only. No writes, no login.
- Conservative D14: prefer a miss over a false critical.
- D9–D15 can vary run-to-run: they depend on live keyless search hits, not only fetched page content.
