"""Report generation — assembles data and calls LLM for narrative analysis."""

from __future__ import annotations

import logging
from collections import defaultdict

from backend.llm.client import llm_client
from backend.simulation.adoption import compute_world_adoptions
from backend.simulation.world import WorldState

logger = logging.getLogger(__name__)


def _compute_archetype_breakdown(world: WorldState) -> list[dict]:
    """Compute per-archetype aggregate metrics for the report."""
    archetype_groups: dict[str, list] = defaultdict(list)
    npc_archetypes = getattr(world, "npc_archetypes", {})
    for npc in world.npcs.values():
        arch = npc_archetypes.get(npc.id, "unknown")
        archetype_groups[arch].append(npc)

    breakdown = []
    for arch, npcs in sorted(archetype_groups.items()):
        aware = [n for n in npcs if n.state.aware]
        adopted = [n for n in npcs if getattr(n.state, "adopted", False)]
        interests = [n.state.interest_score for n in aware]
        mean_interest = sum(interests) / len(interests) if interests else 0.0
        breakdown.append({
            "archetype": arch,
            "count": len(npcs),
            "aware_count": len(aware),
            "adopted_count": len(adopted),
            "adoption_rate": round(len(adopted) / len(aware), 3) if aware else 0.0,
            "mean_interest": round(mean_interest, 3),
        })
    return breakdown


def generate_report(world: WorldState, convergence: dict | None = None) -> dict:
    """Generate the full structured report for a completed simulation."""
    metrics = world.compute_metrics()
    npc_results = world.get_npc_results()
    archetype_breakdown = _compute_archetype_breakdown(world)

    # Summarize discussions for the report prompt
    discussion_summaries = []
    for d in world.discussion_log:
        discussion_summaries.append({
            "between": d.get("between", []),
            "key_point": d.get("key_point", ""),
            "outcome": d.get("outcome_summary", ""),
        })

    # Build extra context for the report LLM call
    competitor_profiles = getattr(world, "competitor_profiles", None)

    # Call LLM for narrative analysis
    try:
        analysis = llm_client.generate_report(
            idea=world.idea.to_dict(),
            metrics=metrics,
            npc_results=npc_results,
            discussions=discussion_summaries,
            num_ticks=world.config.num_ticks,
            population_size=len(world.npcs),
            archetype_breakdown=archetype_breakdown,
            convergence=convergence,
            competitor_profiles=competitor_profiles,
        )
    except Exception:
        logger.exception("Failed to generate LLM report, using metrics only")
        analysis = {
            "executive_summary": "Report generation failed. See raw metrics.",
            "adoption_likelihood": "unknown",
            "segments": [],
            "top_objections": [],
            "recommendations": [],
            "risk_factors": [],
        }

    # Product profile (if available)
    profile = getattr(world, "product_profile", None)
    profile_dict = profile.to_dict() if profile is not None else None

    # Combine everything into the final report
    report = {
        "metrics": metrics,
        "analysis": analysis,
        "npc_results": npc_results,
        "discussion_highlights": discussion_summaries[:10],
        "event_count": len(world.event_log),
        "ticks_completed": world.current_tick,
    }
    if profile_dict:
        report["product_profile"] = profile_dict
    asset_signals = getattr(world, "asset_signals", None)
    if asset_signals is not None:
        report["asset_signals"] = asset_signals.to_dict()
    competition_context = getattr(world, "competition_context", None)
    if competition_context is not None:
        report["competition_context"] = competition_context.to_dict()
    competitor_profiles = getattr(world, "competitor_profiles", None)
    if competitor_profiles:
        report["competitor_profiles"] = competitor_profiles
    # Adoption breakdown (final per-NPC adoption already computed by engine)
    adoption_summary = compute_world_adoptions(world)
    report["adoption_breakdown"] = {
        "adoption_rate": adoption_summary["adoption_rate"],
        "adopted_count": adoption_summary["adopted_count"],
        "aware_count": adoption_summary["aware_count"],
        "top_blockers": [
            {"blocker": b, "count": c} for b, c in adoption_summary["top_blockers"]
        ],
    }
    report["archetype_breakdown"] = archetype_breakdown
    if convergence:
        report["convergence"] = convergence
    return report
