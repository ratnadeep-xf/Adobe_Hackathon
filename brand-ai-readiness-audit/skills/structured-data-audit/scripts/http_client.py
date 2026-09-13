#!/usr/bin/env python3
"""Same-origin HTTP helper for structured-data-audit."""

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


def fetch(url: str, origin: str, delay: bool = True) -> dict[str, Any]:
    result: dict[str, Any] = {
        "url": url,
        "final_url": None,
        "status": None,
        "headers": {},
        "text": None,
        "error": None,
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
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xml,text/plain,*/*"},
            timeout=TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        if response.status_code == 429:
            time.sleep(_retry_after_seconds(response.headers))
            response = requests.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xml,text/plain,*/*"},
                timeout=TIMEOUT_SECONDS,
                allow_redirects=True,
            )
            result["retried_429"] = True
    except requests.exceptions.Timeout:
        result["error"] = "timeout"
        result["blocked"] = True
        return result
    except requests.exceptions.ConnectionError as exc:
        message = str(exc) or "connection error"
        lowered = message.lower()
        result["error"] = "connection reset" if "reset" in lowered else (
            "connection refused" if "refused" in lowered else "connection error"
        )
        result["blocked"] = True
        return result
    except requests.RequestException as exc:
        result["error"] = str(exc) or "request failed"
        result["blocked"] = True
        return result

    result["status"] = response.status_code
    result["final_url"] = response.url
    result["headers"] = {}
    last_modified = response.headers.get("Last-Modified")
    if last_modified:
        result["headers"]["last-modified"] = last_modified
    if not same_origin(response.url, origin):
        result["error"] = "redirected off-origin"
        return result
    try:
        result["text"] = response.text
    except Exception:
        result["text"] = response.content.decode("utf-8", errors="replace")
    if response.status_code in {401, 403, 429, 405}:
        result["blocked"] = True
    return result
