"""Retry idempotent checkpoint I/O after a transient database disconnect.

Retry the save itself, never graph.invoke/stream: repeating a graph can rerun AI
nodes. PostgresSaver's checkpoint/blob/write keys and ON CONFLICT statements
make repeating these individual writes safe, including an acknowledgement lost
after the database committed. Each attempt checks out a fresh pooled connection.
"""

import logging
import time

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import InterfaceError, OperationalError

log = logging.getLogger(__name__)
RETRY_DELAYS = (0.25, 1.0, 2.0)


def transient_connection_error(error):
    code = getattr(error, "sqlstate", None)
    return code is None or code.startswith("08") or code in {"57P01", "57P02", "57P03"}


class RetryingPostgresSaver(PostgresSaver):
    def _retry_io(self, name, operation, *args):
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                return operation(*args)
            except (OperationalError, InterfaceError) as error:
                if not transient_connection_error(error) or attempt == len(RETRY_DELAYS):
                    raise
                # Do not log connection strings, checkpoint text or raw DB errors.
                log.warning("Checkpoint %s connection interrupted; retrying database operation (%d/%d)", name, attempt + 1, len(RETRY_DELAYS))
                time.sleep(RETRY_DELAYS[attempt])

    def put(self, config, checkpoint, metadata, new_versions):
        return self._retry_io("put", super().put, config, checkpoint, metadata, new_versions)

    def put_writes(self, config, writes, task_id, task_path=""):
        # Keep the same materialized writes and task ID across attempts.
        return self._retry_io("put_writes", super().put_writes, config, tuple(writes), task_id, task_path)

    def get_tuple(self, config):
        return self._retry_io("get_tuple", super().get_tuple, config)
