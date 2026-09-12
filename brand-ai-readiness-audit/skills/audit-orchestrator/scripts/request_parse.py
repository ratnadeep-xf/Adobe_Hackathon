#!/usr/bin/env python3
"""Pull a URL/domain and optional brand name out of a free-form request."""

from __future__ import annotations

import re
from urllib.parse import urlparse

URL_RE = re.compile(
    r"(https?://[^\s,;]+)|(\bwww\.[^\s,;]+)|(\b[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}\b)"
)
QUOTED_RE = re.compile(r"[\"“]([^\"”]{2,80})[\"”]")


def parse_request(text: str) -> dict:
    raw = (text or "").strip()
    match = URL_RE.search(raw)
    target = match.group(0).rstrip(").,]") if match else raw
    if target.startswith("www."):
        target = "https://" + target
    if target.startswith(("http://", "https://")):
        origin = f"{urlparse(target).scheme}://{urlparse(target).netloc}"
        host = urlparse(target).netloc
    else:
        origin = "https://" + target.split("/")[0]
        host = urlparse(origin).netloc
    host = host.lower()
    if host.startswith("www."):
        display_host = host[4:]
    else:
        display_host = host

    quoted = QUOTED_RE.search(raw)
    brand = quoted.group(1).strip() if quoted else ""
    return {
        "raw": raw,
        "target": target,
        "origin": origin.rstrip("/"),
        "host": display_host,
        "brand": brand,
    }
