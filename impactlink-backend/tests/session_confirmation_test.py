import unittest

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt
from utils.session_execution import resume_session_command


class ConfirmationTests(unittest.TestCase):
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
