import threading
import unittest
from unittest.mock import patch

from flows import scratch_flow
from agents.planning_agent import DRAFTING_WAVES
from langgraph.graph import StateGraph, START, END
from state.proposal_state import ProposalState


class DraftingParallelismTests(unittest.TestCase):
    def test_worker_tokens_reach_the_graph_custom_stream(self):
        def run_section(section, **kwargs):
            kwargs["on_token"]("Live preview")
            kwargs["on_status"]("reviewing")
            return section["key"], {"title": section["title"], "content": "Reviewed text", "score": 90, "retries": 0, "flagged": False}

        builder = StateGraph(ProposalState)
        builder.add_node("draft", scratch_flow.node_draft_sections)
        builder.add_edge(START, "draft")
        builder.add_edge("draft", END)
        graph = builder.compile()
        state = {"session_id": "stream-test", "profile": {"org_name": "Test"}, "grant": {}, "funder_vocab": [], "retry_counts": {}, "flagged_sections": []}
        with patch.object(scratch_flow, "run_section_subgraph", side_effect=run_section):
            events = list(graph.stream(state, stream_mode="custom"))
        tokens = [event for event in events if event["type"] == "token"]
        completed = [event for event in events if event["type"] == "section_complete"]
        self.assertEqual(len(tokens), 10)
        self.assertEqual(len(completed), 10)
        self.assertTrue(all(event["content"] == "Live preview" for event in tokens))
        self.assertTrue(all(event["section"]["content"] == "Reviewed text" for event in completed))

    def test_wave_sections_run_together_and_later_waves_receive_completed_context(self):
        barriers = [threading.Barrier(len(wave)) for wave in DRAFTING_WAVES]
        wave_by_key = {key: i for i, wave in enumerate(DRAFTING_WAVES) for key in wave}
        lock = threading.Lock()
        completed = set()
        active = 0
        peak = 0
        events = []

        def run_section(section, **kwargs):
            nonlocal active, peak
            key = section["key"]
            wave = wave_by_key[key]
            previous = {k for keys in DRAFTING_WAVES[:wave] for k in keys}
            with lock:
                self.assertTrue(previous.issubset(completed))
                active += 1
                peak = max(peak, active)
            for previous_key in previous:
                self.assertIn(previous_key, kwargs["prior_sections_context"])
            # A wave must start all its independent sections concurrently.
            barriers[wave].wait(timeout=3)
            kwargs["on_token"](f"draft:{key}")
            kwargs["on_status"]("reviewing")
            with lock:
                active -= 1
                completed.add(key)
            return key, {"title": key, "content": key, "score": 90, "retries": 0, "flagged": False}

        state = {
            "session_id": "parallelism-test", "profile": {"org_name": "Test"},
            "grant": {"title": "Test grant"}, "funder_vocab": [],
            "drafting_plan": None, "retry_counts": {}, "flagged_sections": [],
        }
        with patch.object(scratch_flow, "MAX_WORKERS", 4), \
             patch.object(scratch_flow, "run_section_subgraph", side_effect=run_section), \
             patch.object(scratch_flow, "_progress_writer", return_value=events.append):
            result = scratch_flow.node_draft_sections(state)

        self.assertEqual(peak, 4)
        self.assertEqual(len(result["sections"]), 10)
        self.assertEqual(completed, set(wave_by_key))
        self.assertTrue(all(section["score"] == 90 for section in result["sections"].values()))
        for kind in ("section_start", "token", "section_status", "section_complete"):
            self.assertEqual({event["section_key"] for event in events if event["type"] == kind}, set(wave_by_key))


if __name__ == "__main__":
    unittest.main()
