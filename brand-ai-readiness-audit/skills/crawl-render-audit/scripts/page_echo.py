#!/usr/bin/env python3
"""Detect sampled internals that are a homepage echo (suspected soft-404).

Sitemap sampling already avoids most guessed-path issues. This is a second,
cheaper layer: if a sampled URL's title and word count match the homepage,
it is not a distinct page for D5/D7/D8 scoring.
"""

from __future__ import annotations

import re
from typing import Any

from fetch_quality import visible_text

ECHO_FLAG = "identical_to_homepage_suspected_soft_404"


def html_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.I | re.S)
    if not match:
        return ""
    text = re.sub(r"<[^>]+>", "", match.group(1))
    return re.sub(r"\s+", " ", text).strip()


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title or "").strip().lower()


def word_count(html: str) -> int:
    words = [w for w in visible_text(html or "").split() if w]
    return len(words)


def is_homepage_echo(
    sample_html: str,
    home_title: str,
    home_words: int,
) -> bool:
    """True when title + word count are effectively identical to the homepage."""
    sample_title = normalize_title(html_title(sample_html))
    home_norm = normalize_title(home_title)
    if sample_title != home_norm:
        return False
    if not sample_title and not home_norm:
        # Both untitled — only treat as echo if word counts also match closely.
        pass
    sample_words = word_count(sample_html)
    if home_words == 0:
        return sample_words == 0
    delta = abs(sample_words - home_words)
    return delta <= max(15, int(0.05 * home_words))


def mark_homepage_echoes(
    homepage_html: str,
    sampled_pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flag sampled pages that echo the homepage. Returns coverage rows."""
    home_title = html_title(homepage_html or "")
    home_words = word_count(homepage_html or "")
    echoes: list[dict[str, Any]] = []
    for page in sampled_pages:
        html = page.get("html") or page.get("text") or ""
        if not html:
            continue
        if not is_homepage_echo(html, home_title, home_words):
            continue
        page[ECHO_FLAG] = True
        echoes.append(
            {
                "url": page.get("final_url") or page.get("url"),
                "title": html_title(html),
                "word_count": word_count(html),
                "flag": ECHO_FLAG,
            }
        )
    return echoes
