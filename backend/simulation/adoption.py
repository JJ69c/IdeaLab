"""Per-NPC adoption model — behavioral outcome separate from interest.

Adoption answers: "Would this person actually start using this product?"
It is NOT interest (curiosity), NOT willingness to try (low commitment),
NOT willingness to pay (financial readiness). It is a composite behavioral
outcome gated by interest and filtered through barriers.

Formula:
    adoption_score = interest_score × (1.0 - effective_barrier)

    effective_barrier = weighted sum of personality-adjusted barriers:
        trust_gap:     trust_barrier × (0.5 + 0.5 × skepticism)
        clarity_gap:   (1.0 - utility_clarity)
        price_gap:     price_friction × price_sensitivity   (paid products only)
        trial_gap:     trial_friction × (1.0 - tech_savviness)
        switching_gap: switching_cost_pressure × (0.3 + 0.7 × conformity)
        inertia_gap:   incumbent_trust_pressure × (0.3 + 0.7 × (1 - openness))

    Hard gates (force adopted = False):
        - Not aware
        - interest_score < 0.30
        - Paid product AND would_pay = False

    Threshold: adopted = True if adoption_score >= 0.50

All inputs are deterministic — no LLM calls. The formula is inspectable
and each barrier can be tuned independently.
"""

from __future__ import annotations

from dataclasses import dataclass

# Barrier weights (sum to 1.0)
BARRIER_WEIGHTS = {
    "trust": 0.20,
    "clarity": 0.15,
    "price": 0.20,
    "trial": 0.15,
    "switching": 0.15,
    "inertia": 0.15,
}

# Threshold for adopted = True
ADOPTION_THRESHOLD = 0.50

# Minimum interest to even consider adoption
MIN_INTEREST_FOR_ADOPTION = 0.30

# Price friction above which the product is considered "paid"
PAID_PRODUCT_THRESHOLD = 0.05


@dataclass(frozen=True)
class AdoptionResult:
    """Per-NPC adoption outcome."""

    adopted: bool
    score: float                # 0.0-1.0
    blockers: tuple[str, ...]   # Human-readable barrier explanations
    barriers: dict              # Raw barrier values for inspection
    hard_gate_reason: str       # "" if no hard gate triggered


_BLOCKER_LABELS = {
    "trust_gap": "Insufficient trust in the product",
    "clarity_gap": "Unclear value proposition",
    "price_gap": "Price too high for this person",
    "trial_gap": "Too difficult to try",
    "switching_gap": "High switching cost from current solution",
    "inertia_gap": "Strong attachment to incumbents",
}


