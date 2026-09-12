#!/usr/bin/env python3
"""Classify a fetch as usable content vs interstitial/error/hard-block.

This is the gate that must run before any skill reasons about page *content*
or *identity*. A 404 stub or JS-challenge is not the brand's homepage.
"""

from __future__ import annotations

import re
from typing import Any

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None

HARD_BLOCK_ERRORS = {
    "timeout",
    "connection reset",
    "connection refused",
    "connection error",
}

INTERSTITIAL_RE = re.compile(
    r"please enable javascript|enable javascript to proceed|"
    r"checking your browser|just a moment(?:\.\.\.)?|attention required|"
    r"cf-browser-verification|challenge-platform|client challenge|"
    r"unusual traffic|verify you are (?:a )?human|captcha|"
    r"access denied|pardon our interruption|blocked because|"
    r"bot detection|security check",
    re.I,
)

ERROR_BODY_RE = re.compile(
    r"^\s*(?:not found|404|page not found|error\s*404|the page cannot be found)\s*\.?\s*$",
    re.I,
)


def visible_text(html: str) -> str:
    if not html:
        return ""
    if BeautifulSoup is None:
        return re.sub(r"<[^>]+>", " ", html)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "template", "svg"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def classify_fetch(
    status: int | None,
    html: str | None = None,
    error: str | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    """Return {usable, class, reason, word_count, preview}.

    class is one of: usable | interstitial | error | hard_block
    """
    body = html or ""
    text = visible_text(body)
    words = [w for w in text.split() if w]
    preview = text[:160]

    result = {
        "url": url,
        "status": status,
        "usable": False,
        "class": "error",
        "reason": "",
        "word_count": len(words),
        "preview": preview,
    }

    if error in HARD_BLOCK_ERRORS or (status is None and error):
        result["class"] = "hard_block"
        result["reason"] = error or "no response"
        return result
    if status in {401, 403}:
        result["class"] = "hard_block"
        result["reason"] = f"HTTP {status}"
        return result
    if status in {404, 410}:
        result["class"] = "error"
        result["reason"] = f"HTTP {status} stub"
        return result

    haystack = f"{text}\n{body[:2000]}"
    if INTERSTITIAL_RE.search(haystack):
        result["class"] = "interstitial"
        result["reason"] = "bot-check / JS-challenge / interstitial page"
        return result

    if status in {200, 203} or (isinstance(status, int) and 200 <= status < 400):
        if ERROR_BODY_RE.match(text) or (
            len(words) <= 4 and ERROR_BODY_RE.search(text)
        ):
            result["class"] = "error"
            result["reason"] = "generic not-found body"
            return result
        if len(body.strip()) < 20 and len(words) < 3:
            result["class"] = "error"
            result["reason"] = "empty or tiny body"
            return result
        result["usable"] = True
        result["class"] = "usable"
        result["reason"] = "usable content"
        return result

    result["reason"] = f"HTTP {status}" if status is not None else (error or "unusable")
    return result


def classify_page(page: dict[str, Any]) -> dict[str, Any]:
    """Classify a homepage / sampled-page dict; attach fetch_quality on it."""
    quality = classify_fetch(
        page.get("status"),
        page.get("html") or page.get("text"),
        page.get("error"),
        page.get("final_url") or page.get("url"),
    )
    page["fetch_quality"] = quality
    return quality


def homepage_quality(bundle: dict[str, Any] | None) -> dict[str, Any]:
    if not bundle:
        return {"usable": False, "class": "error", "reason": "no site bundle"}
    home = bundle.get("homepage") or {}
    existing = home.get("fetch_quality")
    if isinstance(existing, dict) and existing.get("class"):
        return existing
    return classify_page(home)
