"""
Phase 5.1 validation: _is_english_site() pre-exclusion rate check

Targets: URLs that were rejected by scraper_agent as
"Japanese page not found (overseas company, English site)"
in the 108-minute listup log.
"""
import sys
import os
import re
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.search_agent import _is_english_site
from config import count_japanese_chars

TARGETS = [
    {"url": "https://www.pcmag.com",          "expected": "exclude",    "note": "US IT media"},
    {"url": "https://expertinsights.com",      "expected": "exclude",    "note": "US IT site"},
    {"url": "https://www.comparitech.com",     "expected": "exclude",    "note": "US IT site"},
    {"url": "https://geekflare.com",           "expected": "exclude",    "note": "US IT site"},
    {"url": "https://www.tateandlyle.com",     "expected": "exclude",    "note": "UK food company"},
    {"url": "https://www.hatarako.net",        "expected": "pass",       "note": "Japanese job portal"},
    {"url": "https://www.oricon.co.jp",        "expected": "pass_co_jp", "note": ".co.jp -> spec pass (scraper handles)"},
    {"url": "https://www.academy.co.jp",       "expected": "pass_co_jp", "note": ".co.jp -> spec pass (scraper handles)"},
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

JP_LEGAL_KW = ["株式会社", "有限会社", "合同会社",
               "一般社団法人", "一般財団法人", "学校法人", "医療法人"]


def fetch_title_and_snippet(url: str, timeout: int = 10) -> tuple[str, str]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        soup = BeautifulSoup(resp.content, "html.parser")
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""
        meta_desc = ""
        for meta in soup.find_all("meta"):
            name = meta.get("name", "").lower()
            prop = meta.get("property", "").lower()
            if name in ("description", "og:description") or prop == "og:description":
                meta_desc = meta.get("content", "")
                if meta_desc:
                    break
        return title[:120], meta_desc[:200]
    except Exception as e:
        return f"[FETCH FAILED: {type(e).__name__}]", ""


def trunc(s: str, n: int) -> str:
    return s[:n] + "..." if len(s) > n else s


def main():
    sep = "=" * 78
    print(sep)
    print("Phase 5.1 Validation: _is_english_site() pre-exclusion check")
    print(sep)
    print()

    rows = []
    exclude_ok = 0
    exclude_total = 0
    spec_pass = 0
    miss = 0

    for item in TARGETS:
        url = item["url"]
        expected = item["expected"]
        note = item["note"]

        print(f"  Fetching: {url}")
        title, snippet = fetch_title_and_snippet(url)

        ja = count_japanese_chars(title + " " + snippet)
        legal = any(kw in title for kw in JP_LEGAL_KW)
        is_eng = _is_english_site(url, title, snippet)

        result_str = "EXCLUDE" if is_eng else "PASS"

        if expected == "exclude":
            exclude_total += 1
            if is_eng:
                verdict = "[OK] correct exclusion"
                exclude_ok += 1
            else:
                verdict = "[NG] MISS - should have been excluded"
                miss += 1
        elif expected == "pass_co_jp":
            spec_pass += 1
            verdict = "[SPEC] .co.jp always passes" if not is_eng else "[!!] unexpected exclusion"
        else:
            verdict = "[OK] correct pass" if not is_eng else "[NG] false exclusion"

        rows.append({
            "url": url,
            "title": trunc(title, 40),
            "snippet": trunc(snippet, 55),
            "ja": ja,
            "legal": "YES" if legal else "NO",
            "result": result_str,
            "verdict": verdict,
            "note": note,
        })

    print()
    print("-" * 78)
    hdr = f"{'URL':<36} {'JA':>4} {'Legal':>6} {'Result':<9} {'Verdict'}"
    print(hdr)
    print("-" * 78)
    for r in rows:
        print(f"{r['url'][:36]:<36} {r['ja']:>4} {r['legal']:>6} {r['result']:<9} {r['verdict']}")
        print(f"  title  : {r['title']}")
        print(f"  snippet: {r['snippet']}")
        print(f"  note   : {r['note']}")
        print()

    print("=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"Targets total    : {len(TARGETS)}")
    print(f"  Should exclude : {exclude_total}  (non-Japanese, overseas sites)")
    print(f"  Spec .co.jp    : {spec_pass}   (always pass; scraper handles)")
    print()

    if exclude_total > 0:
        rate = exclude_ok / exclude_total * 100
        print(f"Pre-exclusion rate: {exclude_ok}/{exclude_total} = {rate:.0f}%")
        if miss > 0:
            print(f"Misses (should exclude but passed): {miss}")
            for r in rows:
                if "MISS" in r["verdict"]:
                    print(f"  -> {r['url']}")
                    print(f"     title  : {r['title']}")
                    print(f"     snippet: {r['snippet']}")
    else:
        rate = 0

    print()
    print("DEPLOY RECOMMENDATION:")
    if rate >= 70:
        print(f"  GO  - {rate:.0f}% >= 70% threshold. Safe to deploy.")
    elif rate >= 50:
        print(f"  WAIT - {rate:.0f}% is 50-70%. Review misses before deciding.")
    else:
        print(f"  NO  - {rate:.0f}% < 50%. Revisit filter logic before deploy.")

    print()
    print("NOTE: .co.jp sites (oricon, academy) are spec-pass in _is_english_site().")
    print("      They continue to be caught by scraper_agent's page-content check.")


if __name__ == "__main__":
    main()
