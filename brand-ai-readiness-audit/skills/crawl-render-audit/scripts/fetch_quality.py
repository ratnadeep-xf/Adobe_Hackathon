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

D3_SPECS = {
    "waf_403": {
        "title": "Homepage blocked by WAF or bot-detection (HTTP 403)",
        "severity": "critical",
        "action": (
            "Review WAF/CDN/bot-detection rules so ordinary HTTP clients and "
            "crawlers can reach public pages. A 403 is a confirmed infrastructure "
            "block, not a robots.txt disallow."
        ),
    },
    "rate_limited_429": {
        "title": "Homepage rate-limited (HTTP 429 after retry)",
        "severity": "high",
        "action": (
            "This client was rate-limited even after one Retry-After-aware retry. "
            "Confirm whether public crawlers are throttled too aggressively, or "
            "wait and re-audit. A 429 is not as conclusive as a confirmed 403."
        ),
    },
    "auth_401_homepage": {
        "title": "Entire site gated behind authentication (homepage HTTP 401)",
        "severity": "critical",
        "action": (
            "The homepage itself requires authentication, so the whole origin is "
            "gated for unauthenticated visitors. If any public content exists, "
            "serve it without a login wall. Distinct from D6, which only covers "
            "internal URLs."
        ),
    },
    "empty_202": {
        "title": "Homepage accepted but returned no real content (empty 2xx / HTTP 202)",
        "severity": "critical",
        "action": (
            "The server accepted the request but returned an empty or non-content "
            "body (often a bot-challenge interstitial). Allow simple HTTP clients "
            "to receive the real homepage HTML, not an empty 202/2xx placeholder."
        ),
    },
    "method_not_allowed_405": {
        "title": "Homepage rejected GET (HTTP 405)",
        "severity": "critical",
        "action": (
            "Allow GET on the public homepage. A 405 on `/` means ordinary crawlers "
            "cannot retrieve the page at all."
        ),
    },
    "no_response_timeout": {
        "title": "Homepage did not respond (timeout or connection failure)",
        "severity": "critical",
        "action": (
            "The homepage timed out or the connection was reset/refused. Confirm "
            "whether the origin is down, geographically blocked, or dropping "
            "automated clients — this audit cannot tell those apart from a hard block."
        ),
    },
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
    if status in {401, 403, 429, 405}:
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

    if status in {200, 202, 203} or (isinstance(status, int) and 200 <= status < 400):
        if ERROR_BODY_RE.match(text) or (
            len(words) <= 4 and ERROR_BODY_RE.search(text)
        ):
            result["class"] = "error"
            result["reason"] = "generic not-found body"
            return result
        empty_body = len(body.strip()) < 20 and len(words) < 3
        if status == 202 or empty_body:
            result["class"] = "interstitial"
            result["reason"] = "empty_202"
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


def d3_subcategory(page: dict[str, Any], quality: dict[str, Any] | None = None) -> str | None:
    """Map a homepage fetch to a D3 sub-category, or None if D3 does not apply."""
    status = page.get("status")
    error = page.get("error")
    quality = quality or page.get("fetch_quality") or {}

    if status == 403:
        return "waf_403"
    if status == 429:
        return "rate_limited_429"
    if status == 401:
        return "auth_401_homepage"
    if status == 405:
        return "method_not_allowed_405"
    if error in HARD_BLOCK_ERRORS or (status is None and (error or page.get("blocked"))):
        return "no_response_timeout"
    if status == 202 or (quality.get("class") == "interstitial" and quality.get("reason") == "empty_202"):
        return "empty_202"
    return None


def homepage_quality(bundle: dict[str, Any] | None) -> dict[str, Any]:
    if not bundle:
        return {"usable": False, "class": "error", "reason": "no site bundle"}
    home = bundle.get("homepage") or {}
    existing = home.get("fetch_quality")
    if isinstance(existing, dict) and existing.get("class"):
        return existing
    return classify_page(home)
