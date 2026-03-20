"""
grants.ca.gov - Full Detail Scraper
Reads grant titles from the downloaded CSV, visits each detail page,
and saves results as a JSON array matching the target schema.

Requirements:
    pip install requests beautifulsoup4 pandas

Usage:
    python grants_scraper.py

Input:  grants_ca_gov_nonprofits.csv  (must be in the same folder)
Output: grants_ca_gov_details.json
"""

import json
import time
import re
import requests
from bs4 import BeautifulSoup
import pandas as pd

# ── Config ────────────────────────────────────────────────────────────────────

INPUT_FILE  = "data/grants_ca_gov_nonprofits.csv"
OUTPUT_FILE = "grants_ca_gov_details.json"
DELAY = 1.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

session = requests.Session()
session.headers.update(HEADERS)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_soup(url: str) -> BeautifulSoup:
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def txt(el) -> str:
    return el.get_text(" ", strip=True) if el else ""


def title_to_url(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return f"https://www.grants.ca.gov/grants/{slug}/"


def dl_map(soup) -> dict:
    """Return all dt/dd pairs as a flat dict."""
    out = {}
    for dl in soup.select("dl"):
        for dt in dl.select("dt"):
            key = txt(dt).rstrip(":").strip()
            dd = dt.find_next_sibling("dd")
            if dd:
                out[key] = txt(dd)
    return out


def section_text(soup, heading: str) -> str | None:
    """Return body text under a named h3 heading."""
    h3 = soup.find("h3", string=re.compile(re.escape(heading), re.I))
    if not h3:
        return None
    parts = []
    for sib in h3.find_next_siblings():
        if sib.name in ("h2", "h3", "h4"):
            break
        t = txt(sib)
        if t:
            parts.append(t)
    return " ".join(parts) if parts else None


def parse_amount(val: str | None) -> str | None:
    """Return dollar string or None."""
    if not val or val.strip().lower() in ("", "dependent", "n/a"):
        return None
    return val.strip()


def parse_date(val: str | None) -> str | None:
    """Normalise date strings; return None if empty/unknown."""
    if not val or val.strip().lower() in ("", "n/a", "ongoing", "dependent"):
        return None
    return val.strip()


# ── Detail page scraper ───────────────────────────────────────────────────────

def scrape_detail(url: str, row: dict) -> dict:
    soup = get_soup(url)
    kv  = dl_map(soup)

    # ── Eligibility list ──────────────────────────────────────────────────────
    eligibility = []
    elig_h3 = soup.find("h3", string=re.compile(r"Eligible Applicants", re.I))
    if elig_h3:
        ul = elig_h3.find_next("ul")
        if ul:
            eligibility = [li.get_text(strip=True) for li in ul.select("li")]
        else:
            # Sometimes plain text, not a list
            raw = section_text(soup, "Eligible Applicants")
            if raw:
                eligibility = [s.strip() for s in re.split(r"[,\n|]", raw) if s.strip()]

    # ── Contact fields ────────────────────────────────────────────────────────
    contact_raw = None
    for dt in soup.select("dt"):
        if "contact" in txt(dt).lower():
            dd = dt.find_next_sibling("dd")
            contact_raw = txt(dd)
            break

    contact_name  = None
    contact_email = None
    contact_phone = None
    if contact_raw:
        email_m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", contact_raw)
        phone_m = re.search(r"[\d\-().+ ]{7,}", contact_raw)
        contact_email = email_m.group(0) if email_m else None
        contact_phone = phone_m.group(0).strip() if phone_m else None
        # Name = everything before the first comma / phone / email
        name_part = re.split(r",|\d{3}", contact_raw)[0].strip()
        contact_name = name_part if name_part else None

    # ── Apply / resource links ────────────────────────────────────────────────
    apply_links = []
    apply_h2 = soup.find("h2", string=re.compile(r"How to Apply", re.I))
    if apply_h2:
        ul = apply_h2.find_next("ul")
        if ul:
            apply_links = [a.get("href", "") for a in ul.select("a")]

    # ── Funding details from CSV row (fallback) + page ────────────────────────
    total_funding_raw = kv.get(
        "Total estimated available funding",
        row.get("Estimated Total Funding", "")
    )
    low_high_raw = kv.get(
        "Estimated amount per award",
        row.get("Estimated Low/High", "")
    )

    low_amt = high_amt = None
    if low_high_raw and "–" in low_high_raw:
        parts = [p.strip() for p in low_high_raw.split("–")]
        low_amt  = parse_amount(parts[0])
        high_amt = parse_amount(parts[1]) if len(parts) > 1 else None

    # ── Build output record ───────────────────────────────────────────────────
    record = {
        "grant_id":               kv.get("Portal ID"),
        "opportunity_number":     None,           # not on this site
        "title":                  txt(soup.select_one("h1")),
        "funder_name":            kv.get("Grantor"),
        "top_agency":             kv.get("Grantor"),   # same source; no parent listed
        "agency_code":            None,
        "description":            section_text(soup, "Description")
                                  or section_text(soup, "Purpose"),
        "max_award_amount":       high_amt,
        "min_award_amount":       low_amt,
        "estimated_total_funding": parse_amount(total_funding_raw),
        "expected_num_awards":    parse_amount(kv.get("Expected number of awards")),
        "cost_sharing_required":  (
            row.get("Match Funding", "No").strip().lower() not in ("no", "", "none")
        ),
        "opportunity_status":     kv.get("Status", row.get("Deadline", "")).lower() or None,
        "opportunity_category":   ", ".join(
            kv.get("Categories", row.get("Grant Title", "")).split()[:3]
        ) or None,
        "funding_instrument_types": [
            v.strip() for v in kv.get("Opportunity Type", "Grant").split(",")
        ],
        "funding_activity_categories": [
            c.strip()
            for c in kv.get("Categories", "").split(",")
            if c.strip()
        ] or None,
        "eligibility":            eligibility or None,
        "cfda_aln_numbers":       None,
        "contact_name":           contact_name,
        "contact_email":          contact_email,
        "contact_phone":          contact_phone,
        "post_date":              parse_date(
            kv.get("Open Date", row.get("Open Date", ""))
        ),
        "close_date":             parse_date(
            kv.get("Deadline", row.get("Deadline", ""))
            .replace("Active", "").strip()
        ),
        "archive_date":           None,
        "grants_gov_url":         url,
        "apply_links":            apply_links or None,
        "matching_funding_requirement": section_text(soup, "Matching Funding Requirement"),
        "eligible_geographies":   section_text(soup, "Eligible Geographies"),
        "funding_source":         kv.get("Funding Source"),
        "funding_method":         kv.get("Funding Method",
                                         row.get("Funds Disbursement")),
        "period_of_performance":  kv.get("Period of performance"),
        "expected_award_announcement": kv.get("Expected award announcement"),
    }

    return record


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("grants.ca.gov → JSON Detail Scraper")
    print("=" * 60)

    df = pd.read_csv(INPUT_FILE)
    print(f"Loaded {len(df)} grants from {INPUT_FILE}\n")

    results = []
    for i, row in df.iterrows():
        title = str(row.get("Grant Title", "")).strip()
        if not title:
            continue
        url = title_to_url(title)
        print(f"[{i+1}/{len(df)}] {url}")
        try:
            record = scrape_detail(url, row.to_dict())
            results.append(record)
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({
                "grant_id": None,
                "title": title,
                "grants_gov_url": url,
                "error": str(e),
            })
        time.sleep(DELAY)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nDone! Saved {len(results)} grants to '{OUTPUT_FILE}'")


if __name__ == "__main__":
    main()