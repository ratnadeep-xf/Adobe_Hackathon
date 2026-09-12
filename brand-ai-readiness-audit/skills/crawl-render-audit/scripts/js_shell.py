#!/usr/bin/env python3
"""JS-shell heuristic: visible-text length + text-to-HTML ratio (D5).

A low ratio on a long page is normal (bulky CSS/JS) and must not flag.
A short absolute word count flags regardless of ratio.
Read-only. No network — pass HTML in.
"""

from __future__ import annotations

import argparse
import json
import sys

from bs4 import BeautifulSoup

# Principled starting points — tune later, do not fit to a specific site.
# Absolute cutoff is "placeholder / empty shell" (Loading…, empty mount point),
# not "shorter than a typical marketing page". A low ratio on a long page
# is normal and is ignored once word_count >= RATIO_WORD_CAP.
ABSOLUTE_WORD_THRESHOLD = 20
RATIO_WORD_CAP = 200
RATIO_THRESHOLD = 0.04

STRIP_TAGS = ("script", "style", "template", "svg")


def visible_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(STRIP_TAGS):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def score_html(html: str) -> dict:
    text = visible_text(html)
    words = [w for w in text.split() if w]
    word_count = len(words)
    text_len = len(text)
    html_len = len(html or "")
    ratio = (text_len / html_len) if html_len else 0.0

    flagged = False
    reason = None
    if word_count < ABSOLUTE_WORD_THRESHOLD:
        flagged = True
        reason = "absolute_word_count"
    elif word_count < RATIO_WORD_CAP and ratio < RATIO_THRESHOLD:
        flagged = True
        reason = "low_ratio_and_modest_text"
    else:
        reason = "not_a_shell"

    return {
        "word_count": word_count,
        "visible_text_chars": text_len,
        "raw_html_chars": html_len,
        "text_to_html_ratio": round(ratio, 4),
        "flagged": flagged,
        "reason": reason,
        "thresholds": {
            "absolute_word_count": ABSOLUTE_WORD_THRESHOLD,
            "ratio_word_cap": RATIO_WORD_CAP,
            "ratio_threshold": RATIO_THRESHOLD,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score HTML for a JS-shell gap.")
    parser.add_argument("file", nargs="?", help="HTML file (default: stdin)")
    args = parser.parse_args(argv)

    if args.file:
        with open(args.file, encoding="utf-8", errors="replace") as fh:
            html = fh.read()
    else:
        html = sys.stdin.read()

    json.dump(score_html(html), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
