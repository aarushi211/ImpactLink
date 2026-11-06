import unittest
from unittest.mock import MagicMock, patch

from services.grant_refresh import GrantSources, amount, content_hash, normalize_california, normalize_federal, refresh_records
from services.eligibility import evaluate_eligibility


def california(**updates):
    return normalize_california({"PortalID": 123, "Title": "Water project", "Status": "active", "ApplicantType": "Nonprofit", **updates})


class NormalizationTests(unittest.TestCase):
    def test_california_preserves_ids_and_geography_evidence(self):
        record = california(Geography="Only the Delta counties", MatchingFunds="Required", ApplicantTypeNotes="Requires 501(c)(3)")
        self.assertEqual(record["grant_id"], "123")
        self.assertEqual(record["eligible_geographies"], "Only the Delta counties")
        self.assertEqual(record["eligibility_rules"]["MatchingFunds"], "Required")
        self.assertEqual(evaluate_eligibility(record, {"applicant_type": "nonprofit", "project_states": ["CA"]})["status"], "unverified")

    def test_closed_source_is_ineligible_even_if_deadline_missing(self):
        self.assertEqual(evaluate_eligibility(california(Status="closed"))["status"], "ineligible")

    def test_no_geography_or_rolling_deadline_is_invented(self):
        record = california()
        self.assertEqual(record["eligible_geographies"], "")
        self.assertEqual(record["close_date"], "")
        self.assertNotIn("geography", record["eligibility_rules"])

    def test_exact_award_ranges_and_statewide_geography_come_from_source(self):
        record = california(EstAmounts="Between $10,000.00 and $300,000.00", Geography="Statewide")
        self.assertEqual((record["award_floor"], record["award_ceiling"]), (10000, 300000))
        self.assertEqual(record["eligibility_rules"]["geography"], {"states": ["CA"]})

    def test_federal_keeps_subtype_restrictions_and_unknown_categories(self):
        record = normalize_federal({"id": 42, "opportunityTitle": "Research", "ost": "POSTED", "synopsis": {
            "applicantTypes": [{"id": "12", "description": "Nonprofits with 501(c)(3)"}, {"id": "20", "description": "Private institutions of higher education"}],
            "responseDateStr": "2027-01-01-00-00-00", "responseDateDesc": "11:59 PM ET", "costSharing": True,
        }})
        self.assertEqual(record["grant_id"], "grants-gov:42")
        self.assertEqual(record["close_date"], "2027-01-01")
        self.assertNotIn("deadline_timezone", record["eligibility_rules"])
        self.assertIn("Private institutions of higher education", record["eligibility_rules"]["applicant_types"])
        self.assertTrue(record["eligibility_rules"]["requires_cost_share"])
        self.assertTrue(any("501(c)(3)" in label for label in record["eligibility"]))

    def test_invalid_identity_and_missing_synopsis_fail(self):
        with self.assertRaises(ValueError):
            california(PortalID=None)
        with self.assertRaises(ValueError):
            normalize_federal({"id": 42, "opportunityTitle": "Unpublished"})

    def test_amounts_preserve_missing_instead_of_inventing_zero(self):
        self.assertEqual(amount("$1,234.00"), 1234)
        for value in (None, "unknown", "NaN", "Infinity", "-1"):
            self.assertIsNone(amount(value))


class SourceTests(unittest.TestCase):
    def test_california_paginates_until_total_and_fails_partial_response(self):
        sources = GrantSources(delay=0)
        with patch.object(sources, "request", side_effect=[{"records": [{"PortalID": 1, "Title": "One"}], "total": 2}, {"records": [{"PortalID": 2, "Title": "Two"}], "total": 2}]) as request:
            self.assertEqual(len(sources.california()), 2)
            self.assertEqual(request.call_args.args[1]["offset"], 1)
        with patch.object(sources, "request", return_value={"records": [], "total": 2}):
            with self.assertRaises(ValueError):
                sources.california()

    def test_federal_refreshes_tracked_grants_even_if_not_in_discovery(self):
        sources = GrantSources(delay=0)
        def response(url, payload, **kwargs):
            if url.endswith("search2"):
                return {"oppHits": [{"id": "2"}], "hitCount": 1}
            identifier = payload["opportunityId"]
            return {"id": identifier, "opportunityTitle": "Grant", "synopsis": {}, "ost": "CLOSED" if identifier == 1 else "POSTED"}
        with patch.object(sources, "request", side_effect=response):
            rows = sources.federal(limit=1, existing_ids=["1"])
        self.assertEqual([row["source_id"] for row in rows], ["1", "2"])
        self.assertEqual(rows[0]["eligibility_rules"]["opportunity_status"], "closed")

    def test_api_errors_are_not_treated_as_an_empty_success(self):
        session = MagicMock()
        session.get.return_value.json.return_value = {"success": False}
        with patch("services.grant_refresh.time.sleep"):
            with self.assertRaises(ValueError):
                GrantSources(session, delay=0).request("https://example.com", {})
        self.assertEqual(session.get.call_count, 3)


class PersistenceTests(unittest.TestCase):
    def connection(self, rows=()):
        conn = MagicMock()
        conn.execute.return_value = rows
        conn.cursor.return_value.__enter__.return_value.fetchall.return_value = rows
        return conn

    def test_dry_run_never_writes_or_embeds(self):
        conn, encode = self.connection(), MagicMock()
        report = refresh_records(conn, [california()], encode)
        self.assertEqual(report["inserted"], 1)
        encode.assert_not_called()
        self.assertFalse(any(call.args[0].startswith(("INSERT", "UPDATE", "DELETE", "DROP")) for call in conn.execute.call_args_list))

    def test_unchanged_content_only_updates_freshness(self):
        record = california()
        row = {"grant_id": "123", "source": "california", "source_id": "123", "title": record["title"], "content_hash": content_hash(record), "document": "old"}
        conn, encode = self.connection([row]), MagicMock()
        report = refresh_records(conn, [record], encode, dry_run=False)
        self.assertEqual(report["unchanged"], 1)
        encode.assert_not_called()
        self.assertIn("last_verified_at", conn.execute.call_args.args[0])

    def test_new_limit_does_not_prevent_existing_closed_updates(self):
        record = california(Status="closed")
        row = {"grant_id": "123", "source": "california", "source_id": "123", "title": record["title"], "content_hash": None, "document": "old"}
        report = refresh_records(self.connection([row]), [record, california(PortalID=999)], MagicMock(), new_limit=0)
        self.assertEqual(report["updated"], 1)
        self.assertEqual(report["skipped"], 1)

    def test_duplicate_source_and_legacy_collision_fail_without_writes(self):
        record = california()
        with self.assertRaises(ValueError):
            refresh_records(self.connection(), [record, record], MagicMock())
        row = {"grant_id": "123", "source": None, "source_id": None, "title": "Unrelated", "content_hash": None, "document": "old"}
        with self.assertRaises(ValueError):
            refresh_records(self.connection([row]), [record], MagicMock())


if __name__ == "__main__":
    unittest.main()
