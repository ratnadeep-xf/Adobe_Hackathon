#!/usr/bin/env python3
"""
Phase 1 Field Research — automated technical audit across a batch of sites.

What this automates (fully, no judgment calls needed):
  - robots.txt presence + whether it blocks common crawlers
  - sitemap.xml presence (declared in robots.txt or at the default path)
  - JSON-LD / schema.org structured data presence and basic validity
  - "JS-shell" heuristic: ratio of visible text to raw HTML size, as a proxy
    for how much content only appears after JavaScript execution
  - freshness signals: copyright year found in footer text, HTTP
    Last-Modified header if present
  - basic on-page orientation signals: presence/length of meta description,
    title tag, H1 count (rough proxy for "engagement" clarity)

What this does NOT automate (see phase1_ai_ground_truth.py for a
semi-automated version of this half):
  - Actually asking an AI assistant "tell me about [brand]" and judging
    whether the answer is accurate/well-cited. That's a judgment call.

Usage:
    pip install requests beautifulsoup4 --break-system-packages
    python phase1_field_research.py sites.txt --out results.csv

sites.txt: one URL per line, '#' for comments, blank lines ignored.
"""

import argparse
import csv
import re
import sys
import time
from dataclasses import dataclass, asdict
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; FieldResearchBot/1.0; +research-only)"
TIMEOUT = 10
COMMON_CRAWLER_TOKENS = ["*", "googlebot", "bingbot", "gptbot", "ccbot", "perplexitybot"]


@dataclass
class SiteReport:
    url: str
    reachable: bool = False
    status_code: int = None
    robots_txt_present: bool = False
    robots_blocks_common_crawlers: bool = False
    sitemap_present: bool = False
    sitemap_source: str = ""
    jsonld_present: bool = False
    jsonld_block_count: int = 0
    jsonld_types_found: str = ""
    visible_text_chars: int = 0
    raw_html_chars: int = 0
    text_to_html_ratio: float = 0.0
    js_shell_suspected: bool = False
    title_present: bool = False
    title_text: str = ""
    meta_description_present: bool = False
    meta_description_length: int = 0
    h1_count: int = 0
    copyright_year_found: str = ""
    last_modified_header: str = ""
    error: str = ""


def fetch(url, timeout=TIMEOUT):
    return requests.get(
        url, headers={"User-Agent": USER_AGENT}, timeout=timeout, allow_redirects=True
    )


def check_robots(base_url):
    """Returns (present, blocks_common_crawlers, sitemap_url_or_None)."""
    robots_url = urljoin(base_url, "/robots.txt")
    try:
        resp = fetch(robots_url)
    except requests.RequestException:
        return False, False, None

    if resp.status_code != 200 or not resp.text.strip():
        return False, False, None

    text = resp.text.lower()
    blocks_common = False
    current_agent_is_common = False
    sitemap_url = None

    for raw_line in resp.text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()

        if key == "user-agent":
            agent = value.lower()
            current_agent_is_common = agent in COMMON_CRAWLER_TOKENS
        elif key == "disallow" and current_agent_is_common:
            if value == "/":
                blocks_common = True
        elif key == "sitemap":
            sitemap_url = value

    return True, blocks_common, sitemap_url


def check_sitemap(base_url, robots_sitemap_url):
    if robots_sitemap_url:
        try:
            resp = fetch(robots_sitemap_url)
            if resp.status_code == 200 and "<urlset" in resp.text.lower() or "<sitemapindex" in resp.text.lower():
                return True, "declared in robots.txt"
        except requests.RequestException:
            pass

    default_url = urljoin(base_url, "/sitemap.xml")
    try:
        resp = fetch(default_url)
        if resp.status_code == 200 and ("<urlset" in resp.text.lower() or "<sitemapindex" in resp.text.lower()):
            return True, "default /sitemap.xml"
    except requests.RequestException:
        pass

    return False, ""


def check_jsonld(soup):
    scripts = soup.find_all("script", type="application/ld+json")
    types_found = set()
    for s in scripts:
        content = s.string or ""
        matches = re.findall(r'"@type"\s*:\s*"([^"]+)"', content)
        types_found.update(matches)
    return len(scripts) > 0, len(scripts), ", ".join(sorted(types_found))


