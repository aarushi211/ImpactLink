"""Prevent concurrent advances of the same session within this backend worker."""

from contextlib import contextmanager
import threading
from langgraph.types import Command

_lock = threading.Lock()
_running = set()


def resume_session_command(user_input):
    """An empty confirmation must still carry a truthy LangGraph resume value."""
    return Command(resume=user_input or {"confirmed": True})


def is_session_running(session_id):
    with _lock:
        return session_id in _running


@contextmanager
def session_execution(session_id):
    with _lock:
        if session_id in _running:
            raise ValueError("This session is already drafting. Check its saved status before trying again.")
        _running.add(session_id)
    try:
        yield
    finally:
        with _lock:
            _running.discard(session_id)
