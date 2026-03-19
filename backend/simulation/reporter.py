"""Report generation — assembles data and calls LLM for narrative analysis."""

from __future__ import annotations

import logging

from backend.llm.client import llm_client
from backend.simulation.world import WorldState

logger = logging.getLogger(__name__)


def generate_report(world: WorldState, convergence: dict | None = None) -> dict:
    """Generate the full structured report for a completed simulation."""
    metrics = world.compute_metrics()
    npc_results = world.get_npc_results()

    # Summarize discussions for the report prompt
    discussion_summaries = []
    for d in world.discussion_log:
        discussion_summaries.append({
            "between": d.get("between", []),
            "key_point": d.get("key_point", ""),
            "outcome": d.get("outcome_summary", ""),
        })

    # Call LLM for narrative analysis
    try:
        analysis = llm_client.generate_report(
            idea=world.idea.to_dict(),
            metrics=metrics,
            npc_results=npc_results,
            discussions=discussion_summaries,
            num_ticks=world.config.num_ticks,
            population_size=len(world.npcs),
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
    if convergence:
        report["convergence"] = convergence
    return report
