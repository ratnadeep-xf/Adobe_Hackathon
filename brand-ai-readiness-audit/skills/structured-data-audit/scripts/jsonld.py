#!/usr/bin/env python3
"""Extract JSON-LD blocks and classify @type as generic vs domain-specific.

Read-only. No network — pass HTML in. Used by D7 (block counts) and D8
(type quality).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from bs4 import BeautifulSoup

GENERIC_TYPES = {
    "organization",
    "corporation",
    "website",
    "webpage",
    "collectionpage",
    "searchaction",
    "breadcrumblist",
    "listitem",
    "itemlist",
    "imageobject",
    "entrypoint",
    "sitenavigationelement",
    "wpheader",
    "wpfooter",
    "wpsidebar",
    "readaction",
    "viewaction",
    "thing",
    "brand",
    "contactpoint",
    "postaladdress",
    "geocoordinates",
    "propertyvalue",
    "quantitativevalue",
    "openinghoursspecification",
}

EXPECTED_BY_SEGMENT = {
    "product": {"Product", "Offer", "AggregateOffer", "Service"},
    "products": {"Product", "Offer", "AggregateOffer", "Service"},
    "shop": {"Product", "Offer", "AggregateOffer", "Service"},
    "store": {"Product", "Offer", "AggregateOffer", "Service"},
    "pricing": {"Product", "Offer", "AggregateOffer", "Service"},
    "price": {"Product", "Offer", "AggregateOffer", "Service"},
}

# Article-family types apply to an individual post, not the listing index.
ARTICLE_FAMILY = {"Article", "NewsArticle", "BlogPosting"}
LISTING_SEGMENTS = {
    "blog", "news", "article", "articles", "press", "stories", "events", "event",
    "jobs", "careers", "job",
}
ARTICLE_SEGMENTS = {"blog", "news", "article", "articles", "press", "stories"}
EVENT_SEGMENTS = {"events", "event"}
JOB_SEGMENTS = {"jobs", "careers", "job"}

_LOCALE_LANGS = {
    "en", "de", "fr", "es", "it", "ja", "ko", "zh", "pt", "nl", "ru", "pl",
    "tr", "ar", "hi", "sv", "da", "fi", "no", "nb", "cs", "hu", "ro", "th",
    "vi", "id", "uk", "he", "el", "ms",
}

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


def normalize_type(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    token = value.strip()
    if not token:
        return None
    if "/" in token:
        token = token.rstrip("/").rsplit("/", 1)[-1]
    if token.startswith("schema:"):
        token = token.split(":", 1)[1]
    return token


def classify_type(name: str) -> str:
    return "generic" if name.lower() in GENERIC_TYPES else "domain-specific"


def _strip_json_noise(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r"^\s*<!--", "", text)
    text = re.sub(r"-->\s*$", "", text)
    return text.strip()


def _collect_primary_types(node: Any, out: list[str]) -> None:
    if isinstance(node, list):
        for item in node:
            _collect_primary_types(item, out)
        return
    if not isinstance(node, dict):
        return
    raw_type = node.get("@type")
    if isinstance(raw_type, list):
        for item in raw_type:
            normalized = normalize_type(item)
            if normalized:
                out.append(normalized)
    else:
        normalized = normalize_type(raw_type)
        if normalized:
            out.append(normalized)
    if "@graph" in node:
        graph = node["@graph"]
        if isinstance(graph, list):
            for item in graph:
                if isinstance(item, dict):
                    _collect_primary_types({k: item[k] for k in item if k != "@graph"}, out)
        elif isinstance(graph, dict):
            _collect_primary_types(graph, out)
    if "mainEntity" in node:
        _collect_primary_types(node["mainEntity"], out)


def extract_jsonld(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html or "", "html.parser")
    scripts = soup.find_all(
        "script",
        attrs={"type": lambda value: bool(value and "ld+json" in value.lower())},
    )
    types: list[str] = []
    parse_errors: list[str] = []
    blocks: list[dict[str, Any]] = []

    for index, tag in enumerate(scripts):
        raw = tag.string if tag.string is not None else tag.get_text()
        raw = _strip_json_noise(raw or "")
        block_types: list[str] = []
        parsed = False
        try:
            payload = json.loads(raw) if raw else None
            if payload is None:
                parse_errors.append(f"block_{index}: empty")
            else:
                _collect_primary_types(payload, block_types)
                parsed = True
        except json.JSONDecodeError as exc:
            parse_errors.append(f"block_{index}: {exc.msg}")
        types.extend(block_types)
        blocks.append({"index": index, "types": block_types, "parsed": parsed})

    unique = list(dict.fromkeys(types))
    generic = [t for t in unique if classify_type(t) == "generic"]
    specific = [t for t in unique if classify_type(t) == "domain-specific"]
    return {
        "block_count": len(scripts),
        "parse_errors": parse_errors,
        "types": unique,
        "types_generic": generic,
        "types_specific": specific,
        "blocks": blocks,
    }


def _path_parts(url: str) -> list[str]:
    from urllib.parse import urlparse

    return [p for p in urlparse(url).path.split("/") if p]


def _is_locale(segment: str) -> bool:
    token = (segment or "").lower().replace("_", "-")
    lang = token.split("-", 1)[0]
    return lang in _LOCALE_LANGS and bool(re.fullmatch(r"[a-z]{2}(?:-[a-z]{2,4})?", token))


def content_segments(url: str) -> list[str]:
    parts = [p.lower() for p in _path_parts(url)]
    if parts and _is_locale(parts[0]):
        return parts[1:]
    return parts


def first_segment(url: str) -> str:
    segs = content_segments(url)
    return segs[0] if segs else ""


def is_homepage_url(url: str) -> bool:
    from urllib.parse import urlparse

    path = urlparse(url).path or "/"
    if path in {"", "/"}:
        return True
    return not content_segments(url)


def is_listing_url(url: str) -> bool:
    segs = content_segments(url)
    return len(segs) == 1 and segs[0] in LISTING_SEGMENTS


def path_class(url: str) -> str:
    if is_homepage_url(url):
        return "key"
    return "key" if first_segment(url) in KEY_FIRST_SEGMENTS else "marginal"


def expected_types_for_url(url: str) -> list[str]:
    if is_homepage_url(url) or is_listing_url(url):
        return []
    segs = content_segments(url)
    if not segs:
        return []
    head = segs[0]
    if head in EXPECTED_BY_SEGMENT:
        return sorted(EXPECTED_BY_SEGMENT[head])
    # Individual article/event/job URLs have a slug after the listing segment.
    if len(segs) >= 2 and head in ARTICLE_SEGMENTS:
        return sorted(ARTICLE_FAMILY)
    if len(segs) >= 2 and head in EVENT_SEGMENTS:
        return ["Event"]
    if len(segs) >= 2 and head in JOB_SEGMENTS:
        return ["JobPosting"]
    return []


def locale_prefix(url: str) -> str:
    parts = [p.lower() for p in _path_parts(url)]
    if parts and _is_locale(parts[0]):
        return parts[0].replace("_", "-")
    return ""


def suggested_type_examples(url: str, text: str = "") -> list[str]:
    """Page-dependent @type examples — never a fixed commercial list."""
    expected = expected_types_for_url(url)
    if expected:
        return expected[:4]
    hay = f"{url} {text or ''}"
    hints: list[tuple[re.Pattern[str], list[str]]] = [
        (re.compile(r"\b(?:software|saas|api|platform|application)\b", re.I), ["SoftwareApplication"]),
        (re.compile(r"\b(?:course|learn|learning|education|classroom|students)\b", re.I), ["EducationalOrganization", "Course"]),
        (re.compile(r"\b(?:nonprofit|non-profit|charity|donate)\b", re.I), ["NGO", "EducationalOrganization"]),
        (re.compile(r"\b(?:restaurant|menu|cafe|café)\b", re.I), ["Restaurant"]),
        (re.compile(r"\b(?:hotel|lodging|resort)\b", re.I), ["LodgingBusiness"]),
        (re.compile(r"\b(?:shop|store|buy|product)\b", re.I), ["Product", "Offer"]),
        (re.compile(r"\b(?:article|news|blog)\b", re.I), ["Article"]),
        (re.compile(r"\b(?:event|conference|webinar)\b", re.I), ["Event"]),
    ]
    for pattern, types in hints:
        if pattern.search(hay):
            return types
    return []


def purpose_mismatch(url: str, types: list[str]) -> bool:
    expected = {t.lower() for t in expected_types_for_url(url)}
    if not expected or not types:
        return False
    found = {t.lower() for t in types}
    return expected.isdisjoint(found)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract JSON-LD types from HTML.")
    parser.add_argument("file", nargs="?", help="HTML file (default: stdin)")
    parser.add_argument("--url", default="", help="Optional page URL for path-class / expected types")
    args = parser.parse_args(argv)

    if args.file:
        with open(args.file, encoding="utf-8", errors="replace") as fh:
            html = fh.read()
    else:
        html = sys.stdin.read()

    result = extract_jsonld(html)
    if args.url:
        result["url"] = args.url
        result["path_class"] = path_class(args.url)
        result["expected_types"] = expected_types_for_url(args.url)
        result["purpose_mismatch"] = purpose_mismatch(args.url, result["types"])
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
