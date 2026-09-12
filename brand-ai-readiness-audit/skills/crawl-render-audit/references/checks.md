# D1–D6 check logic

Deterministic rules for `crawl-render-audit`. Thresholds are principled
starting points (to be tuned later), not fitted to any particular site.
Every finding must quote something actually observed: a rule, a status
code, a count, or a URL that appeared in a sitemap.

Run the homepage fetch **before** robots.txt (D3). After that, obey
robots.txt. Never guess internal paths.

---

## Shared setup

1. Normalize input to an origin: if the value has no scheme, try `https://`
   first; if the TLS/connection fails (not a 403), try `http://`. Homepage
   URL is `{origin}/`.
2. Identify fetches as read-only. Do not impersonate Googlebot or a named
   AI crawler.
3. Prefer `scripts/robots_parser.py`, `scripts/sitemap_sampler.py`, and
   `scripts/js_shell.py` over hand-parsing.
4. If a pre-fetched site bundle is present and already contains a field,
   use that field and do not re-fetch it.
5. Immediately after the homepage fetch, classify the response with
   `scripts/fetch_quality.py` as `usable`, `interstitial`, `error`, or
   `hard_block`. Downstream content/identity checks must read this
   classification first. D3 covers `hard_block` (403 / connection). A
   404 stub or JS-challenge is **not** D3 — emit a single `FQ` finding
   at `medium` (uncertainty, not a claim about the brand) and do not
   score that body as the homepage.

---

## D1 — Full-site crawler block

**Detects:** `robots.txt` shuts out every crawler via `User-agent: *` +
`Disallow: /`.

**Steps**

1. Fetch `{origin}/robots.txt`.
2. If the status is not 200 or the body is empty/non-text, D1 does **not**
   fire (absence of robots.txt is not a block).
3. Parse into groups with `scripts/robots_parser.py`.
4. Collect every group whose user-agent list includes `*` (case-insensitive).
5. D1 fires if those `*` rules include a `Disallow` whose path is `/`
   (optional trailing `*` does not change this: `Disallow: /` is a root
   block). Quote the exact line(s).
6. An `Allow: /public` (or similar) next to `Disallow: /` does **not**
   cancel D1 — the root is still disallowed. Only an `Allow: /` on the
   `*` group cancels a same-group `Disallow: /`.
7. `Disallow: /admin` or any longer path is not D1.

**Evidence:** quote the `User-agent` / `Disallow` lines and the robots.txt
URL.

**Severity:** `critical`.

**Suggested action:** remove or narrow the `User-agent: *` `Disallow: /`
rule so public pages can be crawled and cited.

**After D1 fires:** do not request further paths on the origin (robots.txt
forbids it). Homepage HTML from D3 may still be scored for D5. Skip D2 as
a separate finding (the `*` rule already covers named agents); keep the
parser's named-agent table in the bundle.

---

## D2 — Named AI-crawler block (training vs live-agent)

**Detects:** robots.txt blocks specific AI user-agents. Training-crawler
access and live-agent access are different permissions and must be
reported separately.

**Classification** (canonical names; match case-insensitively):

| Category | User-agents |
|---|---|
| `training-crawler` | GPTBot, ClaudeBot, anthropic-ai, Google-Extended, Applebot-Extended, CCBot, Bytespider, meta-externalagent, PerplexityBot, Amazonbot, cohere-ai, Diffbot |
| `live-agent` | ChatGPT-User, OAI-SearchBot, Claude-User, Claude-SearchBot, Perplexity-User, Google-CloudVertexBot, Meta-ExternalFetcher |

A site can allow `GPTBot` while blocking `ChatGPT-User` — those are not
the same check.

**Steps**

1. Skip emitting a D2 finding if D1 already fired.
2. For each catalogued agent, ask the parser whether path `/` is disallowed
   for that agent. A named group takes precedence over `*`. No named group
   and no blocking `*` → not blocked.
3. Split blocked agents into `training-crawler` and `live-agent`.
4. Ignore unknown `User-agent` tokens. Do not guess that a novel name is
   an AI crawler.
5. If neither category has a blocked agent, D2 does not fire.