def compute_npc_adoption(
    *,
    interest_score: float,
    would_pay: bool,
    aware: bool,
    personality: dict,
    profile_dict: dict | None = None,
    competition_dict: dict | None = None,
) -> AdoptionResult:
    """Compute adoption outcome for a single NPC.

    Args:
        interest_score: NPC's current interest (0-1).
        would_pay: Whether the NPC would pay (from LLM reaction).
        aware: Whether the NPC is aware of the idea.
        personality: Dict with openness, skepticism, tech_savviness,
                     price_sensitivity, conformity, etc.
        profile_dict: ProductProfile.to_dict() — product-level dimensions.
        competition_dict: CompetitionContext.to_dict() — competition dimensions.

    Returns:
        AdoptionResult with adopted flag, score, and barrier breakdown.
    """
    # --- Hard gates ---
    if not aware:
        return AdoptionResult(
            adopted=False, score=0.0, blockers=(),
            barriers={}, hard_gate_reason="not_aware",
        )

    if interest_score < MIN_INTEREST_FOR_ADOPTION:
        return AdoptionResult(
            adopted=False, score=0.0, blockers=("Insufficient interest",),
            barriers={}, hard_gate_reason="low_interest",
        )

    # Product and competition dimensions (defaults when unavailable)
    p = profile_dict or {}
    c = competition_dict or {}

    price_friction = p.get("price_friction", 0.3)
    trust_barrier = p.get("trust_barrier", 0.3)
    utility_clarity = p.get("utility_clarity", 0.5)
    trial_friction = p.get("trial_friction", 0.3)

    is_paid = price_friction > PAID_PRODUCT_THRESHOLD

    # Hard gate: paid product requires would_pay
    if is_paid and not would_pay:
        return AdoptionResult(
            adopted=False, score=0.0,
            blockers=("Would not pay for this product",),
            barriers={}, hard_gate_reason="would_not_pay",
        )

    # --- Personality traits ---
    skepticism = personality.get("skepticism", 0.5)
    price_sensitivity = personality.get("price_sensitivity", 0.5)
    tech_savviness = personality.get("tech_savviness", 0.5)
    openness = personality.get("openness", 0.5)
    conformity = personality.get("conformity", 0.5)

    # --- Compute individual barriers (each 0-1) ---
    trust_gap = trust_barrier * (0.5 + 0.5 * skepticism)
    clarity_gap = 1.0 - utility_clarity
    price_gap = price_friction * price_sensitivity if is_paid else 0.0
    trial_gap = trial_friction * (1.0 - tech_savviness)

    switching_cost_pressure = c.get("switching_cost_pressure", 0.0)
    incumbent_trust_pressure = c.get("incumbent_trust_pressure", 0.0)
    switching_gap = switching_cost_pressure * (0.3 + 0.7 * conformity)
    inertia_gap = incumbent_trust_pressure * (0.3 + 0.7 * (1.0 - openness))

    # --- Weighted barrier ---
    effective_barrier = (
        BARRIER_WEIGHTS["trust"] * trust_gap
        + BARRIER_WEIGHTS["clarity"] * clarity_gap
        + BARRIER_WEIGHTS["price"] * price_gap
        + BARRIER_WEIGHTS["trial"] * trial_gap
        + BARRIER_WEIGHTS["switching"] * switching_gap
        + BARRIER_WEIGHTS["inertia"] * inertia_gap
    )
    effective_barrier = max(0.0, min(1.0, effective_barrier))

    # --- Adoption score ---
    adoption_score = interest_score * (1.0 - effective_barrier)
    adoption_score = max(0.0, min(1.0, round(adoption_score, 4)))

    # --- Determine blockers (barriers > 0.5 are significant) ---
    barrier_values = {
        "trust_gap": round(trust_gap, 3),
        "clarity_gap": round(clarity_gap, 3),
        "price_gap": round(price_gap, 3),
        "trial_gap": round(trial_gap, 3),
        "switching_gap": round(switching_gap, 3),
        "inertia_gap": round(inertia_gap, 3),
        "effective_barrier": round(effective_barrier, 3),
    }

    blockers = []
    for key, label in _BLOCKER_LABELS.items():
        if barrier_values[key] > 0.5:
            blockers.append(label)

    adopted = adoption_score >= ADOPTION_THRESHOLD

    return AdoptionResult(
        adopted=adopted,
        score=adoption_score,
        blockers=tuple(blockers),
        barriers=barrier_values,
        hard_gate_reason="",
    )


def compute_world_adoptions(world) -> dict:
    """Compute adoption for all NPCs in the world.

    Sets adoption fields on each aware NPC's state and returns summary stats.
    Call after all tick phases complete (interest_score is settled for this tick).
    """
    profile_dict = (
        world.product_profile.to_dict()
        if getattr(world, "product_profile", None)
        else None
    )
    competition_dict = (
        world.competition_context.to_dict()
        if getattr(world, "competition_context", None)
        else None
    )

    adopted_count = 0
    blocker_counts: dict[str, int] = {}

    for npc in world.npcs.values():
        personality = npc.to_profile_dict().get("personality", {})
        result = compute_npc_adoption(
            interest_score=npc.state.interest_score,
            would_pay=npc.state.would_pay,
            aware=npc.state.aware,
            personality=personality,
            profile_dict=profile_dict,
            competition_dict=competition_dict,
        )
        npc.state.adopted = result.adopted
        npc.state.adoption_score = result.score
        npc.state.adoption_blockers = list(result.blockers)

        if result.adopted:
            adopted_count += 1
        for blocker in result.blockers:
            blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1

    aware_count = len(world.aware_npcs)
    return {
        "adoption_rate": round(adopted_count / aware_count, 3) if aware_count else 0,
        "adopted_count": adopted_count,
        "aware_count": aware_count,
        "top_blockers": sorted(blocker_counts.items(), key=lambda x: -x[1]),
    }
