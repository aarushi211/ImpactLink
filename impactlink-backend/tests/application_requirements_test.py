import unittest
from unittest.mock import patch

from services.application import ApplicationSpec, section_definitions, length_check, validate_application, validate_review_input, merge_checklist
from flows import scratch_flow, improve_flow, section_subgraph


SPEC = {"stage": "loi", "source_reference": "Example RFP, page 2", "sections": [
    {"key": "need", "title": "Why this project?", "instructions": "Describe the local need", "max_words": 3, "max_characters": 30},
    {"key": "delivery", "title": "How will you deliver?", "instructions": "Describe the work plan", "max_characters": 40},
], "attachments": [{"id": "letter", "title": "Support letter", "stage": "loi", "required": True, "status": "not_started"}]}
GRANT = {"title": "Example grant", "application_spec": SPEC}


class ApplicationTests(unittest.TestCase):
    def test_custom_questions_replace_ten_sections_in_exact_order(self):
        definitions = section_definitions(GRANT)
        self.assertEqual([item["key"] for item in definitions], ["need", "delivery"])
        self.assertEqual(definitions[0]["title"], "Why this project?")
        self.assertEqual(definitions[0]["word_target"], "at most 3 words")

    def test_stage_starters_and_general_template_are_distinct(self):
        self.assertEqual(len(section_definitions({})), 10)
        self.assertEqual(len(section_definitions({"application_spec": {"stage": "loi"}})), 3)
        self.assertEqual(len(section_definitions({"application_spec": {"stage": "reporting"}})), 4)

    def test_generic_starter_does_not_invent_funder_requirements(self):
        report = validate_application({"proposal": {"content": "Existing proposal"}}, {"application_spec": {"source_reference": "Source URL"}})
        self.assertTrue(report["can_finalize_text"])

    def test_word_and_unicode_character_counts_include_spaces_and_normalized_newlines(self):
        result = length_check("é 😀\r\nOK", {"max_words": 3, "max_characters": 6})
        self.assertEqual((result["words"], result["characters"]), (3, 6))
        self.assertTrue(result["within_limits"])
        self.assertFalse(length_check("é 😀\r\nOK!", {"max_characters": 6})["within_limits"])
        self.assertFalse(length_check("one two three four", {"max_words": 3})["within_limits"])

    def test_missing_sections_and_attachments_are_not_silently_marked_ready(self):
        result = validate_application({"need": {"content": "One two three four"}}, GRANT)
        self.assertEqual(result["missing_sections"], ["delivery"])
        self.assertEqual(result["over_limit_sections"], ["need"])
        self.assertEqual(result["pending_attachments"], ["letter"])
        self.assertEqual(result["submission_readiness"], "not_verified")

    def test_not_applicable_required_attachment_remains_pending(self):
        grant = merge_checklist(GRANT, {"attachment_statuses": {"letter": "not_applicable"}})
        self.assertEqual(validate_application({}, grant)["pending_attachments"], ["letter"])
        self.assertEqual(GRANT["application_spec"]["attachments"][0]["status"], "not_started")

    def test_checklist_updates_only_known_ids_and_statuses(self):
        grant = merge_checklist(GRANT, {"attachment_statuses": {"letter": "ready"}})
        self.assertEqual(validate_application({}, grant)["pending_attachments"], [])
        for statuses in ({"other": "ready"}, {"letter": "invented"}, ["ready"]):
            with self.assertRaises(ValueError):
                merge_checklist(GRANT, {"attachment_statuses": statuses})

    def test_final_review_rejects_manual_edits_and_leaves_original_untouched(self):
        state = {"gate": "draft_review", "grant": GRANT, "sections": {"need": {"content": "Short need"}, "delivery": {"content": "Short delivery"}}}
        validate_review_input(state, {})
        with self.assertRaisesRegex(ValueError, "Application requirements"):
            validate_review_input(state, {"sections": {"need": "One two three four"}})
        self.assertEqual(state["sections"]["need"]["content"], "Short need")
        with self.assertRaises(ValueError):
            validate_review_input({**state, "gate": "final_save", "sections": {}}, {})

    def test_duplicate_keys_fractional_limits_and_invalid_stage_rejected(self):
        for spec in ({"sections": [SPEC["sections"][0], SPEC["sections"][0]]}, {"sections": [{**SPEC["sections"][0], "max_words": 2.5}]}, {"stage": "invented"}):
            with self.assertRaises(ValueError):
                ApplicationSpec.model_validate(spec)


