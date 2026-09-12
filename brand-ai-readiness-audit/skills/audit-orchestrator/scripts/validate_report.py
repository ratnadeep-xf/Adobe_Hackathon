#!/usr/bin/env python3
"""Validate the orchestrator report against the required schema."""

from __future__ import annotations

import re
from typing import Any

SEVERITIES = {"critical", "high", "medium", "low"}
ID_RE = re.compile(r"^F-\d{3}$")


class ReportSchemaError(ValueError):
    pass


def validate_report(report: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise ReportSchemaError("report must be an object")
    for key in ("site", "audited_at", "summary", "findings"):
        if key not in report:
            raise ReportSchemaError(f"missing root field {key}")
    if not isinstance(report["site"], str) or not report["site"].strip():
        raise ReportSchemaError("site must be a non-empty string")
    if not isinstance(report["audited_at"], str) or "T" not in report["audited_at"]:
        raise ReportSchemaError("audited_at must be an ISO-8601 timestamp")
    summary = report["summary"]
    if not isinstance(summary, dict):
        raise ReportSchemaError("summary must be an object")
    for key in ("total_findings", "critical", "high", "medium"):
        if key not in summary or not isinstance(summary[key], int):
            raise ReportSchemaError(f"summary.{key} must be an int")
    findings = report["findings"]
    if not isinstance(findings, list):
        raise ReportSchemaError("findings must be an array")
    if summary["total_findings"] != len(findings):
        raise ReportSchemaError("summary.total_findings must equal len(findings)")

    counts = {name: 0 for name in SEVERITIES}
    seen_ids: set[str] = set()
    for index, item in enumerate(findings, start=1):
        if not isinstance(item, dict):
            raise ReportSchemaError(f"findings[{index}] must be an object")
        for key in ("id", "title", "severity", "evidence", "suggested_action"):
            if key not in item:
                raise ReportSchemaError(f"findings[{index}] missing {key}")
        if not ID_RE.match(str(item["id"])):
            raise ReportSchemaError(f"findings[{index}].id must look like F-001")
        if item["id"] in seen_ids:
            raise ReportSchemaError(f"duplicate finding id {item['id']}")
        seen_ids.add(item["id"])
        expected = f"F-{index:03d}"
        if item["id"] != expected:
            raise ReportSchemaError(f"findings[{index}].id must be {expected}")
        if item["severity"] not in SEVERITIES:
            raise ReportSchemaError(f"findings[{index}].severity is not allowed")
        if not str(item["title"]).strip() or not str(item["evidence"]).strip():
            raise ReportSchemaError(f"findings[{index}] title/evidence empty")
        action = item["suggested_action"]
        if not isinstance(action, dict) or not action.get("summary") or not action.get("priority"):
            raise ReportSchemaError(f"findings[{index}].suggested_action needs summary and priority")
        counts[item["severity"]] += 1

    for name in ("critical", "high", "medium"):
        if summary[name] != counts[name]:
            raise ReportSchemaError(f"summary.{name} does not match findings")
    if "low" in summary and summary["low"] != counts["low"]:
        raise ReportSchemaError("summary.low does not match findings")
    return report
