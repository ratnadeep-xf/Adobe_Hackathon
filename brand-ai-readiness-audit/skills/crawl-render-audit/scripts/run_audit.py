#!/usr/bin/env python3
"""Standalone D1–D6 crawl/render audit.

Usage:
  python scripts/run_audit.py https://example.com
  python scripts/run_audit.py https://example.com --bundle site_bundle.json

Read-only. Fetches only the audited origin. Accepts a pre-fetched site
bundle so a later orchestrator can reuse network work.
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

from fetch_quality import D3_SPECS, classify_page, d3_subcategory  # noqa: E402
from http_client import chain_has_auth_block, fetch  # noqa: E402
from js_shell import score_html  # noqa: E402
from page_echo import ECHO_FLAG, mark_homepage_echoes  # noqa: E402
from robots_parser import d2_blocked, is_path_allowed, parse_robots  # noqa: E402
from sitemap_sampler import classify_path, collect_from_declared, locale_prefix  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def add_scheme(raw: str, scheme: str) -> str:
    host_path = raw.strip()
    parsed = urlparse(f"{scheme}://{host_path}")
    return f"{parsed.scheme}://{parsed.netloc}"


def origin_from_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def site_host(origin: str) -> str:
    return urlparse(origin).netloc


def finding(
    check_id: str,
    title: str,
    severity: str,
    evidence: str,
    action: str,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "title": title,
        "severity": severity,
        "evidence": evidence,
        "suggested_action": {"summary": action, "priority": severity},
    }


def empty_fetch(url: str) -> dict[str, Any]:
    return {
        "url": url,
        "final_url": None,
        "status": None,
        "headers": {},
        "text": None,
        "html": None,
        "error": None,
        "history_statuses": [],
        "blocked": False,
    }


def homepage_from_bundle(bundle: dict[str, Any], url: str) -> dict[str, Any]:
    raw = bundle.get("homepage") or {}
    page = empty_fetch(raw.get("url") or url)
    page.update({k: raw[k] for k in raw})
    if page.get("html") and not page.get("text"):
        page["text"] = page["html"]
    if page.get("text") and not page.get("html"):
        page["html"] = page["text"]
    return page


def robots_from_bundle(bundle: dict[str, Any], url: str) -> dict[str, Any]:
    raw = bundle.get("robots_txt") or {}
    page = empty_fetch(raw.get("url") or url)
    page.update({k: raw[k] for k in raw})
    return page


def resolve_origin(raw: str, bundle: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
    if bundle and bundle.get("origin"):
        origin = bundle["origin"].rstrip("/")
        return origin, fetch(origin + "/", origin, delay=False)

    value = raw.strip()
    if value.startswith("http://") or value.startswith("https://"):
        origin = origin_from_url(value)
        return origin, fetch(origin.rstrip("/") + "/", origin, delay=False)

    https_origin = add_scheme(value, "https")
    homepage = fetch(https_origin.rstrip("/") + "/", https_origin, delay=False)
    if homepage.get("status") is None and homepage.get("error"):
        http_origin = add_scheme(value, "http")
        http_home = fetch(http_origin.rstrip("/") + "/", http_origin, delay=False)
        if http_home.get("status") is not None or not http_home.get("error"):
            return http_origin, http_home
        if http_home.get("error") and not homepage.get("error"):
            return http_origin, http_home
    return https_origin, homepage


def page_path(url: str) -> str:
    path = urlparse(url).path or "/"
    return path if path.startswith("/") else "/" + path


def score_page(url: str, origin: str, html: str, status: int | None) -> dict[str, Any]:
    metrics = score_html(html or "")
    metrics["url"] = url
    metrics["status"] = status
    metrics["path_class"] = classify_path(url, origin)
    return metrics


def run(target: str, bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    notes: dict[str, dict[str, str]] = {}

    def mark(check_id: str, status: str, reason: str) -> None:
        notes[check_id] = {"status": status, "reason": reason}
        if status == "skipped" and not any(row.get("id") == check_id for row in skipped):
            skipped.append({"id": check_id, "reason": reason})

    if bundle and bundle.get("homepage"):
        origin = (bundle.get("origin") or origin_from_url(bundle["homepage"].get("url") or target)).rstrip("/")
        homepage = homepage_from_bundle(bundle, origin + "/")
    else:
        origin, homepage = resolve_origin(target, bundle)
        homepage["html"] = homepage.get("text")

    robots_url = origin.rstrip("/") + "/robots.txt"
    if bundle and bundle.get("robots_txt") and (
        bundle["robots_txt"].get("text") is not None or bundle["robots_txt"].get("status")
    ):
        robots = robots_from_bundle(bundle, robots_url)
    else:
        robots = fetch(robots_url, origin)
    robots_text = robots.get("text") or ""
    parsed_robots = parse_robots(robots_text) if robots.get("status") == 200 and robots_text.strip() else parse_robots("")
    d2 = d2_blocked(parsed_robots)

    home_quality = homepage.get("fetch_quality") or classify_page(homepage)
    homepage["fetch_quality"] = home_quality

    d3_kind = d3_subcategory(homepage, home_quality)
    d3_hit = d3_kind is not None
    if d3_hit:
        status = homepage.get("status")
        err = homepage.get("error")
        header_bits = homepage.get("headers") or {}
        spec = D3_SPECS[d3_kind]
        evidence = (
            f"D3 sub-category={d3_kind}. Homepage {homepage.get('url') or origin + '/'} "
            f"returned status={status if status is not None else 'null'}"
        )
        if err:
            evidence += f", error={err}"
        if homepage.get("retried_429"):
            evidence += ", retried once after Retry-After/backoff"
        if header_bits:
            evidence += f", headers={header_bits}"
        evidence += ". This is an infrastructure-level block, recorded before robots.txt checks."
        findings.append(
            finding(
                "D3",
                spec["title"],
                spec["severity"],
                evidence,
                spec["action"],
            )
        )
        mark("D3", "fired", f"{d3_kind}: {evidence[:140]}")
    elif not home_quality.get("usable"):
        findings.append(
            finding(
                "FQ",
                "Homepage fetch did not return usable page content",
                "medium",
                (
                    f"Fetch classified as {home_quality.get('class')} "
                    f"({home_quality.get('reason')}); status={homepage.get('status')}; "
                    f"preview={home_quality.get('preview')!r}. "
                    "On-page identity and engagement checks were not run against this body."
                ),
                "This fetch received an error stub or bot-check page, not the real homepage. "
                "Retry from a normal browser session or allow simple HTTP clients; do not "
                "treat this as a fact about the brand's content or identity.",
            )
        )
        mark("FQ", "fired", f"{home_quality.get('class')}: {home_quality.get('reason')}")
        mark("D3", "clear", "homepage was reachable; fetch-quality is not a hard block")
    else:
        mark("D3", "clear", "homepage was reachable")
        mark("FQ", "clear", "homepage fetch classified as usable content")

    d1_hit = bool(parsed_robots.get("wildcard_root_disallow"))
    if d1_hit:
        quoted = "; ".join(parsed_robots.get("wildcard_quoted_rules") or ["Disallow: /"])
        findings.append(
            finding(
                "D1",
                "Full-site crawler block in robots.txt",
                "critical",
                f"{robots_url} User-agent: * includes {quoted}. Every crawler is shut out at the root.",
                "Remove or narrow the User-agent: * Disallow: / rule so public pages can be crawled.",
            )
        )
        mark("D1", "fired", quoted)
    else:
        mark("D1", "clear", "User-agent: * does not Disallow: /")

    if not d1_hit:
        if d2["blocked_live_agents"] or d2["blocked_training_crawlers"]:
            live = [a["user_agent"] for a in d2["blocked_live_agents"]]
            training = [a["user_agent"] for a in d2["blocked_training_crawlers"]]
            severity = "high" if live else "medium"
            evidence = (
                f"Named AI user-agents root-disallowed in {robots_url}. "
                f"live-agent={live or '[]'}; training-crawler={training or '[]'}."
            )
            if live and training:
                action = (
                    "Allow the blocked live-agent user-agents if real-time citation matters. "
                    "Training-crawler blocks can remain if that is an intentional opt-out."
                )
            elif live:
                action = (
                    "Allow the blocked live-agent user-agents if real-time citation or "
                    "browsing access matters."
                )
            else:
                action = (
                    "Training-crawler user-agents are root-disallowed. If that is an "
                    "intentional training opt-out, no change is required for live citation."
                )
            findings.append(
                finding(
                    "D2",
                    "Named AI-crawler block in robots.txt",
                    severity,
                    evidence,
                    action,
                )
            )
            mark("D2", "fired", evidence)
        else:
            mark("D2", "clear", "no catalogued live-agent or training-crawler is root-disallowed")
    else:
        mark("D2", "skipped", "D1 already covers a full-site * root disallow")

    allow_further_fetches = (not d3_hit) and (not d1_hit)
    have_prefetched_sitemaps = bool(bundle and bundle.get("sitemaps"))

    sitemap_result: dict[str, Any]
    def skipped_fetch(url: str, origin: str) -> dict[str, Any]:
        return {
            "url": url,
            "final_url": None,
            "status": None,
            "headers": {},
            "text": None,
            "content": b"",
            "error": "fetch skipped (robots.txt or homepage hard block)",
            "history_statuses": [],
            "blocked": False,
        }

    if have_prefetched_sitemaps:
        sitemap_result = collect_from_declared(
            origin,
            parsed_robots.get("sitemaps") or [],
            fetcher=None if allow_further_fetches else skipped_fetch,
            prefetched=bundle.get("sitemaps"),
            preferred_locale=locale_prefix(homepage.get("final_url") or homepage.get("url") or origin),
        )
    elif allow_further_fetches:
        sitemap_result = collect_from_declared(
            origin,
            parsed_robots.get("sitemaps") or [],
            preferred_locale=locale_prefix(homepage.get("final_url") or homepage.get("url") or origin),
        )
    else:
        sitemap_result = {
            "checked": [],
            "sitemaps": [],
            "all_locs_collected": [],
            "sampled_internal_urls": [],
            "valid_sitemap_found": False,
            "page_url_count": 0,
            "sitemap_empty_after_recursion": False,
        }

    if have_prefetched_sitemaps or allow_further_fetches:
        if not sitemap_result["valid_sitemap_found"]:
            checked = sitemap_result.get("checked") or []
            if not checked:
                evidence = (
                    "No valid sitemap document was retrieved. "
                    "No sitemap locations could be requested from this fetch."
                )
            else:
                bits = [
                    f"{c['url']} (source={c['source']}, status={c.get('status')}, valid={c.get('is_valid_sitemap')})"
                    for c in checked
                ]
                evidence = "No valid sitemap document was retrieved. Checked: " + "; ".join(bits)
            htmlish = any(
                c.get("status") == 200 and not c.get("is_valid_sitemap") for c in checked
            )
            if htmlish:
                action = (
                    "A sitemap URL returned HTTP 200 but the body was not sitemap XML "
                    "(HTML or an interstitial). From this fetch we cannot tell whether a "
                    "sitemap exists — confirm the declared Sitemap: URLs return XML, or "
                    "retry from a less-blocked client."
                )
            else:
                action = (
                    "No sitemap document was reachable at the declared or default locations "
                    "from this fetch. If one is published, declare it with a Sitemap: line "
                    "in robots.txt and ensure that URL returns XML."
                )
            findings.append(
                finding(
                    "D4",
                    "Sitemap missing or unreachable",
                    "medium",
                    evidence,
                    action,
                )
            )
            mark("D4", "fired", evidence[:240])
        elif sitemap_result.get("sitemap_empty_after_recursion"):
            checked = sitemap_result.get("checked") or []
            bits = [
                f"{c['url']} (kind={c.get('kind')}, source={c['source']}, valid={c.get('is_valid_sitemap')})"
                for c in checked
            ]
            depth = sitemap_result.get("recursion_depth_cap", 2)
            evidence = (
                f"Valid sitemap XML was retrieved but no page <loc> URLs were reachable "
                f"within recursion depth {depth} (nested sitemapindex only). Checked: "
                + "; ".join(bits)
            )
            findings.append(
                finding(
                    "D4",
                    "Sitemap present but no page URLs reachable",
                    "low",
                    evidence,
                    "Publish or declare a urlset (page URLs), not only nested sitemapindex "
                    "documents, or make those child urlsets reachable within two index hops.",
                )
            )
            mark("D4", "fired", f"valid sitemap XML but 0 page URLs after depth {depth}")
        else:
            mark("D4", "clear", "a valid sitemap document was retrieved")
    else:
        mark("D4", "skipped", "sitemap not requested (robots.txt or homepage hard block)")

    empty_after_recursion = bool(sitemap_result.get("sitemap_empty_after_recursion"))
    empty_after_reason = (
        "sitemap present but no page URLs reachable within recursion depth"
    )

    sampled_urls: list[str]
    sampled_pages: list[dict[str, Any]] = []
    if bundle and bundle.get("sampled_pages"):
        sampled_urls = list(bundle.get("sampled_internal_urls") or [p.get("url") for p in bundle["sampled_pages"]])
        for raw in bundle["sampled_pages"]:
            page = {
                "url": raw.get("url"),
                "final_url": raw.get("final_url"),
                "status": raw.get("status"),
                "headers": raw.get("headers") or {},
                "html": raw.get("html") or raw.get("text"),
                "error": raw.get("error"),
                "history_statuses": raw.get("history_statuses") or [],
            }
            if raw.get(ECHO_FLAG):
                page[ECHO_FLAG] = True
            sampled_pages.append(page)
    elif allow_further_fetches:
        sampled_urls = list(sitemap_result.get("sampled_internal_urls") or [])
        for url in sampled_urls:
            path = page_path(url)
            if robots_text.strip() and not is_path_allowed(parsed_robots, "*", path):
                continue
            result = fetch(url, origin)
            sampled_pages.append(
                {
                    "url": url,
                    "final_url": result.get("final_url"),
                    "status": result.get("status"),
                    "headers": result.get("headers") or {},
                    "html": result.get("text"),
                    "error": result.get("error"),
                    "history_statuses": result.get("history_statuses") or [],
                }
            )
    else:
        sampled_urls = []

    homepage_html = homepage.get("html") or homepage.get("text") or ""
    echo_samples = mark_homepage_echoes(homepage_html, sampled_pages)

    page_scores: list[dict[str, Any]] = []
    homepage_scorable = bool(home_quality.get("usable")) and homepage.get("status") in {200, 203}
    if empty_after_recursion:
        mark("D5", "skipped", empty_after_reason)
        homepage_scorable = False
    if homepage_scorable and not d3_hit:
        page_scores.append(
            score_page(
                homepage.get("final_url") or homepage.get("url") or origin + "/",
                origin,
                homepage.get("html") or homepage.get("text") or "",
                homepage.get("status"),
            )
        )

    gated: list[dict[str, Any]] = []
    for page in sampled_pages:
        auth, status = chain_has_auth_block(page)
        if auth and not (d3_hit and page.get("url") == homepage.get("url")):
            gated.append(
                {
                    "url": page.get("url"),
                    "status": status,
                    "final_url": page.get("final_url"),
                }
            )
            continue
        if page.get(ECHO_FLAG):
            continue
        html = page.get("html") or ""
        page_quality = classify_page(page)
        if page.get("status") in {200, 203} and html and page_quality.get("usable"):
            page["js_shell"] = score_page(page.get("final_url") or page["url"], origin, html, page.get("status"))
            page_scores.append(page["js_shell"])

    flagged = [s for s in page_scores if s.get("flagged")]
    if flagged:
        key_hit = any(s.get("path_class") == "key" for s in flagged)
        severity = "high" if key_hit else "low"
        details = "; ".join(
            f"{s['url']} words={s['word_count']} ratio={s['text_to_html_ratio']} class={s['path_class']}"
            for s in flagged
        )
        findings.append(
            finding(
                "D5",
                "JS-shell content gap on sampled pages",
                severity,
                f"Flagged {len(flagged)}/{len(page_scores)} scored pages (absolute word count < 20, or < 200 words with ratio < 0.04). {details}",
                "Server-render primary content (or provide an equivalent in the initial HTML) so non-JS crawlers can read the page.",
            )
        )
        mark("D5", "fired", details[:240])
    elif empty_after_recursion:
        pass
    elif not page_scores:
        mark("D5", "skipped", "no HTML page could be scored")
    else:
        mark("D5", "clear", f"{len(page_scores)} page(s) scored; none flagged as a JS-shell")
    if echo_samples:
        extra = f"excluded {len(echo_samples)} homepage-echo sample(s) from D5 scoring"
        if "D5" in notes:
            notes["D5"]["reason"] = (notes["D5"].get("reason") or "") + f"; {extra}"
        else:
            mark("D5", "clear", extra)

    if gated:
        bits = ", ".join(f"{g['url']} status={g['status']}" for g in gated)
        findings.append(
            finding(
                "D6",
                "Auth-gated internal pages",
                "medium",
                f"{len(gated)} sampled internal URL(s) returned 401/403 for an unauthenticated visitor: {bits}",
                "If those URLs are meant to be discoverable, offer a public unauthenticated representation. Do not require login to read them.",
            )
        )
        mark("D6", "fired", bits[:240])
    elif empty_after_recursion:
        mark("D6", "skipped", empty_after_reason)
    elif not sampled_pages:
        mark("D6", "skipped", "no internal URLs were sampled")
    else:
        mark("D6", "clear", f"{len(sampled_pages)} sampled internal page(s); none returned 401/403")

    if any(not is_homepage_url(s["url"], origin) for s in page_scores):
        d5_coverage = "homepage_and_internal"
    elif page_scores:
        d5_coverage = "homepage_only"
    else:
        d5_coverage = "none"

    order = {"D3": 0, "FQ": 1, "D1": 2, "D2": 3, "D4": 4, "D5": 5, "D6": 6}
    findings.sort(key=lambda f: order.get(f["id"], 99))

    sitemap_bundle = []
    for record in sitemap_result.get("sitemaps") or []:
        sitemap_bundle.append(
            {
                "url": record.get("url"),
                "source": record.get("source"),
                "status": record.get("status"),
                "is_valid_sitemap": record.get("is_valid_sitemap"),
                "text": record.get("text"),
            }
        )

    return {
        "skill": "crawl-render-audit",
        "site": site_host(origin),
        "audited_at": utc_now(),
        "findings": findings,
        "site_bundle": {
            "origin": origin,
            "host": site_host(origin),
            "homepage": {
                "url": homepage.get("url") or origin + "/",
                "final_url": homepage.get("final_url"),
                "status": homepage.get("status"),
                "headers": homepage.get("headers") or {},
                "html": homepage.get("html") or homepage.get("text"),
                "error": homepage.get("error"),
                "retried_429": bool(homepage.get("retried_429")),
                "fetch_quality": home_quality,
            },
            "robots_txt": {
                "url": robots.get("url") or robots_url,
                "status": robots.get("status"),
                "text": robots.get("text"),
                "error": robots.get("error"),
            },
            "sitemaps": sitemap_bundle,
            "sitemap_empty_after_recursion": empty_after_recursion,
            "sampled_internal_urls": [p.get("url") for p in sampled_pages if p.get("url")],
            "sampled_pages": [
                {
                    "url": p.get("url"),
                    "final_url": p.get("final_url"),
                    "status": p.get("status"),
                    "headers": p.get("headers") or {},
                    "html": p.get("html"),
                    "error": p.get("error"),
                    "history_statuses": p.get("history_statuses") or [],
                    **({ECHO_FLAG: True} if p.get(ECHO_FLAG) else {}),
                }
                for p in sampled_pages
            ],
        },
        "coverage": {
            "d5": d5_coverage,
            "skipped_checks": skipped,
            "check_notes": notes,
            "homepage_fetch_quality": home_quality,
            "d3_subcategory": d3_kind,
            "homepage_echo_samples": echo_samples,
            "preferred_locale": locale_prefix(homepage.get("final_url") or homepage.get("url") or ""),
            "sampled_internal_urls": [p.get("url") for p in sampled_pages if p.get("url")],
            "page_scores": page_scores,
            "robots_parse": {
                "wildcard_root_disallow": parsed_robots.get("wildcard_root_disallow"),
                "sitemaps_declared": parsed_robots.get("sitemaps"),
                "d2": d2,
            },
        },
    }


def is_homepage_url(url: str, origin: str) -> bool:
    from sitemap_sampler import content_segments, is_homepage

    if is_homepage(url, origin):
        return True
    return not content_segments(url)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run crawl-render-audit (D1–D6).")
    parser.add_argument("target", help="Domain or URL to audit")
    parser.add_argument("--bundle", help="Path to a pre-fetched site_bundle JSON")
    args = parser.parse_args(argv)

    bundle = None
    if args.bundle:
        with open(args.bundle, encoding="utf-8") as fh:
            loaded = json.load(fh)
        bundle = loaded.get("site_bundle", loaded)

    report = run(args.target, bundle)
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
