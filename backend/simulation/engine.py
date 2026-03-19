"""Core simulation engine — orchestrates the tick loop with event emission."""

from __future__ import annotations

import logging
import random
from typing import Callable

from backend.config import settings
from backend.llm.client import llm_client
from backend.simulation.convergence import ConvergenceTracker
from backend.simulation.npc import Npc
from backend.simulation.asset_signals import AssetSignals, compute_asset_adjustment
from backend.simulation.evaluation import (
    compute_archetype_baseline,
    compute_individual_delta,
    get_archetype_evaluation,
)
from backend.simulation.product_profile import build_product_profile
from backend.simulation.propagation import (
    calculate_peer_influence,
    compute_discussion_weight,
    compute_spreads,
    select_discussion_pairs,
)
from backend.simulation.population import generate_population
from backend.simulation.reporter import generate_report
from backend.simulation.world import InjectedIdea, SimConfig, WorldState, load_population

logger = logging.getLogger(__name__)

# Type alias for the event callback
EventCallback = Callable[[dict], None]
_noop: EventCallback = lambda e: None


def create_world(
    idea: InjectedIdea,
    config: SimConfig,
    preset: str = "balanced",
    asset_signals: AssetSignals | None = None,
) -> WorldState:
    """Initialize a world with a population, injected idea, and product profile.

    Uses the archetype-based population generator by default. Falls back to
    the legacy JSON population if the generator fails.
    """
    try:
        npcs, npc_archetypes = generate_population(
            size=config.population_size,
            preset=preset,
        )
    except Exception:
        logger.warning("Population generator failed, falling back to legacy JSON", exc_info=True)
        npcs = load_population(limit=config.population_size)
        npc_archetypes = {}

    for npc in npcs:
        npc.reset_state()

    world = WorldState(
        idea=idea,
        config=config,
        npcs={npc.id: npc for npc in npcs},
    )
    world.npc_archetypes = npc_archetypes

    # Build the normalized product profile from structured idea fields
    world.product_profile = build_product_profile(idea, asset_signals=asset_signals)
    world.asset_signals = asset_signals
    logger.info(
        "Created world with %d NPCs, %d ticks, preset=%s, profile=%s, assets=%s",
        len(world.npcs), config.num_ticks, preset, world.product_profile.to_dict(),
        "yes" if asset_signals else "none",
    )
    return world


def run_simulation(
    idea: InjectedIdea,
    config: SimConfig,
    emit: EventCallback | None = None,
    asset_signals: AssetSignals | None = None,
) -> dict:
    """Run a full simulation, emitting events for live streaming.

    Args:
        idea: The injected idea to test.
        config: Simulation parameters.
        emit: Optional callback invoked for each event (for SSE streaming).
              If None, events are only logged.
        asset_signals: Optional structured signals from reference assets.
    """
    emit = emit or _noop
    world = create_world(idea, config, asset_signals=asset_signals)
    tracker = ConvergenceTracker()

    # Build edge list for the frontend graph
    edges = _build_edge_list(world)

    emit({
        "type": "simulation_start",
        "tick": 0,
        "data": {
            "npcs": [npc.to_init_dict() for npc in world.npcs.values()],
            "edges": edges,
            "idea": idea.to_dict(),
            "config": {"num_ticks": config.num_ticks, "population_size": len(world.npcs)},
            "product_profile": world.product_profile.to_dict(),
            "asset_signals": world.asset_signals.to_dict() if world.asset_signals else None,
            "npc_archetypes": world.npc_archetypes,
        },
    })

    for tick in range(1, config.num_ticks + 1):
        world.current_tick = tick
        emit({"type": "tick_start", "tick": tick, "data": {}})
        logger.info("=== Tick %d / %d ===", tick, config.num_ticks)

        _run_tick(world, tick, emit)

        # Record convergence snapshot after all phases complete
        convergence = tracker.record_tick(
            tick, world.aware_npcs, npc_archetypes=world.npc_archetypes,
        )

        metrics = world.compute_metrics()
        emit({
            "type": "tick_end",
            "tick": tick,
            "data": {
                "metrics": metrics,
                "convergence": convergence.to_dict(),
            },
        })

        if convergence.converged and tick >= 4:
            logger.info("Simulation converged at tick %d, continuing for stability", tick)

    logger.info("Simulation complete. Generating report...")
    report = generate_report(world, convergence=tracker.to_report_dict())

    emit({"type": "simulation_complete", "tick": config.num_ticks, "data": {"report": report}})
    return report


