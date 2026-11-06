import asyncio
import json
import threading
import unittest

from utils.session_stream import heartbeat_events
from utils.session_execution import session_execution, is_session_running


class HeartbeatTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_work_emits_heartbeats_and_completes(self):
        release = threading.Event()

        def events():
            release.wait(2)
            yield {"type": "complete", "response": {"gate": "draft_review"}}

        stream = heartbeat_events(events(), interval=0.01)
        try:
            self.assertEqual(await anext(stream), ": connected\n\n")
            self.assertEqual(await asyncio.wait_for(anext(stream), 1), ": keep-alive\n\n")
            release.set()
            chunks = [chunk async for chunk in stream]
            payloads = [json.loads(chunk.removeprefix("data: ")) for chunk in chunks if chunk.startswith("data: ")]
            self.assertEqual(payloads[-1]["response"]["gate"], "draft_review")
        finally:
            release.set()
            await stream.aclose()

    async def test_disconnect_does_not_cancel_checkpoint_work(self):
        release, finished = threading.Event(), threading.Event()

        def events():
            release.wait(2)
            finished.set()
            yield {"type": "complete"}

        stream = heartbeat_events(events(), interval=0.01)
        await anext(stream)
        await anext(stream)
        await stream.aclose()
        release.set()
        self.assertTrue(await asyncio.to_thread(finished.wait, 1))

    async def test_failures_are_reported_without_exception_details(self):
        def events():
            raise RuntimeError("private diagnostic")
            yield

        with self.assertLogs("utils.session_stream", level="ERROR"):
            chunks = [chunk async for chunk in heartbeat_events(events(), interval=0.01)]
        self.assertIn('"type": "error"', "".join(chunks))
        self.assertNotIn("private diagnostic", "".join(chunks))


class SessionExecutionTests(unittest.TestCase):
    def test_duplicate_advance_is_rejected_and_lock_is_released(self):
        with session_execution("one"):
            self.assertTrue(is_session_running("one"))
            with self.assertRaisesRegex(ValueError, "already drafting"):
                with session_execution("one"):
                    self.fail("duplicate execution was allowed")
            with session_execution("two"):
                self.assertTrue(is_session_running("two"))
        self.assertFalse(is_session_running("one"))

    def test_failed_work_releases_session(self):
        with self.assertRaises(RuntimeError):
            with session_execution("failed"):
                raise RuntimeError("failed generation")
        self.assertFalse(is_session_running("failed"))


if __name__ == "__main__":
    unittest.main()
