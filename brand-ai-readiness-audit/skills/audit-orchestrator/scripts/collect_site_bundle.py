#!/usr/bin/env python3
"""Build the shared site-fetch bundle using crawl-render-audit scripts."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SKILLS_DIR = Path(__file__).resolve().parents[2]
CRAWL_SCRIPTS = SKILLS_DIR / "crawl-render-audit" / "scripts"


def _load_crawl_modules():
    path = str(CRAWL_SCRIPTS)
    if path not in sys.path:
        sys.path.insert(0, path)
    # Isolate from other skills' identically named modules.
    for name in ("http_client", "robots_parser", "sitemap_sampler", "fetch_quality"):
        sys.modules.pop(name, None)
    import http_client
    import robots_parser
    import sitemap_sampler

    return http_client, robots_parser, sitemap_sampler


def collect_site_bundle(origin: str) -> dict[str, Any]:
    http_client, robots_parser, sitemap_sampler = _load_crawl_modules()
    origin = origin.rstrip("/")
    host = urlparse(origin).netloc

    homepage = http_client.fetch(origin + "/", origin, delay=False)
    homepage_out = {
        "url": homepage.get("url") or origin + "/",
        "final_url": homepage.get("final_url"),
        "status": homepage.get("status"),
        "headers": homepage.get("headers") or {},
        "html": homepage.get("text"),
        "error": homepage.get("error"),
    }
    sys.modules.pop("fetch_quality", None)
    from fetch_quality import classify_page

    quality = classify_page(homepage_out)
    preferred_locale = sitemap_sampler.locale_prefix(
        homepage_out.get("final_url") or homepage_out.get("url") or origin
    )

    robots = http_client.fetch(origin + "/robots.txt", origin)
    robots_text = robots.get("text") or ""
    parsed = robots_parser.parse_robots(robots_text) if robots.get("status") == 200 and robots_text.strip() else robots_parser.parse_robots("")
    root_block = bool(parsed.get("wildcard_root_disallow"))
    hard_block = homepage.get("status") in {401, 403} or (
        homepage.get("status") is None and homepage.get("blocked")
    )

    sitemaps_out: list[dict[str, Any]] = []
    sampled_pages: list[dict[str, Any]] = []
    sampled_urls: list[str] = []
    empty_after = False

    if not hard_block and not root_block:
        sitemap_result = sitemap_sampler.collect_from_declared(
            origin,
            parsed.get("sitemaps") or [],
            preferred_locale=preferred_locale,
        )
        empty_after = bool(sitemap_result.get("sitemap_empty_after_recursion"))
        for record in sitemap_result.get("sitemaps") or []:
            sitemaps_out.append(
                {
                    "url": record.get("url"),
                    "source": record.get("source"),
                    "status": record.get("status"),
                    "is_valid_sitemap": record.get("is_valid_sitemap"),
                    "text": record.get("text"),
                }
            )
        for url in sitemap_result.get("sampled_internal_urls") or []:
            path = urlparse(url).path or "/"
            if robots_text.strip() and not robots_parser.is_path_allowed(parsed, "*", path):
                continue
            result = http_client.fetch(url, origin)
            sampled_urls.append(url)
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

    return {
        "origin": origin,
        "host": host,
        "homepage": homepage_out,
        "robots_txt": {
            "url": robots.get("url") or origin + "/robots.txt",
            "status": robots.get("status"),
            "text": robots.get("text"),
            "error": robots.get("error"),
        },
        "sitemaps": sitemaps_out,
        "sitemap_empty_after_recursion": empty_after,
        "sampled_internal_urls": sampled_urls,
        "sampled_pages": sampled_pages,
    }
