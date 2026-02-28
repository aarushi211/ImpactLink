import json
import requests
from datetime import datetime

# Grants.gov public search API endpoint
SEARCH_URL = "https://apply07.grants.gov/grantsws/rest/opportunities/search/"

def fetch_grants(keyword="", rows=25, start_date=None, end_date=None, opportunity_status="forecasted,posted"):
    """
    Fetch grants from Grants.gov using their REST API.
    
    Args:
        keyword: Search keyword (empty = all grants)
        rows: Number of results to fetch (max 25 per request for pagination)
        start_date: Filter by post date start (MM/DD/YYYY)
        end_date: Filter by post date end (MM/DD/YYYY)
        opportunity_status: Comma-separated statuses (forecasted, posted, closed, archived)
    """
    payload = {
        "keyword": keyword,
        "oppStatuses": opportunity_status,
        "rows": rows,
        "startRecordNum": 0,
        "sortBy": "openDate|desc",
    }
    
    if start_date:
        payload["postDateFrom"] = start_date
    if end_date:
        payload["postDateTo"] = end_date

    print(f"Fetching grants from Grants.gov (keyword='{keyword}', rows={rows})...")
    
    response = requests.post(SEARCH_URL, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    
    raw_opportunities = data.get("oppHits", [])
    print(f"Found {data.get('hitCount', 0)} total grants; processing {len(raw_opportunities)} records.")
    
    grants = []
    for opp in raw_opportunities:
        grant = {
            "grant_id": opp.get("id"),
            "opportunity_number": opp.get("number"),
            "title": opp.get("title"),
            "funder_name": opp.get("agencyName"),
            "agency_code": opp.get("agency"),
            "description": opp.get("synopsis", {}).get("synopsisDesc") if opp.get("synopsis") else None,
            "max_award_amount": opp.get("synopsis", {}).get("awardCeiling") if opp.get("synopsis") else None,
            "min_award_amount": opp.get("synopsis", {}).get("awardFloor") if opp.get("synopsis") else None,
            "estimated_total_funding": opp.get("synopsis", {}).get("estimatedTotalProgramFunding") if opp.get("synopsis") else None,
            "expected_num_awards": opp.get("synopsis", {}).get("expectedNumberOfAwards") if opp.get("synopsis") else None,
            "opportunity_status": opp.get("oppStatus"),
            "opportunity_category": opp.get("oppCat"),
            "funding_instrument_type": opp.get("fundingInstrumentTypes"),
            "eligibility": opp.get("eligibilities"),
            "cfda_numbers": opp.get("cfdaNumbers"),
            "post_date": opp.get("openDate"),
            "close_date": opp.get("closeDate"),
            "archive_date": opp.get("archiveDate"),
            "grants_gov_url": f"https://www.grants.gov/search-results-detail/{opp.get('id')}" if opp.get("id") else None,
        }
        grants.append(grant)
    
    return grants, data.get("hitCount", 0)


def fetch_all_grants(keyword="", max_records=100, opportunity_status="forecasted,posted"):
    """Fetch multiple pages of grants."""
    all_grants = []
    batch_size = 25
    start = 0
    
    while start < max_records:
        payload = {
            "keyword": keyword,
            "oppStatuses": opportunity_status,
            "rows": min(batch_size, max_records - start),
            "startRecordNum": start,
            "sortBy": "openDate|desc",
        }
        
        response = requests.post(SEARCH_URL, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        raw_opportunities = data.get("oppHits", [])
        if not raw_opportunities:
            break
            
        total_hits = data.get("hitCount", 0)
        print(f"  Fetched records {start+1}–{start+len(raw_opportunities)} of {total_hits}")
        
        for opp in raw_opportunities:
            grant = {
                "grant_id": opp.get("id"),
                "opportunity_number": opp.get("number"),
                "title": opp.get("title"),
                "funder_name": opp.get("agencyName"),
                "agency_code": opp.get("agency"),
                "description": opp.get("synopsis", {}).get("synopsisDesc") if opp.get("synopsis") else None,
                "max_award_amount": opp.get("synopsis", {}).get("awardCeiling") if opp.get("synopsis") else None,
                "min_award_amount": opp.get("synopsis", {}).get("awardFloor") if opp.get("synopsis") else None,
                "estimated_total_funding": opp.get("synopsis", {}).get("estimatedTotalProgramFunding") if opp.get("synopsis") else None,
                "expected_num_awards": opp.get("synopsis", {}).get("expectedNumberOfAwards") if opp.get("synopsis") else None,
                "opportunity_status": opp.get("oppStatus"),
                "opportunity_category": opp.get("oppCat"),
                "funding_instrument_type": opp.get("fundingInstrumentTypes"),
                "eligibility": opp.get("eligibilities"),
                "cfda_numbers": opp.get("cfdaNumbers"),
                "post_date": opp.get("openDate"),
                "close_date": opp.get("closeDate"),
                "archive_date": opp.get("archiveDate"),
                "grants_gov_url": f"https://www.grants.gov/search-results-detail/{opp.get('id')}" if opp.get("id") else None,
            }
            all_grants.append(grant)
        
        start += batch_size
        if start >= total_hits:
            break
    
    return all_grants


if __name__ == "__main__":
    # ── CONFIG ──────────────────────────────────────────────────────────────
    KEYWORD = ""          # Leave blank for all grants, or e.g. "health", "education"
    MAX_RECORDS = 100     # How many grants to fetch total
    STATUS = "posted"     # "posted", "forecasted", "closed", "archived", or comma-separated combo
    OUTPUT_FILE = "grants.json"
    # ────────────────────────────────────────────────────────────────────────

    grants = fetch_all_grants(keyword=KEYWORD, max_records=MAX_RECORDS, opportunity_status=STATUS)

    output = {
        "metadata": {
            "source": "grants.gov",
            "extracted_at": datetime.utcnow().isoformat() + "Z",
            "keyword_filter": KEYWORD or "none",
            "status_filter": STATUS,
            "total_records": len(grants),
        },
        "grants": grants,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Saved {len(grants)} grants to '{OUTPUT_FILE}'")
    
    # Preview first grant
    if grants:
        print("\n── Sample grant ──────────────────────────────")
        sample = grants[0]
        for k, v in sample.items():
            if v is not None:
                print(f"  {k}: {str(v)[:120]}")