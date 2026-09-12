#!/usr/bin/env python3
"""Standalone E1–E3 engagement audit (homepage orientation)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from page_signals import concrete_offerings, extract_self_description  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def finding(check_id: str, title: str, severity: str, evidence: str, action: str) -> dict[str, Any]:
    return {
        "id": check_id,
        "title": title,
        "severity": severity,
        "evidence": evidence,
        "suggested_action": {"summary": action, "priority": severity},
    }


def origin_from(raw: str) -> str:
    value = raw.strip()
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    parsed = urlparse(value)
    return f"{parsed.scheme}://{parsed.netloc}"


def run(target: str, bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    origin = (bundle.get("origin") if bundle and bundle.get("origin") else origin_from(target)).rstrip("/")
    homepage = (bundle or {}).get("homepage") or {}
    html = homepage.get("html") or homepage.get("text") or ""
    if not html:
        try:
            import requests

            resp = requests.get(
                origin + "/",
                headers={"User-Agent": "Mozilla/5.0 (compatible; BrandAIReadinessAudit/1.0; +read-only-audit)"},
                timeout=12,
            )
            html = resp.text
            homepage = {"url": origin + "/", "status": resp.status_code, "html": html}
        except Exception as exc:
            return {
                "skill": "engagement-audit",
                "site": urlparse(origin).netloc,
                "audited_at": utc_now(),
                "findings": [],
                "self_description": {},
                "coverage": {
                    "skipped_checks": ["E1", "E2", "E3"],
                    "check_notes": {
                        eid: {"status": "skipped", "reason": str(exc)}
                        for eid in ("E1", "E2", "E3")
                    },
                    "error": str(exc),
                },
            }

    desc = extract_self_description(html)
    findings: list[dict[str, Any]] = []
    skipped: list[str] = []

    quality = homepage.get("fetch_quality")
    if not isinstance(quality, dict) or not quality.get("class"):
        crawl = Path(__file__).resolve().parents[2] / "crawl-render-audit" / "scripts"
        if crawl.is_dir():
            sys.path.insert(0, str(crawl))
            try:
                from fetch_quality import classify_page

                quality = classify_page(homepage)
            except Exception:
                quality = {"usable": True, "class": "usable"}
        else:
            quality = {"usable": True, "class": "usable"}
    notes: dict[str, dict[str, str]] = {}

    def mark(check_id: str, status: str, reason: str) -> None:
        notes[check_id] = {"status": status, "reason": reason}
        if status == "skipped" and check_id not in skipped:
            skipped.append(check_id)

    if not quality.get("usable"):
        for eid, label in (("E1", "orientation"), ("E2", "meta"), ("E3", "H1")):
            mark(eid, "skipped", f"homepage fetch is not usable content; {label} not scored")
        return {
            "skill": "engagement-audit",
            "site": urlparse(origin).netloc,
            "audited_at": utc_now(),
            "findings": [],
            "self_description": desc,
            "coverage": {
                "skipped_checks": skipped,
                "check_notes": notes,
                "homepage_fetch_quality": quality,
            },
        }

    e1 = not desc["concrete_offerings"]
    if e1:
        findings.append(
            finding(
                "E1",
                "Weak on-page orientation",
                "high",
                f"Combined title/meta/H1/opening text names no concrete offering. Text checked: {desc['combined'][:400]!r}.",
                "State a concrete offering or action in the title, meta description, H1, or opening paragraph — not only a slogan.",
            )
        )
        mark("E1", "fired", "combined title/meta/H1/opening names no concrete offering")
    else:
        mark("E1", "clear", f"concrete offering signal(s): {desc['concrete_offerings'][:4]}")

    meta = desc["meta_description"]
    if len(meta) >= 40 and not concrete_offerings(meta):
        findings.append(
            finding(
                "E2",
                "Generic or non-descriptive meta description",
                "medium",
                f"Meta description is {len(meta)} characters but names no concrete offering: {meta!r}.",
                "Rewrite the meta description so it names what is offered, not only marketing filler.",
            )
        )
        mark("E2", "fired", f"meta is {len(meta)} characters with no offering")
    elif not meta or len(meta) < 40:
        mark("E2", "no_signal", "meta description missing or shorter than 40 characters")
    else:
        mark("E2", "clear", "meta description names a concrete offering")

    h1s = desc["h1s"]
    if len(h1s) == 0 or len(h1s) >= 2:
        severity = "medium" if e1 else "low"
        findings.append(
            finding(
                "E3",
                "Missing or duplicate H1 structure",
                severity,
                f"H1 count={len(h1s)}; texts={h1s or '[]'}.",
                "Use exactly one H1 that names the primary topic of the page.",
            )
        )
        mark("E3", "fired", f"H1 count={len(h1s)}")
    else:
        mark("E3", "clear", f"exactly one H1: {h1s[0][:80]!r}")

    return {
        "skill": "engagement-audit",
        "site": urlparse(origin).netloc,
        "audited_at": utc_now(),
        "findings": findings,
        "self_description": desc,
        "coverage": {
            "skipped_checks": skipped,
            "check_notes": notes,
            "homepage_fetch_quality": quality,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run engagement-audit (E1–E3).")
    parser.add_argument("target")
    parser.add_argument("--bundle")
    args = parser.parse_args(argv)
    bundle = None
    if args.bundle:
        with open(args.bundle, encoding="utf-8") as fh:
            loaded = json.load(fh)
        bundle = loaded.get("site_bundle", loaded)
    json.dump(run(args.target, bundle), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
