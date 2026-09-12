# E1–E3 check logic

Homepage only (the crawl-render homepage fetch). Concrete offering ≠
slogan. Length-only meta checks are confirmed useless — do not use them.

If homepage fetch-quality is not `usable` (404 stub, JS-challenge,
hard block), skip E1–E3 entirely. Do not treat an error or interstitial
body as the brand's orientation.

---

## Shared extraction (`scripts/page_signals.py`)

From homepage HTML:

- `title` — `<title>` text
- `meta_description` — `<meta name="description">` content
- `h1s` — text of every `<h1>`
- `first_paragraph` — first visible `<p>` with ≥ 4 words (else first
  substantial block of visible text)
- `combined` — those four joined with spaces

**Filler** (not an offering): tokens such as welcome, innovative, leading,
excellence, world-class, cutting-edge, solutions, digital, transform,
future, empower, seamless, premier, ultimate, next-generation, and common
stopwords.

**Concrete offering:** a remaining content noun (4+ letters, not filler)
and/or a pattern like “we sell/make/provide/build/offer …”.

---

## E1 — Weak on-page orientation

Fire `high` if `combined` states no concrete offering.

**Evidence:** the combined text and the offering list (empty when firing).

---

## E2 — Generic or non-descriptive meta description

1. If meta is missing or shorter than 40 characters, E2 does **not** fire
   (that is a missing-snippet problem, not “long but empty”).
2. If meta is ≥ 40 characters and still has no concrete offering after
   filler is removed, fire `medium`.

**Evidence:** the meta description text itself.

---

## E3 — Missing or duplicate H1 structure

1. Fire if `len(h1s) == 0` or `len(h1s) >= 2`.
2. Severity `low`; upgrade to `medium` only when E1 also fired.

**Evidence:** H1 count and the text of each H1.
