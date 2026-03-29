"""V2 simulation engine -- world-aware, LLM-primary with math guardrails.

Layers 1-2 run as a prep phase before any ticks.
Layer 3 replaces V1's reaction phase; all other phases reuse V1 logic.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable

from backend.config import settings
from backend.llm.client import llm_client
from backend.simulation.convergence import ConvergenceTracker
from backend.simulation.engine import (
    EventCallback,
    create_world,
    _build_edge_list,
    _run_discussion,
    _stratified_seed_selection,
    DISCUSSION_UPLIFT_CAP,
    DISCUSSION_DOWNDRAFT_CAP,
    _noop,
)
from backend.simulation.adoption import compute_world_adoptions
from backend.simulation.evaluation import (
    compute_archetype_baseline,
    get_archetype_evaluation,
)
from backend.simulation.npc import Npc, PeerWarning
from backend.simulation.population import generate_population
from backend.simulation.product_profile import build_product_profile
from backend.simulation.propagation import (
    calculate_peer_influence,
    compute_concern_influence,
    compute_spreads,
    select_discussion_pairs,
)
from backend.simulation.reporter import generate_report
from backend.simulation.world import InjectedIdea, SimConfig, WorldState, load_population
from backend.simulation.world_builder import NpcCategoryContext, WorldContext

logger = logging.getLogger(__name__)

# Guardrail: max deviation of LLM score from archetype baseline
GUARDRAIL_MAX_DEVIATION = 0.30


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_simulation_v2(
    idea: InjectedIdea,
    config: SimConfig,
    emit: EventCallback | None = None,
    asset_signals=None,
    population_override: list[dict] | None = None,
    seed_override: list[str] | None = None,
) -> dict:
    """Run a full V2 simulation with world-aware LLM-primary reactions.

    Args:
        idea: The injected idea to test.
        config: Simulation parameters.
        emit: Optional callback invoked for each event (for SSE streaming).
        asset_signals: Optional structured signals from reference assets.
        population_override: Saved NPC data from a parent simulation (for variants).
        seed_override: NPC IDs to use as tick-1 seeds instead of stratified sampling.

    Returns:
        Structured simulation report dict.
    """
    emit = emit or _noop
    world = create_world(
        idea, config,
        asset_signals=asset_signals,
        population_override=population_override,
        seed_override=seed_override,
    )
    tracker = ConvergenceTracker()

    # --- V2 Prep: Layers 1 & 2 (before any ticks) ---
    world_context, npc_contexts = _run_v2_prep(world, idea, emit)

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
            "competition_context": world.competition_context.to_dict() if world.competition_context else None,
            "npc_archetypes": world.npc_archetypes,
            "world_context": world_context.to_dict(),
            "simulation_version": "v2",
        },
    })

    # --- Tick loop ---
    for tick in range(1, config.num_ticks + 1):
        world.current_tick = tick
        emit({"type": "tick_start", "tick": tick, "data": {}})
        logger.info("=== V2 Tick %d / %d ===", tick, config.num_ticks)

        _run_v2_tick(world, tick, emit, world_context, npc_contexts)

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
            logger.info("V2 simulation converged at tick %d, continuing for stability", tick)

    logger.info("V2 simulation complete. Generating report...")
    report = generate_report(world, convergence=tracker.to_report_dict())

    emit({"type": "simulation_complete", "tick": config.num_ticks, "data": {"report": report}})
    return report


# ---------------------------------------------------------------------------
# Layer 1 & 2: V2 Prep Phase
# ---------------------------------------------------------------------------

def _run_v2_prep(
    world: WorldState,
    idea: InjectedIdea,
    emit: EventCallback,
) -> tuple[WorldContext, dict[str, NpcCategoryContext]]:
    """Run V2 prep layers before the tick loop.

    Layer 1 -- World Construction: single LLM call to build shared market context.
    Layer 2 -- NPC Enrichment: batched LLM calls to generate per-NPC category context.

    Returns:
        (world_context, npc_contexts) where npc_contexts maps npc_id -> NpcCategoryContext.
    """
    idea_dict = idea.to_dict()

    # --- Layer 1: World Construction ---
    emit({
        "type": "v2_progress",
        "tick": 0,
        "data": {"phase": "world_builder", "message": "Building world context..."},
    })

    try:
        world_context = llm_client.build_world_context(idea_dict)
    except Exception:
        logger.exception("Layer 1 world construction failed, using default context")
        world_context = WorldContext.default()

    emit({
        "type": "v2_progress",
        "tick": 0,
        "data": {
            "phase": "world_builder_complete",
            "message": "World context ready.",
            "world_context": world_context.to_dict(),
        },
    })

    logger.info(
        "V2 Layer 1 complete: market_maturity=%s, key_players=%d",
        world_context.market_maturity,
        len(world_context.key_players),
    )

    # --- Layer 2: NPC Enrichment ---
    emit({
        "type": "v2_progress",
        "tick": 0,
        "data": {"phase": "npc_enrichment", "message": "Enriching NPC backgrounds..."},
    })

    all_npcs = list(world.npcs.values())
    npc_contexts: dict[str, NpcCategoryContext] = {}
    batch_size = settings.reaction_batch_size

    for i in range(0, len(all_npcs), batch_size):
        batch = all_npcs[i : i + batch_size]
        profiles = [npc.to_profile_dict() for npc in batch]

        try:
            enrichments = llm_client.enrich_npcs(
                profiles,
                world_context.to_dict(),
                idea_dict,
            )

            # Map results by npc_id
            enrichment_map = {e.get("npc_id", ""): e for e in enrichments}

            for npc in batch:
                raw = enrichment_map.get(npc.id)
                if raw:
                    npc_contexts[npc.id] = NpcCategoryContext.from_dict(raw)
                else:
                    logger.warning(
                        "No enrichment returned for NPC %s, using default", npc.id,
                    )
                    npc_contexts[npc.id] = NpcCategoryContext.default(npc.id)
        except Exception:
            logger.exception(
                "Layer 2 enrichment failed for batch starting at %d, using defaults", i,
            )
            for npc in batch:
                npc_contexts[npc.id] = NpcCategoryContext.default(npc.id)

    emit({
        "type": "v2_progress",
        "tick": 0,
        "data": {
            "phase": "npc_enrichment_complete",
            "message": f"Enriched {len(npc_contexts)} NPCs.",
            "enriched_count": len(npc_contexts),
        },
    })

    logger.info("V2 Layer 2 complete: enriched %d NPCs", len(npc_contexts))

    return world_context, npc_contexts


# ---------------------------------------------------------------------------
# Layer 3: V2 Batch Reaction (LLM-primary, math guardrails)
# ---------------------------------------------------------------------------

def _v2_batch_react(
    world: WorldState,
    npcs: list[Npc],
    tick: int,
    emit: EventCallback,
    world_context: WorldContext,
    npc_contexts: dict[str, NpcCategoryContext],
):
    """Get V2 reactions for newly aware NPCs in batches.

    The LLM generates interest_score directly. A math guardrail clamps the
    score to within GUARDRAIL_MAX_DEVIATION of the archetype baseline,
    preventing hallucinated extremes while keeping the LLM as primary scorer.
    """
    batch_size = settings.reaction_batch_size
    idea_dict = world.idea.to_dict()
    world_context_dict = world_context.to_dict()
    profile = getattr(world, "product_profile", None)

    for i in range(0, len(npcs), batch_size):
        batch = npcs[i : i + batch_size]

        # Build enriched profiles: attach category_context to each NPC profile
        enriched_profiles = []
        for npc in batch:
            npc_profile = npc.to_profile_dict()
            ctx = npc_contexts.get(npc.id)
            if ctx:
                npc_profile["category_context"] = ctx.to_dict()
            else:
                npc_profile["category_context"] = NpcCategoryContext.default(npc.id).to_dict()
            enriched_profiles.append(npc_profile)

        try:
            reactions = llm_client.v2_batch_react(
                enriched_profiles,
                idea_dict,
                world_context_dict,
            )
        except Exception:
            logger.exception("V2 batch_react failed for batch starting at %d", i)
            reactions = []

        reaction_map = {r.get("npc_id", ""): r for r in reactions}

        for npc in batch:
            reaction = reaction_map.get(npc.id, {})

            # --- Compute archetype baseline for guardrail ---
            archetype_id = world.npc_archetypes.get(npc.id)
            eval_def = get_archetype_evaluation(archetype_id)
            idea_category = getattr(world.idea, "category", None)
            baseline = (
                compute_archetype_baseline(profile, eval_def, category=idea_category)
                if profile
                else 0.5
            )

            # Cache baseline on world for later use (influence resistance floor)
            if not hasattr(world, "_npc_baselines"):
                world._npc_baselines = {}
            world._npc_baselines[npc.id] = baseline

            # --- Extract LLM score and apply guardrail ---
            llm_score = reaction.get("interest_score")
            if llm_score is None:
                # Fallback: if LLM didn't return a score, use baseline
                logger.warning(
                    "NPC %s: no interest_score in V2 reaction, falling back to baseline %.3f",
                    npc.id, baseline,
                )
                llm_score = baseline
            else:
                llm_score = float(llm_score)

            # Guardrail clamp: keep within GUARDRAIL_MAX_DEVIATION of baseline
            floor = max(0.0, baseline - GUARDRAIL_MAX_DEVIATION)
            ceiling = min(1.0, baseline + GUARDRAIL_MAX_DEVIATION)
            final_score = max(floor, min(ceiling, llm_score))

            was_clamped = final_score != llm_score
            if was_clamped:
                logger.info(
                    "[CLAMPED] NPC %s (%s): llm=%.3f baseline=%.3f floor=%.3f ceiling=%.3f -> final=%.3f",
                    npc.id, archetype_id or "?",
                    llm_score, baseline, floor, ceiling, final_score,
                )
            else:
                logger.debug(
                    "NPC %s (%s): llm=%.3f baseline=%.3f -> final=%.3f (no clamp)",
                    npc.id, archetype_id or "?",
                    llm_score, baseline, final_score,
                )

            # Overwrite the score in the reaction dict before applying
            reaction["interest_score"] = final_score

            # Apply reaction to NPC state
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
                    "llm_raw_score": round(llm_score, 3),
                    "was_clamped": was_clamped,
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
                "stance": npc.state.stance,
                "interest": npc.state.interest_score,
                "baseline": round(baseline, 3),
                "llm_raw_score": round(llm_score, 3),
                "was_clamped": was_clamped,
            })


# ---------------------------------------------------------------------------
# V2 Tick: full tick with V2 reaction phase, all other phases from V1
# ---------------------------------------------------------------------------

def _run_v2_tick(
    world: WorldState,
    tick: int,
    emit: EventCallback,
    world_context: WorldContext,
    npc_contexts: dict[str, NpcCategoryContext],
):
    """Execute one V2 simulation tick.

    Phase 1 (Awareness): Same as V1 with seed_override support.
    Phase 2 (Reaction): V2 LLM-primary with guardrail clamp.
    Phase 3 (Discussion): V1 _run_discussion.
    Phase 4 (Peer Influence): V1 calculate_peer_influence.
    Phase 4b (Concern propagation): V1 logic with downdraft cap.
    Phase 5 (Spread): V1 compute_spreads.
    Phase 6 (Adoption): V1 compute_world_adoptions.
    """

    # --- Phase 1: Awareness ---
    if tick == 1:
        all_npcs = list(world.npcs.values())
        seed_count = min(world.config.seed_count, len(all_npcs))
        _override_ids = getattr(world, "_seed_override", None)
        if _override_ids:
            # Fixed seeds: use the exact NPC IDs from the parent simulation.
            # Skip any IDs that don't exist in this world (defensive).
            seeds = [world.npcs[nid] for nid in _override_ids if nid in world.npcs]
            if not seeds:
                logger.warning("seed_override produced 0 valid seeds -- falling back to stratified")
                seeds = _stratified_seed_selection(
                    all_npcs, seed_count, npc_archetypes=world.npc_archetypes,
                )
            elif len(seeds) < seed_count:
                logger.info(
                    "seed_override: %d/%d IDs matched, using those only",
                    len(seeds), seed_count,
                )
        else:
            seeds = _stratified_seed_selection(
                all_npcs, seed_count, npc_archetypes=world.npc_archetypes,
            )
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

    # --- Phase 2: Reaction (V2 LLM-primary with guardrails) ---
    newly_aware = [n for n in world.npcs.values() if n.state.awareness_tick == tick]
    if newly_aware:
        _v2_batch_react(world, newly_aware, tick, emit, world_context, npc_contexts)

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

    # --- Phase 4b: Concern propagation (negative influence, content-aware) ---
    concern_events = compute_concern_influence(world)

    # Group concern events by target for aggregation and event enrichment
    target_concerns: dict[str, list] = defaultdict(list)
    for evt in concern_events:
        target_concerns[evt.target_id].append(evt)

    # Apply aggregated deltas and emit events with per-source details
    baselines = getattr(world, "_npc_baselines", {})
    for target_id, events in target_concerns.items():
        target_npc = world.npcs.get(target_id)
        if not target_npc:
            continue
        total_delta = sum(e.final_delta for e in events)
        # Apply downdraft floor so concern propagation cannot push an NPC
        # below their baseline minus the cap.
        if DISCUSSION_DOWNDRAFT_CAP > 0 and total_delta < 0:
            target_baseline = baselines.get(target_id, 0.5)
            concern_floor = target_baseline - DISCUSSION_DOWNDRAFT_CAP
            room = min(0.0, concern_floor - target_npc.state.interest_score)
            total_delta = max(total_delta, room)
        old_interest = target_npc.state.interest_score
        new_stance = target_npc.state.apply_influence(total_delta, tick)
        emit({
            "type": "concern_applied",
            "tick": tick,
            "data": {
                "npc_id": target_npc.id, "name": target_npc.name,
                "delta": round(total_delta, 4),
                "old_interest": round(old_interest, 3),
                "new_interest": round(target_npc.state.interest_score, 3),
                "sources": [
                    {
                        "source_name": e.source_name,
                        "theme": e.theme,
                        "content": e.objection_content[:150],
                        "delta": round(e.final_delta, 4),
                    }
                    for e in events if e.objection_content
                ],
            },
        })
        if new_stance:
            emit({
                "type": "npc_state_change",
                "tick": tick,
                "data": {
                    "npc_id": target_npc.id, "name": target_npc.name,
                    "new_stance": new_stance,
                    "interest_score": round(target_npc.state.interest_score, 3),
                    "reason": "concern_influence",
                },
            })

    # Write PeerWarning memory per individual concern event (preserves source attribution).
    # No guard on objection_content: NPCs dampened by general negativity (no explicit
    # objection) still get a memory so Ask NPC responses can explain why their interest
    # dropped, even when the source had no articulated objection.
    for evt in (e for evts in target_concerns.values() for e in evts):
        target_npc = world.npcs.get(evt.target_id)
        if target_npc:
            content = evt.objection_content if evt.objection_content else "expressed general skepticism about the product"
            target_npc.state.record_peer_warning(PeerWarning(
                tick=tick,
                source_id=evt.source_id,
                source_name=evt.source_name,
                source_archetype=evt.source_archetype,
                theme=evt.theme,
                content=content,
                delta=evt.final_delta,
            ))

    # --- Re-derive would_recommend and would_pay before spread ---
    # Interest may have changed via discussion/influence/concern since initial reaction.
    for npc in world.aware_npcs:
        npc.state.update_would_recommend()
        npc.state.update_would_pay()

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

    # --- Phase 6: Adoption (deterministic, per-NPC) ---
    compute_world_adoptions(world)

    # --- Log tick metrics ---
    metrics = world.compute_metrics()
    logger.info(
        "V2 Tick %d: aware=%d, interested=%d, awareness=%.0f%%",
        tick, metrics["aware_count"], len(world.interested_npcs),
        metrics["awareness_rate"] * 100,
    )
