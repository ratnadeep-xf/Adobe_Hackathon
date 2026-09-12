#!/usr/bin/env python3
"""Load homepage + sampled pages from a site bundle, or fetch them.

Never guesses internal paths. Sitemap locs only, same-origin, small cap.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urljoin, urlparse

from http_client import fetch, same_origin
from jsonld import first_segment, is_homepage_url, locale_prefix

MAX_INTERNAL = 6
MAX_CHILD_SITEMAPS = 3
NON_HTML_SUFFIXES = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".css", ".js", ".zip", ".mp4")


def localname(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _looks_like_html(body: str) -> bool:
    snippet = (body or "")[:2000].lstrip().lower()
    return snippet.startswith("<!doctype html") or snippet.startswith("<html")


def parse_sitemap_locs(body: str) -> tuple[list[str], list[str]]:
    locs: list[str] = []
    children: list[str] = []
    text = (body or "").strip()
    if not text or _looks_like_html(text):
        return locs, children
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return locs, children
    kind = localname(root.tag).lower()
    if kind not in {"urlset", "sitemapindex"}:
        return locs, children
    if kind == "sitemapindex":
        for node in root:
            if localname(node.tag).lower() != "sitemap":
                continue
            for child in node:
                if localname(child.tag).lower() == "loc" and child.text:
                    children.append(child.text.strip())
    else:
        for node in root:
            if localname(node.tag).lower() != "url":
                continue
            for child in node:
                if localname(child.tag).lower() == "loc" and child.text:
                    locs.append(child.text.strip())
    return locs, children


def _robots_sitemaps_and_root_block(text: str) -> tuple[list[str], bool]:
    sitemaps: list[str] = []
    star = False
    root_disallow = False
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            star = value.split()[0].lower() == "*" if value else False
        elif key == "disallow" and star and value in {"/", "/*"}:
            root_disallow = True
        elif key == "sitemap" and value:
            sitemaps.append(value)
    return sitemaps, root_disallow


def _locale_ok(url: str, preferred_locale: str) -> bool:
    if not preferred_locale:
        return True
    loc = locale_prefix(url)
    if not loc:
        return True
    pref = preferred_locale.lower().replace("_", "-")
    return loc == pref or loc.split("-")[0] == pref.split("-")[0]


def _sample(locs: list[str], origin: str, preferred_locale: str = "") -> list[str]:
    picked: list[str] = []
    seen: set[str] = set()
    for url in locs:
        if url in seen or not same_origin(url, origin) or is_homepage_url(url):
            continue
        path = urlparse(url).path.lower()
        if any(path.endswith(suffix) for suffix in NON_HTML_SUFFIXES):
            continue
        seen.add(url)
        picked.append(url)
    preferred = [u for u in picked if _locale_ok(u, preferred_locale)]
    pool = preferred if preferred else picked
    key = [u for u in pool if first_segment(u) in {
        "about", "pricing", "price", "product", "products", "services",
        "service", "features", "solutions", "shop", "store",
    }]
    rest = [u for u in pool if u not in key]
    ordered = key + rest
    return ordered[:MAX_INTERNAL]


def pages_from_bundle(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    home = bundle.get("homepage") or {}
    html = home.get("html") or home.get("text")
    if html and home.get("status") in {None, 200, 203}:
        page = {
            "url": home.get("final_url") or home.get("url") or "",
            "html": html,
            "status": home.get("status") or 200,
            "role": "homepage",
        }
        if home.get("fetch_quality"):
            page["fetch_quality"] = home["fetch_quality"]
        pages.append(page)
    for raw in bundle.get("sampled_pages") or []:
        html = raw.get("html") or raw.get("text")
        status = raw.get("status")
        if not html or status not in {200, 203, None}:
            continue
        url = raw.get("final_url") or raw.get("url") or ""
        if is_homepage_url(url):
            continue
        pages.append({"url": url, "html": html, "status": status or 200, "role": "internal"})
    return pages


def fetch_pages(origin: str) -> list[dict[str, Any]]:
    origin = origin.rstrip("/")
    homepage = fetch(origin + "/", origin, delay=False)
    pages: list[dict[str, Any]] = []
    html = homepage.get("text")
    if homepage.get("status") in {200, 203} and html:
        pages.append({
            "url": homepage.get("final_url") or origin + "/",
            "html": html,
            "status": homepage.get("status"),
            "role": "homepage",
        })

    robots = fetch(origin + "/robots.txt", origin)
    declared, root_block = _robots_sitemaps_and_root_block(robots.get("text") or "")
    if root_block:
        return pages

    preferred_locale = locale_prefix(pages[0]["url"]) if pages else ""

    sitemap_urls = [urljoin(origin + "/", u) for u in declared if same_origin(urljoin(origin + "/", u), origin)]
    if not sitemap_urls:
        sitemap_urls = [origin + "/sitemap.xml"]

    locs: list[str] = []
    children_budget = MAX_CHILD_SITEMAPS
    for sitemap_url in sitemap_urls:
        result = fetch(sitemap_url, origin)
        if result.get("status") != 200 or not result.get("text"):
            continue
        found, children = parse_sitemap_locs(result["text"])
        locs.extend(found)
        children_sorted = sorted(
            children,
            key=lambda u: 0 if _locale_ok(u, preferred_locale) else 1,
        )
        for child in children_sorted:
            if children_budget <= 0:
                break
            if not same_origin(child, origin):
                continue
            children_budget -= 1
            child_result = fetch(child, origin)
            if child_result.get("status") == 200 and child_result.get("text"):
                more, nested = parse_sitemap_locs(child_result["text"])
                if preferred_locale:
                    matching = [u for u in more if _locale_ok(u, preferred_locale)]
                    locs.extend(matching or more)
                else:
                    locs.extend(more)
                # One extra index hop (depth 2): nested sitemapindex → urlset.
                if not more and nested:
                    for grandchild in nested[:MAX_CHILD_SITEMAPS]:
                        if not same_origin(grandchild, origin):
                            continue
                        grand = fetch(grandchild, origin)
                        if grand.get("status") == 200 and grand.get("text"):
                            grand_locs, _ = parse_sitemap_locs(grand["text"])
                            locs.extend(grand_locs)
                            if locs:
                                break
        if locs:
            break

    if not locs and sitemap_urls[0] != origin + "/sitemap.xml":
        result = fetch(origin + "/sitemap.xml", origin)
        if result.get("status") == 200 and result.get("text"):
            found, _ = parse_sitemap_locs(result["text"])
            locs.extend(found)

    for url in _sample(locs, origin, preferred_locale):
        result = fetch(url, origin)
        if result.get("status") in {200, 203} and result.get("text"):
            pages.append({
                "url": result.get("final_url") or url,
                "html": result.get("text"),
                "status": result.get("status"),
                "role": "internal",
            })
    return pages
