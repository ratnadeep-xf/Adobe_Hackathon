# D9–D13 check logic

Deterministic rules for `freshness-corroboration`. Thresholds are
principled starting points. Every finding quotes observed domains,
snippets, or on-page text.

Prefer a pre-fetched search bundle and homepage. One brand-name search
per audit.

---

## Shared setup

1. Brand name: `--brand` if given, else homepage `<title>` (trimmed), else
   the registrable domain label.
2. Search query is the exact brand name. Use `scripts/web_search.py`
   (ddgs / DuckDuckGo, keyless). Cap results (~8).
3. Distinct domains: `urlparse` netloc, strip leading `www.`, ignore empty.
4. Hosts match when stripped-www labels are equal.

---

## D9 — Weak organic footprint

**Detects:** a name search returns very few distinct domains.

**Steps**

1. Count distinct result domains.
2. `high` if count is under 3 (including 0).
3. `medium` if count is 3 or 4.
4. 5 or more: D9 does not fire.

**Evidence:** count + the domain list.

**Suggested action:** publish and earn independent coverage so the brand
name resolves to more than a handful of domains.

---

## D10 — Own domain absent from its own name search

**Detects:** other results exist, but the audited host is not among them.

**Steps**

1. Skip if the search returned zero results (D9 already covers emptiness).
2. Compare **registrable domain (eTLD+1)**, not exact host. `community.example.com`
   matches audited `example.com`. A result on a different registrable domain
   (`other.org`, or a platform host the brand does not share) does not.
3. Fire if no search-result domain shares that eTLD+1.
4. Severity: `critical`.

**Evidence:** present/absent + full domain list.

**Suggested action:** make the official site discoverable under the brand
name (indexable homepage, consistent name, listings that point at the
domain).

---

## D11 — Thin or low-diversity corroboration sources

**Detects:** results exist but they are all the same kind of source.

**Buckets** (`scripts/source_classifier.py`): `official`, `reference`,
`press`, `review_directory`, `social`, `other`. Classification is by
broad host *patterns* (wiki/encyclopedia stems; newspaper words like
`news`/`times`/`tribune`; common review directories; major social
networks) plus widely distributed wire/national hosts. Not a list of
outlets from any one research pass.

**Steps**

1. Skip if fewer than 2 results (D9 covers absence).
2. Fire when only one bucket is represented.
3. Severity: `medium`.

**Evidence:** bucket breakdown (counts + example domains).

---

## D12 — Stale or contradicted facts

**Detects:** a checkable official-site fact disagrees with independent
sources, or cannot be confirmed anywhere else.

**Steps**

1. From homepage visible text, extract at most two facts via patterns:
   founding/established year; “headquartered/based in …” location.
2. If none found, skip D12.
3. For each fact, scan search titles + snippets for a conflicting value
   (different year; different location token) or any confirmation.
4. `high` if any fact is directly contradicted.
5. `low` if facts exist on-site and none are confirmed or contradicted.

**Evidence:** the fact, official wording, and conflicting/confirming
snippets with URLs.

---

## D13 — Copyright / freshness signal

**Detects:** footer copyright year or `Last-Modified` suggests staleness.

**HARD RULE (implemented in code, not optional):** D13 severity is
always `low`. Never upgrade. This signal is confirmed noisy — active
sites often have no year at all. D13 alone must never justify a
high-severity finding.

**Steps**

1. Regex `©` / `copyright` + a 4-digit year (19xx/20xx) in page text.
2. Read `Last-Modified` from the homepage headers if present.
3. Fire only when a copyright year is present **and**
   `year <= current_calendar_year - 2`.
4. Do **not** fire on a missing year (too noisy).
5. Assign severity `low` in the constructor. Do not take a parameter
   that can raise it.

**Evidence:** year found (or the Last-Modified value if used as context).

**Suggested action:** update the visible copyright year if the site is
still maintained. Treat as hygiene, not as proof the brand is dead.
