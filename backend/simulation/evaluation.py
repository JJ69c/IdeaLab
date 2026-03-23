"""Archetype-level evaluation: maps ProductProfile signals to deterministic interest baselines.

This is the core of the simulation redesign. Instead of letting the LLM
generate an interest_score (0-1) that dominates the outcome, we compute a
deterministic baseline from ProductProfile dimensions x archetype-specific
weights. The LLM then provides only a bounded hint (+-0.10) on top.

Score composition:
    archetype_baseline  (0.15-0.85)  deterministic, from ProductProfile x weights
  + individual_delta    (+-0.20)     deterministic, from trait deviation x ProductProfile
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

# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------

# Baseline center: the interest score a product with zero net signal produces.
# At 0.50 (old default) "neutral" landed in the "curious" band, biasing green.
# At 0.40, "neutral" lands in "indifferent", requiring genuine product
# strength to push into positive stances.
BASELINE_CENTER: float = 0.40

ARCHETYPES_PATH = (
    Path(__file__).parent.parent.parent / "data" / "npc_templates" / "archetypes.json"
)

# ---------------------------------------------------------------------------
# Category-archetype affinity matrix
# ---------------------------------------------------------------------------
# Maps (archetype, category_group) → identity_fit multiplier.
# 1.0 = neutral (same as product-level identity_fit).
# >1.0 = this archetype naturally gravitates toward this category.
# <1.0 = poor fit — the product's category doesn't resonate with this persona.
#
# Categories are grouped to keep the matrix manageable:
#   tech:     saas, mobile_app, productivity_tool, developer_tool, ai_ml_product, browser_extension
#   consumer: social_platform, marketplace, content_media, ecommerce, gaming, subscription_box
#   fintech:  payments, lending, insurance, investing, crypto_web3
#   health:   health_wellness, biotech, mental_health, fitness
#   hardware: consumer_hardware, iot_smart_home, wearable
#   impact:   education, nonprofit, energy_climate, food_beverage
#   other:    real_estate, transportation, general, (unknown)

_CATEGORY_TO_GROUP: dict[str, str] = {
    "saas": "tech", "mobile_app": "tech", "productivity_tool": "tech",
    "developer_tool": "tech", "ai_ml_product": "tech", "browser_extension": "tech",
    "social_platform": "consumer", "marketplace": "consumer", "content_media": "consumer",
    "ecommerce": "consumer", "gaming": "consumer", "subscription_box": "consumer",
    "payments": "fintech", "lending": "fintech", "insurance": "fintech",
    "investing": "fintech", "crypto_web3": "fintech",
    "health_wellness": "health", "biotech": "health", "mental_health": "health",
    "fitness": "health",
    "consumer_hardware": "hardware", "iot_smart_home": "hardware", "wearable": "hardware",
    "education": "impact", "nonprofit": "impact", "energy_climate": "impact",
    "food_beverage": "impact",
    "real_estate": "other", "transportation": "other", "general": "other",
}

# Rows = archetypes, Columns = category groups
# Design rationale:
#   - analytical_skeptic: drawn to tech, skeptical of consumer/fintech hype
#   - trend_adopter: drawn to consumer, tech, crypto — anything with buzz
#   - price_pragmatist: drawn to consumer/tech (value-clear), avoids fintech/hardware (cost)
#   - health_evaluator: strongly drawn to health, moderate for impact, cold to fintech
#   - brand_buyer: drawn to consumer, hardware (status), cold to impact/tech-tools
#   - social_follower: drawn to consumer/social, moderate elsewhere
#   - convenience_user: drawn to tech/consumer (solve daily problems), cold to fintech
#   - values_buyer: drawn to impact/health, cold to fintech/consumer-frivolous
_CATEGORY_AFFINITY: dict[str, dict[str, float]] = {
    "analytical_skeptic": {
        "tech": 1.30, "consumer": 0.75, "fintech": 0.80, "health": 0.95,
        "hardware": 1.10, "impact": 1.00, "other": 0.90,
    },
    "trend_adopter": {
        "tech": 1.20, "consumer": 1.35, "fintech": 1.15, "health": 0.80,
        "hardware": 1.10, "impact": 0.70, "other": 0.85,
    },
    "price_pragmatist": {
        "tech": 1.10, "consumer": 1.15, "fintech": 0.75, "health": 0.90,
        "hardware": 0.70, "impact": 0.85, "other": 1.00,
    },
    "health_evaluator": {
        "tech": 0.80, "consumer": 0.70, "fintech": 0.60, "health": 1.50,
        "hardware": 0.85, "impact": 1.15, "other": 0.80,
    },
    "brand_buyer": {
        "tech": 0.85, "consumer": 1.40, "fintech": 0.90, "health": 0.80,
        "hardware": 1.25, "impact": 0.65, "other": 0.90,
    },
    "social_follower": {
        "tech": 0.90, "consumer": 1.30, "fintech": 0.85, "health": 0.85,
        "hardware": 0.95, "impact": 0.80, "other": 0.95,
    },
    "convenience_user": {
        "tech": 1.25, "consumer": 1.15, "fintech": 0.75, "health": 0.90,
        "hardware": 1.00, "impact": 0.80, "other": 0.95,
    },
    "values_buyer": {
        "tech": 0.80, "consumer": 0.65, "fintech": 0.60, "health": 1.20,
        "hardware": 0.75, "impact": 1.50, "other": 0.90,
    },
}


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

def get_identity_fit_multiplier(archetype_id: str | None, category: str | None) -> float:
    """Get the identity_fit multiplier for an archetype–category pair.

    Returns 1.0 (neutral) if the archetype or category is unknown.
    """
    if not archetype_id or not category:
        return 1.0
    cat_group = _CATEGORY_TO_GROUP.get(category.lower().strip(), "other")
    arch_affinities = _CATEGORY_AFFINITY.get(archetype_id)
    if not arch_affinities:
        return 1.0
    return arch_affinities.get(cat_group, 1.0)


def compute_archetype_baseline(
    profile: ProductProfile,
    eval_def: ArchetypeEvaluation,
    category: str | None = None,
) -> float:
    """Compute deterministic interest baseline from product signals x archetype weights.

    Raw score is in approximately [-0.5, +0.5]:
      - All positive weights at max signal (1.0) ≈ +0.5
      - All negative weights at max signal (1.0) ≈ -0.5

    Linearly mapped to [0.15, 0.85] via: baseline = BASELINE_CENTER + raw.
    Floor/ceiling prevents deterministic scores from being extreme,
    leaving room for LLM hint and social dynamics to shift outcomes.

    When a category is provided, the identity_fit signal is multiplied by the
    archetype–category affinity before weighting. This makes the same product's
    identity_fit resonate differently across archetypes: a health product feels
    like a natural fit for health_evaluators but alien to trend_adopters.

    Returns:
        float: Interest baseline in [0.15, 0.85].
    """
    # Per-archetype identity_fit adjustment
    fit_multiplier = get_identity_fit_multiplier(eval_def.archetype_id, category)

    raw = 0.0
    for dim_name, weight in eval_def.weights.items():
        signal = getattr(profile, dim_name, 0.5)
        if dim_name == "identity_fit":
            signal = min(1.0, signal * fit_multiplier)
        raw += weight * signal

    return max(0.15, min(0.85, BASELINE_CENTER + raw))


def compute_individual_delta(
    personality: NpcPersonality, profile: ProductProfile
) -> float:
    """Per-NPC variation on top of archetype baseline. Returns delta in [-0.20, +0.20].

    This captures how an individual NPC's traits deviate from their archetype
    midpoint, interacting with product signals. A high-novelty-seeking NPC
    in a low-novelty-seeking archetype gets a novelty boost their archetype
    baseline doesn't reflect.

    Coefficients are scaled so that within-archetype variation is meaningful
    (std ~0.03-0.06), creating genuine per-NPC diversity while keeping the
    archetype's behavioral core intact.
    """
    delta = 0.0

    openness = personality.openness
    skepticism = personality.skepticism
    price_sens = personality.price_sensitivity
    tech = personality.tech_savviness
    novelty_seek = personality.novelty_seeking
    conformity = personality.conformity

    # --- Linear terms (2x coefficients for meaningful within-archetype spread) ---

    # Price-sensitive NPC + expensive product
    delta -= profile.price_friction * price_sens * 0.20

    # Low tech-savviness + high trial friction
    delta -= profile.trial_friction * (1 - tech) * 0.12

    # High novelty seeking + novel product
    delta += profile.novelty * novelty_seek * 0.12

    # High skepticism + high trust barrier
    delta -= profile.trust_barrier * skepticism * 0.12

    # Clear utility + high openness
    delta += profile.utility_clarity * openness * 0.10

    # Strong differentiation universal boost
    delta += profile.differentiation * 0.05

    # Market saturation dampens less adventurous NPCs
    delta -= profile.market_saturation * (1 - novelty_seek) * 0.10

    # Conformist penalty for unproven products (low market saturation)
    delta -= conformity * (1.0 - profile.market_saturation) * 0.06

    # --- Interaction terms ---

    # Expensive + unproven + skeptical compound penalty
    delta -= profile.price_friction * profile.trust_barrier * skepticism * 0.10

    # Clear value + differentiated + open-minded compound boost
    delta += profile.utility_clarity * profile.differentiation * openness * 0.08

    return max(-0.20, min(0.20, round(delta, 4)))
