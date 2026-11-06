"""Source-backed grant refresh. No LLM extraction, destructive reloads, or inferred rules."""

import hashlib
import html
import json
import math
import re
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import requests
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

CA_API = "https://data.ca.gov/api/3/action/datastore_search"
CA_RESOURCE = "111c8c88-21f6-453c-ae2c-b4785a0624f5"
FEDERAL_API = "https://api.grants.gov/v1/api/"
SOURCE_NAMES = {"california", "grants_gov"}


def text(value):
    return html.unescape(re.sub(r"<[^>]*>", " ", str(value or ""))).strip()


def amount(value):
    try:
        parsed = Decimal(str(value).replace("$", "").replace(",", ""))
        return int(parsed) if parsed.is_finite() and parsed >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def normalize_california(raw):
    identifier = str(raw.get("PortalID") or "").strip()
    title = text(raw.get("Title"))
    if not identifier.isdigit() or not title:
        raise ValueError("California record has no stable PortalID or title")
    labels = [value.strip() for value in str(raw.get("ApplicantType") or "").split(";") if value.strip()]
    if raw.get("ApplicantTypeNotes"):
        labels.append("Eligibility details: " + text(raw["ApplicantTypeNotes"]))
    status = str(raw.get("Status") or "").lower()
    rules = {"opportunity_status": {"active": "posted"}.get(status, status)}
    award_range = re.fullmatch(r"Between\s+(\$[\d,.]+)\s+and\s+(\$[\d,.]+)", text(raw.get("EstAmounts")), flags=re.IGNORECASE)
    award_floor, award_ceiling = (amount(award_range[1]), amount(award_range[2])) if award_range else (None, None)
    if text(raw.get("Geography")).casefold() in {"statewide", "statewide california", "all california counties", "throughout california", "california"}:
        rules["geography"] = {"states": ["CA"]}
    # Keep prose as source evidence; do not turn 'California agency' into statewide eligibility.
    for key in ("MatchingFunds", "MatchingFundsNotes", "LOI", "EstAmounts"):
        if raw.get(key):
            rules[key] = text(raw[key])
    return {
        "grant_id": identifier, "source": "california", "source_id": identifier,
        "source_url": text(raw.get("GrantURL")) or "https://www.grants.ca.gov/",
        "source_updated_at": str(raw.get("LastUpdated") or ""),
        "title": title, "agency": text(raw.get("AgencyDept")),
        "award_floor": award_floor, "award_ceiling": award_ceiling,
        "application_url": text(raw.get("GrantURL")), "portal_url": "https://www.grants.ca.gov/",
        "close_date": text(raw.get("ApplicationDeadline")),
        "focus_areas": text(raw.get("Categories")),
        "contact_email": text(raw.get("ContactInfo")), "contact_name": "",
        "funding_method": text(raw.get("FundingMethod")), "estimated_total": text(raw.get("EstAvailFunds")),
        "description": "\n\n".join(filter(None, [text(raw.get("Purpose")), text(raw.get("Description"))])),
        "eligibility": labels, "eligible_geographies": text(raw.get("Geography")), "eligibility_rules": rules,
    }


# Codes with narrower conditions keep their original labels as additional evidence.
FEDERAL_TYPES = {"00": "public_agency", "01": "public_agency", "02": "public_agency",
                 "04": "public_agency", "05": "public_agency", "07": "tribal_government",
                 "12": "nonprofit", "13": "nonprofit", "21": "individual",
                 "22": "business", "23": "business"}


