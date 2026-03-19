"""World state for a single simulation run."""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path

from backend.simulation.npc import Npc

logger = logging.getLogger(__name__)

DEFAULT_POPULATION_PATH = Path(__file__).parent.parent.parent / "data" / "npc_templates" / "default_population.json"


@dataclass
class InjectedIdea:
    title: str
    description: str
    category: str = "general"
    stage: str = "concept"
    target_audience: str = "general public"
    problem_statement: str = ""
    price_point: str = "not specified"
    existing_alternatives: str = ""
    differentiator: str = ""
    known_strengths: str = ""
    known_risks: str = ""

    def to_dict(self) -> dict:
        d = {
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "stage": self.stage,
            "target_audience": self.target_audience,
            "price_point": self.price_point,
        }
        # Only include optional fields when populated
        if self.problem_statement:
            d["problem_statement"] = self.problem_statement
        if self.existing_alternatives:
            d["existing_alternatives"] = self.existing_alternatives
        if self.differentiator:
            d["differentiator"] = self.differentiator
        if self.known_strengths:
            d["known_strengths"] = self.known_strengths
        if self.known_risks:
            d["known_risks"] = self.known_risks
        return d


@dataclass
class SimConfig:
    num_ticks: int = 8
    population_size: int = 30
    seed_count: int = 5


@dataclass
class SpreadEvent:
    source_id: str
    target_id: str


@dataclass
class WorldState:
    idea: InjectedIdea
    config: SimConfig
    npcs: dict[str, Npc] = field(default_factory=dict)
    current_tick: int = 0
    event_log: list[dict] = field(default_factory=list)
    discussion_log: list[dict] = field(default_factory=list)
    pending_spreads: list[SpreadEvent] = field(default_factory=list)

    # Set by engine after world creation (avoids circular import)
    product_profile: object | None = None

    # Per-pair discussion cooldown: maps frozenset({npc_a_id, npc_b_id}) → last tick discussed
    discussion_cooldowns: dict = field(default_factory=dict)

    # npc_id → archetype_id (set by engine when using archetype-based generation)
    npc_archetypes: dict[str, str] = field(default_factory=dict)

    # Structured signals from reference assets (set by engine when assets provided)
    asset_signals: object | None = None

    @property
    def aware_npcs(self) -> list[Npc]:
        return [n for n in self.npcs.values() if n.state.aware]

    @property
    def interested_npcs(self) -> list[Npc]:
        return [n for n in self.npcs.values() if n.state.aware and n.state.interest_score >= 0.6]

    @property
    def unaware_npcs(self) -> list[Npc]:
        return [n for n in self.npcs.values() if not n.state.aware]

    def log_event(self, tick: int, npc_id: str, event_type: str, data: dict):
        entry = {"tick": tick, "npc_id": npc_id, "event_type": event_type, "data": data}
        self.event_log.append(entry)

    def compute_metrics(self) -> dict:
        total = len(self.npcs)
        aware = len(self.aware_npcs)
        if aware == 0:
            return {
                "awareness_rate": 0, "interest_rate": 0, "rejection_rate": 0,
                "viral_coefficient": 0, "net_sentiment": 0, "adoption_likelihood": 0,
            }

        interested = sum(1 for n in self.aware_npcs if n.state.stance in ("interested", "curious"))
        opposed = sum(1 for n in self.aware_npcs if n.state.stance in ("opposed", "skeptical"))
        spreaders = sum(
            1 for n in self.aware_npcs
            if n.state.interest_score >= 0.6 and n.state.would_recommend
        )

        avg_interest = sum(n.state.interest_score for n in self.aware_npcs) / aware
        would_pay_count = sum(1 for n in self.aware_npcs if n.state.would_pay)

        return {
            "total_npcs": total,
            "aware_count": aware,
            "awareness_rate": round(aware / total, 3),
            "interest_rate": round(interested / aware, 3) if aware else 0,
            "rejection_rate": round(opposed / aware, 3) if aware else 0,
            "viral_coefficient": round(spreaders / interested, 3) if interested else 0,
            "net_sentiment": round(avg_interest * 2 - 1, 3),  # map 0-1 to -1 to 1
            "would_pay_rate": round(would_pay_count / aware, 3) if aware else 0,
            "adoption_likelihood": round(
                (avg_interest * 0.4 + (would_pay_count / aware) * 0.3 + (spreaders / max(interested, 1)) * 0.3), 3
            ),
        }

    def get_npc_results(self) -> list[dict]:
        results = []
        for npc in self.npcs.values():
            result = npc.state.to_result_dict()
            result["npc_id"] = npc.id
            result["name"] = npc.name
            result["occupation"] = npc.occupation
            result["age"] = npc.age
            results.append(result)
        return results


def load_population(path: Path | None = None, limit: int | None = None) -> list[Npc]:
    """Load NPC population from a JSON file."""
    path = path or DEFAULT_POPULATION_PATH
    with open(path) as f:
        data = json.load(f)

    npcs = [Npc.from_dict(d) for d in data.get("npcs", data)]

    if limit and len(npcs) > limit:
        npcs = random.sample(npcs, limit)

    logger.info("Loaded %d NPCs from %s", len(npcs), path)
    return npcs
