#!/usr/bin/env python3
"""Extract title / meta / H1 / opening text and detect a concrete offering."""

from __future__ import annotations

import argparse
import json
import re
import sys

from bs4 import BeautifulSoup

FILLER = {
    "welcome", "innovative", "innovation", "leading", "leader", "excellence",
    "world", "class", "world-class", "cutting", "edge", "cutting-edge",
    "next", "generation", "next-generation", "solutions", "solution",
    "digital", "transform", "transformation", "future", "empower",
    "empowering", "seamless", "best", "premier", "ultimate", "your",
    "our", "we", "the", "and", "for", "with", "from", "that", "this",
    "you", "home", "official", "website", "site", "page", "online",
    "company", "inc", "llc", "ltd", "group", "global", "international",
}

OFFERING_RE = re.compile(
    r"\bwe\s+(?:sell|make|build|provide|offer|design|create|run|operate|teach|help)\b"
    r"|platform\s+for|software\s+for|\bshop\b|\bstore\b",
    re.I,
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_self_description(html: str) -> dict:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "template", "svg"]):
        tag.decompose()

    title_tag = soup.find("title")
    title = _clean(title_tag.get_text(" ", strip=True) if title_tag else "")

    meta_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    meta = ""
    if meta_tag and meta_tag.get("content"):
        meta = _clean(meta_tag.get("content"))

    h1s = [_clean(h.get_text(" ", strip=True)) for h in soup.find_all("h1")]
    h1s = [h for h in h1s if h]

    first_paragraph = ""
    for p in soup.find_all("p"):
        text = _clean(p.get_text(" ", strip=True))
        if len(text.split()) >= 4:
            first_paragraph = text
            break
    if not first_paragraph:
        body = _clean(soup.get_text(" ", strip=True))
        first_paragraph = body[:280]

    combined = _clean(" ".join([title, meta, " ".join(h1s), first_paragraph]))
    offerings = concrete_offerings(combined)
    return {
        "title": title,
        "meta_description": meta,
        "h1s": h1s,
        "first_paragraph": first_paragraph,
        "combined": combined,
        "concrete_offerings": offerings,
    }


def concrete_offerings(text: str) -> list[str]:
    found: list[str] = []
    if OFFERING_RE.search(text or ""):
        found.append(OFFERING_RE.search(text).group(0))
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9'+-]{3,}", text or "")
    content = []
    for token in tokens:
        if token.lower() in FILLER:
            continue
        if token[:1].isupper() or len(token) >= 5:
            content.append(token)
    # Keep a few distinctive leftovers as offering candidates
    for token in content[:6]:
        if token not in found:
            found.append(token)
    # Slogan-only pages often leave only 0–1 leftover proper nouns (the brand).
    # Require either an offering verb or 2+ non-filler content tokens.
    if not OFFERING_RE.search(text or "") and len(content) < 2:
        return []
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract homepage orientation signals.")
    parser.add_argument("file", nargs="?", help="HTML file (default: stdin)")
    args = parser.parse_args(argv)
    html = open(args.file, encoding="utf-8", errors="replace").read() if args.file else sys.stdin.read()
    json.dump(extract_self_description(html), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