**Evidence:** two lists — `blocked_training_crawlers` and
`blocked_live_agents` — each with the quoted `Disallow` rule that caused
the block.

**Severity:**

- `high` if one or more **live-agent** user-agents are blocked (breaks
  real-time citation / browsing).
- `medium` if **only** training-crawlers are blocked.

**Suggested action:** generate from the categories that actually fired.
If only training-crawlers are blocked, say so and do not lead with
live-agent advice. If only live-agents are blocked, advise on live
access. If both, mention both.

---

## D3 — Infrastructure-level hard block (WAF / 403)

**Detects:** the homepage is unreachable to an automated visitor *before*
robots.txt is a useful signal. Harder than a robots disallow: there is
nothing to parse.

**Steps**

1. Fetch `{origin}/` **before** fetching robots.txt.
2. D3 fires when any of these is true:
   - HTTP status is `403`
   - the TCP/TLS connection is reset, refused, or times out
   - the client is blocked with no usable HTML body (e.g. empty 403 from a WAF)
3. Status `401` on the homepage is D3 as well (the whole site is gated).
4. Status `200`–`399` (after redirects) is not D3. Follow same-host
   redirects; record `final_url`.
5. A 404 homepage is not D3 (the server answered).
6. Do **not** classify a later internal 403 as D3 — that is D6.
7. If D3 fires, you may still GET `/robots.txt` once for the bundle. Do
   not sample internal pages.

**Evidence:** HTTP status (or `null` on connection failure), a short
error string if the request never completed, and a small header subset
when present (`server`, `cf-ray`, `x-*`, `www-authenticate`,
`content-type`).

**Severity:** `critical`.

**Suggested action:** review WAF/CDN/bot rules so ordinary HTTP clients
and reputable crawlers can reach public pages. This skill only recommends.

---

## D4 — Sitemap missing or unreachable

**Detects:** no usable sitemap, so automated visitors cannot discover
real internal URLs.

**Locations to check (only these):**

1. Every `Sitemap:` URL declared in robots.txt (absolute or origin-relative).
2. If none of those produce a valid sitemap, `{origin}/sitemap.xml`.

Do **not** probe `/sitemap_index.xml`, `/sitemap-index.xml`,
`/sitemaps/sitemap.xml`, or any other guessed path.

**Valid sitemap:**

- HTTP 200 (after redirects)
- Body parses as XML
- Root (or a descendant) is `urlset` or `sitemapindex` (ignore XML
  namespaces)
- Not an HTML page, not an empty/error document pretending to be 200
  (soft-404)

A `sitemapindex` is valid XML. Child sitemaps listed *inside* it are
declared, not guessed — fetch them (same origin only). If a child is
itself a `sitemapindex`, recurse **one additional level** (total depth
cap 2) to reach `urlset` page URLs. Do not walk huge index trees.

If valid sitemap XML is found but **zero page `<loc>` URLs** remain
after that depth cap, D4 fires a separate **low** finding (“sitemap
present but no page URLs reachable”). That is not a silent pass, and
D5/D6/D7/D8 skip with that reason.

`.xml.gz` on a declared URL may be decompressed; that is not a guessed
path.

**Steps**

1. Record each location tried: URL, source (`robots.txt` or
   `default /sitemap.xml`), status, `is_valid_sitemap`.
2. D4 fires only if **no** location produced a valid sitemap.
3. An empty but well-formed `urlset` is valid — D4 does not fire; D5/D6
   simply have no internal URLs.

**Evidence:** the list of locations checked and the result for each.

**Severity:** `medium`.

**Suggested action:** distinguish “we could not retrieve a valid sitemap
from this fetch” from “the site never published one.” A 200 response
whose body is HTML or a JS-challenge is not a sitemap — say that the
URL did not return XML. A 404 / connection miss should say the
locations were unreachable. Do not claim the site never published a
sitemap.

---

## D5 — JS-shell content gap (sampled internal pages)

**Detects:** a simple HTTP fetch returns a page whose visible text is
too thin to be the real content — typical of a client-rendered shell.
This often appears on internal pages even when the homepage is
server-rendered, so homepage-only scanning is not enough.

