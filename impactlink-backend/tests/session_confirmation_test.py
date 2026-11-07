import unittest
from unittest.mock import Mock, patch

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt
from utils.session_execution import resume_session_command


class ConfirmationTests(unittest.TestCase):
    def test_corrections_and_extra_context_reach_planning_after_saved_interrupt(self):
        from flows.scratch_flow import node_slot_confirm, node_plan_draft
        from state.proposal_state import ProposalState, new_state

        builder = StateGraph(ProposalState)
        builder.add_node("confirm", node_slot_confirm)
        builder.add_node("plan", node_plan_draft)
        builder.add_edge(START, "confirm")
        builder.add_edge("confirm", "plan")
        builder.add_edge("plan", END)
        graph = builder.compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "corrected-answers"}}
        state = new_state("corrected-answers", "scratch", {}, {})
        state["gate"] = "slot_confirm"
        state["slots"] = {
            "mission": {"question": "Mission?", "value": "Old mission", "filled": True, "ask_count": 1},
            "sustainability": {"question": "Continuation?", "value": None, "filled": False, "ask_count": 2},
        }
        self.assertTrue(graph.invoke(state, config)["__interrupt__"])
        plan = Mock(section_priorities=[], red_flags=[])
        plan.model_dump.return_value = {}
        with patch("flows.scratch_flow.PlanningAgent.create_plan", return_value=plan) as planner:
            result = graph.invoke(resume_session_command({
                "slots": {"mission": "Restore wetlands", "sustainability": "Volunteer maintenance"},
                "draft_instructions": "Mention the pilot and use plain language.",
            }), config)
        profile = planner.call_args.kwargs["profile"]
        self.assertEqual(profile["mission"], "Restore wetlands")
        self.assertEqual(profile["sustainability"], "Volunteer maintenance")
        self.assertEqual(profile["draft_instructions"], "Mention the pilot and use plain language.")
        self.assertEqual(result["profile"], profile)
        self.assertTrue(result["slots"]["sustainability"]["filled"])
        self.assertEqual(state["slots"]["mission"]["value"], "Old mission")

    def test_invalid_confirmation_is_rejected_before_resuming(self):
        from services.application import validate_review_input
        state = {"gate": "slot_confirm", "slots": {"mission": {}}}
        for payload in ({"slots": []}, {"slots": {"unknown": "oops"}},
                        {"slots": {"mission": {"nested": "invalid"}}},
                        {"slots": {"mission": "x" * 20001}},
                        {"draft_instructions": "x" * 2001}, {"draft_instructions": False}):
            with self.subTest(payload_type=str(payload)[:50]), self.assertRaises(ValueError):
                validate_review_input(state, payload)
        validate_review_input(state, {"slots": {"mission": ""}, "draft_instructions": ""})

    def test_empty_confirmation_resumes_an_actual_saved_interrupt(self):
        def confirm(state):
            response = interrupt({"gate": "final_save"})
            return {"gate": "complete", "confirmed": response.get("confirmed", False)}
        builder = StateGraph(dict)
        builder.add_node("confirm", confirm)
        builder.add_edge(START, "confirm")
        builder.add_edge("confirm", END)
        graph = builder.compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "empty-confirmation"}}
        initial = graph.invoke({"gate": "final_save"}, config)
        self.assertTrue(initial["__interrupt__"])
        result = graph.invoke(resume_session_command({}), config)
        self.assertEqual(result, {"gate": "complete", "confirmed": True})


if __name__ == "__main__":
    unittest.main()
