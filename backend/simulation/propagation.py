"""Deterministic social influence and spread logic. No LLM calls here.

When a ProductProfile is available on the WorldState, the profile dimensions
modulate the base formulas:
- market_saturation dampens peer influence (strong priors in crowded markets)
- novelty boosts word-of-mouth spread
- price_friction reduces casual recommendations
- trust_barrier increases the threshold for positive spread

Includes both positive spread (recommendation) and negative concern propagation:
- Positive spread: enthusiastic NPCs make unaware connections aware
- Concern spread: skeptical/low-interest NPCs dampen interest of aware connections

Stage 3 additions:
- Archetype-aware susceptibility via susceptibility_multiplier
- Exposure decay: diminishing returns over time (except Followers)
- Resistance floor: archetypes below their floor are nearly immune to peer influence
- Source credibility: archetype-specific discussion weight multipliers
"""

from __future__ import annotations

import random

from backend.simulation.evaluation import get_archetype_evaluation
from backend.simulation.npc import Npc
from backend.simulation.world import SpreadEvent, WorldState


# ---------------------------------------------------------------------------
# Archetype source credibility multipliers for discussions
# ---------------------------------------------------------------------------

# How credible each archetype is as a discussion SOURCE.
# Analytical Skeptics carry outsized weight when they endorse.
# Social Followers amplify but don't originate conviction.
_SOURCE_CREDIBILITY: dict[str, float] = {
    "analytical_skeptic": 1.3,
    "health_evaluator": 1.15,
    "values_buyer": 1.05,
    "convenience_user": 0.90,
    "trend_adopter": 0.85,
    "brand_buyer": 0.85,
    "price_pragmatist": 0.80,
    "social_follower": 0.55,
}


def compute_peer_susceptibility(npc: Npc, world: WorldState) -> float:
    """Archetype-aware susceptibility to peer influence.

    Base formula: conformity * (1 - skepticism * 0.3) * 0.3
    Then multiplied by:
    - archetype susceptibility_multiplier
    - exposure decay (diminishing returns over ticks for most archetypes)
    """
    base = npc.personality.conformity * (1.0 - npc.personality.skepticism * 0.3) * 0.3

    # Archetype multiplier
    archetype_id = getattr(npc, "archetype", None)
    eval_def = get_archetype_evaluation(archetype_id)
    base *= eval_def.susceptibility_multiplier

    # Exposure decay: diminishing returns over time
    exposure = npc.state.exposure_count
    if archetype_id == "social_follower":
        # Social Followers get INCREASING returns (social proof accumulates)
        decay = min(1.5, 1.0 + 0.08 * exposure)
    else:
        # Everyone else: diminishing returns
        decay = 1.0 / (1.0 + 0.25 * exposure)

    return base * decay


def calculate_peer_influence(npc: Npc, world: WorldState) -> float:
    """Calculate how much an NPC's opinion shifts based on their social connections.

    Uses a weighted average of connected NPCs' interest scores, modulated by
    susceptibility, trust weights, and archetype resistance floor.
    """
    if not npc.social_connections:
        return 0.0

    weighted_sum = 0.0
    weight_total = 0.0

    for conn_id in npc.social_connections:
        connected = world.npcs.get(conn_id)
        if not connected or not connected.state.aware:
            continue

        trust = npc.trust_weights.get(conn_id, 0.5)
        influence = connected.personality.social_influence

        # How much this connection's opinion matters
        weight = trust * influence
        weighted_sum += connected.state.interest_score * weight
        weight_total += weight

    if weight_total == 0:
        return 0.0

    peer_avg = weighted_sum / weight_total
    current = npc.state.interest_score

    # Delta is pulled toward peer average, modulated by susceptibility
    susceptibility = compute_peer_susceptibility(npc, world)
    raw_delta = (peer_avg - current) * susceptibility

    # Product profile modulation: saturated markets → stronger priors
    profile = getattr(world, "product_profile", None)
    if profile is not None:
        saturation_damper = 1.0 - profile.market_saturation * 0.30
        raw_delta *= saturation_damper

    # Resistance floor: if the NPC's baseline is below their archetype's
    # resistance_floor, peer influence is heavily dampened. The product is
    # fundamentally wrong for them — no amount of enthusiasm changes that.
    archetype_id = getattr(npc, "archetype", None)
    eval_def = get_archetype_evaluation(archetype_id)
    if eval_def.resistance_floor > 0 and profile is not None:
        from backend.simulation.evaluation import compute_archetype_baseline
        idea_category = getattr(world.idea, "category", None) if hasattr(world, "idea") else None
        baseline = compute_archetype_baseline(profile, eval_def, category=idea_category)
        if baseline < eval_def.resistance_floor:
            raw_delta *= 0.15  # nearly immune

    return round(raw_delta, 4)


