"""Prevent concurrent advances of the same session within this backend worker."""

from contextlib import contextmanager
import threading

_lock = threading.Lock()
_running = set()


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
