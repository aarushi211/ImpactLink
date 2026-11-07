import unittest
from typing import TypedDict
from unittest.mock import MagicMock, patch

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from psycopg import OperationalError, InterfaceError, IntegrityError
from psycopg.errors import QueryCanceled, InvalidPassword, ConnectionFailure

from utils.checkpoint_store import RetryingPostgresSaver, RETRY_DELAYS


class RecoveryState(TypedDict):
    sections: dict
    gate: str


class CheckpointRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.saver = RetryingPostgresSaver(MagicMock())
        sleeper = patch("utils.checkpoint_store.time.sleep")
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)

    def test_failed_writes_retry_with_exactly_the_same_ids_and_payload(self):
        config = {"configurable": {"thread_id": "draft", "checkpoint_ns": "", "checkpoint_id": "checkpoint-1"}}
        writes = [("sections", {"summary": {"content": "Already generated draft."}})]
        with patch.object(PostgresSaver, "put_writes", side_effect=[OperationalError("connection lost"), None]) as put:
            self.saver.put_writes(config, writes, "task-1", "rewrite_sections")
        self.assertEqual(put.call_count, 2)
        self.assertEqual(put.call_args_list[0], put.call_args_list[1])
        self.assertEqual(put.call_args.args, (config, tuple(writes), "task-1", "rewrite_sections"))
        self.sleep.assert_called_once_with(RETRY_DELAYS[0])

    def test_checkpoint_commit_can_be_retried_without_changing_checkpoint_id(self):
        config = {"configurable": {"thread_id": "draft"}}
        checkpoint = {"id": "fixed-id", "channel_values": {"sections": {"summary": "Draft"}}}
        with patch.object(PostgresSaver, "put", side_effect=[ConnectionFailure(), config]) as put:
            self.assertEqual(self.saver.put(config, checkpoint, {}, {}), config)
        self.assertEqual(put.call_args_list[0], put.call_args_list[1])
        self.assertEqual(checkpoint["id"], "fixed-id")

    def test_status_reads_reconnect_after_a_disconnect(self):
        with patch.object(PostgresSaver, "get_tuple", side_effect=[InterfaceError("closed"), "saved checkpoint"]) as read:
            self.assertEqual(self.saver.get_tuple({"configurable": {"thread_id": "draft"}}), "saved checkpoint")
        self.assertEqual(read.call_count, 2)

    def test_permanent_and_non_connection_errors_are_not_retried(self):
        for error in (IntegrityError("constraint"), QueryCanceled(), InvalidPassword()):
            with self.subTest(error=type(error).__name__):
                with patch.object(PostgresSaver, "get_tuple", side_effect=error) as read:
                    with self.assertRaises(type(error)):
                        self.saver.get_tuple({})
                self.assertEqual(read.call_count, 1)
        self.sleep.assert_not_called()

    def test_persistent_disconnect_fails_after_bounded_attempts(self):
        with patch.object(PostgresSaver, "put_writes", side_effect=OperationalError("offline")) as put:
            with self.assertRaises(OperationalError):
                self.saver.put_writes({}, [], "task")
        self.assertEqual(put.call_count, len(RETRY_DELAYS) + 1)
        self.assertEqual(self.sleep.call_count, len(RETRY_DELAYS))

    def test_graph_keeps_generated_draft_without_rerunning_node_after_lost_write_ack(self):
        storage = InMemorySaver()
        generated = []
        failures = []

        def draft(state):
            generated.append(True)
            return {"sections": {"summary": {"content": "Generated exactly once."}}, "gate": "draft_review"}

        def review(state):
            interrupt({"gate": "draft_review", "sections": state["sections"]})
            return {}

        def save_writes(config, writes, task_id, task_path=""):
            storage.put_writes(config, writes, task_id, task_path)
            if any(channel == "sections" for channel, _ in writes) and not failures:
                failures.append(True)
                raise OperationalError("connection lost after commit")

        builder = StateGraph(RecoveryState)
        builder.add_node("draft", draft)
        builder.add_node("review", review)
        builder.add_edge(START, "draft")
        builder.add_edge("draft", "review")
        builder.add_edge("review", END)
        graph = builder.compile(checkpointer=self.saver)
        config = {"configurable": {"thread_id": "recover-write"}}
        with patch.object(PostgresSaver, "get_tuple", side_effect=storage.get_tuple), patch.object(PostgresSaver, "put", side_effect=storage.put), patch.object(PostgresSaver, "put_writes", side_effect=save_writes):
            result = graph.invoke({"sections": {}, "gate": "none"}, config)
            recovered = graph.get_state(config)
        self.assertEqual(len(generated), 1)
        self.assertEqual(len(failures), 1)
        self.assertTrue(result["__interrupt__"])
        self.assertEqual(recovered.values["sections"]["summary"]["content"], "Generated exactly once.")
        self.assertEqual(recovered.tasks[0].interrupts[0].value["gate"], "draft_review")


if __name__ == "__main__":
    unittest.main()
