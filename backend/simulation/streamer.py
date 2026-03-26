"""Thread-safe event store for streaming simulation events via SSE."""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

# How long (seconds) to keep completed simulation events in memory
# before auto-purging.  Gives SSE clients time to finish reading.
CLEANUP_DELAY_SECONDS = 120


class SimulationEventStore:
    """Stores simulation events in memory for streaming to clients.

    Thread-safe: the simulation runs in a background thread and pushes events,
    while the SSE endpoint reads from the main async thread.

    Completed simulations are auto-purged after CLEANUP_DELAY_SECONDS to
    prevent unbounded memory growth.
    """

    def __init__(self):
        self._events: dict[str, list[dict]] = {}
        self._complete: dict[str, bool] = {}
        self._completed_at: dict[str, float] = {}  # sim_id → monotonic timestamp
        self._lock = threading.Lock()

    def push(self, sim_id: str, event: dict):
        with self._lock:
            self._events.setdefault(sim_id, []).append(event)

    def mark_complete(self, sim_id: str):
        with self._lock:
            self._complete[sim_id] = True
            self._completed_at[sim_id] = time.monotonic()

    def is_complete(self, sim_id: str) -> bool:
        with self._lock:
            return self._complete.get(sim_id, False)

    def get_events_from(self, sim_id: str, cursor: int) -> list[dict]:
        with self._lock:
            return list(self._events.get(sim_id, [])[cursor:])

    def register(self, sim_id: str):
        """Pre-register a simulation so has_simulation() returns True immediately."""
        with self._lock:
            self._events.setdefault(sim_id, [])

    def has_simulation(self, sim_id: str) -> bool:
        with self._lock:
            return sim_id in self._events

    def cleanup(self, sim_id: str):
        with self._lock:
            self._events.pop(sim_id, None)
            self._complete.pop(sim_id, None)
            self._completed_at.pop(sim_id, None)

    def purge_stale(self):
        """Remove completed simulations older than CLEANUP_DELAY_SECONDS.

        Call this periodically (e.g. after each simulation completes or from
        a background timer) to bound memory usage.
        """
        now = time.monotonic()
        to_remove: list[str] = []
        with self._lock:
            for sim_id, completed_at in self._completed_at.items():
                if now - completed_at > CLEANUP_DELAY_SECONDS:
                    to_remove.append(sim_id)
            for sim_id in to_remove:
                event_count = len(self._events.get(sim_id, []))
                self._events.pop(sim_id, None)
                self._complete.pop(sim_id, None)
                self._completed_at.pop(sim_id, None)
                logger.info(
                    "Purged event store for sim %s (%d events freed)", sim_id, event_count
                )
        return len(to_remove)

    def active_count(self) -> int:
        """Number of simulations currently held in memory."""
        with self._lock:
            return len(self._events)


# Singleton — shared between the simulation thread and SSE endpoint
event_store = SimulationEventStore()