def _build_edge_list(world: WorldState) -> list[dict]:
    """Build deduplicated edge list with trust weights for the graph."""
    seen = set()
    edges = []
    for npc in world.npcs.values():
        for conn_id in npc.social_connections:
            if conn_id not in world.npcs:
                continue
            key = tuple(sorted([npc.id, conn_id]))
            if key not in seen:
                seen.add(key)
                trust = npc.trust_weights.get(conn_id, 0.5)
                edges.append({"source": key[0], "target": key[1], "trust": trust})
    return edges


def _stratified_seed_selection(npcs: list[Npc], count: int) -> list[Npc]:
    """Select seed NPCs with stratification by novelty_seeking.

    Ensures at least 1 NPC from the top quartile (high novelty_seeking)
    and 1 from the bottom quartile (low novelty_seeking) when count >= 3.
    Remaining slots are filled randomly from the rest of the population.
    This prevents all-Enthusiast or all-Skeptic seed groups.
    """
    if count <= 2 or len(npcs) < 4:
        return random.sample(npcs, count)

    sorted_by_ns = sorted(npcs, key=lambda n: n.personality.novelty_seeking)
    q_size = max(1, len(sorted_by_ns) // 4)
    bottom_q = sorted_by_ns[:q_size]
    top_q = sorted_by_ns[-q_size:]

    seeds: list[Npc] = []

    # Guarantee 1 from top quartile (early adopter type)
    top_pick = random.choice(top_q)
    seeds.append(top_pick)

    # Guarantee 1 from bottom quartile (conservative type)
    bottom_pick = random.choice(bottom_q)
    seeds.append(bottom_pick)

    # Fill remaining from the rest of the population
    remaining = [n for n in npcs if n not in seeds]
    fill_count = count - len(seeds)
    if fill_count > 0 and remaining:
        seeds.extend(random.sample(remaining, min(fill_count, len(remaining))))

    return seeds


def _run_tick(world: WorldState, tick: int, emit: EventCallback):
    """Execute one simulation tick with all 5 phases."""

    # --- Phase 1: Awareness ---
    if tick == 1:
        all_npcs = list(world.npcs.values())
        seed_count = min(world.config.seed_count, len(all_npcs))
        seeds = _stratified_seed_selection(all_npcs, seed_count)
        for npc in seeds:
            npc.state.become_aware(tick, source="direct_exposure")
            world.log_event(tick, npc.id, "became_aware", {"source": "direct_exposure"})
            emit({
                "type": "npc_aware",
                "tick": tick,
                "data": {"npc_id": npc.id, "name": npc.name, "source": "direct_exposure"},
            })
    else:
        for spread in world.pending_spreads:
            target = world.npcs.get(spread.target_id)
            if target and not target.state.aware:
                source_npc = world.npcs.get(spread.source_id)
                source_name = source_npc.name if source_npc else spread.source_id
                target.state.become_aware(tick, source=spread.source_id)
                world.log_event(tick, target.id, "became_aware", {"source": spread.source_id})
                emit({
                    "type": "npc_aware",
                    "tick": tick,
                    "data": {
                        "npc_id": target.id, "name": target.name,
                        "source": spread.source_id, "source_name": source_name,
                    },
                })
        world.pending_spreads = []

    # --- Exposure tracking (increment for all already-aware NPCs) ---
    for npc in world.aware_npcs:
        npc.state.increment_exposure()

    # --- Phase 2: Reaction (batched LLM calls) ---
    newly_aware = [n for n in world.npcs.values() if n.state.awareness_tick == tick]
    if newly_aware:
        _batch_react(world, newly_aware, tick, emit)

    # --- Phase 3: Discussion (LLM, capped) ---
    pairs = select_discussion_pairs(world, max_pairs=settings.max_discussions_per_tick)
    for npc_a, npc_b in pairs:
        _run_discussion(world, npc_a, npc_b, tick, emit)

    # --- Phase 4: Influence (deterministic) ---
    for npc in world.aware_npcs:
        delta = calculate_peer_influence(npc, world)
        new_stance = npc.state.apply_influence(delta, tick)
        if new_stance:
            emit({
                "type": "npc_state_change",
                "tick": tick,
                "data": {
                    "npc_id": npc.id, "name": npc.name,
                    "new_stance": new_stance,
                    "interest_score": round(npc.state.interest_score, 3),
                    "reason": "peer_influence",
                },
            })

    # --- Re-derive would_recommend before spread (interest may have changed) ---
    for npc in world.aware_npcs:
        npc.state.update_would_recommend()

    # --- Phase 5: Spread ---
    world.pending_spreads = compute_spreads(world)
    for spread in world.pending_spreads:
        source_npc = world.npcs.get(spread.source_id)
        target_npc = world.npcs.get(spread.target_id)
        emit({
            "type": "npc_spread",
            "tick": tick,
            "data": {
                "source_id": spread.source_id,
                "source_name": source_npc.name if source_npc else "",
                "target_id": spread.target_id,
                "target_name": target_npc.name if target_npc else "",
            },
        })
        world.log_event(tick, spread.source_id, "will_spread", {"target": spread.target_id})

    metrics = world.compute_metrics()
    logger.info(
        "Tick %d: aware=%d, interested=%d, awareness=%.0f%%",
        tick, metrics["aware_count"], len(world.interested_npcs),
        metrics["awareness_rate"] * 100,
    )


def _batch_react(world: WorldState, npcs: list[Npc], tick: int, emit: EventCallback):
    """Get reactions for newly aware NPCs in batches.

    Score composition (deterministic-dominant):
        archetype_baseline  (0.15-0.85)  from ProductProfile x archetype weights
      + individual_delta    (+-0.10)     from trait deviation x ProductProfile
      + asset_delta         (+-0.08)     from AssetSignals x traits
      + llm_hint            (+-0.10)     LLM qualitative adjustment
      = final interest_score (0-1)       clamped
    """
    batch_size = settings.reaction_batch_size
    idea_dict = world.idea.to_dict()
    asset_signals_dict = world.asset_signals.to_dict() if getattr(world, "asset_signals", None) else None
    profile = getattr(world, "product_profile", None)

    for i in range(0, len(npcs), batch_size):
        batch = npcs[i : i + batch_size]
        profiles = [npc.to_profile_dict() for npc in batch]

        try:
            reactions = llm_client.batch_react(profiles, idea_dict, asset_signals_dict=asset_signals_dict)
        except Exception:
            logger.exception("LLM batch_react failed for batch starting at %d", i)
            reactions = [
                {"npc_id": npc.id, "interest_adjustment": 0.0,
                 "reasoning": "Unable to process", "objections": [],
                 "would_pay": False, "would_recommend": False, "emotional_reaction": "meh"}
                for npc in batch
            ]

        reaction_map = {r["npc_id"]: r for r in reactions}
        for npc in batch:
            reaction = reaction_map.get(npc.id, {})

            # --- Deterministic baseline from archetype weights x ProductProfile ---
            archetype_id = world.npc_archetypes.get(npc.id)
            eval_def = get_archetype_evaluation(archetype_id)
            baseline = compute_archetype_baseline(profile, eval_def) if profile else 0.5

            # --- Individual trait variation (+-0.10) ---
            ind_delta = compute_individual_delta(npc.personality, profile) if profile else 0.0

            # --- Asset signal adjustment (+-0.08) ---
            asset_delta = 0.0
            signals = getattr(world, "asset_signals", None)
            if signals is not None:
                personality_dict = npc.to_profile_dict().get("personality", {})
                asset_delta = compute_asset_adjustment(signals, personality_dict)

            # --- LLM hint (bounded +-0.10) ---
            # The LLM now returns interest_adjustment instead of interest_score.
            # Fallback: if old-style interest_score is returned, convert to delta from baseline.
            raw_hint = reaction.get("interest_adjustment")
            if raw_hint is None:
                # Backward compat: if LLM still returns interest_score, treat as hint
                old_score = reaction.get("interest_score", 0.5)
                raw_hint = old_score - 0.5  # center around 0
            llm_hint = max(-0.10, min(0.10, float(raw_hint)))

            # --- Compose final score ---
            final_score = max(0.0, min(1.0, baseline + ind_delta + asset_delta + llm_hint))
            reaction["interest_score"] = final_score

            logger.debug(
                "NPC %s (%s): baseline=%.3f ind=%.3f asset=%.3f llm=%.3f → final=%.3f",
                npc.id, archetype_id or "?",
                baseline, ind_delta, asset_delta, llm_hint, final_score,
            )

            # Cache baseline on world for later use (influence resistance floor)
            if not hasattr(world, "_npc_baselines"):
                world._npc_baselines = {}
            world._npc_baselines[npc.id] = baseline

            new_stance = npc.state.apply_reaction(reaction, tick)

            emit({
                "type": "npc_reaction",
                "tick": tick,
                "data": {
                    "npc_id": npc.id,
                    "name": npc.name,
                    "stance": npc.state.stance,
                    "interest_score": round(npc.state.interest_score, 3),
                    "reasoning": npc.state.reasoning,
                    "objections": npc.state.objections,
                    "would_pay": npc.state.would_pay,
                    "emotional_reaction": npc.state.emotional_reaction,
                    "baseline": round(baseline, 3),
                    "individual_delta": round(ind_delta, 3),
                    "asset_delta": round(asset_delta, 3),
                    "llm_hint": round(llm_hint, 3),
                },
            })

            if new_stance:
                emit({
                    "type": "npc_state_change",
                    "tick": tick,
                    "data": {
                        "npc_id": npc.id, "name": npc.name,
                        "new_stance": new_stance,
                        "interest_score": round(npc.state.interest_score, 3),
                        "reason": "initial_reaction",
                    },
                })

            world.log_event(tick, npc.id, "reacted", {
                "stance": npc.state.stance, "interest": npc.state.interest_score,
                "baseline": round(baseline, 3),
            })


def _run_discussion(
    world: WorldState, npc_a: Npc, npc_b: Npc, tick: int, emit: EventCallback
):
    """Simulate a discussion between two NPCs."""
    trust = npc_a.trust_weights.get(npc_b.id, 0.5)

    emit({
        "type": "discussion_start",
        "tick": tick,
        "data": {
            "npc_a_id": npc_a.id, "npc_a_name": npc_a.name,
            "npc_b_id": npc_b.id, "npc_b_name": npc_b.name,
        },
    })

    try:
        result = llm_client.simulate_discussion(
            npc_a=npc_a.to_profile_dict(),
            npc_b=npc_b.to_profile_dict(),
            idea=world.idea.to_dict(),
            stance_a=npc_a.state.stance,
            interest_a=npc_a.state.interest_score,
            stance_b=npc_b.state.stance,
            interest_b=npc_b.state.interest_score,
            trust_level=trust,
        )
    except Exception:
        logger.exception("Discussion LLM failed for %s and %s", npc_a.id, npc_b.id)
        return

    outcome = result.get("outcome", {})
    key_point = outcome.get("key_point", "")

    raw_a_delta = outcome.get("a_interest_delta", 0)
    raw_b_delta = outcome.get("b_interest_delta", 0)

    # Weight each delta by how persuasive the *other* NPC is to this target.
    # A's shift is caused by B speaking → B is source, A is target.
    a_weight = compute_discussion_weight(
        npc_b.personality.social_influence, trust, npc_a.personality.skepticism,
        source_archetype=getattr(npc_b, "archetype", None),
    )
    b_weight = compute_discussion_weight(
        npc_a.personality.social_influence, trust, npc_b.personality.skepticism,
        source_archetype=getattr(npc_a, "archetype", None),
    )
    a_delta = round(raw_a_delta * a_weight, 4)
    b_delta = round(raw_b_delta * b_weight, 4)

    a_new_stance = npc_a.state.apply_discussion_outcome(a_delta, tick, npc_b.id)
    b_new_stance = npc_b.state.apply_discussion_outcome(b_delta, tick, npc_a.id)

    emit({
        "type": "discussion_end",
        "tick": tick,
        "data": {
            "npc_a_id": npc_a.id, "npc_a_name": npc_a.name,
            "npc_b_id": npc_b.id, "npc_b_name": npc_b.name,
            "a_delta": round(a_delta, 3),
            "b_delta": round(b_delta, 3),
            "a_interest": round(npc_a.state.interest_score, 3),
            "b_interest": round(npc_b.state.interest_score, 3),
            "a_stance": npc_a.state.stance,
            "b_stance": npc_b.state.stance,
            "key_point": key_point,
            "exchanges": result.get("exchanges", []),
        },
    })

    # Emit state changes if stances shifted
    for npc, new_st, delta in [(npc_a, a_new_stance, a_delta), (npc_b, b_new_stance, b_delta)]:
        if new_st:
            emit({
                "type": "npc_state_change",
                "tick": tick,
                "data": {
                    "npc_id": npc.id, "name": npc.name,
                    "new_stance": new_st,
                    "interest_score": round(npc.state.interest_score, 3),
                    "reason": "discussion",
                },
            })

    world.discussion_log.append({
        "tick": tick,
        "between": [npc_a.id, npc_b.id],
        "exchanges": result.get("exchanges", []),
        "key_point": key_point,
        "outcome_summary": f"{npc_a.name}: {a_delta:+.2f}, {npc_b.name}: {b_delta:+.2f}",
    })

    # Record cooldown so this pair is skipped for the next N ticks
    world.discussion_cooldowns[frozenset({npc_a.id, npc_b.id})] = tick

    world.log_event(tick, npc_a.id, "discussed", {"with": npc_b.id, "key_point": key_point})