def normalize_federal(raw):
    identifier = str(raw.get("id") or "")
    title = text(raw.get("opportunityTitle"))
    synopsis = raw.get("synopsis")
    if not identifier.isdigit() or not title or not isinstance(synopsis, dict):
        raise ValueError("Federal record lacks an ID, title or published synopsis")
    labels, types = [], []
    for item in synopsis.get("applicantTypes") or []:
        label = text(item.get("description"))
        mapped = FEDERAL_TYPES.get(str(item.get("id")))
        types.append(mapped or label or "Unspecified applicant category")
        if label:
            labels.append("Eligibility details: " + label)
    if synopsis.get("applicantEligibilityDesc"):
        labels.append("Eligibility details: " + text(synopsis["applicantEligibilityDesc"]))
    rules = {"applicant_types": sorted(set(types)), "opportunity_status": str(raw.get("ost") or "").lower()}
    if synopsis.get("costSharing") is not None:
        rules["requires_cost_share"] = synopsis["costSharing"]
    if synopsis.get("responseDateDesc"):
        rules["deadline_notes"] = text(synopsis["responseDateDesc"])
    # The API's responseDate is commonly midnight even when its notes specify 11:59pm.
    # Preserve the date without claiming that timestamp/timezone is an exact deadline.
    close_date = ""
    date_str = synopsis.get("responseDateStr") or ""
    if re.match(r"^\d{4}-\d{2}-\d{2}", date_str):
        close_date = date_str[:10]
    elif synopsis.get("responseDate"):
        try:
            close_date = datetime.strptime(" ".join(synopsis["responseDate"].split()[:3]), "%b %d, %Y").date().isoformat()
        except ValueError:
            pass
    agency = synopsis.get("agencyDetails") or raw.get("agencyDetails") or {}
    return {
        "grant_id": "grants-gov:" + identifier, "source": "grants_gov", "source_id": identifier,
        "source_url": f"https://www.grants.gov/search-results-detail/{identifier}",
        "source_updated_at": str(synopsis.get("lastUpdatedDate") or ""),
        "title": title, "agency": text(agency.get("agencyName")),
        "award_floor": amount(synopsis.get("awardFloor")), "award_ceiling": amount(synopsis.get("awardCeiling")),
        "application_url": f"https://www.grants.gov/search-results-detail/{identifier}",
        "portal_url": "https://www.grants.gov/", "close_date": close_date,
        "focus_areas": "; ".join(text(item.get("description")) for item in synopsis.get("fundingActivityCategories") or []),
        "contact_email": text(synopsis.get("agencyContactEmail")), "contact_name": text(synopsis.get("agencyContactName")),
        "funding_method": "; ".join(text(item.get("description")) for item in synopsis.get("fundingInstruments") or []),
        "estimated_total": "", "description": text(synopsis.get("synopsisDesc")),
        "eligibility": labels, "eligible_geographies": "", "eligibility_rules": rules,
    }


class GrantSources:
    def __init__(self, session=None, delay=0.25):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "ImpactLink grant refresh", "Accept": "application/json"})
        self.delay = delay

    def request(self, url, payload, *, post=False):
        for attempt in range(3):
            try:
                time.sleep(self.delay)
                response = self.session.post(url, json=payload, timeout=(10, 40)) if post else self.session.get(url, params=payload, timeout=(10, 40))
                response.raise_for_status()
                body = response.json()
                if not isinstance(body, dict) or body.get("success") is False or body.get("errorcode", 0) not in (0, "0"):
                    raise ValueError("Grant source returned an unsuccessful response")
                if not isinstance(body.get("result" if not post else "data"), dict):
                    raise ValueError("Grant source response has no data object")
                return body.get("data") if post else body["result"]
            except (requests.RequestException, ValueError):
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)

    def california(self):
        records, offset, seen = [], 0, set()
        while offset < 20000:
            data = self.request(CA_API, {"resource_id": CA_RESOURCE, "limit": 500, "offset": offset, "sort": "PortalID desc"})
            batch = data.get("records")
            if not isinstance(batch, list):
                raise ValueError("California feed has no records list")
            for raw in batch:
                identifier = str(raw.get("PortalID") or "")
                if identifier in seen:
                    raise ValueError("California pagination returned duplicate identities")
                seen.add(identifier)
                records.append(normalize_california(raw))
            offset += len(batch)
            if offset >= int(data.get("total", 0)):
                return records
            if not batch:
                raise ValueError("California feed ended before its reported total")
        raise ValueError("California feed exceeds safety pagination limit")

    def federal(self, *, limit=100, keyword="", existing_ids=()):
        identifiers = list(dict.fromkeys(existing_ids))
        discovered, start = [], 0
        while len(discovered) < limit:
            data = self.request(FEDERAL_API + "search2", {"rows": min(25, limit - len(discovered)), "startRecordNum": start, "keyword": keyword, "oppStatuses": "posted"}, post=True)
            hits = data.get("oppHits")
            if not isinstance(hits, list):
                raise ValueError("Federal search has no opportunity list")
            new_ids = [str(hit["id"]) for hit in hits if str(hit.get("id", "")).isdigit()]
            if hits and not set(new_ids).difference(discovered):
                raise ValueError("Federal pagination did not advance")
            discovered.extend(new_ids)
            start += len(hits)
            if not hits or start >= int(data.get("hitCount", 0)):
                break
        identifiers = list(dict.fromkeys(identifiers + discovered[:limit]))
        records = []
        for identifier in identifiers:
            raw = self.request(FEDERAL_API + "fetchOpportunity", {"opportunityId": int(identifier)}, post=True)
            if str(raw.get("id")) != identifier:
                raise ValueError("Federal source returned a different opportunity ID")
            records.append(normalize_federal(raw))
        return records


