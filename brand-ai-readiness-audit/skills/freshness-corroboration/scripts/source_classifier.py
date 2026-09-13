#!/usr/bin/env python3
"""Classify search-result domains into corroboration buckets (D11).

Tokens are *category patterns* that show up for almost any brand — generic
newspaper/review/wiki stems plus widely distributed host labels. This is
not a list of outlets from any one research pass.
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urlparse

# Encyclopedias, wikis, library catalogs — any-brand reference hits.
REFERENCE_TOKENS = (
    "wikipedia.", "wikidata.", "wikiwand.", "mediawiki.",
    "britannica.", "encyclopedia.", "infoplease.",
    "fandom.", "baike.", "worldcat.", "archive.org",
    "scholarpedia.", "citizendium.",
)

# Generic press stems first (news, times, tribune…) then major wire/
# national/international hosts that appear for almost any notable brand.
PRESS_TOKENS = (
    "news", "times", "tribune", "herald", "gazette", "observer",
    "chronicle", "telegraph", "journal", "daily", "post.com",
    "reuters.", "apnews.", "ap.org", "afp.", "bbc.", "npr.",
    "cnn.", "nbcnews.", "abcnews.", "cbsnews.", "foxnews.",
    "nytimes.", "wsj.", "ft.com", "economist.", "washingtonpost.",
    "usatoday.", "latimes.", "guardian.", "independent.",
    "bloomberg.", "forbes.", "fortune.", "cnbc.", "axios.",
    "politico.", "aljazeera.", "dw.com", "scmp.", "straitstimes.",
    "lemonde.", "elpais.", "spiegel.", "zeit.",
    "gizmodo.", "mashable.", "pcmag.", "tomshardware.", "wired.",
    "zdnet.", "engadget.", "venturebeat.",
)

# Consumer and B2B review / directory hosts used across industries.
REVIEW_TOKENS = (
    "yelp.", "trustpilot.", "tripadvisor.", "sitejabber.",
    "bbb.org", "yellowpages.", "angi.", "angieslist.",
    "checkatrade.", "homestars.", "reviews.io",
    "g2.com", "g2crowd.", "capterra.", "trustradius.",
    "softwareadvice.", "getapp.", "producthunt.",
    "glassdoor.", "crunchbase.", "clutch.co",
    "consumerreports.", "mouthshut.",
)

SOCIAL_TOKENS = (
    "facebook.", "instagram.", "twitter.", "x.com", "youtube.",
    "tiktok.", "linkedin.", "threads.net", "pinterest.",
    "reddit.", "bsky.app", "tumblr.",
)


def _host(value: str) -> str:
    if "/" in value or value.startswith("http"):
        netloc = urlparse(value).netloc.lower()
    else:
        netloc = value.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def classify_domain(domain: str, official_host: str = "") -> str:
    host = _host(domain)
    official = _host(official_host) if official_host else ""
    if official and host == official:
        return "official"
    if any(token in host for token in REFERENCE_TOKENS):
        return "reference"
    if any(token in host for token in REVIEW_TOKENS):
        return "review_directory"
    if any(token in host for token in SOCIAL_TOKENS):
        return "social"
    if any(token in host for token in PRESS_TOKENS):
        return "press"
    return "other"


def classify_domains(domains: list[str], official_host: str = "") -> dict:
    buckets: dict[str, list[str]] = {
        "official": [],
        "reference": [],
        "press": [],
        "review_directory": [],
        "social": [],
        "other": [],
    }
    for domain in domains:
        buckets[classify_domain(domain, official_host)].append(domain)
    represented = [name for name, items in buckets.items() if items]
    return {
        "buckets": buckets,
        "represented": represented,
        "diversity_count": len(represented),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify result domains.")
    parser.add_argument("domains", nargs="+")
    parser.add_argument("--official", default="")
    args = parser.parse_args(argv)
    json.dump(classify_domains(args.domains, args.official), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())