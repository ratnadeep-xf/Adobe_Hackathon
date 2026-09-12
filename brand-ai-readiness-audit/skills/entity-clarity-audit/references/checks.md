# D14–D15 check logic

Reuse the freshness search bundle and the engagement self-description.
Do not guess a second brand from memory.

---

## D14 — Name collision / mistaken identity

**Detects:** the search-grounded picture of the name is a *different
kind of thing* than the audited site says it is.

**Inputs:** site `combined` text (title/meta/H1/opening) vs search
titles+snippets. **Precondition:** homepage fetch-quality is `usable`.
Skip D14 entirely on interstitial, error-stub, or hard-block bodies —
those are not the brand's self-description.

**Script rule (conservative):**

1. If fetch-quality is not `usable`, skip D14 (no finding).
2. Build content-token sets (words 5+ letters, minus filler).
3. Fire only if both sides have ≥ 3 content tokens and their
   intersection is empty.
4. Severity: `critical`.

An agent may still fire D14 when the script does not, if the two
quoted descriptions are clearly different entities. Never fire from
model memory without those two strings.

**Evidence:** both descriptions side by side.

---

## D15 — Domain-vs-business divergence

**Detects:** the domain fails or is parked/unrelated, while the named
business still appears on independent domains.

**Unreachable homepage (required for a critical finding):**

- fetch-quality class is `hard_block`, or
- no HTTP response (timeout, connection reset/refused, DNS failure)

A short body, a 404 stub, or a JS-challenge is **not** enough. Those
are fetch-quality problems, not proof the business lost its domain.
Never fire D15 at critical from thin or error-page text alone.

**Independent presence:** search bundle has ≥ 2 distinct domains that
are not the audited host.

- If domain is bad **and** independent presence: `critical`.
- If domain is bad **and** no independent presence: no finding
  (business appears defunct).
- If domain is fine: D15 does not fire.

**Evidence:** domain status + independent domain list (or its absence).