**URL source (mandatory):**

1. Collect `<loc>` URLs from valid sitemaps only (`scripts/sitemap_sampler.py`).
2. Keep same-origin http(s) URLs. Drop obvious non-HTML (`pdf`, images,
   `css`, `js`, archives).
3. Drop the homepage itself from the *internal* sample (it is already
   fetched).
4. Sample several remaining URLs (default cap: 6), preferring path
   diversity (different first path segments) and, when they *already
   appear in the sitemap*, paths that look like product / pricing /
   about / services / features / shop. When the sitemap mixes locale
   trees, prefer the locale of the homepage URL over whichever locale
   appears first in the index. Strip a leading locale segment before
   classifying a path as key vs marginal (`/en-us/pricing` is key).
5. **Never invent a URL.** If the sitemap is missing or empty, do not
   guess `/about` or `/pricing`. Coverage becomes `homepage_only` (or
   `none` if the homepage was not fetched).

**Per-page metric** (`scripts/js_shell.py`):

1. Parse HTML. Remove `script`, `style`, `template`, `svg`. Keep
   `noscript` text (a crawler without JS can still read it).
2. `visible_text` = stripped visible text.
3. `word_count` = whitespace-separated tokens.
4. `text_to_html_ratio` = `len(visible_text) / len(raw_html)` (`0` if
   empty HTML).
5. Fetch status must be 200 (or a 2xx/3xx that yielded HTML). Do not
   JS-shell-score 401/403 pages — those are D6.

**Flag a page as a JS-shell when:**

- `word_count < 20` — **regardless of ratio** (empty mount point, "Loading…",
  or other placeholder chrome), or
- `word_count < 200` **and** `text_to_html_ratio < 0.04`

**Do not flag** when `word_count >= 200`, even if the ratio is very low.
A long page with bulky CSS/JS is normal, not a shell. A short but fully
server-rendered page with a *high* ratio is also not a shell.

**Key vs marginal path** (severity only; still never guess these paths):

- **Key:** homepage, or the first path segment is one of
  `about`, `pricing`, `price`, `product`, `products`, `services`,
  `service`, `features`, `solutions`, `shop`, `store` (plus common
  singular/plural already listed).
- **Marginal:** everything else that came from the sitemap (legal,
  blog posts, tags, pagination, etc.).

**Severity:**

- `high` if one or more **key** pages are flagged.
- `low` if only marginal pages are flagged.

**Evidence:** for every scored page, URL, `word_count`,
`text_to_html_ratio`, `flagged` true/false. The finding lists the
flagged subset.

**Suggested action:** server-render primary content (or provide an
equivalent in the initial HTML / `noscript`) so non-JS crawlers can
read the page.

If no HTML page could be scored, do not emit D5; add `D5` to
`coverage.skipped_checks`.

---

## D6 — Auth-gated content wall

**Detects:** an internal URL is inaccessible to an unauthenticated
visitor. Distinct from D3 (homepage-level block) and D5 (reachable HTML
with no content).

**Steps**

1. Inspect the same sitemap sample used for D5 (and only those URLs).
2. Record a page if the request, or any hop in its redirect chain,
   returned `401` or `403`.
3. Exclude the homepage if it was already classified as D3.
4. Soft login pages that return `200` with a login form are **not** D6
   (no status-code evidence). Do not guess.
5. If nothing in the sample returned 401/403, D6 does not fire.

**Evidence:** each gated URL + status code (and `final_url` if redirected).

**Severity:** `medium`.

**Suggested action:** if those URLs are meant to be discoverable, provide
a public, unauthenticated representation. Do not attempt to log in.

---

## Severity recap

| ID | Severity |
|---|---|
| D3 | critical (hard block only) |
| FQ | medium (404 stub / JS-challenge / unusable body — uncertainty) |
| D1 | critical |
| D2 | high if any live-agent blocked; medium if only training-crawlers |
| D4 | medium |
| D5 | high if key pages; low if only marginal |
| D6 | medium |

Do not invent extra severities. Do not upgrade D4/D6 because the site
"seems important."
