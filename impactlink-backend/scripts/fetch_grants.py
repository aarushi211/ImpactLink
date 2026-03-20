"""
scripts/fetch_grants.py
═══════════════════════════════════════════════════════════════════════════════
ImpactLink — Multi-Source Grant Data Extraction Pipeline
═══════════════════════════════════════════════════════════════════════════════
"""

import os, json, time, argparse, hashlib
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

try:
    import requests
except ImportError:
    raise SystemExit("Run: pip install requests")

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════

SIMPLER_API_KEY = os.getenv("SIMPLER_GRANTS_API_KEY", "")
OUTPUT_DIR      = Path("data")
OUTPUT_FILE     = OUTPUT_DIR / "grants_enriched.json"
UA              = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
HEADERS         = {"User-Agent": UA}

def _post(url, payload, extra_headers=None, timeout=20):
    h = {**HEADERS, "Content-Type": "application/json", **(extra_headers or {})}
    r = requests.post(url, json=payload, headers=h, timeout=timeout)
    r.raise_for_status()
    return r.json()

def _get(url, params=None, extra_headers=None, timeout=20):
    h = {**HEADERS, **(extra_headers or {})}
    r = requests.get(url, params=params, headers=h, timeout=timeout)
    r.raise_for_status()
    return r.json()

# ══════════════════════════════════════════════════════════════════════════════
# PORTAL INFO TABLE  
# ══════════════════════════════════════════════════════════════════════════════

PORTAL_INFO = {
    "NSF Research.gov": {"apply_url": "https://www.research.gov", "requires_sam": True},
    "NIH ASSIST": {"apply_url": "https://public.era.nih.gov/assist", "requires_sam": True},
    "Grants.gov": {"apply_url": "https://www.grants.gov", "requires_sam": True},
    "Simpler Grants.gov": {"apply_url": "https://simpler.grants.gov", "requires_sam": True},
    "California Grants Portal": {"apply_url": "https://www.grants.ca.gov", "requires_sam": False},
    "Illinois GATA Portal": {"apply_url": "https://grants.illinois.gov/portal/", "requires_sam": True},
    "NY Grants Gateway": {"apply_url": "https://grantsgateway.ny.gov", "requires_sam": False},
}
FALLBACK_PORTAL = PORTAL_INFO["Grants.gov"]

def portal_from_agency(code):
    code = (code or "").upper()
    if "NSF" in code: return "NSF Research.gov"
    if "NIH" in code or "HHS" in code: return "NIH ASSIST"
    if "CA-STATE" in code: return "California Grants Portal"
    return "Grants.gov"

# ══════════════════════════════════════════════════════════════════════════════
# SOURCE 1 — Simpler Grants API (Fixed 422 Error & Response Parsing)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_simpler(keywords="", limit=100):
    if not SIMPLER_API_KEY:
        print("  ⚠  No SIMPLER_GRANTS_API_KEY — falling back to legacy grants.gov\n")
        return fetch_legacy(keywords=keywords, limit=limit)

    print("  [Simpler.grants.gov] Fetching federal grants...")
    results, page = [], 1
    
    # 2026 Constraint: Strict 100 character limit
    clean_query = (keywords or "nonprofit").strip()[:99]

    while len(results) < limit:
        # Fixed Payload: Exact enum values and 'page_offset' key required
        payload = {
            "query": clean_query,
            "pagination": {
                "page_offset": page,
                "page_size": min(25, limit - len(results)),
                "sort_order": [{"order_by": "close_date", "sort_direction": "ascending"}]
            },
            "filters": {
                "opportunity_status": {"one_of": ["posted"]},
                "applicant_type": {"one_of": ["nonprofits"]}
            }
        }
        try:
            data = _post("https://api.simpler.grants.gov/v1/opportunities/search",
                         payload, {"X-API-Key": SIMPLER_API_KEY})
            batch = data.get("data", [])
            if not batch: break
            results.extend(batch)
            print(f"     Page {page}: +{len(batch)} grants")
            if len(batch) < 25: break
            page += 1
            time.sleep(0.5)
        except Exception as e:
            print(f"     ✗ Simpler API Error: {e}")
            break

    out = [_norm_simpler(r) for r in results[:limit]]
    print(f"  ✓ Simpler.grants.gov: {len(out)} grants\n")
    return out

def _norm_simpler(raw):
    oid = raw.get("opportunity_id", "")
    num = raw.get("opportunity_number", "")
    
    # Flat JSON structure support
    return {
        "id": num or oid,
        "source": "simpler_grants",
        "number": num,
        "title": raw.get("opportunity_title", "Untitled Grant"),
        "agency": raw.get("agency_name", "Federal Agency"),
        "openDate": raw.get("post_date", ""),
        "closeDate": raw.get("close_date", ""),
        "oppStatus": raw.get("opportunity_status", "posted"),
        "award_floor": int(raw.get("award_floor", 0) or 0),
        "award_ceiling": int(raw.get("award_ceiling", 0) or 0),
        "geography": ["Federal"],
        "eligibility": "nonprofits",
        "application_url": f"https://simpler.grants.gov/opportunity/{oid}",
        "requires_sam": True,
        "application_portal": "Simpler Grants.gov"
    }

