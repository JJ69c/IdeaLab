"""Archetype-level evaluation: maps ProductProfile signals to deterministic interest baselines.

This is the core of the simulation redesign. Instead of letting the LLM
generate an interest_score (0-1) that dominates the outcome, we compute a
deterministic baseline from ProductProfile dimensions x archetype-specific
weights. The LLM then provides only a bounded hint (+-0.10) on top.

Score composition:
    archetype_baseline  (0.15-0.85)  deterministic, from ProductProfile x weights
  + individual_delta    (+-0.10)     deterministic, from trait deviation x ProductProfile
  + asset_delta         (+-0.08)     deterministic, from AssetSignals x traits
  + llm_hint            (+-0.10)     LLM qualitative reasoning + bounded adjustment
  = final interest_score (0-1)       clamped
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from backend.simulation.npc import NpcPersonality
from backend.simulation.product_profile import ProductProfile

logger = logging.getLogger(__name__)

ARCHETYPES_PATH = (
    Path(__file__).parent.parent.parent / "data" / "npc_templates" / "archetypes.json"
)


@dataclass(frozen=True)
class ArchetypeEvaluation:
    """Weights mapping ProductProfile dimensions to interest contribution.

    Positive weight: high signal value = interest boost.
    Negative weight: high signal value = interest penalty.
    Absolute values of all weights should sum to approximately 1.0.
    """

    archetype_id: str
    weights: dict[str, float]
    adoption_threshold: float = 0.65
    resistance_floor: float = 0.0
    susceptibility_multiplier: float = 1.0


# ---------------------------------------------------------------------------
# Module-level cache (loaded once, reused)
# ---------------------------------------------------------------------------

_EVAL_CACHE: dict[str, ArchetypeEvaluation] | None = None

# Default fallback for archetypes without evaluation_weights in JSON
_DEFAULT_WEIGHTS: dict[str, float] = {
    "novelty": 0.10,
    "utility_clarity": 0.15,
    "differentiation": 0.10,
    "price_friction": -0.15,
    "trust_barrier": -0.15,
    "identity_fit": 0.10,
    "trial_friction": -0.10,
    "market_saturation": -0.10,
}


def _load_evaluations(path: Path | None = None) -> dict[str, ArchetypeEvaluation]:
    """Parse ArchetypeEvaluation definitions from archetypes.json."""
    path = path or ARCHETYPES_PATH
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    evals: dict[str, ArchetypeEvaluation] = {}
    for a in raw.get("archetypes", []):
        arch_id = a["id"]
        weights = a.get("evaluation_weights", _DEFAULT_WEIGHTS)
        evals[arch_id] = ArchetypeEvaluation(
            archetype_id=arch_id,
            weights=weights,
            adoption_threshold=a.get("adoption_threshold", 0.65),
            resistance_floor=a.get("resistance_floor", 0.0),
            susceptibility_multiplier=a.get("susceptibility_multiplier", 1.0),
        )
    return evals


def get_archetype_evaluation(archetype_id: str | None) -> ArchetypeEvaluation:
    """Get the ArchetypeEvaluation for a given archetype ID.

    Returns a neutral fallback if the archetype is unknown or None.
    """
    global _EVAL_CACHE
    if _EVAL_CACHE is None:
        try:
            _EVAL_CACHE = _load_evaluations()
        except Exception:
            logger.exception("Failed to load archetype evaluations, using defaults")
            _EVAL_CACHE = {}

    if archetype_id and archetype_id in _EVAL_CACHE:
        return _EVAL_CACHE[archetype_id]

    return ArchetypeEvaluation(
        archetype_id=archetype_id or "unknown",
        weights=_DEFAULT_WEIGHTS,
    )


def reload_evaluations(path: Path | None = None) -> None:
    """Force reload of evaluation definitions (useful after updating archetypes.json)."""
    global _EVAL_CACHE
    _EVAL_CACHE = _load_evaluations(path)


# ---------------------------------------------------------------------------
# Deterministic baseline computation
# ---------------------------------------------------------------------------

def compute_archetype_baseline(
    profile: ProductProfile, eval_def: ArchetypeEvaluation
) -> float:
    """Compute deterministic interest baseline from product signals x archetype weights.

    Raw score is in approximately [-0.5, +0.5]:
      - All positive weights at max signal (1.0) ≈ +0.5
      - All negative weights at max signal (1.0) ≈ -0.5

    Linearly mapped to [0.15, 0.85] via: baseline = 0.5 + raw.
    Floor/ceiling prevents deterministic scores from being extreme,
    leaving room for LLM hint and social dynamics to shift outcomes.

    Returns:
        float: Interest baseline in [0.15, 0.85].
    """
    raw = 0.0
    for dim_name, weight in eval_def.weights.items():
        signal = getattr(profile, dim_name, 0.5)
        raw += weight * signal

    return max(0.15, min(0.85, 0.5 + raw))


def compute_individual_delta(
    personality: NpcPersonality, profile: ProductProfile
) -> float:
    """Per-NPC variation on top of archetype baseline. Returns delta in [-0.10, +0.10].

    This captures how an individual NPC's traits deviate from their archetype
    midpoint, interacting with product signals. A high-novelty-seeking NPC
    in a low-novelty-seeking archetype gets a novelty boost their archetype
    baseline doesn't reflect.

    This replaces the old compute_npc_adjustment() which operated on LLM scores.
    Same logic, recalibrated for the +-0.10 range.
    """
    delta = 0.0

    openness = personality.openness
    skepticism = personality.skepticism
    price_sens = personality.price_sensitivity
    tech = personality.tech_savviness
    novelty_seek = personality.novelty_seeking

    # --- Linear terms ---

    # Price-sensitive NPC + expensive product
    delta -= profile.price_friction * price_sens * 0.10

    # Low tech-savviness + high trial friction
    delta -= profile.trial_friction * (1 - tech) * 0.06

    # High novelty seeking + novel product
    delta += profile.novelty * novelty_seek * 0.06

    # High skepticism + high trust barrier
    delta -= profile.trust_barrier * skepticism * 0.06

    # Clear utility + high openness
    delta += profile.utility_clarity * openness * 0.05

    # Strong differentiation universal boost
    delta += profile.differentiation * 0.03

    # Market saturation dampens less adventurous NPCs
    delta -= profile.market_saturation * (1 - novelty_seek) * 0.05

    # --- Interaction terms ---

    # Expensive + unproven + skeptical compound penalty
    delta -= profile.price_friction * profile.trust_barrier * skepticism * 0.05

    # Clear value + differentiated + open-minded compound boost
    delta += profile.utility_clarity * profile.differentiation * openness * 0.04

    return max(-0.10, min(0.10, round(delta, 4)))
