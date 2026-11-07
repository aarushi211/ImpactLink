import json
import unittest
from unittest.mock import patch
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from agents import rewriter_agent, gap_analysis_agent
from flows import improve_flow
from state.proposal_state import new_state
from state.proposal_state import ProposalState
from langgraph.graph import StateGraph, START
from langgraph.checkpoint.memory import InMemorySaver


class LocalEditTests(unittest.TestCase):
    def test_existing_markdown_table_is_one_unit_and_is_preserved_outside_the_gap(self):
        table = "| Category | Amount |\n| --- | ---: |\n| Staff | $80,000 |\n| Travel | $55,000 |"
        original = "Original introduction.\n\n" + table + "\n\nKeep this conclusion."
        units = rewriter_agent.text_units(original)
        self.assertEqual([unit.group() for unit in units if unit.group().startswith("|")], [table])
        result = rewriter_agent.apply_local_edits(original, units, {"edits": [{"unit": 0, "replacement": "Introduction with the missing detail.", "reason": "Required introductory fact"}]}, {0})
        self.assertEqual(result, original.replace("Original introduction.", "Introduction with the missing detail."))

    def test_only_the_reviewed_local_block_is_converted_to_a_table(self):
        source = "Staff: $80,000\nTravel: $55,000"
        original = "Keep the original introduction.\n\n" + source + "\n\nKeep the original conclusion."
        table = "| Category | Amount |\n| --- | ---: |\n| Staff | $80,000 |\n| Travel | $55,000 |"
        units = rewriter_agent.text_units(original)
        start = next(i for i, unit in enumerate(units) if unit.group() == "Staff: $80,000")
        result = rewriter_agent.apply_local_edits(original, units, {"edits": [{"unit": start, "end_unit": start + 1, "replacement": table, "reason": "Required cost table"}]}, {start, start + 1})
        self.assertEqual(result, original.replace(source, table))

    def test_out_of_scope_replacement_is_rejected_even_when_model_returns_valid_json(self):
        reply = RunnableLambda(lambda _: AIMessage(content=json.dumps({"edits": [{"unit": 0, "replacement": "Unrequested rewrite.", "reason": "Polish"}]})))
        with patch.object(rewriter_agent, "_get_llm", return_value=reply), self.assertRaisesRegex(ValueError, "outside the reviewed gaps"):
            rewriter_agent.rewrite_section("proposal", "Proposal", "Keep this sentence. Fix this sentence.", [{"description": "Fix the second sentence", "target_units": [1]}], [], {}, {})

    def test_missing_table_can_be_inserted_without_replacing_original_text(self):
        original = "Keep this context.\n\nKeep this ending."
        table = "\n\n| Activity | Timing |\n| --- | --- |\n| Planning | Months 1–3 |"
        result = rewriter_agent.apply_local_edits(original, rewriter_agent.text_units(original), {"edits": [{"unit": 0, "operation": "insert_after", "replacement": table, "reason": "Required work-plan table"}]}, {0})
        self.assertEqual(result, original.replace("Keep this context.", "Keep this context." + table))

    def test_older_gap_analysis_is_localized_before_editing(self):
        def reply(prompt):
            if "Locate the smallest set" in prompt.to_string():
                return AIMessage(content='{"units": [1]}')
            return AIMessage(content=json.dumps({"edits": [{"unit": 1, "replacement": "Monitoring is monthly.", "reason": "Clarify timing"}]}))
        with patch.object(rewriter_agent, "_get_llm", return_value=RunnableLambda(reply)):
            result = rewriter_agent.rewrite_section("proposal", "Proposal", "Keep this fact. Monitoring is planned.", [{"description": "Clarify monitoring frequency"}], [], {}, {})
        self.assertEqual(result, "Keep this fact. Monitoring is monthly.")

    def test_one_sentence_edit_preserves_every_other_character(self):
        original = "## 03 Community Plan\n\nWe serve 400 youth.  Sessions run monthly.\n\nPartners are not yet confirmed.\n"
        units = rewriter_agent.text_units(original)
        index = next(i for i, span in enumerate(units) if span.group() == "Sessions run monthly.")
        edited = rewriter_agent.apply_local_edits(original, units, {"edits": [{"unit": index, "replacement": "Sessions run monthly, with attendance recorded at each session.", "reason": "Add the requested monitoring method"}]})
        self.assertEqual(edited, original.replace("Sessions run monthly.", "Sessions run monthly, with attendance recorded at each session."))

    def test_empty_edit_list_preserves_complete_original_including_whitespace(self):
        original = "  Existing facts.\n\n## 04 Budget\n$275,000.00 over 24 months.\n"
        self.assertEqual(rewriter_agent.apply_local_edits(original, rewriter_agent.text_units(original), {"edits": []}), original)

    def test_invalid_or_duplicate_units_cannot_replace_other_text(self):
        text = "Keep this. Edit that."
        for edits in ([{"unit": 99, "replacement": "Replacement", "reason": "Reason"}],
                      [{"unit": 0, "replacement": "A", "reason": "Reason"}] * 2,
                      [{"unit": True, "replacement": "A", "reason": "Reason"}],
                      [{"unit": 0, "replacement": "A", "reason": ""}]):
            with self.subTest(edits=edits), self.assertRaises(ValueError):
                rewriter_agent.apply_local_edits(text, rewriter_agent.text_units(text), {"edits": edits})

    def test_model_edits_use_stable_ids_and_never_return_json_as_draft_text(self):
        original = "Jane Example leads the program. We track attendance."
        seen = []
        def reply(prompt):
            seen.append(prompt.to_string())
            return AIMessage(content=json.dumps({"edits": [{"unit": 1, "replacement": "We track attendance at every workshop.", "reason": "Specify the monitoring frequency"}]}))
        with patch.object(rewriter_agent, "_get_llm", return_value=RunnableLambda(reply)):
            result = rewriter_agent.rewrite_section("evaluation", "Evaluation", original, [{"description": "Specify monitoring frequency", "target_units": [1]}], [], {}, {})
        self.assertEqual(result, "Jane Example leads the program. We track attendance at every workshop.")
        self.assertIn('"unit": 1', seen[0])