# ══════════════════════════════════════════════════════════════════════════════
# SOURCE 2 — Legacy Grants.gov (Fallback)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_legacy(keywords="", limit=50):
    print("  [grants.gov legacy API] Fetching federal grants (no key needed)...")
    results = []
    payload = {
        "keyword": keywords[:99],
        "oppStatuses": "posted",
        "eligibilities": "25",
        "rows": min(25, limit),
        "startRecordNum": 0,
    }
    try:
        data = _post("https://api.grants.gov/v1/api/search2", payload)
        results.extend(data.get("oppHits", []))
    except Exception as e:
        print(f"     ✗ Legacy API Error: {e}")

    return [_norm_legacy(r) for r in results[:limit]]

def _norm_legacy(raw):
    gid = str(raw.get("id", ""))
    return {
        "id": gid,
        "source": "grants_gov",
        "title": raw.get("title", ""),
        "agency": raw.get("agencyName", ""),
        "closeDate": raw.get("closeDate", ""),
        "application_url": f"https://www.grants.gov/search-results-detail/{gid}",
        "requires_sam": True,
        "application_portal": "Grants.gov"
    }

# ══════════════════════════════════════════════════════════════════════════════
# SOURCE 3 & 4 — State Open Data APIs & Scrapers 
# ══════════════════════════════════════════════════════════════════════════════

def fetch_california(keywords="", limit=100):
    print("  [California Grants Portal / data.ca.gov] Fetching CA state grants...")
    # Socrata ID
    CA_API = "https://data.ca.gov/api/3/action/datastore_search"
    params = {"resource_id": "111c8c88-21f6-453c-ae2c-b4785a0624f5", "limit": limit}
    if keywords: params["q"] = keywords
    
    try:
        data = _get(CA_API, params=params)
        results = data.get("result", {}).get("records", [])
        out = []
        for r in results:
            url = r.get("How to Apply URL", r.get("grantUrl", ""))
            out.append({
                "id": f"ca_{r.get('_id', '')}",
                "source": "california_grants",
                "title": r.get("Grant Name", "CA Grant"),
                "agency": r.get("Agency Name", "CA Agency"),
                "closeDate": r.get("Application Due Date", ""),
                "application_url": url or "https://www.grants.ca.gov",
                "requires_sam": False,
                "application_portal": "California Grants Portal"
            })
        print(f"  ✓ California Grants Portal: {len(out)} grants\n")
        return out
    except Exception as e:
        print(f"     ✗ CA API error: {e}")
        return []

def fetch_newyork(limit=50):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    print("  [NY Grants Gateway] Scraping grantsmanagement.ny.gov ...")
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA)
        try:
            page.goto("https://grantsmanagement.ny.gov/opportunities", wait_until="networkidle")
            # Force wait for JS list population
            page.wait_for_selector(".views-row a, article a", timeout=10000)
            
            links = page.query_selector_all(".views-row a, article a")
            seen = set()
            for link in links:
                href = link.get_attribute("href")
                title = link.inner_text().strip()
                if href and len(title) > 5 and href not in seen:
                    seen.add(href)
                    results.append({
                        "id": f"ny_{hashlib.md5(href.encode()).hexdigest()[:8]}",
                        "title": title,
                        "source": "newyork_gateway",
                        "application_url": href if href.startswith("http") else f"https://grantsmanagement.ny.gov{href}",
                        "requires_sam": False,
                        "application_portal": "NY Grants Gateway"
                    })
                if len(results) >= limit: break
        except Exception as e:
            print(f"     ✗ NY Scrape Error: {e}")
        finally:
            browser.close()
            
    print(f"  ✓ New York Grants Gateway: {len(results)} grants\n")
    return results

# ══════════════════════════════════════════════════════════════════════════════
# MAIN RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="ImpactLink grant pipeline")
    ap.add_argument("--source", choices=["all","federal","california","newyork"], default="all")
    ap.add_argument("--keywords", default="nonprofit education community")
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    grants = []

    if args.source in ("all", "federal"):
        grants.extend(fetch_simpler(args.keywords, args.limit))
    if args.source in ("all", "california"):
        grants.extend(fetch_california(args.keywords, args.limit))
    if args.source in ("all", "newyork"):
        grants.extend(fetch_newyork(args.limit))

    # Deduplicate and save
    unique_grants = {g["id"]: g for g in grants if g.get("id")}
    final_list = list(unique_grants.values())
    
    out = {
        "metadata": {
            "last_updated": datetime.now().isoformat(),
            "total_grants": len(final_list)
        },
        "grants": final_list
    }
    
    OUTPUT_FILE.write_text(json.dumps(out, indent=2))
    print(f"\n✓ Saved {len(final_list)} grants to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()