class CustomFlowTests(unittest.TestCase):
    def test_scratch_streams_only_custom_questions_and_returns_funder_order(self):
        seen = []
        def draft(section, **kwargs):
            seen.append(section["key"])
            kwargs["on_token"]("Draft")
            return section["key"], {"title": section["title"], "content": "Short answer", "score": 90, "retries": 0, "flagged": False}
        state = {"session_id": "test", "profile": {"org_name": "Example"}, "grant": GRANT, "funder_vocab": [], "retry_counts": {}, "flagged_sections": []}
        with patch.object(scratch_flow, "run_section_subgraph", side_effect=draft), patch.object(scratch_flow, "_progress_writer", return_value=lambda _: None):
            result = scratch_flow.node_draft_sections(state)
        self.assertEqual(set(seen), {"need", "delivery"})
        self.assertEqual(list(result["sections"]), ["need", "delivery"])
        self.assertEqual(result["sections"]["need"]["limits"]["max_words"], 3)

    def test_high_ai_score_cannot_bypass_hard_length_limit(self):
        definition = section_definitions(GRANT)[0]
        with patch.object(section_subgraph.SectionDraftAgent, "draft", return_value="one two three four"), \
             patch.object(section_subgraph.SectionScoringAgent, "evaluate", return_value={"score": 95, "feedback": "Good", "routing": "approve"}), \
             patch.object(section_subgraph.SectionRewriteAgent, "rewrite", return_value="Short answer") as rewrite:
            _, result = section_subgraph.run_section_subgraph(definition, session_id="test", profile={}, grant=GRANT, funder_vocab=[])
        rewrite.assert_called_once()
        self.assertIn("Hard maximum", rewrite.call_args.args[2])
        self.assertTrue(result["limits"]["within_limits"])

    def test_exhausted_length_retries_are_flagged_and_not_truncated(self):
        definition = section_definitions(GRANT)[0]
        content = "one two three four"
        with patch.object(section_subgraph.SectionDraftAgent, "draft", return_value=content), \
             patch.object(section_subgraph.SectionScoringAgent, "evaluate", return_value={"score": 95, "feedback": "Good", "routing": "approve"}), \
             patch.object(section_subgraph.SectionRewriteAgent, "rewrite", return_value=content) as rewrite:
            _, result = section_subgraph.run_section_subgraph(definition, session_id="test", profile={}, grant=GRANT, funder_vocab=[])
        self.assertEqual(rewrite.call_count, section_subgraph.MAX_RETRIES)
        self.assertTrue(result["flagged"])
        self.assertEqual(result["content"], content)
        self.assertFalse(result["limits"]["within_limits"])

    def test_improve_creates_missing_application_answers_from_uploaded_context(self):
        state = {"session_id": "test", "profile": {}, "grant": GRANT, "funder_vocab": [], "original_sections": {"proposal": "The uploaded project source"}, "analysis": {"sections_to_rewrite": [], "user_additions": ""}, "retry_counts": {}, "flagged_sections": []}
        with patch.object(improve_flow, "rewrite_section", return_value="Short answer") as rewrite, patch.object(improve_flow, "score_section", return_value={"score": 95, "feedback": "Good"}):
            result = improve_flow.node_rewrite_sections(state)
        self.assertEqual(list(result["sections"]), ["need", "delivery"])
        self.assertTrue(all(call.args[2] == "The uploaded project source" for call in rewrite.call_args_list))


if __name__ == "__main__":
    unittest.main()
