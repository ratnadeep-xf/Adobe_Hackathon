#!/usr/bin/env python3
"""Same-origin HTTP helper for crawl-render-audit.

Only the audited origin is fetched. Timeouts, redirect history, and a
short delay keep the crawl recommend-only and non-abusive.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import requests

USER_AGENT = "Mozilla/5.0 (compatible; BrandAIReadinessAudit/1.0; +read-only-audit)"
TIMEOUT_SECONDS = 12
INTER_REQUEST_DELAY_SECONDS = 0.35
DEFAULT_429_WAIT_SECONDS = 4
MAX_429_WAIT_SECONDS = 15

_DIAGNOSTIC_HEADERS = (
    "server",
    "content-type",
    "www-authenticate",
    "cf-ray",
    "cf-mitigated",
    "x-cache",
    "x-robots-tag",
    "last-modified",
    "location",
    "retry-after",
)


def hosts_equivalent(host_a: str, host_b: str) -> bool:
    def strip_www(host: str) -> str:
        host = (host or "").lower()
        return host[4:] if host.startswith("www.") else host

    return strip_www(host_a) == strip_www(host_b) and bool(strip_www(host_a))


def same_origin(url: str, origin: str) -> bool:
    parsed = urlparse(url)
    origin_parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"}:
        return False
    return hosts_equivalent(parsed.netloc, origin_parsed.netloc)


def _header_subset(headers: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if not headers:
        return out
    for key in _DIAGNOSTIC_HEADERS:
        value = headers.get(key)
        if value:
            out[key] = value
    return out


def _retry_after_seconds(headers: Any) -> float:
    raw = ""
    if headers:
        raw = headers.get("Retry-After") or headers.get("retry-after") or ""
    raw = str(raw).strip()
    if not raw:
        return float(DEFAULT_429_WAIT_SECONDS)
    try:
        return max(0.5, min(float(raw), MAX_429_WAIT_SECONDS))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(raw)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        wait = (when - datetime.now(timezone.utc)).total_seconds()
        if wait <= 0:
            return float(DEFAULT_429_WAIT_SECONDS)
        return min(wait, MAX_429_WAIT_SECONDS)
    except (TypeError, ValueError, OverflowError):
        return float(DEFAULT_429_WAIT_SECONDS)


def _get(url: str):
    return requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xml,text/plain,*/*"},
        timeout=TIMEOUT_SECONDS,
        allow_redirects=True,
    )


def fetch(url: str, origin: str, delay: bool = True) -> dict[str, Any]:
    """GET a same-origin URL. Raises nothing — errors are in the result dict."""
    result: dict[str, Any] = {
        "url": url,
        "final_url": None,
        "status": None,
        "headers": {},
        "text": None,
        "error": None,
        "history_statuses": [],
        "blocked": False,
        "retried_429": False,
    }
    if not same_origin(url, origin):
        result["error"] = "refusing off-origin fetch"
        result["blocked"] = True
        return result

    if delay:
        time.sleep(INTER_REQUEST_DELAY_SECONDS)

    try:
        response = _get(url)
        if response.status_code == 429:
            time.sleep(_retry_after_seconds(response.headers))
            response = _get(url)
            result["retried_429"] = True
    except requests.exceptions.Timeout:
        result["error"] = "timeout"
        result["blocked"] = True
        return result
    except requests.exceptions.ConnectionError as exc:
        message = str(exc) or "connection error"
        lowered = message.lower()
        if "reset" in lowered:
            result["error"] = "connection reset"
        elif "refused" in lowered:
            result["error"] = "connection refused"
        else:
            result["error"] = "connection error"
        result["blocked"] = True
        return result
    except requests.RequestException as exc:
        result["error"] = str(exc) or "request failed"
        result["blocked"] = True
        return result

    history = [h.status_code for h in response.history]
    result["history_statuses"] = history
    result["status"] = response.status_code
    result["final_url"] = response.url
    result["headers"] = _header_subset(response.headers)

    final_ok = same_origin(response.url, origin)
    if not final_ok:
        result["error"] = "redirected off-origin"
        result["text"] = None
        return result

    # Decode as text; binary sitemaps are handled by the caller via content.
    result["content"] = response.content
    try:
        result["text"] = response.text
    except Exception:
        result["text"] = response.content.decode("utf-8", errors="replace")

    if response.status_code in {401, 403, 429, 405}:
        result["blocked"] = True
    return result


def chain_has_auth_block(result: dict[str, Any]) -> tuple[bool, int | None]:
    statuses = list(result.get("history_statuses") or [])
    if result.get("status") is not None:
        statuses.append(result["status"])
    for status in statuses:
        if status in {401, 403}:
            return True, status
    return False, None
