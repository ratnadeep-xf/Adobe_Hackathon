#!/usr/bin/env python3
"""Keyless brand-name search via DuckDuckGo (no API key)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from urllib.parse import urlparse


# Multi-part public suffixes only. Not a brand or platform list.
_MULTI_PART_SUFFIXES = frozenset(
    {
        "co.uk", "org.uk", "ac.uk", "gov.uk", "ltd.uk", "plc.uk", "me.uk",
        "com.au", "net.au", "org.au", "edu.au", "gov.au",
        "co.nz", "org.nz", "govt.nz",
        "co.jp", "or.jp", "ne.jp", "ac.jp", "go.jp",
        "co.in", "net.in", "org.in", "firm.in",
        "com.br", "com.mx", "com.ar", "com.co",
        "co.za", "org.za",
        "co.kr", "or.kr",
        "com.cn", "com.hk", "com.tw", "com.sg",
        "co.id", "com.my", "com.ph",
        "com.tr", "com.ua",
    }
)


def domain_of(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return ""


def _strip_host(host: str) -> str:
    host = (host or "").lower()
    if ":" in host:
        host = host.split(":", 1)[0]
    return host[4:] if host.startswith("www.") else host


def registrable_domain(host: str) -> str:
    """eTLD+1 (example.com, bbc.co.uk). Subdomains collapse to the same value."""
    host = _strip_host(host)
    if not host:
        return ""
    parts = [p for p in host.split(".") if p]
    if len(parts) < 2:
        return host
    last_two = ".".join(parts[-2:])
    if last_two in _MULTI_PART_SUFFIXES and len(parts) >= 3:
        return ".".join(parts[-3:])
    return last_two


def hosts_match(host_a: str, host_b: str) -> bool:
    """True when both hosts share an eTLD+1 (subdomains of the audited site count)."""
    a = registrable_domain(host_a)
    b = registrable_domain(host_b)
    return bool(a) and a == b


def first_own_domain_match(audited_host: str, domains: list[str]) -> str:
    """Return the first search domain whose eTLD+1 matches the audited host."""
    for domain in domains:
        if hosts_match(audited_host, domain):
            return domain
    return ""


def web_search(query: str, max_results: int = 8, retries: int = 3) -> list[dict]:
    """Free, keyless DuckDuckGo search. Returns [{title, url, snippet}]."""
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError as exc:
            raise RuntimeError("Install ddgs: pip install ddgs") from exc

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href") or r.get("url", ""),
                    "snippet": r.get("body", ""),
                }
                for r in results
            ]
        except Exception as exc:
            last_err = exc
            time.sleep(2 * attempt)
    return []


def search_bundle(query: str, audited_host: str = "", max_results: int = 8) -> dict:
    results = web_search(query, max_results=max_results)
    domains = []
    for row in results:
        host = domain_of(row.get("url") or "")
        if host and host not in domains:
            domains.append(host)
    matched = first_own_domain_match(audited_host, domains) if audited_host else ""
    return {
        "query": query,
        "results": results,
        "distinct_domains": domains,
        "own_domain_present": bool(matched),
        "own_domain_match": matched or None,
        "error": None if results or query else "empty query",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Keyless brand-name search.")
    parser.add_argument("query")
    parser.add_argument("--host", default="", help="Audited host for own-domain flag")
    args = parser.parse_args(argv)
    json.dump(search_bundle(args.query, args.host), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
