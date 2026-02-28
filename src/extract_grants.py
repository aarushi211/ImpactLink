import json
import time
import requests
from datetime import datetime

SEARCH_URL = "https://api.grants.gov/v1/api/search2"
DETAIL_URL = "https://api.grants.gov/v1/api/fetchOpportunity"


# ── API wrappers ──────────────────────────────────────────────────────────────

def search_grants(keyword="", rows=25, start_record=0, opp_statuses="posted"):
    """
    Call search2 and return (hits_list, total_hit_count).

    opp_statuses: pipe-separated string e.g. "posted" or "posted|forecasted"
    """
    payload = {
        "keyword":        keyword,
        "oppStatuses":    opp_statuses,   # MUST be pipe-separated, e.g. "posted|forecasted"
        "rows":           rows,
        "startRecordNum": start_record,
        "eligibilities":  "",
        "agencies":       "",
        "aln":            "",
        "fundingCategories": "",
    }

    resp = requests.post(
        SEARCH_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()

    # Response structure: { "errorcode": 0, "data": { "hitCount": N, "oppHits": [...] } }
    if body.get("errorcode") != 0:
        raise RuntimeError(f"search2 API error: {body.get('msg')} | payload={payload}")

    data  = body.get("data", {})
    hits  = data.get("oppHits", [])
    total = data.get("hitCount", 0)
    return hits, total


def fetch_detail(opp_id):
    """
    Call fetchOpportunity for one grant.
    Returns the inner 'data' dict, or None on failure.
    """
    try:
        resp = requests.post(
            DETAIL_URL,
            json={"opportunityId": int(opp_id)},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("errorcode") == 0:
            return body.get("data", {})
        print(f"    ⚠  fetchOpportunity non-zero errorcode for {opp_id}: {body.get('msg')}")
    except Exception as exc:
        print(f"    ⚠  fetchOpportunity failed for {opp_id}: {exc}")
    return None


# ── Data normalisation ────────────────────────────────────────────────────────

def build_grant(hit, detail):
    """Merge search hit + detail into a clean flat record."""

    # detail sub-objects (all may be absent)
    synopsis    = (detail or {}).get("synopsis") or {}
    ag_detail   = (detail or {}).get("agencyDetails") or {}
    top_ag      = (detail or {}).get("topAgencyDetails") or {}
    opp_cat_obj = (detail or {}).get("opportunityCategory") or {}
    alns        = (detail or {}).get("alns") or []

    # Funder name — richest available source wins
    funder_name = (
        synopsis.get("agencyName")
        or ag_detail.get("agencyName")
        or top_ag.get("agencyName")
        or hit.get("agencyName")   # search2 field name is agencyName
    )

    # Lists → human-readable strings
    eligibility = [
        t["description"]
        for t in synopsis.get("applicantTypes", [])
        if t.get("description")
    ]
    funding_instruments = [
        f["description"]
        for f in synopsis.get("fundingInstruments", [])
        if f.get("description")
    ]
    funding_categories = [
        c["description"]
        for c in synopsis.get("fundingActivityCategories", [])
        if c.get("description")
    ]
    cfda_numbers = [
        f"{a['alnNumber']} – {a.get('programTitle', '')}"
        for a in alns
        if a.get("alnNumber")
    ]

    return {
        "grant_id":                    str(hit.get("id") or (detail or {}).get("id", "")),
        "opportunity_number":          hit.get("number") or (detail or {}).get("opportunityNumber"),
        "title":                       hit.get("title") or (detail or {}).get("opportunityTitle"),
        "funder_name":                 funder_name,
        "top_agency":                  top_ag.get("agencyName"),
        "agency_code":                 hit.get("agencyCode") or synopsis.get("agencyCode"),
        "description":                 synopsis.get("synopsisDesc"),
        "max_award_amount":            synopsis.get("awardCeiling"),
        "min_award_amount":            synopsis.get("awardFloor"),
        "estimated_total_funding":     synopsis.get("estimatedTotalProgramFunding"),
        "expected_num_awards":         synopsis.get("expectedNumberOfAwards"),
        "cost_sharing_required":       synopsis.get("costSharing"),
        "opportunity_status":          hit.get("oppStatus"),
        "opportunity_category":        opp_cat_obj.get("description") if isinstance(opp_cat_obj, dict) else str(opp_cat_obj or ""),
        "funding_instrument_types":    funding_instruments or None,
        "funding_activity_categories": funding_categories or None,
        "eligibility":                 eligibility or None,
        "cfda_aln_numbers":            cfda_numbers or None,
        "contact_name":                synopsis.get("agencyContactName"),
        "contact_email":               synopsis.get("agencyContactEmail"),
        "contact_phone":               synopsis.get("agencyContactPhone") or synopsis.get("agencyPhone"),
        "post_date":                   hit.get("openDate"),
        "close_date":                  hit.get("closeDate") or synopsis.get("responseDateDesc"),
        "archive_date":                hit.get("archiveDate"),
        "grants_gov_url":              f"https://www.grants.gov/search-results-detail/{hit.get('id')}" if hit.get("id") else None,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def fetch_all_grants(keyword="", max_records=50, opp_statuses="posted", delay=0.25):
    """
    Search then enrich every grant with fetchOpportunity detail.

    Args:
        keyword:      Topic filter ("health", "education", …). Blank = all grants.
        max_records:  Maximum number of grants to retrieve.
        opp_statuses: Pipe-separated status filter: "posted", "forecasted",
                      "closed", "archived", or combos like "posted|forecasted".
        delay:        Seconds to sleep between detail calls (be polite to the API).
    """
    all_grants  = []
    batch_size  = 25
    start_rec   = 0

    print(f"\n🔍  Grants.gov search — keyword='{keyword or 'ALL'}', "
          f"status='{opp_statuses}', max={max_records}")

    while start_rec < max_records:
        fetch_n = min(batch_size, max_records - start_rec)

        print(f"\n  → search2: startRecord={start_rec}, rows={fetch_n}")
        hits, total = search_grants(
            keyword=keyword,
            rows=fetch_n,
            start_record=start_rec,
            opp_statuses=opp_statuses,
        )

        if not hits:
            print("  No more hits.")
            break

        print(f"  Got {len(hits)} hits (total available: {total})")

        for hit in hits:
            opp_id = hit.get("id")
            title  = (hit.get("title") or "")[:65]
            print(f"    fetchOpportunity({opp_id})  {title}…")

            detail = fetch_detail(opp_id)
            grant  = build_grant(hit, detail)
            all_grants.append(grant)

            time.sleep(delay)

        start_rec += len(hits)
        if start_rec >= total:
            break

    return all_grants


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # ── CONFIG ─────────────────────────────────────────────────────────────
    KEYWORD      = ""               # e.g. "health", "climate", "education" — or "" for all
    MAX_RECORDS  = 200               # Total grants to fetch (1 API detail call each)
    OPP_STATUSES = "posted"         # "posted" | "forecasted" | "closed" | "posted|forecasted"
    OUTPUT_FILE  = "data/grants_v2.json"
    DELAY        = 0.25             # Seconds between detail calls; raise to 0.5 if rate-limited
    # ───────────────────────────────────────────────────────────────────────

    grants = fetch_all_grants(
        keyword=KEYWORD,
        max_records=MAX_RECORDS,
        opp_statuses=OPP_STATUSES,
        delay=DELAY,
    )

    output = {
        "metadata": {
            "source":         "grants.gov (search2 + fetchOpportunity APIs)",
            "extracted_at":   datetime.utcnow().isoformat() + "Z",
            "keyword_filter": KEYWORD or "none",
            "status_filter":  OPP_STATUSES,
            "total_records":  len(grants),
        },
        "grants": grants,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅  Saved {len(grants)} enriched grants → '{OUTPUT_FILE}'")

    # Pretty-print first grant as a sanity check
    if grants:
        print("\n── Sample (first grant) ──────────────────────────────────────")
        for k, v in grants[0].items():
            if v not in (None, [], ""):
                val = ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)
                print(f"  {k:<35} {val[:100]}")