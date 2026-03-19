"""Thread-safe event store for streaming simulation events via SSE."""

from __future__ import annotations

import threading


class SimulationEventStore:
    """Stores simulation events in memory for streaming to clients.

    Thread-safe: the simulation runs in a background thread and pushes events,
    while the SSE endpoint reads from the main async thread.
    """

    def __init__(self):
        self._events: dict[str, list[dict]] = {}
        self._complete: dict[str, bool] = {}
        self._lock = threading.Lock()

    def push(self, sim_id: str, event: dict):
        with self._lock:
            self._events.setdefault(sim_id, []).append(event)

    def mark_complete(self, sim_id: str):
        with self._lock:
            self._complete[sim_id] = True

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


# Singleton — shared between the simulation thread and SSE endpoint
event_store = SimulationEventStore()
