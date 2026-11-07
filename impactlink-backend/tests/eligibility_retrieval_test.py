import unittest
from unittest.mock import MagicMock, patch
from langchain_core.runnables import RunnableLambda

from services import vector_store as store


class EligibilityRetrievalTests(unittest.TestCase):
    def test_target_only_scores_selected_grant_without_catalog_search(self):
        model = MagicMock()
        model.encode.return_value.tolist.return_value = [0.1, 0.2]
        llm = MagicMock()
        ranking = store.ReRankedGrant(grant_id="target", refined_fit_score=83, match_explanation="Revised monitoring aligns", fit_level="strong", application_tip="Confirm outcomes")
        llm.with_structured_output.return_value = RunnableLambda(lambda _: store.ReRankerList(rankings=[ranking]))
        row = {"grant_id": "target", "title": "Target grant", "agency": "Agency", "description": "Required monitoring", "award_ceiling": 300000, "similarity": 0.62}
        proposal = {"sections": {"summary": {"content": "Revised outcome monitoring"}}}
        with patch.object(store, "_eligibility_candidates", return_value=(["target"], {"target": {"status": "unverified"}})) as eligibility, patch.object(store, "_get_model", return_value=model), patch.object(store, "_get_llm", return_value=llm), patch.object(store, "_vector_search") as search, patch.object(store, "_vector_search_grant", return_value=row) as selected:
            result = store.find_similar_grants(proposal, top_k=1, include_grant_id="target", target_only=True)
        eligibility.assert_called_once_with({}, ["target"])
        selected.assert_called_once_with([0.1, 0.2], "target")
        search.assert_not_called()
        self.assertEqual(result[0]["grant_id"], "target")
        self.assertEqual(result[0]["similarity_score"], 83)
        self.assertEqual(result[0]["score_method"], "ai_project_fit")
        self.assertIn("Revised outcome monitoring", model.encode.call_args.args[0])

    def test_ineligible_target_is_not_embedded_or_scored(self):
        with patch.object(store, "_eligibility_candidates", return_value=([], {"target": {"status": "ineligible"}})), patch.object(store, "_get_model") as model, patch.object(store, "_get_llm") as llm:
            self.assertEqual(store.find_similar_grants({}, include_grant_id="target", target_only=True), [])
        model.assert_not_called()
        llm.assert_not_called()

    def test_no_eligible_records_skips_embedding_and_llm_work(self):
        with patch.object(store, "_eligibility_candidates", return_value=([], {})), \
             patch.object(store, "_get_model") as model, patch.object(store, "_get_llm") as llm:
            self.assertEqual(store.find_similar_grants({}), [])
            self.assertEqual(store.topic_search_grants("restoration"), [])
            model.assert_not_called()
            llm.assert_not_called()

    def test_selected_grant_cannot_bypass_eligibility(self):
        model = MagicMock()
        model.encode.return_value.tolist.return_value = [0.1, 0.2]
        with patch.object(store, "_eligibility_candidates", return_value=(["allowed"], {})), \
             patch.object(store, "_get_model", return_value=model), \
             patch.object(store, "_vector_search", return_value=[]) as search, \
             patch.object(store, "_vector_search_grant") as selected:
            store.find_similar_grants({}, include_grant_id="expired")
            selected.assert_not_called()
            search.assert_called_once_with([0.1, 0.2], n_results=20, allowed_grant_ids=["allowed"])

    def test_sql_filters_before_vector_limit(self):
        pool = MagicMock()
        cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = []
        with patch.object(store, "_get_pool", return_value=pool):
            store._vector_search([0.1, 0.2], 20, ["allowed"])
        query, params = cursor.execute.call_args.args
        self.assertLess(query.index("WHERE"), query.index("ORDER BY"))
        self.assertLess(query.index("ORDER BY"), query.index("LIMIT"))
        self.assertEqual(params[1:3], (["allowed"], ["allowed"]))

    def test_check_catalog_excludes_failures_but_retains_unknowns(self):
        pool = MagicMock()
        cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            {"grant_id": "closed", "close_date": "2000-01-01", "eligibility": ["Nonprofit"]},
            {"grant_id": "unknown", "close_date": "Ongoing", "eligibility": []},
        ]
        with patch.object(store, "_get_pool", return_value=pool):
            allowed, checks = store._eligibility_candidates({})
        self.assertEqual(allowed, ["unknown"])
        self.assertEqual(checks["closed"]["status"], "ineligible")
        self.assertEqual(checks["unknown"]["status"], "unverified")

    def test_unknown_cached_ids_are_not_claimed_eligible(self):
        with patch.object(store, "_eligibility_candidates", return_value=([], {})):
            self.assertEqual(store.check_grant_eligibility(["missing"], {})["missing"]["status"], "unverified")


if __name__ == "__main__":
    unittest.main()
