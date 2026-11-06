"""Deterministic basic eligibility checks. Unknown facts never mean ineligible."""

import json
import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

STATE_NAMES = (
    "AL:Alabama|AK:Alaska|AZ:Arizona|AR:Arkansas|CA:California|CO:Colorado|CT:Connecticut|DE:Delaware|"
    "DC:District of Columbia|FL:Florida|GA:Georgia|HI:Hawaii|ID:Idaho|IL:Illinois|IN:Indiana|IA:Iowa|"
    "KS:Kansas|KY:Kentucky|LA:Louisiana|ME:Maine|MD:Maryland|MA:Massachusetts|MI:Michigan|MN:Minnesota|"
    "MS:Mississippi|MO:Missouri|MT:Montana|NE:Nebraska|NV:Nevada|NH:New Hampshire|NJ:New Jersey|"
    "NM:New Mexico|NY:New York|NC:North Carolina|ND:North Dakota|OH:Ohio|OK:Oklahoma|OR:Oregon|"
    "PA:Pennsylvania|RI:Rhode Island|SC:South Carolina|SD:South Dakota|TN:Tennessee|TX:Texas|"
    "UT:Utah|VT:Vermont|VA:Virginia|WA:Washington|WV:West Virginia|WI:Wisconsin|WY:Wyoming"
)
STATES = {alias.casefold(): code for entry in STATE_NAMES.split("|") for code, name in [entry.split(":")] for alias in (code, name)}
TYPES = {
    "nonprofit": "nonprofit", "non-profit": "nonprofit", "nonprofit organization": "nonprofit",
    "public agency": "public_agency", "public_agency": "public_agency", "government": "public_agency",
    "tribal government": "tribal_government", "tribal_government": "tribal_government",
    "business": "business", "for-profit": "business", "individual": "individual",
    "other legal entity": "other_legal_entity", "other_legal_entity": "other_legal_entity",
}


def values(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if isinstance(item, str) and item.strip()]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return values(parsed)
        except ValueError:
            pass
        return [part.strip() for part in re.split(r"[,;|]", value) if part.strip()]
    return []


def _states(value):
    parts = values(value)
    codes = {STATES[part.casefold()] for part in parts if part.casefold() in STATES}
    return codes, bool(parts) and len(codes) > 0 and all(part.casefold() in STATES for part in parts)


def _check(criterion, status, message):
    return {"criterion": criterion, "status": status, "message": message}


def _deadline(grant, rules, now):
    raw = str(grant.get("close_date") or "").strip()
    if raw.lower() in {"closed", "expired", "archived", "cancelled", "canceled"} or str(rules.get("opportunity_status", "")).lower() in {"closed", "archived", "cancelled", "canceled"}:
        return _check("deadline", "fail", "The source marks this opportunity as closed or archived.")
    if raw.lower() in {"ongoing", "rolling", "open until filled"}:
        return _check("deadline", "pass", "The recorded deadline is rolling; confirm availability with the funder.")
    deadline = None
    try:
        deadline = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%m/%d/%Y", "%m/%d/%Y %H:%M:%S", "%B %d, %Y", "%b %d, %Y"):
            try:
                deadline = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
    if deadline is None:
        return _check("deadline", "unknown", "No unambiguous closing date is recorded.")
    has_time = bool(re.search(r"(?:T|\s)\d{1,2}:\d{2}", raw))
    zone_name = rules.get("deadline_timezone")
    if deadline.tzinfo is None and zone_name:
        try:
            deadline = deadline.replace(tzinfo=ZoneInfo(zone_name))
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            return _check("deadline", "unknown", "The recorded deadline timezone could not be verified.")
    if deadline.tzinfo is not None:
        cutoff = deadline if has_time else datetime.combine(deadline.date() + timedelta(days=1), time.min, deadline.tzinfo)
        return _check("deadline", "fail" if now >= cutoff else "pass", "The application deadline has passed." if now >= cutoff else "The recorded deadline has not passed.")
    # Missing timezone: exclude only after this date has ended everywhere.
    latest_cutoff = datetime.combine(deadline.date() + timedelta(days=1), time.min, timezone(timedelta(hours=-12)))
    if now >= latest_cutoff:
        return _check("deadline", "fail", "The recorded closing date has passed in every timezone.")
    return _check("deadline", "unknown", "Closing date recorded, but the deadline timezone needs confirmation.")


def evaluate_eligibility(grant, applicant=None, *, now=None):
    applicant = applicant if isinstance(applicant, dict) else {}
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Eligibility evaluation requires a timezone-aware clock.")
    rules = grant.get("eligibility_rules") or {}
    invalid_rules = not isinstance(rules, dict)
    if not isinstance(rules, dict):
        rules = {}
    checks = [_deadline(grant, rules, now)]

    labels = values(grant.get("eligibility"))
    explicit_types = values(rules.get("applicant_types"))
    categories = explicit_types or [label for label in labels if not label.casefold().startswith("eligibility details:")]
    allowed = {TYPES[label.casefold()] for label in categories if label.casefold() in TYPES}
    legal_type = TYPES.get(str(applicant.get("applicant_type") or "").strip().casefold())
    if not legal_type or not allowed or any(label.casefold() not in TYPES for label in categories):
        checks.append(_check("applicant_type", "unknown", "Applicant type or the funder's accepted applicant categories need confirmation."))
    elif legal_type not in allowed:
        checks.append(_check("applicant_type", "fail", "Your applicant type is not among the funder's recorded eligible categories."))
    else:
        checks.append(_check("applicant_type", "pass", "Your declared applicant type matches a recorded applicant category."))

    geography = rules.get("geography")
    raw_geography = grant.get("eligible_geographies")
    if geography is None and raw_geography:
        parsed, complete = _states(raw_geography)
        geography = {"states": sorted(parsed)} if complete else None
    if isinstance(geography, dict) and geography == {"unrestricted": True}:
        checks.append(_check("geography", "pass", "The source records no geographic restriction."))
    elif isinstance(geography, dict):
        allowed_states, allowed_complete = _states(geography.get("states"))
        project_states, project_complete = _states(applicant.get("project_states"))
        if allowed_complete and project_complete and allowed_states.isdisjoint(project_states):
            checks.append(_check("geography", "fail", "The declared project states do not overlap the funder's eligible states."))
        elif allowed_complete and project_complete and project_states.issubset(allowed_states) and set(geography) == {"states"}:
            checks.append(_check("geography", "pass", "The declared project states are within the recorded geographic scope."))
        else:
            checks.append(_check("geography", "unknown", "Project location or local geographic restrictions need confirmation."))
    else:
        checks.append(_check("geography", "unknown", "No verified geographic rule is recorded; check the funder's service-area requirements."))

    known_labels = [label for label in labels if label.casefold() in TYPES]
    if invalid_rules or len(known_labels) != len(labels) or any(key not in {"applicant_types", "geography", "deadline_timezone", "opportunity_status"} for key in rules):
        checks.append(_check("additional_requirements", "unknown", "Additional funder conditions need review, such as tax status, partnerships, or matching funds."))
    status = "ineligible" if any(check["status"] == "fail" for check in checks) else "unverified" if any(check["status"] == "unknown" for check in checks) else "potentially_eligible"
    return {"status": status, "checks": checks, "evaluated_at": now.isoformat()}
