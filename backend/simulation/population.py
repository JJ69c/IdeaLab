"""Archetype-based population generation.

Replaces the static default_population.json with a generator that creates
NPC populations from archetype definitions. Each NPC is a variation around
its archetype's trait baseline — not a clone, but recognizably part of a
personality cluster.

Social graph generation uses archetype affinity rules: Enthusiasts connect
to Gatekeepers, Followers connect to Pragmatists, etc.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path

from backend.simulation.npc import Npc, NpcPersonality

logger = logging.getLogger(__name__)

ARCHETYPES_PATH = (
    Path(__file__).parent.parent.parent / "data" / "npc_templates" / "archetypes.json"
)

TRAIT_NAMES = [
    "openness", "skepticism", "tech_savviness",
    "price_sensitivity", "social_influence", "conformity", "novelty_seeking",
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ArchetypeDef:
    id: str
    label: str
    decision_style: str
    typical_objections: list[str]
    traits: dict[str, tuple[float, float]]  # trait_name → (min, max)
    preferred_connections: list[str]
    # Evaluation fields (used by evaluation.py, parsed here for convenience)
    evaluation_weights: dict[str, float] | None = None
    adoption_threshold: float = 0.65
    resistance_floor: float = 0.0
    susceptibility_multiplier: float = 1.0


def load_archetypes(path: Path | None = None) -> dict:
    """Load the full archetypes.json and return the raw dict."""
    path = path or ARCHETYPES_PATH
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_archetype_defs(raw: dict) -> dict[str, ArchetypeDef]:
    """Parse archetype definitions from archetypes.json."""
    defs = {}
    for a in raw["archetypes"]:
        traits = {
            name: (a["traits"][name]["min"], a["traits"][name]["max"])
            for name in TRAIT_NAMES
        }
        defs[a["id"]] = ArchetypeDef(
            id=a["id"],
            label=a["label"],
            decision_style=a["decision_style"],
            typical_objections=a["typical_objections"],
            traits=traits,
            preferred_connections=a["preferred_connections"],
            evaluation_weights=a.get("evaluation_weights"),
            adoption_threshold=a.get("adoption_threshold", 0.65),
            resistance_floor=a.get("resistance_floor", 0.0),
            susceptibility_multiplier=a.get("susceptibility_multiplier", 1.0),
        )
    return defs


# ---------------------------------------------------------------------------
# NPC generation
# ---------------------------------------------------------------------------

def _sample_trait(lo: float, hi: float, rng: random.Random) -> float:
    """Sample a trait value uniformly within the archetype range.

    Uniform distribution (not triangular) gives better within-archetype
    diversity.  Trait bounds are already widened for secondary traits and
    kept narrow for signature traits, so uniform sampling respects
    archetype identity while producing meaningful individual variation.
    """
    return round(rng.uniform(lo, hi), 3)


def generate_npc(
    npc_id: str,
    archetype: ArchetypeDef,
    name: str,
    occupation: str,
    income_level: str,
    rng: random.Random,
) -> Npc:
    """Generate a single NPC as a variation of the given archetype."""
    traits = {}
    for trait_name in TRAIT_NAMES:
        lo, hi = archetype.traits[trait_name]
        traits[trait_name] = _sample_trait(lo, hi, rng)

    age = rng.randint(22, 58)

    # Communication style derived from archetype
    styles = {
        "analytical_skeptic": ["questioning", "evidence-demanding", "detail-oriented", "cautious"],
        "trend_adopter": ["enthusiastic", "trend-aware", "energetic", "visionary"],
        "price_pragmatist": ["cost-aware", "value-focused", "data-driven", "practical"],
        "health_evaluator": ["evidence-seeking", "health-conscious", "cautiously analytical"],
        "brand_buyer": ["trend-aware", "aesthetics-driven", "brand-conscious", "aspirational"],
        "social_follower": ["agreeable", "consensus-seeking", "observational", "peer-referencing"],
        "convenience_user": ["time-conscious", "direct", "efficiency-focused", "impatient"],
        "values_buyer": ["mission-oriented", "ethics-focused", "principled", "advocacy-driven"],
    }
    style = rng.choice(styles.get(archetype.id, ["neutral"]))

    return Npc(
        id=npc_id,
        name=name,
        age=age,
        occupation=occupation,
        income_level=income_level,
        personality=NpcPersonality(**traits),
        interests=[],
        values=[],
        pain_points=[],
        communication_style=style,
        social_connections=[],  # filled by build_social_graph
        trust_weights={},       # filled by build_social_graph
        archetype=archetype.id,
        decision_style=archetype.decision_style,
    )


# ---------------------------------------------------------------------------
# Social graph generation
# ---------------------------------------------------------------------------

def build_social_graph(
    npcs: list[Npc],
    npc_archetypes: dict[str, str],  # npc_id → archetype_id
    archetype_defs: dict[str, ArchetypeDef],
    rng: random.Random,
    min_connections: int = 2,
    max_connections: int = 5,
):
    """Wire up social connections based on archetype affinity.

    Each NPC gets min_connections to max_connections links. Preferred archetype
    pairings get 3x weight in the selection lottery, so Enthusiasts are more
    likely to connect to Gatekeepers than to Budget-Conscious, etc.

    Trust weights: within-archetype pairs get higher base trust (0.65-0.85),
    cross-archetype pairs get moderate trust (0.40-0.65), with random jitter.
    """
    npc_map = {n.id: n for n in npcs}
    all_ids = [n.id for n in npcs]

    for npc in npcs:
        my_arch = npc_archetypes[npc.id]
        my_def = archetype_defs[my_arch]
        preferred = set(my_def.preferred_connections)

        # Build weighted candidate pool (exclude self and existing connections)
        existing = set(npc.social_connections)
        candidates = [cid for cid in all_ids if cid != npc.id and cid not in existing]

        if not candidates:
            continue

        # How many connections to add (up to max, considering existing)
        target_count = rng.randint(min_connections, max_connections)
        need = max(0, target_count - len(existing))
        if need == 0:
            continue

        # Weight candidates: preferred archetypes get 3x
        weights = []
        for cid in candidates:
            c_arch = npc_archetypes[cid]
            w = 3.0 if c_arch in preferred else 1.0
            weights.append(w)

        # Sample without replacement
        chosen = _weighted_sample(candidates, weights, min(need, len(candidates)), rng)

        for cid in chosen:
            # Add bidirectional connection
            if cid not in npc.social_connections:
                npc.social_connections.append(cid)
            other = npc_map[cid]
            if npc.id not in other.social_connections:
                other.social_connections.append(npc.id)

            # Trust weight
            c_arch = npc_archetypes[cid]
            if c_arch == my_arch:
                trust = round(rng.uniform(0.65, 0.85), 2)
            elif c_arch in preferred:
                trust = round(rng.uniform(0.50, 0.70), 2)
            else:
                trust = round(rng.uniform(0.35, 0.55), 2)

            npc.trust_weights[cid] = trust
            # Give the other side a similar (but not identical) trust
            if npc.id not in other.trust_weights:
                other.trust_weights[npc.id] = round(trust + rng.uniform(-0.08, 0.08), 2)


def _weighted_sample(
    items: list, weights: list[float], k: int, rng: random.Random
) -> list:
    """Weighted sampling without replacement."""
    items = list(items)
    weights = list(weights)
    chosen = []
    for _ in range(k):
        if not items:
            break
        total = sum(weights)
        if total <= 0:
            break
        r = rng.random() * total
        cumulative = 0.0
        for i, w in enumerate(weights):
            cumulative += w
            if r <= cumulative:
                chosen.append(items.pop(i))
                weights.pop(i)
                break
    return chosen


# ---------------------------------------------------------------------------
# Population generation (main entry point)
# ---------------------------------------------------------------------------

def generate_population(
    size: int = 30,
    preset: str = "balanced",
    seed: int | None = None,
) -> tuple[list[Npc], dict[str, str]]:
    """Generate a full NPC population from archetypes.

    Args:
        size: Target population size.
        preset: Composition preset name (from archetypes.json).
        seed: Optional random seed for reproducibility.

    Returns:
        (npcs, npc_archetypes) where npc_archetypes maps npc_id → archetype_id.
    """
    rng = random.Random(seed)
    raw = load_archetypes()
    archetype_defs = parse_archetype_defs(raw)
    presets = raw.get("presets", {})
    name_pool = list(raw.get("name_pool", []))
    occupation_pool = raw.get("occupation_pool", {})
    income_pool = raw.get("income_pool", {})

    # Determine composition
    if preset in presets:
        composition = presets[preset]["composition"]
    else:
        logger.warning("Unknown preset '%s', falling back to 'balanced'", preset)
        composition = presets.get("balanced", {a: 5 for a in archetype_defs})

    # Scale composition to requested size
    raw_total = sum(composition.values())
    if raw_total != size:
        composition = _scale_composition(composition, size)

    # Shuffle name pool
    rng.shuffle(name_pool)

    # Generate NPCs
    npcs: list[Npc] = []
    npc_archetypes: dict[str, str] = {}
    name_idx = 0

    for arch_id, count in composition.items():
        arch_def = archetype_defs[arch_id]
        occupations = occupation_pool.get(arch_id, ["Professional"])
        incomes = income_pool.get(arch_id, ["middle"])

        for i in range(count):
            npc_id = f"npc_{len(npcs) + 1:03d}"

            # Pick name (cycle if pool exhausted)
            name = name_pool[name_idx % len(name_pool)] if name_pool else f"NPC {npc_id}"
            name_idx += 1

            npc = generate_npc(
                npc_id=npc_id,
                archetype=arch_def,
                name=name,
                occupation=rng.choice(occupations),
                income_level=rng.choice(incomes),
                rng=rng,
            )
            npcs.append(npc)
            npc_archetypes[npc_id] = arch_id

    # Build social graph
    build_social_graph(npcs, npc_archetypes, archetype_defs, rng)

    logger.info(
        "Generated %d NPCs from preset '%s': %s",
        len(npcs), preset,
        {k: v for k, v in composition.items()},
    )
    return npcs, npc_archetypes


def _scale_composition(composition: dict[str, int], target: int) -> dict[str, int]:
    """Scale a composition dict to hit a target total, preserving ratios."""
    raw_total = sum(composition.values())
    if raw_total == 0:
        return composition

    # Proportional scaling with rounding
    scaled = {}
    remaining = target
    items = sorted(composition.items(), key=lambda x: x[1], reverse=True)

    for i, (arch_id, count) in enumerate(items):
        if i == len(items) - 1:
            # Last one gets whatever's left
            scaled[arch_id] = max(1, remaining)
        else:
            n = max(1, round(count / raw_total * target))
            n = min(n, remaining - (len(items) - i - 1))  # leave at least 1 for each remaining
            scaled[arch_id] = n
            remaining -= n

    return scaled
