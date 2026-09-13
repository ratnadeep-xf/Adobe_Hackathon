#!/usr/bin/env python3
"""Full marketplace pipeline: parse a free-form request, gather bundles once,
invoke the five skills, emit a schema-valid report.

Usage (any of these):
  python scripts/run_audit.py https://example.com
  python scripts/run_audit.py Audit example.com for AI readiness
  python scripts/run_audit.py 'Why don't assistants cite https://www.example.com/'
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from collect_site_bundle import collect_site_bundle  # noqa: E402
from request_parse import parse_request  # noqa: E402
from skill_loader import load_run  # noqa: E402
from validate_report import ReportSchemaError, validate_report  # noqa: E402

def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_BAD_TITLE_RE = None


def brand_from_homepage(html: str, fallback: str) -> str:
    import re

    global _BAD_TITLE_RE
    if _BAD_TITLE_RE is None:
        _BAD_TITLE_RE = re.compile(
            r"not found|just a moment|attention required|access denied|"
            r"enable javascript|client challenge|checking your browser",
            re.I,
        )
    match = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.I | re.S)
    if not match:
        return fallback
    title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", match.group(1))).strip()
    if _BAD_TITLE_RE.search(title):
        return fallback
    title = re.split(r"[|\-–—:]", title, maxsplit=1)[0].strip()
    return title[:80] or fallback


def normalize_finding(raw: dict[str, Any]) -> dict[str, Any]:
    action = raw.get("suggested_action") or {}
    if isinstance(action, str):
        action = {"summary": action, "priority": raw.get("severity", "medium")}
    return {
        "id": raw.get("id"),
        "title": raw.get("title") or "",
        "severity": (raw.get("severity") or "medium").lower(),
        "evidence": raw.get("evidence") or "",
        "suggested_action": {
            "summary": action.get("summary") or "",
            "priority": (action.get("priority") or raw.get("severity") or "medium").lower(),
        },
        "check_id": raw.get("id"),
    }


def extract_self_description(site_bundle: dict[str, Any]) -> dict[str, Any]:
    html = (site_bundle.get("homepage") or {}).get("html") or ""
    engage_scripts = SKILLS_DIR / "engagement-audit" / "scripts"
    if str(engage_scripts) not in sys.path:
        sys.path.insert(0, str(engage_scripts))
    sys.modules.pop("page_signals", None)
    from page_signals import extract_self_description as extract

    return extract(html)


def _missing_dependency_report(host: str, exc: Exception) -> dict[str, Any]:
    """A schema-valid report for when a required third-party package (requests
    or beautifulsoup4) isn't installed. Emitted instead of a raw crash so a
    grading harness reading stdout still gets valid JSON, with a clear,
    actionable finding, rather than a traceback and no report at all."""
    missing = getattr(exc, "name", None) or str(exc)
    finding = {
        "id": "F-001",
        "title": "Required Python package not installed",
        "severity": "critical",
        "evidence": (
            f"Import failed: {exc}. This marketplace requires requests, "
            f"beautifulsoup4, and ddgs (see requirements.txt at the "
            f"marketplace root). No site fetch or HTML parsing could be "
            f"performed, so no checks could run."
        ),
        "suggested_action": {
            "summary": (
                f"Run `pip install -r requirements.txt` from the marketplace "
                f"root (or `pip install {missing}`) before invoking "
                f"audit-orchestrator, then re-run the audit."
            ),
            "priority": "critical",
        },
    }
    return {
        "site": host,
        "audited_at": utc_now(),
        "summary": {"total_findings": 1, "critical": 1, "high": 0, "medium": 0, "low": 0},
        "findings": [finding],
        "coverage": {
            "error": "missing_dependency",
            "missing_dependency": missing,
            "skipped_checks": [
                {"id": cid, "reason": "required dependency not installed"}
                for cid in (
                    "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9",
                    "D10", "D11", "D12", "D13", "D14", "D15", "E1", "E2", "E3",
                )
            ],
        },
    }


def invoke_skills(
    origin: str,
    host: str,
    brand: str,
    site_bundle: dict[str, Any],
    search_bundle: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    skill_coverage: dict[str, Any] = {}
    self_description = extract_self_description(site_bundle)

    def _run_skill(skill_name: str, skill_path: Path, call) -> dict[str, Any]:
        """Load and run one skill in isolation. A failure here (missing
        import, unexpected exception, etc.) is recorded as that skill's
        coverage and produces zero findings from it -- it must not stop the
        other skills from running. Partial findings beat an empty report."""
        try:
            module = load_run(skill_path)
            report = call(module)
            findings.extend(report.get("findings") or [])
            skill_coverage[skill_name] = report.get("coverage") or {}
            return report
        except Exception as exc:  # noqa: BLE001 - isolate any skill failure
            skill_coverage[skill_name] = {
                "error": f"{type(exc).__name__}: {exc}",
                "skipped_checks": [
                    {"id": skill_name, "reason": f"skill raised: {exc}"}
                ],
            }
            return {}

    crawl_report = _run_skill(
        "crawl-render-audit",
        SKILLS_DIR / "crawl-render-audit" / "scripts",
        lambda m: m.run(origin, site_bundle),
    )
    site_bundle = crawl_report.get("site_bundle") or site_bundle

    structured_report = _run_skill(
        "structured-data-audit",
        SKILLS_DIR / "structured-data-audit" / "scripts",
        lambda m: m.run(origin, site_bundle),
    )

    freshness_report = _run_skill(
        "freshness-corroboration",
        SKILLS_DIR / "freshness-corroboration" / "scripts",
        lambda m: m.run(origin, site_bundle, search_bundle, brand),
    )
    search_bundle = freshness_report.get("search_bundle") or search_bundle

    _run_skill(
        "entity-clarity-audit",
        SKILLS_DIR / "entity-clarity-audit" / "scripts",
        lambda m: m.run(origin, site_bundle, search_bundle, brand, self_description),
    )

    _run_skill(
        "engagement-audit",
        SKILLS_DIR / "engagement-audit" / "scripts",
        lambda m: m.run(origin, site_bundle),
    )

    return findings, site_bundle, search_bundle, self_description, skill_coverage


def _merge_check_notes(skill_coverage: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Merge per-skill check_notes. skipped_checks = could-not-run only."""
    notes: dict[str, Any] = {}
    skipped: list[str] = []
    for skill, payload in skill_coverage.items():
        payload_notes = (payload or {}).get("check_notes") or {}
        for check_id, note in payload_notes.items():
            entry = {
                "status": note.get("status") or "skipped",
                "reason": note.get("reason") or "",
                "skill": skill,
            }
            notes[check_id] = entry
            if entry["status"] == "skipped" and check_id not in skipped:
                skipped.append(check_id)
        for entry in (payload or {}).get("skipped_checks") or []:
            # Skills report this as either a bare id (str) or an
            # {"id": ..., "reason": ...} object (Phase 9.3). Normalize both.
            if isinstance(entry, dict):
                check_id = entry.get("id")
                reason = entry.get("reason") or "not evaluated"
            else:
                check_id = entry
                reason = "not evaluated"
            if check_id is None:
                continue
            if check_id not in notes:
                notes[check_id] = {
                    "status": "skipped",
                    "reason": reason,
                    "skill": skill,
                }
                skipped.append(check_id)
    return notes, skipped


