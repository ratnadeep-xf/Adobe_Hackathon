#!/usr/bin/env python3
"""Standalone D9–D13 freshness / corroboration audit."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from source_classifier import classify_domains  # noqa: E402
from web_search import hosts_match, search_bundle  # noqa: E402

# D13 hard cap — do not change. Phase 2: never more than low.
D13_SEVERITY = "low"

FOUNDING_RE = re.compile(
    r"\b(?:founded|established|est\.?|since)\s+(?:in\s+)?((?:19|20)\d{2})\b",
    re.I,
)
HQ_RE = re.compile(
    r"\b(?:headquartered|headquarters|based)\s+in\s+([A-Z][A-Za-z .'-]{2,40})",
)
COPYRIGHT_RE = re.compile(r"(?:©|&copy;|copyright)\s*(?:\(c\))?\s*((?:19|20)\d{2})", re.I)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def finding(check_id: str, title: str, severity: str, evidence: str, action: str) -> dict[str, Any]:
    return {
        "id": check_id,
        "title": title,
        "severity": severity,
        "evidence": evidence,
        "suggested_action": {"summary": action, "priority": severity},
    }


def origin_from(raw: str) -> str:
    value = raw.strip()
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    parsed = urlparse(value)
    return f"{parsed.scheme}://{parsed.netloc}"


def host_of(origin: str) -> str:
    host = urlparse(origin).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def brand_from_html(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.I | re.S)
    if not match:
        return ""
    title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", match.group(1))).strip()
    title = re.split(r"[|\-–—:]", title, maxsplit=1)[0].strip()
    return title[:80]


def visible_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return re.sub(r"<[^>]+>", " ", html or "")
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "template", "svg"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def extract_facts(text: str) -> list[dict[str, str]]:
    facts: list[dict[str, str]] = []
    founding = FOUNDING_RE.search(text or "")
    if founding:
        facts.append({"kind": "founding_year", "value": founding.group(1), "quoted": founding.group(0)})
    hq = HQ_RE.search(text or "")
    if hq:
        facts.append({"kind": "headquarters", "value": hq.group(1).strip(" .,"), "quoted": hq.group(0)})
    return facts[:2]


def run(
    target: str,
    bundle: dict[str, Any] | None = None,
    search: dict[str, Any] | None = None,
    brand: str = "",
) -> dict[str, Any]:
    origin = (bundle.get("origin") if bundle and bundle.get("origin") else origin_from(target)).rstrip("/")
    host = host_of(origin)
    homepage = (bundle or {}).get("homepage") or {}
    html = homepage.get("html") or homepage.get("text") or ""
    headers = homepage.get("headers") or {}
    if not html and not search:
        try:
            import requests

            resp = requests.get(
                origin + "/",
                headers={"User-Agent": "Mozilla/5.0 (compatible; BrandAIReadinessAudit/1.0; +read-only-audit)"},
                timeout=12,
            )
            html = resp.text
            headers = {"last-modified": resp.headers.get("Last-Modified", "")}
            homepage = {"url": origin + "/", "status": resp.status_code, "html": html, "headers": headers}
        except Exception:
            pass

    quality = homepage.get("fetch_quality")
    if not isinstance(quality, dict) or not quality.get("class"):
        crawl = SCRIPT_DIR.parents[1] / "crawl-render-audit" / "scripts"
        if crawl.is_dir():
            sys.path.insert(0, str(crawl))
            try:
                from fetch_quality import classify_page

                quality = classify_page(homepage) if homepage else {"usable": True, "class": "usable"}
            except Exception:
                quality = {"usable": True, "class": "usable"}
        else:
            quality = {"usable": True, "class": "usable"}

    if quality.get("usable"):
        resolved_brand = (brand or "").strip() or brand_from_html(html) or host.split(".")[0]
    else:
        resolved_brand = (brand or "").strip() or host.split(".")[0]
    if search and search.get("results") is not None:
        search_data = search
    else:
        try:
            search_data = search_bundle(resolved_brand, host)
        except RuntimeError as exc:
            search_data = {
                "query": resolved_brand,
                "results": [],
                "distinct_domains": [],
                "own_domain_present": False,
                "error": str(exc),
            }

    domains = list(search_data.get("distinct_domains") or [])
    results = list(search_data.get("results") or [])
    classified = classify_domains(domains, host)
    search_data["buckets"] = classified

    findings: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    notes: dict[str, dict[str, str]] = {}
    count = len(domains)

    def mark(check_id: str, status: str, reason: str) -> None:
        notes[check_id] = {"status": status, "reason": reason}
        if status == "skipped" and not any(row.get("id") == check_id for row in skipped):
            skipped.append({"id": check_id, "reason": reason})

    if count < 3:
        findings.append(
            finding(
                "D9",
                "Weak organic footprint for the brand name",
                "high",
                f"Keyless search for {resolved_brand!r} returned {count} distinct domain(s): {domains or '[]'}.",
                "Earn independent coverage so a name search yields more than a handful of domains.",
            )
        )
        mark("D9", "fired", f"{count} distinct search domain(s)")
    elif count < 5:
        findings.append(
            finding(
                "D9",
                "Thin organic footprint for the brand name",
                "medium",
                f"Keyless search for {resolved_brand!r} returned {count} distinct domain(s): {domains}.",
                "Broaden independent coverage beyond a small set of domains.",
            )
        )
        mark("D9", "fired", f"{count} distinct search domain(s)")
    else:
        mark("D9", "clear", f"{count} distinct search domains; footprint threshold met")

    if count == 0:
        mark("D10", "skipped", "search returned no domains; official-host presence cannot be scored")
    elif not search_data.get("own_domain_present"):
        findings.append(
            finding(
                "D10",
                "Official domain absent from its own name search",
                "critical",
                f"Audited host {host} (eTLD+1) was not matched by any search-result domain {domains} "
                f"for query {resolved_brand!r}.",
                "Make the official site discoverable under the brand name (indexable homepage, consistent naming, inbound listings).",
            )
        )
        mark("D10", "fired", f"no search domain shares eTLD+1 with {host}: {domains}")
    else:
        matched = search_data.get("own_domain_match") or host
        mark(
            "D10",
            "clear",
            f"official eTLD+1 matched search domain {matched!r} (audited host {host})",
        )

    if count < 2:
        mark("D11", "skipped", "fewer than 2 distinct domains; source diversity not scored")
    elif classified["diversity_count"] <= 1:
        findings.append(
            finding(
                "D11",
                "Low-diversity corroboration sources",
                "medium",
                f"All {count} distinct domains fall in bucket(s) {classified['represented']}: {classified['buckets']}.",
                "Seek coverage across press, reviews, reference, and official sources — not a single aggregator type.",
            )
        )
        mark("D11", "fired", f"only bucket(s) {classified['represented']}")
    else:
        mark("D11", "clear", f"source buckets represented: {classified['represented']}")

    if not quality.get("usable"):
        mark("D12", "skipped", "homepage fetch is not usable content; on-site facts not extracted")
        mark("D13", "skipped", "homepage fetch is not usable content; copyright year not scored")
        return {
            "skill": "freshness-corroboration",
            "site": host,
            "audited_at": utc_now(),
            "brand": resolved_brand,
            "findings": findings,
            "search_bundle": search_data,
            "coverage": {
                "skipped_checks": skipped,
                "check_notes": notes,
                "homepage_fetch_quality": quality,
            },
        }

    text = visible_text(html)
    facts = extract_facts(text)
    corpus = " ".join(f"{r.get('title', '')} {r.get('snippet', '')}" for r in results)
    if not facts:
        mark("D12", "no_signal", "no checkable on-site facts (founding year / headquarters) extracted")
    else:
        contradicted = []
        unconfirmed = []
        for fact in facts:
            if fact["kind"] == "founding_year":
                years = set(re.findall(r"\b((?:19|20)\d{2})\b", corpus))
                years.discard(fact["value"])
                if years:
                    contradicted.append(f"{fact['quoted']} vs other years in sources {sorted(years)}")
                elif fact["value"] not in corpus:
                    unconfirmed.append(fact["quoted"])
            else:
                token = fact["value"].split(",")[0].strip()
                if token and token.lower() not in corpus.lower():
                    unconfirmed.append(fact["quoted"])
        if contradicted:
            findings.append(
                finding(
                    "D12",
                    "Official-site fact contradicted by independent sources",
                    "high",
                    "; ".join(contradicted),
                    "Reconcile the official fact with independent sources or correct the on-site statement.",
                )
            )
            mark("D12", "fired", "; ".join(contradicted))
        elif unconfirmed:
            findings.append(
                finding(
                    "D12",
                    "Official-site fact unconfirmed across independent sources",
                    "low",
                    f"On-site fact(s) not repeated in search snippets: {unconfirmed}.",
                    "Repeat checkable facts (founding year, HQ) on independent pages so machines can corroborate them.",
                )
            )
            mark("D12", "fired", f"unconfirmed: {unconfirmed}")
        else:
            mark("D12", "clear", f"on-site fact(s) corroborated in search snippets: {[f['quoted'] for f in facts]}")

    year_match = COPYRIGHT_RE.search(text)
    last_mod = headers.get("last-modified") or headers.get("Last-Modified")
    current_year = datetime.now(timezone.utc).year
    if year_match and int(year_match.group(1)) <= current_year - 2:
        findings.append(
            finding(
                "D13",
                "Copyright year suggests staleness",
                D13_SEVERITY,
                f"Copyright year {year_match.group(1)} found on the homepage"
                + (f"; Last-Modified={last_mod}" if last_mod else "")
                + ". Severity is capped at low (noisy signal).",
                "Update the visible copyright year if the site is still maintained. Do not treat this as proof the brand is inactive.",
            )
        )
        mark("D13", "fired", f"copyright year {year_match.group(1)}")
    elif year_match:
        mark("D13", "clear", f"copyright year {year_match.group(1)} is within two years of {current_year}")
    else:
        mark("D13", "no_signal", "no copyright year found on the homepage")

    return {
        "skill": "freshness-corroboration",
        "site": host,
        "audited_at": utc_now(),
        "brand": resolved_brand,
        "findings": findings,
        "search_bundle": search_data,
        "coverage": {
            "skipped_checks": skipped,
            "check_notes": notes,
            "homepage_fetch_quality": quality,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run freshness-corroboration (D9–D13).")
    parser.add_argument("target")
    parser.add_argument("--brand", default="")
    parser.add_argument("--bundle", help="Site bundle JSON (homepage)")
    parser.add_argument("--search-bundle", help="Pre-fetched search bundle JSON")
    args = parser.parse_args(argv)
    bundle = None
    if args.bundle:
        with open(args.bundle, encoding="utf-8") as fh:
            loaded = json.load(fh)
        bundle = loaded.get("site_bundle", loaded)
    search = None
    if args.search_bundle:
        with open(args.search_bundle, encoding="utf-8") as fh:
            search = json.load(fh)
            search = search.get("search_bundle", search)
    json.dump(run(args.target, bundle, search, args.brand), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
