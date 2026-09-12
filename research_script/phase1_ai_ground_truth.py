#!/usr/bin/env python3
"""
Phase 1 Field Research — semi-automated "ground truth" pass, via Groq.

v2: adds retry/backoff for Groq's free-tier rate limits. groq/compound on
the free tier is capped around 30 requests/minute and ~250 requests/day,
with a tokens-per-minute ceiling underneath that. Both 429 (rate limit)
and 413 (request too large) errors on this tier are usually the same
underlying "you're over the ceiling right now" condition, not an actually
oversized request -- so both are retried with a backoff.

Requires a Groq API key:
    export GROQ_API_KEY=gsk_...   (PowerShell: $env:GROQ_API_KEY="gsk_...")
    pip install groq --break-system-packages

Usage:
    python phase1_ai_ground_truth.py brands.txt --out ground_truth.csv
"""

import argparse
import csv
import os
import re
import sys
import time

try:
    from groq import Groq
except ImportError:
    print("Run: pip install groq --break-system-packages", file=sys.stderr)
    sys.exit(1)


WAIT_PATTERN = re.compile(r"try again in ([\d.]+)s", re.IGNORECASE)


def load_brands(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "," in line:
                brand, domain = [p.strip() for p in line.split(",", 1)]
            else:
                brand, domain = line, ""
            rows.append((brand, domain))
    return rows


def extract_wait_seconds(error_message, default=20.0):
    match = WAIT_PATTERN.search(error_message)
    if match:
        return float(match.group(1)) + 1.0  # small buffer
    return default


def ask_about_brand(client, brand, model="groq/compound", max_retries=6):
    """Ask the model about a brand, retrying through rate limits. Returns
    (answer, used_search, sources, attempts_used)."""
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": f"Tell me about {brand}. What do they do, and what's notable about them?"}
                ],
            )
            message = response.choices[0].message
            answer = message.content or ""

            executed_tools = getattr(message, "executed_tools", None) or []
            used_search = False
            sources = []

            for tool_call in executed_tools:
                tool_type = getattr(tool_call, "type", "") or str(tool_call.__dict__.get("type", ""))
                if "search" in tool_type.lower():
                    used_search = True
                output = getattr(tool_call, "output", None) or getattr(tool_call, "search_results", None)
                if output:
                    text = str(output)
                    for token in text.split():
                        if token.startswith("http"):
                            sources.append(token.strip('",)]'))

            return answer, used_search, sources, attempt

        except Exception as e:
            last_error = e
            msg = str(e)
            is_rate_or_size = ("429" in msg) or ("413" in msg) or ("rate_limit" in msg.lower()) or ("request_too_large" in msg.lower())
            if not is_rate_or_size or attempt == max_retries:
                raise
            wait_s = extract_wait_seconds(msg, default=15.0 * attempt)  # backoff grows if no hint given
            print(f"    -> rate/size limited (attempt {attempt}/{max_retries}), waiting {wait_s:.1f}s...")
            time.sleep(wait_s)

    raise last_error


def main():
    parser = argparse.ArgumentParser(description="Semi-automated AI ground-truth pass for Phase 1 (Groq)")
    parser.add_argument("brands_file", help="Text file: one 'brand, domain' per line")
    parser.add_argument("--out", default="ground_truth.csv")
    parser.add_argument("--model", default="groq/compound", help="groq/compound or groq/compound-mini")
    parser.add_argument("--delay", type=float, default=8.0, help="Seconds between requests (free tier is ~30/min)")
    parser.add_argument("--max-retries", type=int, default=6)
    args = parser.parse_args()

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("Set GROQ_API_KEY first.", file=sys.stderr)
        sys.exit(1)

    client = Groq(api_key=api_key)
    brands = load_brands(args.brands_file)

    rows = []
    for i, (brand, domain) in enumerate(brands, 1):
        print(f"[{i}/{len(brands)}] Asking about: {brand}")
        try:
            answer, used_search, sources, attempts = ask_about_brand(
                client, brand, args.model, args.max_retries
            )
        except Exception as e:
            print(f"    -> gave up after retries: {e}")
            rows.append({
                "brand": brand, "domain": domain, "used_search": "",
                "sources": "", "own_domain_cited": "", "answer": f"ERROR: {e}",
                "your_judgment": "",
            })
            time.sleep(args.delay)
            continue

        own_domain_cited = bool(domain) and any(domain in s for s in sources)
        rows.append({
            "brand": brand,
            "domain": domain,
            "used_search": used_search,
            "sources": " | ".join(sources[:8]),
            "own_domain_cited": own_domain_cited,
            "answer": answer.replace("\n", " ")[:2000],
            "your_judgment": "",  # fill in manually after reading: well / wrong / invisible
        })
        time.sleep(args.delay)

    fieldnames = ["brand", "domain", "used_search", "sources", "own_domain_cited", "answer", "your_judgment"]
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    ok_count = sum(1 for r in rows if not str(r["answer"]).startswith("ERROR"))
    print(f"\nDone. Wrote {len(rows)} rows to {args.out} ({ok_count} succeeded, {len(rows) - ok_count} still errored).")
    if ok_count < len(rows):
        print("If some rows still errored: rerun just those brands in a smaller")
        print("brands.txt, or increase --delay (e.g. --delay 15), or try")
        print("--model groq/compound-mini which uses fewer tokens per call.")
    print("\nNext: open the CSV, read each 'answer', and fill in 'your_judgment'")
    print("as well / wrong / invisible. Then join with phase1_results.csv on")
    print("brand/domain to see which technical flags cluster with poor judgments.")


if __name__ == "__main__":
    main()
