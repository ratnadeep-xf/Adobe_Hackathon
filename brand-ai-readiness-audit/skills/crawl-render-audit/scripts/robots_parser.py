#!/usr/bin/env python3
"""Parse robots.txt for D1 (wildcard root block) and D2 (named AI agents).

Read-only. No network — pass the robots.txt body in. Training-crawler vs
live-agent categories are a fixed public catalog, not a per-site list.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


TRAINING_CRAWLERS = {
    "gptbot": "GPTBot",
    "claudebot": "ClaudeBot",
    "anthropic-ai": "anthropic-ai",
    "google-extended": "Google-Extended",
    "applebot-extended": "Applebot-Extended",
    "ccbot": "CCBot",
    "bytespider": "Bytespider",
    "meta-externalagent": "meta-externalagent",
    "perplexitybot": "PerplexityBot",
    "amazonbot": "Amazonbot",
    "cohere-ai": "cohere-ai",
    "diffbot": "Diffbot",
}

LIVE_AGENTS = {
    "chatgpt-user": "ChatGPT-User",
    "oai-searchbot": "OAI-SearchBot",
    "claude-user": "Claude-User",
    "claude-searchbot": "Claude-SearchBot",
    "perplexity-user": "Perplexity-User",
    "google-cloudvertexbot": "Google-CloudVertexBot",
    "meta-externalfetcher": "Meta-ExternalFetcher",
}

AI_CATALOG = {**TRAINING_CRAWLERS, **LIVE_AGENTS}


def _agent_category(token: str) -> str | None:
    key = token.lower()
    if key in TRAINING_CRAWLERS:
        return "training-crawler"
    if key in LIVE_AGENTS:
        return "live-agent"
    return None


def _normalize_ua(value: str) -> str:
    return value.strip().split()[0].lower() if value.strip() else ""


def parse_robots(text: str) -> dict[str, Any]:
    """Parse robots.txt into groups, sitemap URLs, and D1/D2 views."""
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")

    groups: list[dict[str, Any]] = []
    sitemaps: list[str] = []
    pending_agents: list[str] = []
    current: dict[str, Any] | None = None

    def start_group(agent: str) -> None:
        nonlocal current, pending_agents
        if current is not None and current["rules"]:
            groups.append(current)
            current = None
            pending_agents = []
        pending_agents.append(agent)
        current = {
            "user_agents": list(pending_agents),
            "rules": [],
        }

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "#" in line:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        original = f"{key}: {value}" if key != "user-agent" else f"User-agent: {value}"

        if key == "user-agent":
            agent = _normalize_ua(value)
            if current is not None and current["rules"]:
                start_group(agent)
            elif current is None:
                start_group(agent)
            else:
                pending_agents.append(agent)
                current["user_agents"] = list(pending_agents)
        elif key in {"disallow", "allow"}:
            if current is None:
                start_group("*")
            path = value or ""
            quoted = f"Disallow: {path}" if key == "disallow" else f"Allow: {path}"
            current["rules"].append(
                {
                    "type": key,
                    "path": path,
                    "quoted": quoted,
                    "raw": original,
                }
            )
        elif key == "sitemap":
            if value:
                sitemaps.append(value)

    if current is not None:
        groups.append(current)

    wildcard_rules = []
    for group in groups:
        if any(ua == "*" for ua in group["user_agents"]):
            wildcard_rules.extend(group["rules"])

    wildcard_root_disallow = _has_root_disallow(wildcard_rules)
    wildcard_root_allow = any(
        r["type"] == "allow" and _is_root_path(r["path"]) for r in wildcard_rules
    )
    d1_fires = wildcard_root_disallow and not wildcard_root_allow
    d1_quoted = [
        r["quoted"]
        for r in wildcard_rules
        if r["type"] == "disallow" and _is_root_path(r["path"])
    ]

    named_ai: list[dict[str, Any]] = []
    for token, canonical in AI_CATALOG.items():
        decision = path_access(groups, token, "/")
        named_ai.append(
            {
                "user_agent": canonical,
                "category": _agent_category(token),
                "root_disallowed": not decision["allowed"],
                "matched_via": decision["matched_via"],
                "quoted_rule": decision["quoted_rule"],
                "has_named_group": decision["matched_via"] == "named",
            }
        )

    return {
        "groups": groups,
        "sitemaps": sitemaps,
        "wildcard_root_disallow": d1_fires,
        "wildcard_quoted_rules": d1_quoted,
        "named_ai_agents": named_ai,
    }


def _is_root_path(path: str) -> bool:
    p = (path or "").strip()
    return p == "/" or p == "/*"


def _has_root_disallow(rules: list[dict[str, Any]]) -> bool:
    return any(r["type"] == "disallow" and _is_root_path(r["path"]) for r in rules)


def _path_matches(rule_path: str, request_path: str) -> bool:
    if rule_path == "":
        return False
    rule = rule_path if rule_path.startswith("/") else "/" + rule_path
    req = request_path if request_path.startswith("/") else "/" + request_path
    if rule.endswith("*"):
        rule = rule[:-1]
    return req.startswith(rule)


def path_access(groups: list[dict[str, Any]], user_agent: str, path: str) -> dict[str, Any]:
    """Longest-matching Allow/Disallow among groups that apply to user_agent."""
    ua = _normalize_ua(user_agent)
    named = [g for g in groups if ua in g["user_agents"]]
    wildcard = [g for g in groups if "*" in g["user_agents"]]
    applicable = named if named else wildcard
    matched_via = "named" if named else ("wildcard" if wildcard else "none")

    best: dict[str, Any] | None = None
    best_len = -1
    for group in applicable:
        for rule in group["rules"]:
            if not _path_matches(rule["path"], path):
                continue
            length = len(rule["path"] or "")
            if length > best_len:
                best = rule
                best_len = length
            elif length == best_len and best is not None and rule["type"] == "allow":
                best = rule

    if best is None:
        return {
            "allowed": True,
            "matched_via": matched_via,
            "quoted_rule": None,
        }
    return {
        "allowed": best["type"] == "allow",
        "matched_via": matched_via,
        "quoted_rule": best["quoted"],
    }


def is_path_allowed(parsed: dict[str, Any], user_agent: str, path: str) -> bool:
    return path_access(parsed["groups"], user_agent, path)["allowed"]


def d2_blocked(parsed: dict[str, Any]) -> dict[str, Any]:
    """Named AI agents whose root path is disallowed, split by category."""
    blocked_training = []
    blocked_live = []
    for row in parsed["named_ai_agents"]:
        if not row["root_disallowed"]:
            continue
        item = {
            "user_agent": row["user_agent"],
            "quoted_rule": row["quoted_rule"],
            "matched_via": row["matched_via"],
        }
        if row["category"] == "live-agent":
            blocked_live.append(item)
        else:
            blocked_training.append(item)
    return {
        "blocked_training_crawlers": blocked_training,
        "blocked_live_agents": blocked_live,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse robots.txt for D1/D2.")
    parser.add_argument("file", nargs="?", help="Path to a robots.txt file")
    parser.add_argument("--text", help="Raw robots.txt contents instead of a file")
    args = parser.parse_args(argv)

    if args.text is not None:
        body = args.text
    elif args.file:
        with open(args.file, encoding="utf-8", errors="replace") as fh:
            body = fh.read()
    else:
        body = sys.stdin.read()

    parsed = parse_robots(body)
    parsed["d2"] = d2_blocked(parsed)
    json.dump(parsed, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
