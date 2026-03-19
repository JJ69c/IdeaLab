"""Deterministic social influence and spread logic. No LLM calls here.

When a ProductProfile is available on the WorldState, the profile dimensions
modulate the base formulas:
- market_saturation dampens peer influence (strong priors in crowded markets)
- novelty boosts word-of-mouth spread
- price_friction reduces casual recommendations
- trust_barrier increases the threshold for positive spread
"""

from __future__ import annotations

import random

from backend.simulation.npc import Npc
from backend.simulation.world import SpreadEvent, WorldState


def compute_peer_susceptibility(conformity: float, skepticism: float) -> float:
    """How susceptible an NPC is to peer influence.

    Conformity is the primary driver, but skepticism acts as a damper.
    A high-conformity skeptic (conformity=0.8, skepticism=0.8) resists more
    than a high-conformity trusting NPC (conformity=0.8, skepticism=0.2).

    Returns a multiplier in roughly [0.0, 0.3].
    """
    return conformity * (1.0 - skepticism * 0.3) * 0.3


def calculate_peer_influence(npc: Npc, world: WorldState) -> float:
    """Calculate how much an NPC's opinion shifts based on their social connections.

    Uses a weighted average of connected NPCs' interest scores, modulated by
    the NPC's peer susceptibility (conformity + skepticism), trust weights,
    and product-level market saturation.
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
    susceptibility = compute_peer_susceptibility(
        npc.personality.conformity, npc.personality.skepticism,
    )
    raw_delta = (peer_avg - current) * susceptibility

    # Product profile modulation: saturated markets → people resist peer pressure
    # more because they already have strong opinions about existing solutions
    profile = getattr(world, "product_profile", None)
    if profile is not None:
        saturation_damper = 1.0 - profile.market_saturation * 0.30
        raw_delta *= saturation_damper

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
) -> float:
    """How much a discussion partner's argument actually moves the target.

    Three factors determine whether words land:
    - source_social_influence: credible, articulate speakers persuade more
    - trust: arguments from trusted connections carry more weight
    - target_skepticism: skeptics discount what they hear

    Formula: (source_influence * trust) / max(target_skepticism, 0.2)
    The floor on skepticism (0.2) prevents division-by-near-zero for
    very trusting NPCs. Clamped to [0.3, 1.5] so even the worst pairing
    still allows some effect, and the best can amplify but not double.

    Applied as a multiplier on the raw LLM discussion delta in engine.py.
    """
    raw = source_social_influence * trust / max(target_skepticism, 0.2)
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

    Base probability: interest × social_influence × trust × target_receptiveness × 0.5

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
