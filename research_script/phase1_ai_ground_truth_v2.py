#!/usr/bin/env python3
"""
Phase 1 Field Research — ground-truth pass, decoupled version.

Instead of relying on Groq's `compound` models (which bundle web search
into the same tightly-rate-limited agentic-tool budget), this version does
the two steps separately:

  1. Search the web ourselves with DuckDuckGo — free, keyless, no account
     needed at all.
  2. Hand those real search results to a plain, high-free-tier-limit Groq
     model (default: openai/gpt-oss-20b) and ask it to answer using ONLY
     what was found, plus report which of the given sources it actually
     drew on.

This tests the same thing the compound-model version did ("what surfaces
when you look this brand up, and does the brand's own domain show up in
what a real search returns") without being bottlenecked by Groq's agentic-
tool rate limits.

Setup:
    pip install groq ddgs --break-system-packages
    export GROQ_API_KEY=gsk_...     (PowerShell: $env:GROQ_API_KEY="gsk_...")

Usage:
    python phase1_ai_ground_truth_v2.py brands.txt --out ground_truth.csv
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from urllib.parse import urlparse

try:
    from groq import Groq
except ImportError:
    print("Run: pip install groq --break-system-packages", file=sys.stderr)
    sys.exit(1)

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        print("Run: pip install ddgs --break-system-packages", file=sys.stderr)
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


def web_search(query, max_results=8, retries=3):
    """Free, keyless DuckDuckGo search. Returns list of {title, url, snippet}."""
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
        except Exception as e:
            last_err = e
            time.sleep(2 * attempt)
    print(f"    -> search failed after {retries} attempts: {last_err}")
    return []


def domain_of(url):
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return ""


def extract_wait_seconds(error_message, default=10.0):
    match = WAIT_PATTERN.search(error_message)
    if match:
        return float(match.group(1)) + 1.0
    return default


def ask_llm_about_brand(client, brand, search_results, model, max_retries=5):
    """Give the model the real search results and ask it to summarize using
    only those, plus report which sources it actually used."""
    context_lines = []
    for i, r in enumerate(search_results, 1):
        context_lines.append(f"[{i}] {r['title']} — {r['url']}\n    {r['snippet']}")
    context = "\n".join(context_lines) if context_lines else "(no search results found)"

    prompt = f"""Here are real web search results for the query "{brand}":

{context}

Based ONLY on the search results above, answer: what does {brand} do, and what's
notable about them? If the results don't contain enough to answer, say so plainly
instead of guessing.

Respond with ONLY a JSON object (no markdown fences, no preamble) in this exact shape:
{{"summary": "your answer here", "sources_used": [list of the [n] indices above that you actually drew on, e.g. 1, 3]}}"""

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            raw = response.choices[0].message.content or ""
            cleaned = raw.replace("```json", "").replace("```", "").strip()
            try:
                parsed = json.loads(cleaned)
                summary = parsed.get("summary", "")
                used_indices = parsed.get("sources_used", [])
            except json.JSONDecodeError:
                summary = raw  # fall back to raw text if it didn't follow the JSON format
                used_indices = []
            return summary, used_indices, attempt
        except Exception as e:
            last_error = e
            msg = str(e)
            is_rate = ("429" in msg) or ("rate_limit" in msg.lower())
            if not is_rate or attempt == max_retries:
                raise
            wait_s = extract_wait_seconds(msg, default=10.0 * attempt)
            print(f"    -> rate limited (attempt {attempt}/{max_retries}), waiting {wait_s:.1f}s...")
            time.sleep(wait_s)

    raise last_error


def main():
    parser = argparse.ArgumentParser(description="Decoupled search + LLM ground-truth pass for Phase 1")
    parser.add_argument("brands_file", help="Text file: one 'brand, domain' per line")
    parser.add_argument("--out", default="ground_truth.csv")
    parser.add_argument("--model", default="openai/gpt-oss-20b", help="Any plain (non-compound) Groq model")
    parser.add_argument("--max-results", type=int, default=8, help="Search results to fetch per brand")
    parser.add_argument("--delay", type=float, default=3.0, help="Seconds between brands")
    parser.add_argument("--max-retries", type=int, default=5)
    args = parser.parse_args()

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("Set GROQ_API_KEY first.", file=sys.stderr)
        sys.exit(1)

    client = Groq(api_key=api_key)
    brands = load_brands(args.brands_file)

    rows = []
    for i, (brand, domain) in enumerate(brands, 1):
        print(f"[{i}/{len(brands)}] Researching: {brand}")

        results = web_search(brand, max_results=args.max_results)
        result_domains = [domain_of(r["url"]) for r in results]
        own_domain_in_results = bool(domain) and any(domain in d for d in result_domains if d)

        try:
            summary, used_indices, attempts = ask_llm_about_brand(
                client, brand, results, args.model, args.max_retries
            )
        except Exception as e:
            print(f"    -> gave up after retries: {e}")
            rows.append({
                "brand": brand, "domain": domain,
                "num_search_results": len(results),
                "own_domain_in_search_results": own_domain_in_results,
                "result_domains": " | ".join(sorted(set(d for d in result_domains if d))),
                "own_domain_used_by_llm": "",
                "summary": f"ERROR: {e}",
                "your_judgment": "",
            })
            time.sleep(args.delay)
            continue

        used_urls = []
        for idx in used_indices:
            try:
                used_urls.append(results[int(idx) - 1]["url"])
            except (ValueError, IndexError, TypeError):
                continue
        own_domain_used_by_llm = bool(domain) and any(domain in u for u in used_urls)

        rows.append({
            "brand": brand,
            "domain": domain,
            "num_search_results": len(results),
            "own_domain_in_search_results": own_domain_in_results,
            "result_domains": " | ".join(sorted(set(d for d in result_domains if d))),
            "own_domain_used_by_llm": own_domain_used_by_llm,
            "summary": summary.replace("\n", " ")[:2000],
            "your_judgment": "",  # fill in manually after reading: well / wrong / invisible
        })
        time.sleep(args.delay)

    fieldnames = [
        "brand", "domain", "num_search_results", "own_domain_in_search_results",
        "result_domains", "own_domain_used_by_llm", "summary", "your_judgment",
    ]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    ok_count = sum(1 for r in rows if not str(r["summary"]).startswith("ERROR"))
    print(f"\nDone. Wrote {len(rows)} rows to {args.out} ({ok_count} succeeded, {len(rows) - ok_count} errored).")
    print("\nNew columns worth noting:")
    print("  own_domain_in_search_results — did the brand's own site even show up")
    print("    in a real search for its name? (a pure discoverability signal)")
    print("  own_domain_used_by_llm — did the model actually draw on the brand's")
    print("    own domain, vs. only third-party sources, when answering?")
    print("\nNext: open the CSV, read 'summary', fill in 'your_judgment' as")
    print("well / wrong / invisible, then cross-reference with phase1_results.csv.")


if __name__ == "__main__":
    main()
