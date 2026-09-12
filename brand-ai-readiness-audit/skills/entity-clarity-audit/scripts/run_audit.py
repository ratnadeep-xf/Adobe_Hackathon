#!/usr/bin/env python3
"""Standalone D14–D15 entity-clarity audit.

Reuses a search bundle (does not re-search when one is provided) and the
same title/meta/H1/opening extract as engagement-audit.
"""

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
SKILLS_DIR = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

FILLER = {
    "welcome", "official", "website", "online", "company", "about", "home",
    "https", "http", "www", "com", "the", "and", "for", "with", "from",
}

PARKED_RE = re.compile(
    r"domain is for sale|buy this domain|parked free|this domain is parked",
    re.I,
)


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


def content_tokens(text: str) -> set[str]:
    tokens = re.findall(r"[A-Za-z]{5,}", text or "")
    return {t.lower() for t in tokens if t.lower() not in FILLER}


def extract_self_description(html: str) -> dict[str, Any]:
    engage_scripts = SKILLS_DIR / "engagement-audit" / "scripts"
    if engage_scripts.is_dir():
        sys.path.insert(0, str(engage_scripts))
        try:
            from page_signals import extract_self_description as extract

            return extract(html)
        except Exception:
            pass
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    title = soup.find("title")
    return {
        "title": title.get_text(" ", strip=True) if title else "",
        "meta_description": "",
        "h1s": [h.get_text(" ", strip=True) for h in soup.find_all("h1")],
        "first_paragraph": soup.get_text(" ", strip=True)[:280],
        "combined": soup.get_text(" ", strip=True)[:800],
        "concrete_offerings": [],
    }


def search_summary(search: dict[str, Any]) -> str:
    parts = []
    for row in search.get("results") or []:
        parts.append(f"{row.get('title', '')} — {row.get('snippet', '')}")
    return " | ".join(p.strip(" —") for p in parts if p.strip(" —"))


def _fetch_quality(homepage: dict[str, Any]) -> dict[str, Any]:
    existing = homepage.get("fetch_quality")
    if isinstance(existing, dict) and existing.get("class"):
        return existing
    crawl_scripts = SKILLS_DIR / "crawl-render-audit" / "scripts"
    if crawl_scripts.is_dir():
        sys.path.insert(0, str(crawl_scripts))
        try:
            from fetch_quality import classify_page

            return classify_page(homepage)
        except Exception:
            pass
    status = homepage.get("status")
    if status in {401, 403} or homepage.get("error"):
        return {"usable": False, "class": "hard_block", "reason": str(homepage.get("error") or status)}
    if status in {404, 410}:
        return {"usable": False, "class": "error", "reason": f"HTTP {status}"}
    return {"usable": True, "class": "usable", "reason": "assumed usable"}


def domain_unresolved(homepage: dict[str, Any]) -> tuple[bool, str]:
    """D15 may fire only on a confirmed fetch/DNS failure — not a thin or error body."""
    quality = _fetch_quality(homepage)
    if quality.get("class") == "hard_block":
        return True, quality.get("reason") or "hard block"
    error = (homepage.get("error") or "").lower()
    if error in {"timeout", "connection reset", "connection refused", "connection error"}:
        return True, error
    if homepage.get("status") is None and not (homepage.get("html") or homepage.get("text")):
        return True, "no HTTP response"
    return False, "fetch reached the origin"


def run(
    target: str,
    bundle: dict[str, Any] | None = None,
    search: dict[str, Any] | None = None,
    brand: str = "",
    self_description: dict[str, Any] | None = None,
) -> dict[str, Any]:
    origin = (bundle.get("origin") if bundle and bundle.get("origin") else origin_from(target)).rstrip("/")
    host = host_of(origin)
    homepage = (bundle or {}).get("homepage") or {}
    html = homepage.get("html") or homepage.get("text") or ""
    desc = self_description or extract_self_description(html)

    if search is None:
        fresh_scripts = SKILLS_DIR / "freshness-corroboration" / "scripts"
        sys.path.insert(0, str(fresh_scripts))
        from web_search import search_bundle

        search = search_bundle(brand or host.split(".")[0], host)

    summary = search_summary(search)
    site_text = desc.get("combined") or ""
    findings: list[dict[str, Any]] = []
    skipped: list[str] = []
    notes: dict[str, dict[str, str]] = {}

    def mark(check_id: str, status: str, reason: str) -> None:
        notes[check_id] = {"status": status, "reason": reason}
        if status == "skipped" and check_id not in skipped:
            skipped.append(check_id)

    quality = _fetch_quality(homepage)
    if not quality.get("usable"):
        mark(
            "D14",
            "skipped",
            f"homepage fetch is {quality.get('class')}; site text is not the brand self-description",
        )
    else:
        site_tokens = content_tokens(site_text)
        search_tokens = content_tokens(summary)
        if len(site_tokens) < 3 or len(search_tokens) < 3:
            mark(
                "D14",
                "no_signal",
                f"not enough content tokens to compare (site={len(site_tokens)}, search={len(search_tokens)})",
            )
        elif site_tokens.isdisjoint(search_tokens):
            findings.append(
                finding(
                    "D14",
                    "Name collision / mistaken identity",
                    "critical",
                    f"Site self-description and search-grounded summary of {brand or host!r} share no content tokens. "
                    f"SITE: {site_text[:400]!r} SEARCH: {summary[:400]!r}.",
                    "Disambiguate the official name on-site (unique descriptor, same-as links) so assistants attach the name to this entity.",
                )
            )
            mark("D14", "fired", "site and search content-token sets are disjoint")
        else:
            overlap = sorted(site_tokens & search_tokens)
            mark(
                "D14",
                "clear",
                f"site and search summaries share content tokens {overlap[:8]}",
            )

    unresolved, reason = domain_unresolved(homepage)
    independent = [
        d for d in (search.get("distinct_domains") or [])
        if d and d != host and not d.endswith("." + host)
    ]
    if unresolved and len(independent) >= 2:
        findings.append(
            finding(
                "D15",
                "Domain-vs-business divergence",
                "critical",
                f"Homepage fetch failed ({reason}) while the name still appears on independent domains {independent}.",
                "Restore a working first-party site or officially redirect the name to a live property you control.",
            )
        )
        mark("D15", "fired", f"hard-block ({reason}) with independent presence {independent}")
    elif unresolved:
        mark(
            "D15",
            "no_signal",
            f"homepage fetch failed ({reason}) but fewer than 2 independent domains; business looks defunct",
        )
    else:
        mark("D15", "clear", f"{reason}; domain-vs-business divergence not indicated")

    return {
        "skill": "entity-clarity-audit",
        "site": host,
        "audited_at": utc_now(),
        "findings": findings,
        "site_description": desc,
        "search_summary": summary,
        "coverage": {
            "skipped_checks": skipped,
            "check_notes": notes,
            "homepage_fetch_quality": quality,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run entity-clarity-audit (D14–D15).")
    parser.add_argument("target")
    parser.add_argument("--brand", default="")
    parser.add_argument("--bundle")
    parser.add_argument("--search-bundle")
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