DISCUSSION_COOLDOWN_TICKS = 2  # skip pairs that discussed within this many ticks


def select_discussion_pairs(
    world: WorldState, max_pairs: int = 5
) -> list[tuple[Npc, Npc]]:
    """Select pairs of NPCs who might discuss the idea this tick.

    Prioritizes pairs where:
    - Both are aware
    - They are socially connected
    - At least one has strong feelings (high or low interest)
    - They haven't discussed within the last DISCUSSION_COOLDOWN_TICKS ticks
    """
    candidates: list[tuple[float, Npc, Npc]] = []
    tick = world.current_tick

    for npc in world.aware_npcs:
        for conn_id in npc.social_connections:
            connected = world.npcs.get(conn_id)
            if not connected or not connected.state.aware:
                continue
            if npc.id >= connected.id:  # avoid duplicates
                continue

            # Per-pair cooldown: skip if they discussed within last N ticks
            pair_key = frozenset({npc.id, connected.id})
            last_discussed = world.discussion_cooldowns.get(pair_key)
            if last_discussed is not None and (tick - last_discussed) < DISCUSSION_COOLDOWN_TICKS:
                continue

            # Score: how "interesting" this discussion would be
            opinion_gap = abs(npc.state.interest_score - connected.state.interest_score)
            passion = max(
                abs(npc.state.interest_score - 0.5),
                abs(connected.state.interest_score - 0.5),
            )
            trust = npc.trust_weights.get(conn_id, 0.5)
            score = (opinion_gap * 0.4 + passion * 0.4 + trust * 0.2)
            candidates.append((score, npc, connected))

    # Sort by score descending, take top N
    candidates.sort(key=lambda x: x[0], reverse=True)
    return [(a, b) for _, a, b in candidates[:max_pairs]]


def compute_discussion_weight(
    source_social_influence: float,
    trust: float,
    target_skepticism: float,
    source_archetype: str | None = None,
) -> float:
    """How much a discussion partner's argument actually moves the target.

    Three factors determine whether words land:
    - source_social_influence: credible, articulate speakers persuade more
    - trust: arguments from trusted connections carry more weight
    - target_skepticism: skeptics discount what they hear

    Stage 3 addition: source archetype credibility multiplier.
    Gatekeepers and Skeptics carry high credibility when endorsing.
    Followers have low source weight — they amplify but don't originate conviction.

    Formula: (source_influence * trust * credibility) / max(target_skepticism, 0.2)
    Clamped to [0.3, 1.5].
    """
    credibility = _SOURCE_CREDIBILITY.get(source_archetype or "", 1.0)
    raw = source_social_influence * trust * credibility / max(target_skepticism, 0.2)
    return max(0.3, min(1.5, raw))


def compute_spread_receptiveness(novelty_seeking: float, openness: float) -> float:
    """How receptive an unaware target is to hearing about a new idea.

    Novelty-seeking is the primary driver (do they actively look for new things?),
    but openness provides a secondary willingness to seriously consider it.
    A closed-minded novelty-seeker might hear about it but dismiss it;
    an open-minded person will engage even if they don't seek novelty.

    Weighted blend: 70% novelty_seeking + 30% openness.
    Returns a factor in [0.0, 1.0].
    """
    return novelty_seeking * 0.7 + openness * 0.3


