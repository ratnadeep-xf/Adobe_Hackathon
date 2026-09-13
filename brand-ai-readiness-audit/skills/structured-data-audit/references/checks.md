# D7–D8 check logic

Deterministic rules for `structured-data-audit`. Thresholds are principled
starting points (to be tuned later), not fitted to any particular site.
Every finding must quote something actually observed: a block count, a
`@type` list, or a URL that was actually fetched.

Prefer a pre-fetched site bundle (homepage + crawl-render-audit sampled
pages). Never guess internal paths.

---

## Shared setup

1. Normalize input to an origin: if the value has no scheme, try `https://`
   first; if the TLS/connection fails (not a 403), try `http://`.
2. Pages to score:
   - Homepage HTML (required).
   - Sampled internal pages from the site bundle, **or** real `<loc>` URLs
     from a declared/default sitemap. Never invent `/about` or `/product`.
3. Skip pages whose fetch is 401/403, non-HTML, classified as
   interstitial/error, or flagged
   `identical_to_homepage_suspected_soft_404` (homepage echo / suspected
   soft-404). They are not "missing JSON-LD"; they were not a distinct
   readable page. If the homepage itself is not usable content, skip D7
   and D8 entirely.
4. Strip a leading locale segment before key-vs-marginal and
   path-to-type mapping (`/en-us/pricing` is a pricing page).
5. Identify fetches as read-only. Prefer `scripts/jsonld.py` over
   informal reading of script tags.
6. If a pre-fetched field is present, use it and do not re-fetch.

**Key vs marginal path** (severity / D7-medium only):

- **Key:** homepage, or the first path segment is one of
  `about`, `pricing`, `price`, `product`, `products`, `services`,
  `service`, `features`, `solutions`, `shop`, `store`.
- **Marginal:** everything else that was actually sampled.

---

## D7 — JSON-LD absent

**Detects:** no `application/ld+json` blocks. A page can be well-written
and still give a machine nothing structured to extract.

**Evidence (n=100+22 reachable sites):** JSON-LD presence is roughly a
coin flip — about 56% present / 44% absent. Do not frame absence as
rare, and do not frame presence as the norm.

**Steps**

1. On each scorable page, run `scripts/jsonld.py` and record `block_count`
   (script tags with `ld+json` in their type, whether or not the JSON
   parses).
2. D7 fires in one of these forms — pick the single strongest, do not
   emit two D7 findings:
   - **Homepage has `block_count == 0`:** fire D7. Include internal
     counts in the evidence for context.
   - **Homepage has `block_count >= 1` and at least one key subpage has
     `block_count == 0`:** fire D7 at medium. Marginal pages with no
     JSON-LD do not trigger this by themselves.
3. If every scorable page (including homepage) has `block_count >= 1`,
   D7 does not fire.
4. A script tag that fails to parse still counts as a block for D7
   (something was offered to the machine). Parse errors belong in
   evidence and in D8's type table, not as "absent."
5. If no HTML page could be scored, do not emit D7; add `D7` to
   `coverage.skipped_checks`.

**Evidence:** pages checked, per-page block counts (homepage called out),
and `0` called out explicitly when that is the finding.

**Severity:**

- `high` if the homepage has zero blocks.
- `medium` if JSON-LD is present on the homepage but absent on one or
  more key subpages.

**Suggested action:** add schema.org JSON-LD whose `@type` matches what
the page actually is. Example types must be derived from the page path
or on-page language — do not offer a fixed commercial list
(`Product`, `LocalBusiness`, `Article`) to every site.

---

## D8 — Generic-only or inconsistent structured data

**Detects:** JSON-LD exists but does not help a machine extract a
*specific* fact — only generic chrome types, or types that do not match
the page's evident purpose. This is a disambiguation problem, not a
total absence (that is D7).

**Evidence (n=100+22):** this is the strongest single finding behind this
skill. Among sites that **do** have JSON-LD, 67% still use only generic
Organization/WebSite types with nothing domain-specific. Lead with that
rate; it is not a footnote to D7.

**Generic types** (chrome / identity-wrapper; match case-insensitively,
ignore `https://schema.org/` prefixes):

`Organization`, `Corporation`, `WebSite`, `WebPage`, `CollectionPage`,
`SearchAction`, `BreadcrumbList`, `ListItem`, `ItemList`, `ImageObject`,
`EntryPoint`, `SiteNavigationElement`, `WPHeader`, `WPFooter`,
`WPSideBar`, `ReadAction`, `ViewAction`, `Thing`, `Brand`,
`ContactPoint`, `PostalAddress`, `GeoCoordinates`, `PropertyValue`,
`QuantitativeValue`, `OpeningHoursSpecification`.

**Domain-specific:** any other `@type`, including `LocalBusiness` (and
subtypes), `Product`, `Offer`, `AggregateOffer`, `Article`,
`NewsArticle`, `BlogPosting`, `NewsMediaOrganization`, `Person`,
`SoftwareApplication`, `FAQPage`, `HowTo`, `Event`, `Recipe`, `Course`,
`JobPosting`, `Service`, `Place`. Unknown / custom types are treated as
domain-specific — do not require a memorized industry list.

Primary types are taken from each JSON-LD object's `@type`, each
`@graph` item's `@type`, and `mainEntity` — not every nested
`ImageObject`.

**Steps**

1. Skip D8 if no scorable page has `block_count >= 1`. Absence is D7.
2. Union primary types across all pages that have at least one block.
3. **Generic-only:** fire D8 if that union is non-empty and every type
   is generic (or there are blocks but zero parseable `@type` values).
4. **Purpose mismatch:** for each page that has JSON-LD, if its URL's
   first path segment implies an expected type family and none of the
   page's types sit in that family, fire D8. Expected families:

   | Path shape | Expected type family |
   |---|---|
   | `product`, `products`, `shop`, `store`, `pricing`, `price` | `Product`, `Offer`, `AggregateOffer`, `Service` |
   | **Individual** `blog`/`news`/`article`/`press`/`stories` URL with a slug (`/blog/my-post`) | `Article`, `NewsArticle`, `BlogPosting` |
   | **Listing/index** (`/blog`, `/news`, `/articles`) | none — `WebPage` / `Organization` is consistent |
   | Individual `events`/`event` URL with a slug | `Event` |
   | Individual `jobs`/`careers`/`job` URL with a slug | `JobPosting` |

   Homepage, listing indexes, and paths with no row above have **no**
   expected family — do not guess a vertical from the brand name.
5. Homepage-only `Organization`/`WebSite` plus `Product` on a product
   URL is **consistent** — do not fire D8 for that pattern.
6. Missing blocks on a key page (count = 0) are D7, not D8. Do not
   double-count.
7. If none of the conditions fire, D8 does not fire.

**Evidence:** list of types found (per page and site-wide), the generic
vs domain-specific split, and — when relevant — the expected family for
a mismatched path.

**Severity:** `medium`.

**Suggested action:** add a domain-specific `@type` that matches what
the page is, not only `Organization` / `WebSite`. Name the expected
family when a path mapping fired; otherwise stay generic.

---

## Severity recap

| ID | Severity |
|---|---|
| D7 | high if homepage has zero blocks; medium if homepage has JSON-LD but a key subpage does not |
| D8 | medium |

Do not invent extra severities. Do not upgrade D8 because the site
"seems important."