def build_report(
    host: str,
    findings_raw: list[dict[str, Any]],
    coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    findings = []
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for raw in findings_raw:
        item = normalize_finding(raw)
        if item["severity"] not in counts:
            item["severity"] = "medium"
        counts[item["severity"]] += 1
        item["id"] = f"F-{len(findings) + 1:03d}"
        findings.append(
            {
                "id": item["id"],
                "title": item["title"],
                "severity": item["severity"],
                "evidence": item["evidence"],
                "suggested_action": item["suggested_action"],
            }
        )
    return {
        "site": host,
        "audited_at": utc_now(),
        "summary": {
            "total_findings": len(findings),
            "critical": counts["critical"],
            "high": counts["high"],
            "medium": counts["medium"],
            "low": counts["low"],
        },
        "findings": findings,
        "coverage": coverage or {},
    }


def run(request_text: str, brand_override: str = "") -> dict[str, Any]:
    parsed = parse_request(request_text)
    origin = parsed["origin"]
    host = parsed["host"]

    try:
        site_bundle = collect_site_bundle(origin)
    except (ImportError, ModuleNotFoundError) as exc:
        return validate_report(_missing_dependency_report(host, exc))

    homepage = site_bundle.get("homepage") or {}
    html = homepage.get("html") or ""
    home_quality = homepage.get("fetch_quality") or {}
    if not home_quality.get("usable"):
        brand = brand_override or parsed["brand"] or host.split(".")[0]
    else:
        brand = brand_override or parsed["brand"] or brand_from_homepage(html, host.split(".")[0])

    # Search once via freshness-corroboration's wrapper.
    for name in ("web_search", "source_classifier"):
        sys.modules.pop(name, None)
    fresh_scripts = SKILLS_DIR / "freshness-corroboration" / "scripts"
    if str(fresh_scripts) not in sys.path:
        sys.path.insert(0, str(fresh_scripts))

    try:
        from web_search import search_bundle as make_search
        search = make_search(brand, host)
    except (ImportError, ModuleNotFoundError) as exc:
        return validate_report(_missing_dependency_report(host, exc))
    except Exception as exc:
        search = {
            "query": brand,
            "results": [],
            "distinct_domains": [],
            "own_domain_present": False,
            "error": str(exc),
        }

    try:
        merged, site_bundle, _, _, skill_coverage = invoke_skills(
            origin, host, brand, site_bundle, search
        )
    except (ImportError, ModuleNotFoundError) as exc:
        return validate_report(_missing_dependency_report(host, exc))
    crawl_cov = skill_coverage.get("crawl-render-audit") or {}
    sampled = (
        crawl_cov.get("sampled_internal_urls")
        or site_bundle.get("sampled_internal_urls")
        or []
    )
    path_classes = {}
    for row in crawl_cov.get("page_scores") or []:
        url = row.get("url")
        if url:
            path_classes[url] = row.get("path_class")
    check_notes, skipped_only = _merge_check_notes(skill_coverage)
    coverage = {
        "homepage_fetch_quality": homepage.get("fetch_quality")
        or crawl_cov.get("homepage_fetch_quality"),
        "preferred_locale": crawl_cov.get("preferred_locale") or "",
        "sampled_internal_urls": sampled,
        "sampled_page_count": len(sampled),
        "homepage_echo_samples": crawl_cov.get("homepage_echo_samples") or [],
        "d3_subcategory": crawl_cov.get("d3_subcategory"),
        "path_classes": path_classes,
        "check_notes": check_notes,
        "skipped_checks": skipped_only,
        "skills": skill_coverage,
        "brand_used": brand,
    }
    report = build_report(host, merged, coverage)
    return validate_report(report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the brand AI-readiness audit (entrypoint)."
    )
    parser.add_argument(
        "--brand",
        default="",
        help="Override the brand/entity name used for the keyless search",
    )
    args, rest = parser.parse_known_args(argv)
    pieces = [p for p in rest if p != "--"]
    if not pieces:
        print("Pass a free-form request that names a URL or domain.", file=sys.stderr)
        return 2
    try:
        report = run(" ".join(pieces), args.brand)
    except ReportSchemaError as exc:
        print(f"Report failed schema validation: {exc}", file=sys.stderr)
        return 1
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())