class TargetedSectionTests(unittest.TestCase):
    def test_custom_questions_do_not_discard_source_sections_or_force_unselected_answers(self):
        original = {"proposal": "Keep the project narrative. Monitoring is planned.", "budget": "Keep the original budget table."}
        grant = {"application_spec": {"sections": [{"key": "new_question", "title": "New funder question", "required": True}]}}
        state = new_state("custom-target", "improve", {}, grant, original_sections=original)
        state["analysis"] = {"sections_to_rewrite": ["proposal"], "missing_content": [{"section": "proposal", "description": "Clarify monitoring"}]}
        with patch.object(improve_flow, "rewrite_section", return_value="Keep the project narrative. Monitoring is monthly.") as rewrite, patch.object(improve_flow, "score_section", return_value={"score": 95, "feedback": "Good"}):
            result = improve_flow.node_rewrite_sections(state)
        self.assertEqual(rewrite.call_count, 1)
        self.assertEqual(rewrite.call_args.args[0], "proposal")
        self.assertFalse(rewrite.call_args.args[5]["_new_application_answer"])
        self.assertNotIn("new_question", result["sections"])
        self.assertEqual(result["sections"]["budget"]["content"], original["budget"])

    def test_low_score_does_not_trigger_unrequested_polishing_of_existing_text(self):
        state = new_state("no-polish", "improve", {}, {}, original_sections={"proposal": "Existing text."})
        state["analysis"] = {"sections_to_rewrite": ["proposal"]}
        with patch.object(improve_flow, "rewrite_section", return_value="Existing text with one fix."), patch.object(improve_flow, "score_section", return_value={"score": 40, "feedback": "Polish the whole proposal"}), patch.object(improve_flow, "retry_rewrite") as retry:
            result = improve_flow.node_rewrite_sections(state)
        retry.assert_not_called()
        self.assertTrue(result["sections"]["proposal"]["flagged"])
        self.assertEqual(result["sections"]["proposal"]["content"], "Existing text with one fix.")

    def test_actual_graph_streams_applied_text_and_retains_gaps_for_review(self):
        original = "We serve 400 youth. We track attendance."
        state = new_state("stream-edits", "improve", {}, {}, original_sections={"proposal": original})
        state["analysis"] = {"sections_to_rewrite": ["proposal"], "missing_content": [{"section": "proposal", "description": "Specify when attendance is recorded", "target_units": [1]}]}
        model = RunnableLambda(lambda _: AIMessage(content=json.dumps({"edits": [{"unit": 1, "replacement": "We track attendance at every session.", "reason": "Specify monitoring timing"}]})))
        builder = StateGraph(ProposalState)
        builder.add_node("rewrite", improve_flow.node_rewrite_sections)
        builder.add_node("review", improve_flow.node_draft_review)
        builder.add_edge(START, "rewrite")
        builder.add_edge("rewrite", "review")
        graph = builder.compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "stream-edits"}}
        with patch.object(rewriter_agent, "_get_llm", return_value=model), patch.object(improve_flow, "score_section", return_value={"score": 95, "feedback": "Good"}):
            events = list(graph.stream(state, config, stream_mode="custom"))
        text = "".join(event["content"] for event in events if event.get("type") == "token")
        self.assertEqual(text, "We serve 400 youth. We track attendance at every session.")
        snapshot = graph.get_state(config)
        payload = snapshot.tasks[0].interrupts[0].value
        self.assertEqual(payload["analysis"], state["analysis"])
        self.assertEqual(payload["sections"]["proposal"]["content"], text)

    def test_requested_preferences_are_included_in_gap_analysis(self):
        seen = []
        def reply(prompt):
            seen.append(prompt.to_string())
            return AIMessage(content=json.dumps({"missing_content": [], "weak_evidence": [], "wrong_vocabulary": [], "misalignment": [], "requested_changes": [{"section": "summary", "description": "Clarify the planned activities"}], "sections_to_rewrite": ["summary"]}))
        with patch.object(gap_analysis_agent, "_get_llm", return_value=RunnableLambda(reply)):
            result = gap_analysis_agent.analyze_gaps({"summary": "Existing activities", "budget": "Existing costs"}, {}, [], "Clarify the planned activities in the summary.")
        self.assertIn("Clarify the planned activities in the summary.", seen[0])
        self.assertEqual(result["sections_to_rewrite"], ["summary"])

    def test_analysis_ignores_blanket_selection_and_tracks_requested_changes(self):
        analysis = {"missing_content": [{"section": "evaluation", "description": "Specify monitoring"}], "weak_evidence": [], "wrong_vocabulary": [], "misalignment": [], "requested_changes": [{"section": "budget", "description": "Clarify the supplied cost assumptions"}], "sections_to_rewrite": ["summary", "evaluation", "budget"]}
        result = gap_analysis_agent._normalize_section_keys(analysis, {"summary": "Strong summary", "evaluation": "Monitoring", "budget": "Costs"})
        self.assertEqual(result["sections_to_rewrite"], ["evaluation", "budget"])

    def test_only_selected_section_is_edited_and_untouched_headings_are_preserved(self):
        original = {"summary": "## 03 Summary\n\nKeep these exact words.\n", "evaluation": "We track attendance."}
        state = new_state("targeted", "improve", {}, {}, original_sections=original)
        state["analysis"] = {"sections_to_rewrite": ["evaluation"], "missing_content": [{"section": "evaluation", "description": "Specify timing"}]}
        with patch.object(improve_flow, "rewrite_section", return_value="We track attendance at every session.") as rewrite, patch.object(improve_flow, "score_section", return_value={"score": 95, "feedback": "Good"}):
            result = improve_flow.node_rewrite_sections(state)
        self.assertEqual(rewrite.call_count, 1)
        self.assertEqual(rewrite.call_args.args[0], "evaluation")
        self.assertEqual(result["sections"]["summary"]["content"], original["summary"])
        self.assertEqual(result["diffs"]["summary"], [{"type": "equal", "text": original["summary"]}])

    def test_no_gaps_returns_original_without_generation_or_scoring(self):
        original = {"proposal": "## 07 Existing Proposal\n\nAlready meets the requirements.\n"}
        state = new_state("unchanged", "improve", {}, {}, original_sections=original)
        state["analysis"] = {"sections_to_rewrite": []}
        with patch.object(improve_flow, "rewrite_section") as rewrite, patch.object(improve_flow, "score_section") as score:
            result = improve_flow.node_rewrite_sections(state)
        rewrite.assert_not_called()
        score.assert_not_called()
        self.assertEqual(result["sections"]["proposal"]["content"], original["proposal"])


if __name__ == "__main__":
    unittest.main()
