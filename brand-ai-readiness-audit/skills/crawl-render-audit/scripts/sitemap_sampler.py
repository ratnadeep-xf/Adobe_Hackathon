#!/usr/bin/env python3
"""Fetch and parse real sitemap URLs. Never guess paths (D4 / D5).

Only two discovery methods:
  1. Sitemap: URLs already declared in robots.txt
  2. The default /sitemap.xml path

Child sitemaps named inside a sitemapindex are declared, not guessed.
Same-origin only. Soft-404 HTML pages are not treated as sitemaps.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import sys
import xml.etree.ElementTree as ET
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

from http_client import fetch, hosts_equivalent, same_origin

NON_HTML_SUFFIXES = (
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".css",
    ".js",
    ".zip",
    ".gz",
    ".mp4",
    ".mp3",
    ".woff",
    ".woff2",
    ".ttf",
    ".ico",
)
MAX_CHILD_SITEMAPS = 8
MAX_SITEMAP_DEPTH = 2
MAX_SITEMAP_FETCHES = 20
MAX_COLLECTED_URLS = 200
DEFAULT_SAMPLE_SIZE = 6
MIN_PREFERRED_LOCS = 20

KEY_FIRST_SEGMENTS = {
    "about",
    "pricing",
    "price",
    "product",
    "products",
    "services",
    "service",
    "features",
    "solutions",
    "shop",
    "store",
}


def localname(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def looks_like_html(body: str) -> bool:
    snippet = (body or "")[:2000].lstrip().lower()
    return snippet.startswith("<!doctype html") or snippet.startswith("<html")


def parse_sitemap_xml(body: str) -> dict[str, Any]:
    """Return locs plus whether this is a urlset or sitemapindex."""
    result: dict[str, Any] = {
        "is_valid_sitemap": False,
        "kind": None,
        "locs": [],
        "child_sitemaps": [],
        "error": None,
    }
    text = (body or "").strip()
    if not text or looks_like_html(text):
        result["error"] = "html_or_empty"
        return result
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        result["error"] = f"xml_parse_error: {exc}"
        return result

    kind = localname(root.tag).lower()
    if kind not in {"urlset", "sitemapindex"}:
        for child in list(root):
            if localname(child.tag).lower() in {"urlset", "sitemapindex"}:
                root = child
                kind = localname(child.tag).lower()
                break
        else:
            result["error"] = f"unexpected_root:{kind}"
            return result

    result["kind"] = kind
    result["is_valid_sitemap"] = True

    if kind == "sitemapindex":
        for node in root:
            if localname(node.tag).lower() != "sitemap":
                continue
            for child in node:
                if localname(child.tag).lower() == "loc" and child.text:
                    result["child_sitemaps"].append(child.text.strip())
    else:
        for node in root:
            if localname(node.tag).lower() != "url":
                continue
            for child in node:
                if localname(child.tag).lower() == "loc" and child.text:
                    result["locs"].append(child.text.strip())
    return result


def maybe_gunzip(url: str, content: bytes, text: str | None) -> str:
    looks_gz = url.lower().endswith(".gz") or (content[:2] == b"\x1f\x8b")
    if not looks_gz:
        return text if text is not None else content.decode("utf-8", errors="replace")
    try:
        return gzip.GzipFile(fileobj=io.BytesIO(content)).read().decode("utf-8", errors="replace")
    except OSError:
        return text if text is not None else content.decode("utf-8", errors="replace")


def is_homepage(url: str, origin: str) -> bool:
    parsed = urlparse(url)
    origin_parsed = urlparse(origin)
    if not hosts_equivalent(parsed.netloc, origin_parsed.netloc):
        return False
    path = parsed.path or "/"
    return path in {"", "/"}


def is_htmlish_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return not any(path.endswith(suffix) for suffix in NON_HTML_SUFFIXES)


# Common ISO 639-1 codes + locale tags. Used to skip a leading locale
# segment (en, de-de, en-us). Not a brand/site list.
_LOCALE_LANGS = {
    "en", "de", "fr", "es", "it", "ja", "ko", "zh", "pt", "nl", "ru", "pl",
    "tr", "ar", "hi", "sv", "da", "fi", "no", "nb", "cs", "hu", "ro", "th",
    "vi", "id", "uk", "he", "el", "ms", "bn", "ta", "te", "fa", "sk", "bg",
}


def path_parts(url: str) -> list[str]:
    return [p for p in urlparse(url).path.split("/") if p]


def is_locale_segment(segment: str) -> bool:
    token = (segment or "").lower().replace("_", "-")
    if not token:
        return False
    lang = token.split("-", 1)[0]
    if lang not in _LOCALE_LANGS:
        return False
    return bool(re.fullmatch(r"[a-z]{2}(?:-[a-z]{2,4})?", token))


def locale_prefix(url: str) -> str:
    parts = path_parts(url)
    if parts and is_locale_segment(parts[0]):
        return parts[0].lower().replace("_", "-")
    return ""


def locale_hint(url: str) -> str:
    """Locale from a leading path segment, or from a filename/path token.

    Child sitemap URLs are often /sitemap-en-us.xml rather than /en-us/...
    """
    prefix = locale_prefix(url)
    if prefix:
        return prefix
    raw = urlparse(url).path.lower().replace("_", "-")
    tokens = [t for t in re.split(r"[^a-z]+", raw) if t]
    for i, tok in enumerate(tokens):
        pair = f"{tok}-{tokens[i + 1]}" if i + 1 < len(tokens) else ""
        if pair and is_locale_segment(pair):
            return pair
        if is_locale_segment(tok):
            return tok
    return ""


def content_segments(url: str) -> list[str]:
    parts = path_parts(url)
    if parts and is_locale_segment(parts[0]):
        return [p.lower() for p in parts[1:]]
    return [p.lower() for p in parts]


def first_segment(url: str) -> str:
    segs = content_segments(url)
    return segs[0] if segs else ""


def classify_path(url: str, origin: str) -> str:
    if is_homepage(url, origin) or not content_segments(url):
        return "key"
    return "key" if first_segment(url) in KEY_FIRST_SEGMENTS else "marginal"


def _locale_matches(loc: str, preferred_locale: str) -> bool:
    if not loc or not preferred_locale:
        return False
    pref = preferred_locale.lower().replace("_", "-")
    token = loc.lower().replace("_", "-")
    return token == pref or token.split("-")[0] == pref.split("-")[0]


def _locale_bucket(url: str, preferred_locale: str) -> int:
    """0 = preferred locale or unlocalized; 1 = other locale."""
    loc = locale_hint(url) or locale_prefix(url)
    if not loc or not preferred_locale:
        return 0
    return 0 if _locale_matches(loc, preferred_locale) else 1


def sample_urls(
    candidates: list[str],
    origin: str,
    limit: int = DEFAULT_SAMPLE_SIZE,
    preferred_locale: str = "",
) -> list[str]:
    """Diverse sample from real sitemap URLs only. Never adds guessed paths.

    When the sitemap mixes locale trees, prefer the homepage's locale over
    whichever locale appears first in the index.
    """
    internals: list[str] = []
    seen: set[str] = set()
    for url in candidates:
        if url in seen:
            continue
        if not same_origin(url, origin):
            continue
        if is_homepage(url, origin):
            continue
        if not content_segments(url) and locale_prefix(url):
            # Locale-only path is another homepage, not an internal page.
            continue
        if not is_htmlish_url(url):
            continue
        seen.add(url)
        internals.append(url)
        if len(internals) >= MAX_COLLECTED_URLS:
            break

    internals.sort(key=lambda u: _locale_bucket(u, preferred_locale))

    preferred = [u for u in internals if _locale_bucket(u, preferred_locale) == 0]
    # If the homepage locale is present at all, never fill the sample from
    # a different locale tree just because it appeared first in the index.
    pool = preferred if preferred else internals

    if len(pool) <= limit:
        return pool

    by_segment: dict[str, list[str]] = {}
    for url in pool:
        by_segment.setdefault(first_segment(url) or "_", []).append(url)

    picked: list[str] = []
    for segment, urls in by_segment.items():
        if segment in KEY_FIRST_SEGMENTS and urls:
            picked.append(urls[0])
        if len(picked) >= limit:
            return picked[:limit]

    while len(picked) < limit:
        progressed = False
        for urls in by_segment.values():
            for url in urls:
                if url not in picked:
                    picked.append(url)
                    progressed = True
                    break
            if len(picked) >= limit:
                break
        if not progressed:
            break
    return picked[:limit]


def evaluate_sitemap_body(url: str, source: str, body: str, status: int | None) -> dict[str, Any]:
    parsed = parse_sitemap_xml(body)
    return {
        "url": url,
        "source": source,
        "status": status,
        "is_valid_sitemap": bool(parsed["is_valid_sitemap"] and status == 200),
        "kind": parsed["kind"],
        "error": parsed["error"],
        "locs": parsed["locs"],
        "child_sitemaps": parsed["child_sitemaps"],
        "text": body,
    }


def collect_from_declared(
    origin: str,
    declared_sitemap_urls: list[str],
    fetcher: Callable[[str, str], dict[str, Any]] | None = None,
    prefetched: list[dict[str, Any]] | None = None,
    preferred_locale: str = "",
) -> dict[str, Any]:
    """Resolve declared + default sitemap locations into real internal URLs."""
    fetch_fn = fetcher or fetch
    records: list[dict[str, Any]] = []
    all_locs: list[str] = []
    prefetch_by_url = {item.get("url"): item for item in (prefetched or []) if item.get("url")}

    def load(url: str, source: str) -> dict[str, Any]:
        if url in prefetch_by_url and prefetch_by_url[url].get("text") is not None:
            item = prefetch_by_url[url]
            return evaluate_sitemap_body(
                url, source, item.get("text") or "", item.get("status")
            )
        result = fetch_fn(url, origin)
        content = result.get("content") or b""
        text = maybe_gunzip(url, content, result.get("text")) if content or result.get("text") else (result.get("text") or "")
        record = evaluate_sitemap_body(url, source, text, result.get("status"))
        if result.get("error") and not record["error"]:
            record["error"] = result["error"]
        return record

    candidates: list[tuple[str, str]] = []
    for raw in declared_sitemap_urls:
        absolute = urljoin(origin.rstrip("/") + "/", raw)
        if same_origin(absolute, origin):
            candidates.append((absolute, "robots.txt"))

    if not candidates:
        candidates.append((urljoin(origin.rstrip("/") + "/", "/sitemap.xml"), "default /sitemap.xml"))

    seen_urls: set[str] = set()
    fetch_count = 0
    saw_valid = False
    max_depth_reached = 0

    def _enough_locs() -> bool:
        if len(all_locs) >= MAX_COLLECTED_URLS:
            return True
        if not preferred_locale:
            return len(all_locs) >= MIN_PREFERRED_LOCS
        preferred_count = sum(1 for u in all_locs if _locale_bucket(u, preferred_locale) == 0)
        return preferred_count >= MIN_PREFERRED_LOCS

    def ingest(url: str, source: str, depth: int) -> None:
        nonlocal fetch_count, saw_valid, max_depth_reached
        if url in seen_urls or fetch_count >= MAX_SITEMAP_FETCHES:
            return
        if not same_origin(url, origin):
            return
        seen_urls.add(url)
        fetch_count += 1
        max_depth_reached = max(max_depth_reached, depth)
        record = load(url, source)
        records.append(record)
        if not record["is_valid_sitemap"]:
            return
        saw_valid = True
        locs = list(record.get("locs") or [])
        if preferred_locale and locs:
            matching = [u for u in locs if _locale_bucket(u, preferred_locale) == 0]
            locs = matching or locs
        all_locs.extend(locs)
        children = record.get("child_sitemaps") or []
        if not children or depth >= MAX_SITEMAP_DEPTH or _enough_locs():
            return
        for child in sorted(children, key=lambda u: _locale_bucket(u, preferred_locale)):
            if fetch_count >= MAX_SITEMAP_FETCHES or _enough_locs():
                break
            ingest(child, "sitemapindex child", depth + 1)

    for url, source in candidates:
        ingest(url, source, 0)
        if saw_valid:
            break

    if not saw_valid and candidates and candidates[0][1] == "robots.txt":
        default_url = urljoin(origin.rstrip("/") + "/", "/sitemap.xml")
        if default_url not in seen_urls:
            ingest(default_url, "default /sitemap.xml", 0)

    sampled = sample_urls(all_locs, origin, preferred_locale=preferred_locale)
    empty_after = bool(saw_valid and not all_locs)
    return {
        "checked": [
            {
                "url": r["url"],
                "source": r["source"],
                "status": r["status"],
                "is_valid_sitemap": r["is_valid_sitemap"],
                "kind": r.get("kind"),
                "error": r.get("error"),
            }
            for r in records
        ],
        "sitemaps": records,
        "all_locs_collected": all_locs[:MAX_COLLECTED_URLS],
        "sampled_internal_urls": sampled,
        "valid_sitemap_found": saw_valid,
        "page_url_count": len(all_locs),
        "sitemap_empty_after_recursion": empty_after,
        "recursion_depth_cap": MAX_SITEMAP_DEPTH,
        "recursion_depth_reached": max_depth_reached,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sample real URLs from a site sitemap.")
    parser.add_argument("origin", help="Site origin, e.g. https://example.com")
    parser.add_argument(
        "--sitemap-url",
        action="append",
        default=[],
        help="Declared Sitemap: URL (repeatable). If omitted, only /sitemap.xml is tried.",
    )
    parser.add_argument("--sitemap-file", help="Parse this local XML instead of fetching")
    args = parser.parse_args(argv)

    origin = args.origin if "://" in args.origin else f"https://{args.origin}"
    if args.sitemap_file:
        with open(args.sitemap_file, encoding="utf-8", errors="replace") as fh:
            body = fh.read()
        parsed = parse_sitemap_xml(body)
        sampled = sample_urls(parsed["locs"], origin)
        json.dump(
            {
                "is_valid_sitemap": parsed["is_valid_sitemap"],
                "kind": parsed["kind"],
                "error": parsed["error"],
                "sampled_internal_urls": sampled,
                "locs": parsed["locs"][:MAX_COLLECTED_URLS],
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 0

    result = collect_from_declared(origin, args.sitemap_url)
    # Drop raw sitemap bodies from CLI default output (they can be huge).
    slim = {
        "checked": result["checked"],
        "valid_sitemap_found": result["valid_sitemap_found"],
        "sampled_internal_urls": result["sampled_internal_urls"],
        "collected_url_count": len(result["all_locs_collected"]),
    }
    json.dump(slim, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
