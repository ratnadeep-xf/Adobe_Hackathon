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
compatibility: >
  Requires Python 3.9+, requests, and beautifulsoup4. Outbound HTTP is limited
  to the audited origin (robots.txt, sitemap, sampled pages).
allowed-tools: WebFetch Bash(python *)
---

# Crawl & Render Audit

Read-only. Do not modify the live site. This skill works standalone: given a
URL, it gathers its own site bundle if none is provided.

Detailed check-by-check rules: [references/checks.md](references/checks.md).

## When to use

Use when the question is whether an automated visitor can **reach and read**
the pages at all — before asking whether facts are marked up, corroborated, or
orienting. Typical triggers: robots.txt / crawler blocks, WAF/403 walls,
missing sitemaps, JS-only ("shell") pages, or auth-gated public URLs.

Do not use this skill for structured-data quality, cross-web corroboration,
name collisions, or on-page messaging. Those are other skills.

## Inputs

- **Required:** a domain or URL (free-form). Normalize to an origin
  (`https://example.com`). If a path is included, still audit the site origin;
  treat `/` as the homepage.
- **Optional — pre-fetched site bundle (preferred):** robots.txt body,
  homepage fetch, sitemap body/bodies, and any already-sampled internal pages.
  Accept this bundle when the caller (or a later orchestrator) already gathered
  it. Shape is documented under **Output**.
- **If no bundle is provided:** fetch the target origin yourself (homepage,
  `/robots.txt`, declared/default sitemap, then sampled sitemap URLs only).

Never invent internal paths. If the sitemap yields no real URLs, do not guess
`/about`, `/pricing`, or any other path — a guessed path can silently 200 to
the homepage instead of a real 404.

Dependencies for the helper scripts: `pip install requests beautifulsoup4`.

## Procedure (numbered, deterministic steps)

Run the helpers instead of eyeballing raw robots.txt / HTML. From this skill
folder:

```bash
python scripts/run_audit.py https://example.com
python scripts/run_audit.py https://example.com --bundle site_bundle.json
```

Follow this order even if running checks by hand. Full pass/fail rules live in
[references/checks.md](references/checks.md).

1. **Normalize** the input to an origin. Do not start from robots.txt.
2. **D3 first — homepage hard block.** Fetch the homepage. Classify the
   response with `scripts/fetch_quality.py`. Split D3 into sub-categories
   (`waf_403`, `rate_limited_429`, `auth_401_homepage`, `empty_202`,
   `method_not_allowed_405`, `no_response_timeout`) with distinct titles
   and actions. Retry a 429 once (honor `Retry-After`) before calling it
   a block. If D3 fires, do not crawl internal URLs. A 404 stub or
   JS-challenge is **not** D3 — record `FQ` (medium). Empty 202 / empty
   successful bodies are `interstitial` (`empty_202`). A single
   subsequent `/robots.txt` fetch is allowed only as diagnostics.
3. **Fetch `/robots.txt`.** Parse with `scripts/robots_parser.py` (not by
   informal reading).
4. **D1 — full-site `*` block.** If the `User-agent: *` group contains
   `Disallow: /`, record D1 (critical). Quote the exact rule. After D1, do not
   fetch further paths — robots.txt forbids it. Homepage already fetched in
   step 2 may still be evaluated for D5.
5. **D2 — named AI-crawler blocks.** Using the parser's training-crawler vs
   live-agent classification, record which named agents are root-disallowed.
   Severity: **high** if any live-agent is blocked; **medium** if only
   training-crawlers are. Skip D2 when D1 already covers a full `*` root
   disallow (the named-agent table still belongs in the bundle).
6. **D4 — sitemap.** Use `Sitemap:` URLs declared in robots.txt, then the
   default `/sitemap.xml` only. Confirm the body actually parses as a sitemap
   (`urlset` or `sitemapindex`), not a soft-404 HTML page or JS-challenge
   that returned HTTP 200. Never try other guessed sitemap paths.
   Missing/invalid → D4 (medium). Suggested action must say the sitemap
   could not be retrieved as XML from this fetch — not that the site
   never published one.
7. **Sample real internal URLs** with `scripts/sitemap_sampler.py`. Only URLs
   that appear in a fetched sitemap (or child sitemaps named *inside* a
   sitemap index). Prefer the homepage's locale when the index mixes
   locale trees. Cap the sample; delay between requests; skip paths
   disallowed for `User-agent: *`.
8. **D5 — JS-shell.** For the homepage and each sampled page, run
   `scripts/js_shell.py`. Skip samples flagged
   `identical_to_homepage_suspected_soft_404`. Flag on a **low absolute
   visible-word count**, not on a low text-to-HTML ratio alone. A long
   page with a low ratio is normal. Severity: **high** if a key path
   (product / pricing / about / equivalent) is affected; **low** if only
   marginal paths are.
9. **D6 — auth walls.** While sampling, record 401/403 (or a redirect chain
   that includes them) on internal URLs. These are not D3 (homepage-level) and
   not D5 (content hidden behind JS). Medium.
10. **Emit** findings plus the site bundle (sampled URL list and raw fetched
    content) so a caller can reuse the fetches.

## Output

Standalone JSON from `scripts/run_audit.py` (stdout):

```json
{
  "skill": "crawl-render-audit",
  "site": "example.com",
  "audited_at": "2026-09-20T14:32:00Z",
  "findings": [
    {
      "id": "D1",
      "title": "Full-site crawler block in robots.txt",
      "severity": "critical",
      "evidence": "User-agent: * has Disallow: / in https://example.com/robots.txt.",
      "suggested_action": {
        "summary": "Remove or narrow the User-agent: * Disallow: / rule so public pages can be crawled.",
        "priority": "critical"
      }
    }
  ],
  "site_bundle": {
    "origin": "https://example.com",
    "host": "example.com",
    "homepage": { "url": "", "final_url": "", "status": 200, "headers": {}, "html": "", "error": null },
    "robots_txt": { "url": "", "status": 200, "text": "", "error": null },
    "sitemaps": [],
    "sampled_internal_urls": [],
    "sampled_pages": []
  },
  "coverage": {
    "d5": "homepage_and_internal",
    "skipped_checks": []
  }
}
```

Each finding must include `id`, `title`, `severity`, `evidence`,
`suggested_action` (`summary` + `priority`). Use check ids `D1`–`D6` here; a
later orchestrator may rewrite them to `F-00N`.

`site_bundle` is the reusable fetch: homepage HTML, robots.txt, sitemap
bodies, `sampled_internal_urls`, and raw HTML for each sampled page. Downstream
skills should reuse this rather than re-crawling.

Omit a check from `findings` when it did not fire. If a check could not run
(e.g. no sitemap, so no internal sample), list it under
`coverage.skipped_checks` instead of inventing a finding.

## Guardrails

- Recommend-only. Never submit forms, log in, or change the site.
- Respect robots.txt for every request after the D3 homepage probe.
- Same-origin only. No third-party APIs, search engines, or archives.
- Small sample, timeouts, and inter-request delay. Stay well under a
  5-minute budget.
- Patterns and counts only — no hardcoded domains or "this brand does X".
