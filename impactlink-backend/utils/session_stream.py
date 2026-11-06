"""Keep SSE connections alive while synchronous graph work runs off the event loop."""

import asyncio
import json
import logging
import threading

log = logging.getLogger(__name__)
_workers = set()


async def heartbeat_events(events, interval=15):
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()
    disconnected = threading.Event()
    done = object()

    def send(event):
        if not disconnected.is_set():
            loop.call_soon_threadsafe(queue.put_nowait, event)

    def produce():
        try:
            for event in events:
                send(event)
        except Exception:
            log.exception("Session stream failed")
            send({"type": "error", "message": "Draft generation failed. Check the saved session status before retrying."})
        finally:
            send(done)

    worker = asyncio.create_task(asyncio.to_thread(produce))
    _workers.add(worker)
    worker.add_done_callback(_workers.discard)
    try:
        yield ": connected\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=interval)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if event is done:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    finally:
        # Graph work keeps running and checkpointing if the browser disconnects.
        # Stop queuing events for a consumer that no longer exists.
        disconnected.set()
