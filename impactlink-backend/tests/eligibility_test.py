from copy import deepcopy
from datetime import datetime, timezone
import unittest

from services.eligibility import evaluate_eligibility

NOW = datetime(2026, 11, 5, 13, tzinfo=timezone.utc)
BASE = {"eligibility": ["Nonprofit"], "close_date": "Ongoing", "eligibility_rules": {"geography": {"states": ["CA"]}}}
APPLICANT = {"applicant_type": "nonprofit", "project_states": ["California"]}


class EligibilityTests(unittest.TestCase):
    def check(self, grant=None, applicant=None):
        return evaluate_eligibility(grant or deepcopy(BASE), APPLICANT if applicant is None else applicant, now=NOW)

    def test_matching_known_basic_requirements(self):
        self.assertEqual(self.check()["status"], "potentially_eligible")

    def test_confirmed_type_mismatch_is_excluded(self):
        self.assertEqual(self.check(applicant={**APPLICANT, "applicant_type": "individual"})["status"], "ineligible")

    def test_missing_applicant_type_is_unknown(self):
        self.assertEqual(self.check(applicant={"project_states": ["CA"]})["status"], "unverified")

    def test_unknown_eligible_applicant_category_does_not_produce_false_rejection(self):
        grant = {**BASE, "eligibility": ["Public Agency", "Universities"]}
        self.assertEqual(self.check(grant)["status"], "unverified")

    def test_additional_tax_or_partner_conditions_are_not_claimed_satisfied(self):
        grant = {**BASE, "eligibility": ["Nonprofit", "Eligibility details: Requires a public agency partner and 501(c)(3) status."]}
        self.assertEqual(self.check(grant)["status"], "unverified")

    def test_nonoverlapping_verified_states_are_excluded(self):
        self.assertEqual(self.check(applicant={**APPLICANT, "project_states": ["NY"]})["status"], "ineligible")

    def test_partial_overlap_needs_confirmation(self):
        self.assertEqual(self.check(applicant={**APPLICANT, "project_states": ["CA", "NY"]})["status"], "unverified")

    def test_office_location_and_title_are_not_geographic_proof(self):
        grant = {**BASE, "title": "California grants", "agency": "California agency", "eligibility_rules": {}}
        self.assertEqual(self.check(grant, {"applicant_type": "nonprofit", "location": "California"})["status"], "unverified")

    def test_local_restriction_is_not_assumed_satisfied_by_state_match(self):
        grant = {**BASE, "eligibility_rules": {"geography": {"states": ["CA"], "counties": ["Los Angeles"]}}}
        self.assertEqual(self.check(grant)["status"], "unverified")

    def test_simple_source_state_list_is_supported(self):
        grant = {**BASE, "eligible_geographies": "California, New York", "eligibility_rules": {}}
        self.assertEqual(self.check(grant)["status"], "potentially_eligible")

    def test_prose_geography_is_not_guessed(self):
        grant = {**BASE, "eligible_geographies": "Outside California except designated areas", "eligibility_rules": {}}
        self.assertEqual(self.check(grant)["status"], "unverified")

    def test_timestamp_with_offset_expires_at_its_actual_instant(self):
        grant = {**BASE, "close_date": "2026-11-05T04:00:00-08:00"}
        self.assertEqual(self.check(grant)["status"], "ineligible")
        grant["close_date"] = "2026-11-05T06:00:00-08:00"
        self.assertEqual(self.check(grant)["status"], "potentially_eligible")

    def test_date_without_timezone_is_not_closed_prematurely(self):
        grant = {**BASE, "close_date": "2026-11-04"}
        earlier = datetime(2026, 11, 5, 11, tzinfo=timezone.utc)
        self.assertEqual(evaluate_eligibility(grant, APPLICANT, now=earlier)["status"], "unverified")
        self.assertEqual(self.check(grant)["status"], "ineligible")

    def test_unparseable_deadlines_and_future_unzoned_dates_are_unknown(self):
        for value in ("Not available", "02/03/35", "2035-02-03 17:00:00", ""):
            with self.subTest(value=value):
                self.assertEqual(self.check({**BASE, "close_date": value})["status"], "unverified")

    def test_closed_source_status_overrides_a_rolling_deadline(self):
        grant = deepcopy(BASE)
        grant["eligibility_rules"]["opportunity_status"] = "closed"
        self.assertEqual(self.check(grant)["status"], "ineligible")

    def test_unknown_and_malformed_rules_do_not_create_verified_eligibility(self):
        for rules in ({"geography": {"unrestricted": True, "countries": ["US"]}}, ["bad rules"], {"requires_cost_share": True}):
            with self.subTest(rules=rules):
                self.assertEqual(self.check({**BASE, "eligibility_rules": rules})["status"], "unverified")

    def test_empty_metadata_and_invalid_applicant_are_safe(self):
        self.assertEqual(evaluate_eligibility({}, [], now=NOW)["status"], "unverified")


if __name__ == "__main__":
    unittest.main()
