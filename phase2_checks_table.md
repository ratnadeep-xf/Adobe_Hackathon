# Phase 2 — Checks Table
**Adobe University Hackathon 2026 — Round 3, Agent Skill Marketplace**

Synthesized from three sources: our automated technical scan (`phase1_results.csv`,
22 sites), our AI ground-truth pass (`ground_truth.csv`, 22 sites, real search +
LLM), and a collaborator's independent manual audit (`phase1_findings.md`, a
different 22 sites). Where a pattern showed up independently in more than one
source, it's a stronger signal and noted as such. Every check below is written
as a general procedure — no site names, thresholds are principled starting
points to tune in Phase 8's dry run, not fitted to any site we studied.

Each check maps to a Round-2 appendix mechanism: **A** = crawl access, **B** =
what gets cited, **C** = machine-readability, **D** = corroboration/identity.

---

## Discoverability checks

| ID | Skill | Check | What it detects | How to test | Evidence format | Severity rule |
|---|---|---|---|---|---|---|
| D1 | crawl-render-audit | Full-site crawler block | robots.txt disallows `*` at the root — every crawler, AI or otherwise, is shut out | Fetch `/robots.txt`; parse for a `User-agent: *` block with `Disallow: /` | Quote the exact disallow rule and its scope | **Critical** — nothing downstream can be found at all |
| D2 | crawl-render-audit | Named AI-crawler block (training vs. live-agent) | robots.txt blocks specific AI user-agents (GPTBot, ClaudeBot, PerplexityBot, Google-Extended, CCBot, etc.) — but training-crawler and live-browsing-agent access are separate permissions and must be checked separately (e.g. a site can allow GPTBot while blocking ChatGPT-User) | Parse robots.txt per named AI user-agent; classify each as training-crawler or live-agent; report which category(ies) are blocked | List of blocked agents, split by category | **High** if live-agent access is blocked (breaks real-time citation); **Medium** if only training-crawler access is blocked |
| D3 | crawl-render-audit | Infrastructure-level hard block (WAF/403) | Homepage returns 403 (or connection is reset/blocked) before robots.txt is even reachable — a categorically harder wall than a robots disallow, with zero diagnostic signal available | Fetch homepage; if status is 403/blocked prior to any robots.txt check, flag separately from D1/D2 | HTTP status + response headers if any | **Critical** — indistinguishable from the site not existing, to any automated visitor |
| D4 | crawl-render-audit | Sitemap missing or unreachable | No sitemap declared in robots.txt and none at the default `/sitemap.xml` path | Check robots.txt `Sitemap:` directive, then default path; confirm the response actually parses as a sitemap (not a soft-404) | Which locations were checked and result | **Medium** — narrows discovery surface but doesn't block it outright |
| D5 | crawl-render-audit | JS-shell content gap (sampled internal pages) | Content that only renders after JavaScript executes — invisible to a simple text fetch. Confirmed to occur on internal pages (e.g. an `/about` or `/pricing` page) even when the homepage is fully server-rendered, so homepage-only scanning misses this category | Pull real URLs from the sitemap (never guess paths — a guessed path can silently 200 to the homepage instead of a real 404); sample several internal pages; compute visible-text length and text-to-raw-HTML ratio for each | Per-page word count + ratio; flag pages under a low absolute threshold regardless of ratio (a low ratio on a very long page is normal, not a shell) | **High** if key pages (product/pricing/about) are affected; **Low** if only marginal pages are |
| D6 | crawl-render-audit | Auth-gated content wall | Internal pages return 401/hard login-wall for an unauthenticated visitor — distinct from both a crawl block and a JS-shell; the content isn't hidden, it's inaccessible | While sampling sitemap URLs for D5, record any 401/403 that isn't the D3 homepage-level block | URL + status code | **Medium** — depends on whether the gated content is core to what a visitor would search for |
| D7 | structured-data-audit | JSON-LD absent | No `application/ld+json` blocks found — a page can be extremely well-written and still give a machine nothing structured to extract | Parse homepage (and sampled internal pages) for `<script type="application/ld+json">` | Count of blocks found (0) across pages checked | **High** on homepage; **Medium** if present on homepage but absent on key subpages |
| D8 | structured-data-audit | Generic-only or inconsistent structured data | JSON-LD present but only uses generic types (`Organization`, `WebSite`) with no domain-specific type (`LocalBusiness`, `Product`, `Article`, `NewsMediaOrganization`, etc.), or present on the homepage but missing on the pages where it matters most | Extract `@type` values across all JSON-LD blocks found; compare against a category-appropriate expected type for the page's evident purpose | List of types found vs. what a page of this evident kind would typically warrant | **Medium** — reduces disambiguation value without being a total absence |
| D9 | freshness-corroboration | Weak organic footprint | A real web search for the brand's own name returns very few distinct results — even a large, real company can have a thin public footprint under certain queries | Run a keyless web search for the exact brand/entity name; count distinct domains returned | Result count + domain list | **High** if under ~3 distinct domains; **Medium** under ~5 |
| D10 | freshness-corroboration | Own domain absent from its own name search | The brand's own site doesn't appear anywhere in a search for its own name, even when other results exist | Compare the audited domain against the domain list from D9 | Present/absent + full domain list for transparency | **Critical** — a stronger and more specific version of D9; strongly correlated (in our data) with an AI assistant describing the wrong entity entirely |
| D11 | freshness-corroboration | Thin or low-diversity corroboration sources | The handful of sources that do exist are all the same kind of low-effort aggregator (e.g. two generic reference sites) rather than a mix of independent press, reviews, social, and reference sources | Classify each result domain into a rough bucket (reference/encyclopedia, press, review/directory, social, official); flag when only one bucket is represented | Bucket breakdown | **Medium** — a corroboration diversity problem, not an absence problem |
| D12 | freshness-corroboration | Stale or contradicted facts | A verifiable fact stated on the official site (founding year, HQ location, leadership) is contradicted or unconfirmed across independent sources | Extract 1-2 checkable facts from the official site; compare against what independent sources state | The specific fact and the conflicting values found, with sources | **High** if directly contradicted; **Low** if merely unconfirmed elsewhere |
| D13 | freshness-corroboration | Copyright/freshness signal | Footer copyright year or last-modified header suggests staleness | Regex for `©`/`copyright` + year in footer text; check `Last-Modified` header | Year found (or absent) | **Low only** — confirmed weak/noisy signal in our data (several clearly-active, current sites had no detectable copyright year at all); never let this alone justify a high-severity finding |
| D14 | entity-clarity-audit | Name collision / mistaken identity | An AI-generated answer for the brand's name describes a materially different entity than what the audited domain actually is | Compare the audited site's own stated purpose (title + meta + H1 + opening content) against an independent web-search-grounded summary of the same name; flag material mismatch in subject matter | Both descriptions side by side | **Critical** — the brand is actively being replaced by a different entity in AI answers, not just under-described |
| D15 | entity-clarity-audit | Domain-vs-business divergence | The domain doesn't resolve, or resolves to unrelated/parked content, while a distinctly-named business still has an active presence elsewhere (directories, reviews, socials) | Attempt to reach the domain; if unreachable/unrelated, run the D9-style search anyway to check whether the named business persists independent of its own domain | Domain status + evidence of independent business presence (or its absence) | **Critical** if the business persists without a working domain (total loss of first-party control over the narrative); **N/A** finding-wise if the business itself appears defunct |