def compute_spreads(world: WorldState) -> list[SpreadEvent]:
    """Determine which interested NPCs spread awareness to unaware connections.

    Base probability: interest * social_influence * trust * target_receptiveness * 0.5

    Product profile modulation:
    - Novel ideas spread faster (people talk about things they haven't seen before)
    - Expensive products get recommended less casually
    - High trust barriers require stronger conviction from the spreader
    """
    spreads: list[SpreadEvent] = []
    unaware_ids = {n.id for n in world.unaware_npcs}

    profile = getattr(world, "product_profile", None)

    for npc in world.interested_npcs:
        if not npc.state.would_recommend:
            continue

        for conn_id in npc.social_connections:
            if conn_id not in unaware_ids:
                continue

            target = world.npcs.get(conn_id)
            if not target:
                continue

            trust = npc.trust_weights.get(conn_id, 0.5)
            receptiveness = compute_spread_receptiveness(
                target.personality.novelty_seeking, target.personality.openness,
            )
            prob = (
                npc.state.interest_score
                * npc.personality.social_influence
                * trust
                * receptiveness
                * 0.5
            )

            if profile is not None:
                # Novel ideas generate more buzz
                prob *= 1.0 + profile.novelty * 0.30
                # Expensive products → less casual recommending
                prob *= 1.0 - profile.price_friction * 0.20
                # High trust barrier → need stronger conviction to vouch
                if npc.state.interest_score < 0.7 and profile.trust_barrier > 0.5:
                    prob *= 0.6

            if random.random() < prob:
                spreads.append(SpreadEvent(source_id=npc.id, target_id=conn_id))
                unaware_ids.discard(conn_id)  # each NPC learns at most once per tick

    return spreads


# ---------------------------------------------------------------------------
# Negative concern propagation
# ---------------------------------------------------------------------------

# Threshold below which an NPC is "concerned enough" to voice negativity.
# 0.45 allows indifferent-to-skeptical NPCs (not just opposed) to share concerns.
CONCERN_INTEREST_THRESHOLD = 0.45

# Minimum interest a target must have for concern to be worth sharing.
# 0.25 catches mildly negative NPCs — they can still be dampened further.
# Very low-interest targets (< 0.25) are already convinced it's bad.
CONCERN_TARGET_MIN_INTEREST = 0.25

# Base probability that a concerned NPC shares their negativity per connection.
# Sharing negativity is easier than recommending — you don't have to convince,
# just dampen enthusiasm. 3.0 yields ~10-15% probability per check at typical
# concern_strength/influence/trust values.
CONCERN_SHARE_BASE = 3.0

# How much each concern event moves the target's interest.
CONCERN_DELTA_MULTIPLIER = 0.12


def compute_concern_influence(world: WorldState) -> list[tuple[str, float]]:
    """Compute negative influence from skeptical/low-interest NPCs.

    Unlike positive spread (which makes new people AWARE), concern propagation
    dampens interest of ALREADY-AWARE connections. This models realistic
    word-of-mouth: people share warnings, doubts, and negative impressions
    with their social network.

    Structural design (2026-03-23):
    - Concern propagation does NOT require objections. Low interest alone is
      sufficient — a disinterested or opposed NPC naturally dampens enthusiasm
      through body language, dismissive comments, and social signaling, even
      without articulated objections.
    - NPCs WITH objections get a bonus to share probability (they have specific
      talking points), but the absence of objections is not a gate.
    - Credibility still matters: a skeptic's dismissal carries more weight
      than a follower's indifference.
    - Targets must be aware and above CONCERN_TARGET_MIN_INTEREST (no point
      dampening someone who's already negative).

    Returns:
        List of (target_npc_id, negative_delta) tuples.
    """
    concern_deltas: dict[str, float] = {}

    for npc in world.aware_npcs:
        if npc.state.interest_score >= CONCERN_INTEREST_THRESHOLD:
            continue

        concern_strength = CONCERN_INTEREST_THRESHOLD - npc.state.interest_score

        # Source credibility: a skeptic's warning carries more weight
        archetype_id = getattr(npc, "archetype", None)
        credibility = _SOURCE_CREDIBILITY.get(archetype_id or "", 1.0)

        # NPCs with specific objections are more vocal (bonus to share prob)
        has_objections = bool(npc.state.objections)
        objection_bonus = 1.5 if has_objections else 1.0

        for conn_id in npc.social_connections:
            conn = world.npcs.get(conn_id)
            if not conn or not conn.state.aware:
                continue
            if conn.state.interest_score < CONCERN_TARGET_MIN_INTEREST:
                continue  # already low, no need to dampen further

            trust = npc.trust_weights.get(conn_id, 0.5)

            share_prob = (
                concern_strength
                * npc.personality.social_influence
                * trust
                * CONCERN_SHARE_BASE
                * objection_bonus
            )

            if random.random() < share_prob:
                delta = -(concern_strength * trust * credibility * CONCERN_DELTA_MULTIPLIER)
                concern_deltas[conn_id] = concern_deltas.get(conn_id, 0.0) + delta

    return list(concern_deltas.items())
