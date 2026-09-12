#!/usr/bin/env python3
"""Standalone D7–D8 structured-data audit.

Usage:
  python scripts/run_audit.py https://example.com
  python scripts/run_audit.py https://example.com --bundle site_bundle.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from http_client import fetch  # noqa: E402
from jsonld import (  # noqa: E402
    classify_type,
    expected_types_for_url,
    extract_jsonld,
    path_class,
    purpose_mismatch,
    suggested_type_examples,
)
from page_loader import fetch_pages, pages_from_bundle  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def origin_from(raw: str) -> str:
    value = raw.strip()
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    parsed = urlparse(value)
    return f"{parsed.scheme}://{parsed.netloc}"


def finding(check_id: str, title: str, severity: str, evidence: str, action: str) -> dict[str, Any]:
    return {
        "id": check_id,
        "title": title,
        "severity": severity,
        "evidence": evidence,
        "suggested_action": {"summary": action, "priority": severity},
    }


def resolve_pages(target: str, bundle: dict[str, Any] | None) -> tuple[str, list[dict[str, Any]]]:
    if bundle:
        origin = (bundle.get("origin") or origin_from(bundle.get("homepage", {}).get("url") or target)).rstrip("/")
        pages = pages_from_bundle(bundle)
        if pages:
            return origin, pages
    origin = (bundle.get("origin") if bundle and bundle.get("origin") else origin_from(target)).rstrip("/")
    pages = fetch_pages(origin)
    if pages:
        return origin, pages
    # https failed with no pages: try http once when the input had no scheme
    if "://" not in target.strip():
        http_origin = "http://" + urlparse(origin).netloc
        alt = fetch(http_origin + "/", http_origin, delay=False)
        if alt.get("status") in {200, 203} and alt.get("text"):
            return http_origin, fetch_pages(http_origin)
    return origin, pages


def run(target: str, bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    origin, pages = resolve_pages(target, bundle)
    extractions: list[dict[str, Any]] = []
    for page in pages:
        extracted = extract_jsonld(page["html"])
        extracted["url"] = page["url"]
        extracted["role"] = page["role"]
        extracted["path_class"] = path_class(page["url"])
        extracted["purpose_mismatch"] = purpose_mismatch(page["url"], extracted["types"])
        extractions.append(extracted)

    findings: list[dict[str, Any]] = []
    skipped: list[str] = []
    notes: dict[str, dict[str, str]] = {}

    def mark(check_id: str, status: str, reason: str) -> None:
        notes[check_id] = {"status": status, "reason": reason}
        if status == "skipped" and check_id not in skipped:
            skipped.append(check_id)

    home_page = next((p for p in pages if p.get("role") == "homepage"), None)
    home_quality = None
    if isinstance((home_page or {}).get("fetch_quality"), dict):
        home_quality = home_page.get("fetch_quality")
    elif bundle:
        home_quality = (bundle.get("homepage") or {}).get("fetch_quality")
    if not home_quality:
        crawl = SCRIPT_DIR.parents[1] / "crawl-render-audit" / "scripts"
        if crawl.is_dir() and home_page:
            sys.path.insert(0, str(crawl))
            try:
                from fetch_quality import classify_fetch

                home_quality = classify_fetch(
                    home_page.get("status"), home_page.get("html"), None, home_page.get("url")
                )
            except Exception:
                home_quality = {"usable": True, "class": "usable"}
        else:
            home_quality = {"usable": True, "class": "usable"}

    empty_after = bool((bundle or {}).get("sitemap_empty_after_recursion"))
    empty_after_reason = "sitemap present but no page URLs reachable within recursion depth"

    if not extractions:
        mark("D7", "skipped", "no scorable HTML pages")
        mark("D8", "skipped", "no scorable HTML pages")
        return _report(origin, findings, extractions, skipped, "none", home_quality, notes)

    if not home_quality.get("usable"):
        mark("D7", "skipped", "homepage fetch is not usable content")
        mark("D8", "skipped", "homepage fetch is not usable content")
        return _report(origin, findings, extractions, skipped, "none", home_quality, notes)

    if empty_after:
        mark("D7", "skipped", empty_after_reason)
        mark("D8", "skipped", empty_after_reason)
        return _report(origin, findings, extractions, skipped, "homepage_only", home_quality, notes)

    homepage = next((e for e in extractions if e["role"] == "homepage"), extractions[0])
    internals = [e for e in extractions if e is not homepage]
    key_missing = [
        e for e in internals
        if e["path_class"] == "key" and e["block_count"] == 0
    ]

    per_page_counts = "; ".join(
        f"{e['url']} blocks={e['block_count']} types={e['types'] or '[]'}"
        for e in extractions
    )

    if homepage["block_count"] == 0:
        examples = suggested_type_examples(
            homepage["url"],
            (home_page or {}).get("html") or "",
        )
        example_bit = (
            f" (for example {', '.join(examples)} — whichever matches this page)"
            if examples
            else " (whatever @type matches this page's offering)"
        )
        findings.append(
            finding(
                "D7",
                "No JSON-LD structured data on the homepage",
                "high",
                f"Homepage {homepage['url']} has 0 application/ld+json blocks. "
                f"Pages checked: {per_page_counts}.",
                "Add schema.org JSON-LD whose @type matches what this page actually is"
                + example_bit
                + ", not only a generic WebSite or Organization wrapper.",
            )
        )
        mark("D7", "fired", f"homepage {homepage['url']} has 0 JSON-LD blocks")
    elif key_missing:
        bits = ", ".join(f"{e['url']} blocks=0" for e in key_missing)
        key_examples = suggested_type_examples(key_missing[0]["url"])
        key_bit = (
            f" Use types that match those pages (for example {', '.join(key_examples)})."
            if key_examples
            else " Use types that match what those pages actually describe."
        )
        findings.append(
            finding(
                "D7",
                "JSON-LD missing on key subpages",
                "medium",
                f"Homepage has {homepage['block_count']} JSON-LD block(s) "
                f"({homepage['types'] or 'no @type'}), but key subpages have none: {bits}.",
                "Add schema.org JSON-LD on the key subpages that describe the offering, not only the homepage."
                + key_bit,
            )
        )
        mark("D7", "fired", f"key subpages missing JSON-LD: {bits}")
    else:
        mark("D7", "clear", "homepage and sampled key pages have at least one JSON-LD block")

    pages_with_blocks = [e for e in extractions if e["block_count"] >= 1]
    if not pages_with_blocks:
        mark("D8", "no_signal", "no page has a JSON-LD block; type quality is not scored (absence is D7)")
    else:
        union: list[str] = []
        for e in pages_with_blocks:
            for t in e["types"]:
                if t not in union:
                    union.append(t)
        generic = [t for t in union if classify_type(t) == "generic"]
        specific = [t for t in union if classify_type(t) == "domain-specific"]
        mismatches = [e for e in pages_with_blocks if e["purpose_mismatch"]]
        no_types = all(not e["types"] for e in pages_with_blocks)

        d8_reasons: list[str] = []
        if no_types or (union and not specific):
            d8_reasons.append(
                f"generic-only types site-wide: {union or '[]'} "
                f"(generic={generic or '[]'}; domain-specific=[])"
            )
        if mismatches:
            bits = "; ".join(
                f"{e['url']} types={e['types']} (no overlap with expected family for this path)"
                for e in mismatches
            )
            d8_reasons.append(f"purpose mismatch: {bits}")

        if d8_reasons:
            if mismatches:
                expected = expected_types_for_url(mismatches[0]["url"])
                d8_action = (
                    "Add a @type from the family this path implies"
                    + (f" ({', '.join(expected)})" if expected else "")
                    + ", rather than only Organization/WebSite chrome. "
                    "Listing/index paths do not need an article-family type."
                )
            else:
                d8_action = (
                    "Add a domain-specific @type that matches what the page is, "
                    "rather than only Organization/WebSite chrome."
                )
            findings.append(
                finding(
                    "D8",
                    "JSON-LD is generic-only or inconsistent with page purpose",
                    "medium",
                    " ".join(d8_reasons) + f". Per page: {per_page_counts}.",
                    d8_action,
                )
            )
            mark("D8", "fired", "; ".join(d8_reasons)[:240])
        else:
            mark("D8", "clear", f"domain-specific types present: {specific}; no path-family mismatch")

    if any(e["role"] == "internal" for e in extractions):
        coverage_pages = "homepage_and_internal"
    elif extractions:
        coverage_pages = "homepage_only"
    else:
        coverage_pages = "none"

    return _report(origin, findings, extractions, skipped, coverage_pages, home_quality, notes)


def _report(
    origin: str,
    findings: list[dict[str, Any]],
    extractions: list[dict[str, Any]],
    skipped: list[str],
    coverage_pages: str,
    home_quality: dict[str, Any] | None = None,
    notes: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "skill": "structured-data-audit",
        "site": urlparse(origin).netloc,
        "audited_at": utc_now(),
        "findings": findings,
        "page_extractions": extractions,
        "coverage": {
            "pages": coverage_pages,
            "skipped_checks": skipped,
            "check_notes": notes or {},
            "homepage_fetch_quality": home_quality,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run structured-data-audit (D7–D8).")
    parser.add_argument("target", help="Domain or URL to audit")
    parser.add_argument("--bundle", help="Path to a crawl-render site_bundle JSON")
    args = parser.parse_args(argv)

    bundle = None
    if args.bundle:
        with open(args.bundle, encoding="utf-8") as fh:
            loaded = json.load(fh)
        bundle = loaded.get("site_bundle", loaded)

    json.dump(run(args.target, bundle), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