## Engagement checks

| ID | Skill | Check | What it detects | How to test | Evidence format | Severity rule |
|---|---|---|---|---|---|---|
| E1 | engagement-audit | Weak on-page orientation | A visitor (human or machine) can't quickly tell what the entity concretely does from the page's own visible text | Combine title + meta description + H1(s) + first visible paragraph; check whether a concrete offering/action is plainly stated, not just a slogan | The combined text checked, and what concrete offering (if any) it names | **High** if nothing concrete is stated anywhere in that combined text |
| E2 | engagement-audit | Generic or non-descriptive meta description | Present and technically long enough, but doesn't actually convey what's offered — a length-only check is confirmed too lenient to catch this | Check meta description length AND whether it contains a concrete noun/offering distinct from marketing filler | The meta description text itself | **Medium** — hurts snippet/summary quality even when the page itself is fine |
| E3 | engagement-audit | Missing or duplicate H1 structure | Zero H1s (no clear primary topic marker) or multiple competing H1s on one page | Count `<h1>` elements per page checked | H1 count and text of each found | **Low** individually; **Medium** if it co-occurs with E1 |

---

## Notes carried into Phase 3 (skill decomposition)

- **D1–D6** (crawl/access) and **D7–D8** (structured data) both depend on the same
  sitemap-driven page-sampling step — worth sharing that sampling logic rather
  than duplicating it per skill.
- **D9–D13** (freshness/corroboration) all depend on one search-and-classify
  step per brand — natural to keep as one skill.
- **D14–D15** (entity clarity) depend on both a site-derived description *and*
  an independent search-derived one — this skill needs to call the same search
  step as D9–D13, so plan the interface between skills accordingly (the
  entrypoint may need to run the search once and hand results to both).
- D13's rule (never let it alone justify high severity) is a direct,
  evidence-based override of what a naive implementation would do — worth
  calling out explicitly in that skill's SKILL.md so it isn't silently dropped
  during Phase 6.