FIELDS = ("title", "agency", "award_floor", "award_ceiling", "application_url", "portal_url",
          "close_date", "focus_areas", "contact_email", "contact_name", "funding_method", "estimated_total",
          "description", "eligibility", "eligible_geographies", "eligibility_rules", "source", "source_id", "source_url", "source_updated_at")


def embedding_text(record):
    return "\n".join(str(record.get(key) or "") for key in ("title", "agency", "description", "focus_areas", "eligibility"))


def content_hash(record):
    return hashlib.sha256(json.dumps({key: record.get(key) for key in FIELDS}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def refresh_records(conn, records, encode, *, new_limit=100, dry_run=True):
    """Commit a complete source batch atomically; unchanged content reuses its embedding."""
    if new_limit < 0:
        raise ValueError("new_limit cannot be negative")
    report = {"inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0, "dry_run": dry_run}
    identities = set()
    for record in records:
        identity = (record["source"], record["source_id"])
        if identity in identities or record["source"] not in SOURCE_NAMES:
            raise ValueError("Duplicate or unsupported source identity")
        identities.add(identity)
    with conn.transaction():
        # Prevent overlapping scheduled/manual refreshes for this database.
        conn.execute("SELECT pg_advisory_xact_lock(72183492)")
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT grant_id, source, source_id, title, portal_url, content_hash, document FROM grants")
            existing = {row["grant_id"]: row for row in cursor.fetchall()}
        by_source = {(row["source"], row["source_id"]): row for row in existing.values() if row["source"]}
        for record in records:
            row = by_source.get((record["source"], record["source_id"])) or existing.get(record["grant_id"])
            if row and row["source"] not in (None, record["source"]):
                raise ValueError("Grant ID collides with another source")
            legacy_ca_host = urlparse(row.get("portal_url") or "").hostname if row else None
            ca_evidence = record["source"] == "california" and legacy_ca_host and (legacy_ca_host == "grants.ca.gov" or legacy_ca_host.endswith(".ca.gov"))
            if row and row["source"] is None and not ca_evidence and text(row["title"]).casefold() != record["title"].casefold():
                # Legacy California IDs are preserved only when title corroborates identity.
                raise ValueError("Legacy grant ID/title mismatch; source identity needs review")
            if not row and (report["inserted"] >= new_limit or record["eligibility_rules"].get("opportunity_status") != "posted"):
                report["skipped"] += 1
                continue
            identifier = row["grant_id"] if row else record["grant_id"]
            digest = content_hash(record)
            if row and row["content_hash"] == digest:
                report["unchanged"] += 1
                if not dry_run:
                    conn.execute("UPDATE grants SET last_verified_at = NOW() WHERE grant_id = %s", (identifier,))
                continue
            report["updated" if row else "inserted"] += 1
            if dry_run:
                continue
            document = embedding_text(record)
            if row and row["document"] == document:
                embedding = None
            else:
                embedding = encode(document)
                if hasattr(embedding, "tolist"):
                    embedding = embedding.tolist()
                if len(embedding) != 384 or any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in embedding):
                    raise ValueError("Embedding must contain 384 finite numbers")
            if row:
                assignments = ", ".join(f"{field} = %s" for field in FIELDS)
                params = [Jsonb(record[field]) if field in {"eligibility", "eligibility_rules"} else record.get(field) for field in FIELDS]
                extra = ", embedding = %s::vector" if embedding is not None else ""
                conn.execute(f"UPDATE grants SET {assignments}, document = %s, content_hash = %s, last_verified_at = NOW(){extra} WHERE grant_id = %s", params + [document, digest] + ([json.dumps(embedding)] if embedding is not None else []) + [identifier])
            else:
                columns = ("grant_id",) + FIELDS + ("document", "content_hash", "embedding")
                params = [identifier] + [Jsonb(record[field]) if field in {"eligibility", "eligibility_rules"} else record.get(field) for field in FIELDS] + [document, digest, json.dumps(embedding)]
                placeholders = ", ".join(["%s"] * (len(columns) - 1) + ["%s::vector"])
                conn.execute(f"INSERT INTO grants ({', '.join(columns)}, last_verified_at) VALUES ({placeholders}, NOW())", params)
    return report