def check_js_shell(html_text, soup):
    visible_text = soup.get_text(separator=" ", strip=True)
    text_len = len(visible_text)
    html_len = len(html_text)
    ratio = (text_len / html_len) if html_len else 0.0
    # Heuristic threshold — low text-to-HTML ratio + short absolute text
    # suggests most content is assembled client-side (a "JS shell").
    suspected = ratio < 0.05 and text_len < 500
    return text_len, html_len, ratio, suspected


def check_freshness(soup):
    text = soup.get_text(separator=" ", strip=True)
    match = re.search(r"(?:©|copyright)\s*(\d{4})", text, re.IGNORECASE)
    return match.group(1) if match else ""


def check_onpage_signals(soup):
    title_tag = soup.find("title")
    title_present = bool(title_tag and title_tag.get_text(strip=True))
    title_text = title_tag.get_text(strip=True) if title_present else ""

    meta_desc = soup.find("meta", attrs={"name": re.compile("description", re.I)})
    meta_present = bool(meta_desc and meta_desc.get("content", "").strip())
    meta_len = len(meta_desc.get("content", "").strip()) if meta_present else 0

    h1_count = len(soup.find_all("h1"))

    return title_present, title_text, meta_present, meta_len, h1_count


def audit_site(url):
    report = SiteReport(url=url)
    if not url.startswith("http"):
        url = "https://" + url
        report.url = url

    try:
        resp = fetch(url)
    except requests.RequestException as e:
        report.error = str(e)
        return report

    report.reachable = True
    report.status_code = resp.status_code
    report.last_modified_header = resp.headers.get("Last-Modified", "")

    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

    robots_present, blocks_common, robots_sitemap = check_robots(base)
    report.robots_txt_present = robots_present
    report.robots_blocks_common_crawlers = blocks_common

    sitemap_present, sitemap_source = check_sitemap(base, robots_sitemap)
    report.sitemap_present = sitemap_present
    report.sitemap_source = sitemap_source

    soup = BeautifulSoup(resp.text, "html.parser")

    jsonld_present, jsonld_count, jsonld_types = check_jsonld(soup)
    report.jsonld_present = jsonld_present
    report.jsonld_block_count = jsonld_count
    report.jsonld_types_found = jsonld_types

    text_len, html_len, ratio, js_shell = check_js_shell(resp.text, soup)
    report.visible_text_chars = text_len
    report.raw_html_chars = html_len
    report.text_to_html_ratio = round(ratio, 4)
    report.js_shell_suspected = js_shell

    report.copyright_year_found = check_freshness(soup)

    title_present, title_text, meta_present, meta_len, h1_count = check_onpage_signals(soup)
    report.title_present = title_present
    report.title_text = title_text[:120]
    report.meta_description_present = meta_present
    report.meta_description_length = meta_len
    report.h1_count = h1_count

    return report


def load_sites(path):
    sites = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            sites.append(line)
    return sites


def main():
    parser = argparse.ArgumentParser(description="Automated Phase 1 technical field research")
    parser.add_argument("sites_file", help="Text file with one URL per line")
    parser.add_argument("--out", default="phase1_results.csv", help="Output CSV path")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between requests (be polite)")
    args = parser.parse_args()

    sites = load_sites(args.sites_file)
    if not sites:
        print("No sites found in input file.", file=sys.stderr)
        sys.exit(1)

    reports = []
    for i, site in enumerate(sites, 1):
        print(f"[{i}/{len(sites)}] Auditing {site} ...")
        report = audit_site(site)
        reports.append(report)
        if report.error:
            print(f"    -> error: {report.error}")
        else:
            flags = []
            if report.js_shell_suspected:
                flags.append("JS-SHELL-SUSPECTED")
            if not report.jsonld_present:
                flags.append("NO-JSONLD")
            if not report.robots_txt_present:
                flags.append("NO-ROBOTS")
            if not report.sitemap_present:
                flags.append("NO-SITEMAP")
            if not report.copyright_year_found:
                flags.append("NO-FRESHNESS-SIGNAL")
            print(f"    -> {', '.join(flags) if flags else 'no red flags from automated checks'}")
        time.sleep(args.delay)

    fieldnames = list(asdict(reports[0]).keys())
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in reports:
            writer.writerow(asdict(r))

    print(f"\nDone. Wrote {len(reports)} rows to {args.out}")
    print("Next: open the CSV, sort by the flag columns, and look for which")
    print("combinations of flags cluster with sites you already know are")
    print("poorly cited by AI assistants (cross-reference with the ground-truth")
    print("pass — see phase1_ai_ground_truth.py or do it manually).")


if __name__ == "__main__":
    main()
