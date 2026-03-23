"""Staged experiment matrix — dynamics stabilization correction pass.

Runs 5 configurations × 4 scenarios × N replicas to measure the incremental
effect of each change and seed composition sensitivity.

Run A: seed=5, threshold=0.72, no cap, old concern thresholds (baseline)
Run B: seed=8, threshold=0.72, no cap, old concern thresholds
Run C: seed=8, threshold=0.68, no cap, old concern thresholds
Run D: seed=8, threshold=0.68, cap=0.30, old concern thresholds
Run E: seed=8, threshold=0.68, cap=0.30, new concern thresholds (0.45/0.35/0.50)

Usage:
    cd idealab
    python -m tests.test_dynamics_matrix            # 2 replicas (default)
    python -m tests.test_dynamics_matrix --reps 3   # 3 replicas
    python -m tests.test_dynamics_matrix --resume    # resume from checkpoint
    python -m tests.test_dynamics_matrix --clean     # delete checkpoint, start fresh
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.simulation.world import InjectedIdea, SimConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Shared event collector (same as test_llm_integration.py)
# ---------------------------------------------------------------------------

@dataclass
class ScenarioMetrics:
    name: str
    config_label: str = ""
    awareness_per_tick: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    concern_events: list[dict] = field(default_factory=list)
    spread_events: list[dict] = field(default_factory=list)
    discussions: list[dict] = field(default_factory=list)
    reactions: list[dict] = field(default_factory=list)
    stance_changes: list[dict] = field(default_factory=list)
    final_report: dict = field(default_factory=dict)
    tick_metrics: dict[int, dict] = field(default_factory=dict)
    npc_archetypes: dict[str, str] = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    def make_emit(self):
        def emit(event: dict):
            etype = event.get("type", "")
            tick = event.get("tick", 0)
            data = event.get("data", {})

            if etype == "simulation_start":
                self.npc_archetypes = data.get("npc_archetypes", {})
            elif etype == "tick_end":
                metrics = data.get("metrics", {})
                self.tick_metrics[tick] = metrics
                self.awareness_per_tick[tick] = metrics.get("aware_count", 0)
            elif etype == "npc_reaction":
                self.reactions.append({
                    "tick": tick,
                    "npc_id": data.get("npc_id"),
                    "interest_score": data.get("interest_score"),
                    "baseline": data.get("baseline"),
                    "llm_hint": data.get("llm_hint"),
                    "would_pay": data.get("would_pay"),
                })
            elif etype == "npc_state_change":
                reason = data.get("reason", "")
                self.stance_changes.append({
                    "tick": tick, "reason": reason,
                    "interest_score": data.get("interest_score"),
                })
                if reason == "concern_influence":
                    self.concern_events.append({
                        "tick": tick,
                        "npc_id": data.get("npc_id"),
                        "name": data.get("name"),
                        "interest_score": data.get("interest_score"),
                    })
            elif etype == "npc_spread":
                self.spread_events.append({"tick": tick})
            elif etype == "discussion_end":
                self.discussions.append({
                    "tick": tick,
                    "a_delta": data.get("a_delta"),
                    "b_delta": data.get("b_delta"),
                })
            elif etype == "simulation_complete":
                self.final_report = data.get("report", {})
        return emit


# ---------------------------------------------------------------------------
# 4 representative scenarios
# ---------------------------------------------------------------------------

def make_scenarios(seed_count: int) -> list[tuple[str, InjectedIdea, SimConfig]]:
    config = SimConfig(num_ticks=8, population_size=30, seed_count=seed_count)
    return [
        (
            "strong_free_saas",
            InjectedIdea(
                title="FocusFlow",
                description=(
                    "An AI-powered productivity app that learns your work patterns and "
                    "automatically blocks distractions during your peak focus hours. "
                    "Integrates with calendar, Slack, and browser to create distraction-free "
                    "work sessions. Uses ML to identify your most productive times and "
                    "adapts scheduling suggestions accordingly."
                ),
                category="ai_ml_product",
                stage="mvp",
                target_audience="Remote workers and freelancers who struggle with focus",
                problem_statement=(
                    "Remote workers lose 2+ hours daily to context switching and digital "
                    "distractions. Existing tools require manual configuration and don't "
                    "adapt to individual patterns."
                ),
                price_point="Free",
                existing_alternatives="Freedom, Cold Turkey, Forest app",
                differentiator=(
                    "AI-driven pattern recognition — learns when you're most productive "
                    "and proactively manages distractions without manual setup"
                ),
                known_strengths="Strong retention in beta (72% DAU/MAU), low churn",
                known_risks="Privacy concerns with monitoring work patterns",
            ),
            config,
        ),
        (
            "weak_vague_crypto",
            InjectedIdea(
                title="CryptoGuard",
                description="A blockchain-based security platform that protects your digital assets.",
                category="crypto_web3",
                stage="concept",
                target_audience="crypto users",
                problem_statement="",
                price_point="$50-$100/mo",
                existing_alternatives="",
                differentiator="",
                known_strengths="",
                known_risks="Regulatory uncertainty",
            ),
            config,
        ),
        (
            "niche_nonprofit",
            InjectedIdea(
                title="GreenBridge",
                description=(
                    "A platform connecting urban community gardens with local food banks, "
                    "enabling surplus produce tracking, volunteer coordination, and impact "
                    "reporting. Helps gardens measure their community impact and food banks "
                    "forecast supply from local sources."
                ),
                category="nonprofit",
                stage="mvp",
                target_audience="Community garden coordinators, food bank managers, urban agriculture nonprofits",
                problem_statement=(
                    "30-40% of community garden produce goes unharvested or wasted. Food banks "
                    "can't plan around irregular local supply. Gardens lack tools to prove their "
                    "impact to funders."
                ),
                price_point="Free",
                existing_alternatives="Spreadsheets, Ample Harvest, phone/email coordination",
                differentiator=(
                    "Two-sided matching with impact tracking — gardens see their donation impact, "
                    "food banks get predictable local supply forecasts"
                ),
                known_strengths="Strong demand signal from 12 garden networks surveyed",
                known_risks="Volunteer adoption friction, seasonal usage patterns",
            ),
            config,
        ),
        (
            "premium_hardware",
            InjectedIdea(
                title="AeroSense",
                description=(
                    "A premium smart home air quality monitor with real-time pollutant tracking, "
                    "HVAC integration, and health risk alerts. Hardware device + monthly subscription "
                    "for advanced analytics and filter replacement reminders."
                ),
                category="iot_smart_home",
                stage="prototype",
                target_audience="Health-conscious homeowners, parents with young children, allergy sufferers",
                problem_statement=(
                    "Indoor air quality is 2-5x worse than outdoor but invisible. Existing monitors "
                    "show numbers without actionable insights or HVAC integration."
                ),
                price_point="$100+/mo",
                existing_alternatives="Awair, IQAir AirVisual, PurpleAir",
                differentiator=(
                    "Direct HVAC integration with auto-purification — when PM2.5 spikes, it "
                    "triggers your HVAC system automatically"
                ),
                known_strengths="Patent-pending HVAC integration protocol",
                known_risks="High price point, requires professional installation",
            ),
            config,
        ),
    ]


# ---------------------------------------------------------------------------
# Run configurations
# ---------------------------------------------------------------------------

@dataclass
class RunConfig:
    label: str
    seed_count: int
    recommend_threshold: float
    discussion_cap: float      # 0 = disabled
    concern_interest_thresh: float
    concern_target_min: float
    concern_share_mult: float
    prompt_fix: bool           # whether to use the updated reaction prompt


RUN_CONFIGS = [
    RunConfig("A_baseline",     seed_count=5, recommend_threshold=0.72, discussion_cap=0,    concern_interest_thresh=0.35, concern_target_min=0.45, concern_share_mult=0.30, prompt_fix=False),
    RunConfig("B_seed8",        seed_count=8, recommend_threshold=0.72, discussion_cap=0,    concern_interest_thresh=0.35, concern_target_min=0.45, concern_share_mult=0.30, prompt_fix=False),
    RunConfig("C_thresh068",    seed_count=8, recommend_threshold=0.68, discussion_cap=0,    concern_interest_thresh=0.35, concern_target_min=0.45, concern_share_mult=0.30, prompt_fix=False),
    RunConfig("D_cap030",       seed_count=8, recommend_threshold=0.68, discussion_cap=0.30, concern_interest_thresh=0.35, concern_target_min=0.45, concern_share_mult=0.30, prompt_fix=False),
    RunConfig("E_full",         seed_count=8, recommend_threshold=0.68, discussion_cap=0.40, concern_interest_thresh=0.45, concern_target_min=0.25, concern_share_mult=3.00, prompt_fix=False),
]


# Old prompt text (before Part E fix) — for Runs A-D
_OLD_REACTION_SYSTEM = """You are simulating how different people react to a new product or idea.
You will receive a list of persona profiles and a description of an idea.
For each persona, generate a realistic qualitative reaction based on their personality, archetype, and circumstances.

IMPORTANT: You do NOT decide the interest score. The system computes a deterministic baseline
from the product's structural properties and the persona's archetype. You provide:
1. Qualitative reasoning (WHY this person feels the way they do)
2. Specific objections grounded in their personality
3. A small interest_adjustment (-0.10 to +0.10) ONLY if your qualitative analysis reveals
   something the structural model cannot capture (e.g., a specific pain point match,
   a cultural concern, a personal experience factor). Stay near 0.0 by default.

Rules:
- Stay in character. A skeptic should be skeptical. An early adopter should be excited.
- Reference the persona's actual interests, pain points, and decision style.
- Reactions should feel distinct across personas.
- The interest_adjustment is a HINT, not a score. Keep it small and justified.
- When verified competitors are listed, only reference those specific products by name. Do not invent competitor names or assume products exist that are not listed.
- Output valid JSON only. No markdown, no explanation."""


def apply_run_config(rc: RunConfig):
    """Patch module-level constants to match the run configuration."""
    import backend.simulation.npc as npc_mod
    import backend.simulation.engine as engine_mod
    import backend.simulation.propagation as prop_mod
    import backend.llm.prompts as prompts_mod

    npc_mod.RECOMMEND_THRESHOLD = rc.recommend_threshold
    engine_mod.DISCUSSION_UPLIFT_CAP = rc.discussion_cap
    prop_mod.CONCERN_INTEREST_THRESHOLD = rc.concern_interest_thresh
    prop_mod.CONCERN_TARGET_MIN_INTEREST = rc.concern_target_min

    # Patch the share probability multiplier in the function body is not possible,
    # so we patch the constant and also the function's closure. Since the multiplier
    # is a literal in the function body, we need a different approach.
    # Instead, we replace compute_concern_influence entirely with a version
    # that uses our multiplier.
    _patch_concern_share_mult(prop_mod, rc.concern_share_mult)

    if rc.prompt_fix:
        # Use the updated prompt (already in prompts.py as current code)
        # We need to reload the module to pick up the current file content
        import importlib
        importlib.reload(prompts_mod)
    else:
        # Restore old prompt
        prompts_mod.REACTION_SYSTEM = _OLD_REACTION_SYSTEM


def _patch_concern_share_mult(prop_mod, multiplier: float):
    """Replace compute_concern_influence with a version using the given multiplier."""
    import random as _random

    _SOURCE_CRED = prop_mod._SOURCE_CREDIBILITY

    def patched_concern_influence(world) -> list[tuple[str, float]]:
        concern_deltas: dict[str, float] = {}
        for npc in world.aware_npcs:
            if npc.state.interest_score >= prop_mod.CONCERN_INTEREST_THRESHOLD:
                continue
            concern_strength = prop_mod.CONCERN_INTEREST_THRESHOLD - npc.state.interest_score
            archetype_id = getattr(npc, "archetype", None)
            credibility = _SOURCE_CRED.get(archetype_id or "", 1.0)
            objection_bonus = 1.5 if npc.state.objections else 1.0
            for conn_id in npc.social_connections:
                conn = world.npcs.get(conn_id)
                if not conn or not conn.state.aware:
                    continue
                if conn.state.interest_score < prop_mod.CONCERN_TARGET_MIN_INTEREST:
                    continue
                trust = npc.trust_weights.get(conn_id, 0.5)
                share_prob = (
                    concern_strength
                    * npc.personality.social_influence
                    * trust
                    * multiplier
                    * objection_bonus
                )
                if _random.random() < share_prob:
                    delta = -(concern_strength * trust * credibility * 0.12)
                    concern_deltas[conn_id] = concern_deltas.get(conn_id, 0.0) + delta
        return list(concern_deltas.items())

    prop_mod.compute_concern_influence = patched_concern_influence
    # Also patch the import in engine.py
    import backend.simulation.engine as engine_mod
    engine_mod.compute_concern_influence = patched_concern_influence


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_scenario(m: ScenarioMetrics) -> dict:
    report = m.final_report
    metrics = report.get("metrics", {})
    adoption = report.get("adoption_breakdown", {})
    npc_results = report.get("npc_results", [])

    max_tick = max(m.awareness_per_tick.keys()) if m.awareness_per_tick else 0
    awareness_trajectory = [m.awareness_per_tick.get(t, 0) for t in range(1, max_tick + 1)]
    final_awareness = awareness_trajectory[-1] if awareness_trajectory else 0

    would_recommend_count = sum(1 for n in npc_results if n.get("would_recommend", False))

    stance_counts = defaultdict(int)
    for n in npc_results:
        if n.get("aware", False):
            stance_counts[n.get("stance", "unknown")] += 1

    llm_hints = [r.get("llm_hint", 0) for r in m.reactions]
    avg_llm_hint = sum(llm_hints) / len(llm_hints) if llm_hints else 0
    positive_hints = sum(1 for h in llm_hints if h > 0.02)
    negative_hints = sum(1 for h in llm_hints if h < -0.02)

    total_discussions = len(m.discussions)
    positive_discussions = sum(1 for d in m.discussions if (d.get("a_delta", 0) + d.get("b_delta", 0)) > 0)
    negative_discussions = sum(1 for d in m.discussions if (d.get("a_delta", 0) + d.get("b_delta", 0)) < 0)

    return {
        "name": m.name,
        "config": m.config_label,
        "elapsed_s": round(m.elapsed_seconds, 1),
        "awareness_trajectory": awareness_trajectory,
        "final_awareness": final_awareness,
        "grew_beyond_seeds": final_awareness > (5 if "A_" in m.config_label else 8),
        "would_recommend": would_recommend_count,
        "concern_events": len(m.concern_events),
        "concern_details": m.concern_events[:5],
        "spread_events": len(m.spread_events),
        "discussions_total": total_discussions,
        "discussions_positive": positive_discussions,
        "discussions_negative": negative_discussions,
        "stance_distribution": dict(stance_counts),
        "adoption_rate": adoption.get("adoption_rate", 0),
        "adopted_count": adoption.get("adopted_count", 0),
        "aware_count": adoption.get("aware_count", 0),
        "top_blockers": adoption.get("top_blockers", []),
        "llm_hint_avg": round(avg_llm_hint, 4),
        "llm_hint_positive": positive_hints,
        "llm_hint_negative": negative_hints,
        "interest_rate": metrics.get("interest_rate", 0),
        "rejection_rate": metrics.get("rejection_rate", 0),
        "net_sentiment": metrics.get("net_sentiment", 0),
    }


# ---------------------------------------------------------------------------
# Aggregation helpers for replicas
# ---------------------------------------------------------------------------

def _stddev(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    return math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1))


def _fmt(mean: float, sd: float, decimals: int = 1) -> str:
    """Format as 'mean ± sd'."""
    if sd == 0:
        return f"{mean:.{decimals}f}"
    return f"{mean:.{decimals}f}±{sd:.{decimals}f}"


def aggregate_replicas(
    replica_results: list[list[dict]],
) -> list[dict]:
    """Aggregate per-scenario metrics across replicas.

    Input: list of N replica runs, each containing 4 scenario dicts.
    Output: 4 aggregated scenario dicts with avg/sd fields.
    """
    if not replica_results:
        return []

    scenarios = [r["name"] for r in replica_results[0]]
    aggregated = []

    for scenario in scenarios:
        per_replica = []
        for replica in replica_results:
            r = next((x for x in replica if x["name"] == scenario), None)
            if r:
                per_replica.append(r)

        if not per_replica:
            continue

        n = len(per_replica)

        # Collect numeric vectors
        awarenesses = [r["final_awareness"] for r in per_replica]
        recommends = [r["would_recommend"] for r in per_replica]
        concerns = [r["concern_events"] for r in per_replica]
        spreads = [r["spread_events"] for r in per_replica]
        adoptions = [r["adopted_count"] for r in per_replica]
        hints = [r["llm_hint_avg"] for r in per_replica]
        disc_pos = [r["discussions_positive"] for r in per_replica]
        disc_neg = [r["discussions_negative"] for r in per_replica]

        # Aggregate stance distributions
        all_stances: dict[str, list[int]] = defaultdict(list)
        for r in per_replica:
            stances = r.get("stance_distribution", {})
            for s in ["willing_to_pay", "willing_to_try", "interested", "curious",
                       "indifferent", "skeptical", "opposed"]:
                all_stances[s].append(stances.get(s, 0))

        avg_stances = {s: sum(vals) / n for s, vals in all_stances.items() if sum(vals) > 0}

        # Seed sensitivity = coefficient of variation of awareness
        mean_aw = sum(awarenesses) / n
        sd_aw = _stddev(awarenesses)
        seed_sensitivity = (sd_aw / mean_aw * 100) if mean_aw > 0 else 0

        agg = {
            "name": scenario,
            "config": per_replica[0].get("config", ""),
            "replicas": n,
            # Raw per-replica values for the report
            "awareness_values": awarenesses,
            "recommend_values": recommends,
            "concern_values": concerns,
            "adoption_values": adoptions,
            "hint_values": hints,
            # Averages
            "final_awareness": round(mean_aw, 1),
            "final_awareness_sd": round(sd_aw, 1),
            "would_recommend": round(sum(recommends) / n, 1),
            "would_recommend_sd": round(_stddev(recommends), 1),
            "concern_events": round(sum(concerns) / n, 1),
            "concern_events_sd": round(_stddev(concerns), 1),
            "spread_events": round(sum(spreads) / n, 1),
            "adopted_count": round(sum(adoptions) / n, 1),
            "adopted_count_sd": round(_stddev(adoptions), 1),
            "aware_count": round(mean_aw, 1),
            "llm_hint_avg": round(sum(hints) / n, 4),
            "llm_hint_sd": round(_stddev(hints), 4),
            "discussions_positive": round(sum(disc_pos) / n, 1),
            "discussions_negative": round(sum(disc_neg) / n, 1),
            "seed_sensitivity_pct": round(seed_sensitivity, 1),
            "stance_distribution": {s: round(v, 1) for s, v in avg_stances.items()},
            # Keep individual trajectories
            "awareness_trajectories": [
                r.get("awareness_trajectory", []) for r in per_replica
            ],
            # Keep concern details from all replicas
            "concern_details": [
                ev for r in per_replica for ev in r.get("concern_details", [])
            ],
            # Timing
            "elapsed_s": round(sum(r.get("elapsed_s", 0) for r in per_replica) / n, 1),
        }
        aggregated.append(agg)

    return aggregated


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_matrix_report(
    all_results: dict[str, list[dict]],
    replicas: int = 1,
) -> str:
    lines = []
    lines.append("# Dynamics Stabilization — Experiment Matrix Results")
    lines.append("")
    lines.append(f"Date: 2026-03-21")
    lines.append("Engine: Full LLM (Haiku reactions/discussions, Sonnet reports)")
    lines.append(f"Config: 8 ticks, 30 NPCs per scenario, {replicas} replica(s) per cell")
    lines.append("Seeding: archetype-stratified (1 per archetype guaranteed)")
    lines.append("")

    # Configuration descriptions
    lines.append("## Run Configurations")
    lines.append("")
    lines.append("| Run | Seeds | Threshold | Discuss Cap | Concern (src/tgt/prob) | Prompt Fix |")
    lines.append("|-----|-------|-----------|-------------|----------------------|------------|")
    for rc in RUN_CONFIGS:
        lines.append(
            f"| {rc.label} | {rc.seed_count} | {rc.recommend_threshold} | "
            f"{'off' if rc.discussion_cap == 0 else rc.discussion_cap} | "
            f"{rc.concern_interest_thresh}/{rc.concern_target_min}/{rc.concern_share_mult} | "
            f"{'YES' if rc.prompt_fix else 'no'} |"
        )
    lines.append("")

    # --- Master comparison table ---
    scenarios = ["strong_free_saas", "weak_vague_crypto", "niche_nonprofit", "premium_hardware"]
    run_labels = [rc.label for rc in RUN_CONFIGS]

    multi = replicas > 1

    for scenario in scenarios:
        lines.append(f"## {scenario}")
        lines.append("")
        if multi:
            lines.append("| Run | Aware (avg±sd) | Recomm | Concern | Spread | Adopt | LLM Hint | Seed Sens | Time |")
            lines.append("|-----|---------------|--------|---------|--------|-------|----------|-----------|------|")
        else:
            lines.append("| Run | Aware | Grew? | Recomm | Concern | Spread | Adopt | LLM Hint | Discuss+ | Discuss- | Time |")
            lines.append("|-----|-------|-------|--------|---------|--------|-------|----------|----------|----------|------|")

        for label in run_labels:
            results = all_results.get(label, [])
            r = next((x for x in results if x["name"] == scenario), None)
            if not r:
                cols = 9 if multi else 11
                lines.append(f"| {label} " + "| — " * (cols - 1) + "|")
                continue

            if multi:
                lines.append(
                    f"| {label} "
                    f"| {_fmt(r['final_awareness'], r.get('final_awareness_sd', 0))}/30 "
                    f"| {_fmt(r['would_recommend'], r.get('would_recommend_sd', 0))} "
                    f"| {_fmt(r['concern_events'], r.get('concern_events_sd', 0))} "
                    f"| {r['spread_events']} "
                    f"| {_fmt(r['adopted_count'], r.get('adopted_count_sd', 0))}/{r['aware_count']} "
                    f"| {r['llm_hint_avg']:+.3f}±{r.get('llm_hint_sd', 0):.3f} "
                    f"| {r.get('seed_sensitivity_pct', 0):.0f}% "
                    f"| {r['elapsed_s']}s |"
                )
            else:
                seed_n = 5 if "A_" in label else 8
                grew = "YES" if r["final_awareness"] > seed_n else "NO"
                lines.append(
                    f"| {label} "
                    f"| {r['final_awareness']}/30 "
                    f"| {grew} "
                    f"| {r['would_recommend']} "
                    f"| {r['concern_events']} "
                    f"| {r['spread_events']} "
                    f"| {r['adopted_count']}/{r['aware_count']} "
                    f"| {r['llm_hint_avg']:+.3f} "
                    f"| {r['discussions_positive']} "
                    f"| {r['discussions_negative']} "
                    f"| {r['elapsed_s']}s |"
                )
        lines.append("")

        # Stance distribution comparison
        lines.append(f"### Stance Distributions — {scenario}")
        lines.append("")
        stance_order = ["willing_to_pay", "willing_to_try", "interested", "curious", "indifferent", "skeptical", "opposed"]
        for label in run_labels:
            results = all_results.get(label, [])
            r = next((x for x in results if x["name"] == scenario), None)
            if not r:
                continue
            stances = r["stance_distribution"]
            total = sum(stances.values())
            parts = []
            for s in stance_order:
                count = stances.get(s, 0)
                pct = round(100 * count / total) if total else 0
                if count > 0:
                    fmt_count = f"{count:.0f}" if isinstance(count, float) and count == int(count) else f"{count}"
                    parts.append(f"{s}={fmt_count}({pct}%)")
            lines.append(f"**{label}**: {', '.join(parts) if parts else 'no aware NPCs'}")
        lines.append("")

    # --- Seed sensitivity summary (replicas > 1) ---
    if multi:
        lines.append("## Seed Sensitivity Summary (CoV% of awareness)")
        lines.append("")
        lines.append("| Scenario | " + " | ".join(run_labels) + " |")
        lines.append("|----------|" + "|".join(["-------"] * len(run_labels)) + "|")
        for scenario in scenarios:
            row = f"| {scenario} "
            for label in run_labels:
                results = all_results.get(label, [])
                r = next((x for x in results if x["name"] == scenario), None)
                if r:
                    sens = r.get("seed_sensitivity_pct", 0)
                    row += f"| {sens:.0f}% "
                else:
                    row += "| — "
            row += "|"
            lines.append(row)
        lines.append("")
        lines.append("_Lower CoV% = less sensitive to seed composition. Target: <15%._")
        lines.append("")

        # Per-replica raw values
        lines.append("### Per-Replica Awareness Values")
        lines.append("")
        for scenario in scenarios:
            lines.append(f"**{scenario}**:")
            for label in run_labels:
                results = all_results.get(label, [])
                r = next((x for x in results if x["name"] == scenario), None)
                if r and "awareness_values" in r:
                    lines.append(f"  {label}: {r['awareness_values']}")
            lines.append("")

    # --- Awareness trajectories ---
    lines.append("## Awareness Trajectories")
    lines.append("")
    for scenario in scenarios:
        lines.append(f"### {scenario}")
        for label in run_labels:
            results = all_results.get(label, [])
            r = next((x for x in results if x["name"] == scenario), None)
            if not r:
                continue
            if "awareness_trajectories" in r:
                for i, traj in enumerate(r["awareness_trajectories"]):
                    lines.append(f"  {label} rep{i+1}: {traj}")
            elif "awareness_trajectory" in r:
                lines.append(f"  {label}: {r['awareness_trajectory']}")
        lines.append("")

    # --- Concern propagation summary ---
    lines.append("## Concern Propagation Summary")
    lines.append("")
    any_concerns = False
    for label in run_labels:
        for r in all_results.get(label, []):
            ce = r.get("concern_events", 0)
            if (isinstance(ce, (int, float)) and ce > 0):
                any_concerns = True
                lines.append(f"**{label} / {r['name']}**: {ce} events")
                for ev in r.get("concern_details", [])[:5]:
                    lines.append(f"  - Tick {ev['tick']}: {ev.get('name', '?')} → interest {ev.get('interest_score', '?')}")
    if not any_concerns:
        lines.append("No concern propagation events in any run.")
    lines.append("")

    # --- LLM Hint comparison ---
    lines.append("## LLM Hint Comparison (avg per scenario)")
    lines.append("")
    lines.append("| Scenario | " + " | ".join(run_labels) + " |")
    lines.append("|----------|" + "|".join(["-------"] * len(run_labels)) + "|")
    for scenario in scenarios:
        row = f"| {scenario} "
        for label in run_labels:
            results = all_results.get(label, [])
            r = next((x for x in results if x["name"] == scenario), None)
            if r:
                row += f"| {r['llm_hint_avg']:+.3f} "
                if multi and r.get("llm_hint_sd"):
                    row = row.rstrip() + f"±{r['llm_hint_sd']:.3f} "
            else:
                row += "| — "
        row += "|"
        lines.append(row)
    lines.append("")

    # === STAGED ANALYSIS ===
    lines.append("---")
    lines.append("")
    lines.append("## Staged Analysis")
    lines.append("")

    def _get(label, scenario):
        return next((x for x in all_results.get(label, []) if x["name"] == scenario), None)

    def _aw(r):
        if multi and r.get("final_awareness_sd"):
            return f"{r['final_awareness']}±{r['final_awareness_sd']}"
        return str(r["final_awareness"])

    # A→B
    lines.append("### A→B: Effect of increasing seed count (5→8)")
    lines.append("")
    for scenario in scenarios:
        a, b = _get("A_baseline", scenario), _get("B_seed8", scenario)
        if a and b:
            lines.append(
                f"- **{scenario}**: awareness {_aw(a)}→{_aw(b)}, "
                f"recommenders {a['would_recommend']}→{b['would_recommend']}, "
                f"concern {a['concern_events']}→{b['concern_events']}"
            )
    lines.append("")

    # B→C
    lines.append("### B→C: Effect of lowering threshold (0.72→0.68)")
    lines.append("")
    for scenario in scenarios:
        b, c = _get("B_seed8", scenario), _get("C_thresh068", scenario)
        if b and c:
            lines.append(
                f"- **{scenario}**: awareness {_aw(b)}→{_aw(c)}, "
                f"recommenders {b['would_recommend']}→{c['would_recommend']}, "
                f"concern {b['concern_events']}→{c['concern_events']}"
            )
    lines.append("")

    # C→D
    lines.append("### C→D: Effect of discussion uplift cap (0.30)")
    lines.append("")
    for scenario in scenarios:
        c, d = _get("C_thresh068", scenario), _get("D_cap030", scenario)
        if c and d:
            lines.append(
                f"- **{scenario}**: awareness {_aw(c)}→{_aw(d)}, "
                f"recommenders {c['would_recommend']}→{d['would_recommend']}, "
                f"concern {c['concern_events']}→{d['concern_events']}"
            )
    lines.append("")

    # D→E
    lines.append("### D→E: Effect of relaxed concern propagation + balanced prompt")
    lines.append("")
    for scenario in scenarios:
        d, e = _get("D_cap030", scenario), _get("E_full", scenario)
        if d and e:
            lines.append(
                f"- **{scenario}**: awareness {_aw(d)}→{_aw(e)}, "
                f"recommenders {d['would_recommend']}→{e['would_recommend']}, "
                f"concern {d['concern_events']}→{e['concern_events']}, "
                f"LLM hint {d['llm_hint_avg']:+.3f}→{e['llm_hint_avg']:+.3f}"
            )
    lines.append("")

    # Verdict placeholder
    lines.append("---")
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append("_(To be filled based on analysis of results above)_")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    from backend.simulation.engine import run_simulation

    parser = argparse.ArgumentParser(description="Dynamics stabilization experiment matrix")
    parser.add_argument("--reps", type=int, default=2, help="Replicas per (config, scenario) cell")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint if available")
    parser.add_argument("--clean", action="store_true", help="Delete checkpoint and start fresh")
    args = parser.parse_args()
    num_replicas = max(1, args.reps)

    output_dir = PROJECT_ROOT / "process_doc"
    output_dir.mkdir(exist_ok=True)
    checkpoint_path = output_dir / "dynamics_matrix_checkpoint.json"

    # Load checkpoint if resuming
    all_results: dict[str, list[dict]] = {}
    checkpoint_replicas: int = num_replicas
    if args.clean and checkpoint_path.exists():
        checkpoint_path.unlink()
        print("Checkpoint deleted.")
    elif args.resume and checkpoint_path.exists():
        with open(checkpoint_path, encoding="utf-8") as f:
            ckpt = json.load(f)
        all_results = ckpt.get("results", {})
        checkpoint_replicas = ckpt.get("replicas", num_replicas)
        num_replicas = checkpoint_replicas
        completed = list(all_results.keys())
        print(f"Resuming from checkpoint: {len(completed)}/{len(RUN_CONFIGS)} configs done ({completed})")
        print(f"Using {num_replicas} replicas (from checkpoint)")
    elif checkpoint_path.exists() and not args.clean:
        print(f"Checkpoint exists ({checkpoint_path.name}). Use --resume to continue or --clean to restart.")

    total_runs = len(RUN_CONFIGS) * 4 * num_replicas
    remaining_configs = [rc for rc in RUN_CONFIGS if rc.label not in all_results]
    remaining_runs = len(remaining_configs) * 4 * num_replicas

    print("=" * 70)
    print("Dynamics Stabilization — Experiment Matrix")
    print("=" * 70)
    print(f"Runs: {len(RUN_CONFIGS)} configs x 4 scenarios x {num_replicas} replicas = {total_runs} total")
    if remaining_runs < total_runs:
        print(f"Remaining: {len(remaining_configs)} configs x 4 scenarios x {num_replicas} replicas = {remaining_runs} runs")
    print()

    for rc in remaining_configs:
        print(f"\n{'=' * 70}")
        print(f"RUN: {rc.label}")
        print(f"  seeds={rc.seed_count}, threshold={rc.recommend_threshold}, "
              f"cap={rc.discussion_cap}, concern={rc.concern_interest_thresh}/"
              f"{rc.concern_target_min}/{rc.concern_share_mult}, "
              f"prompt_fix={'YES' if rc.prompt_fix else 'no'}")
        print(f"{'=' * 70}")

        apply_run_config(rc)

        # Collect per-replica results
        replica_results: list[list[dict]] = []

        for rep in range(num_replicas):
            scenarios = make_scenarios(rc.seed_count)
            rep_results = []

            for i, (name, idea, config) in enumerate(scenarios, 1):
                cell_label = f"[rep{rep+1}/{num_replicas}] [{i}/4]"
                print(f"\n  {cell_label} {name} ({idea.title})")

                collector = ScenarioMetrics(name=name, config_label=rc.label)
                emit = collector.make_emit()

                start = time.time()
                try:
                    report = run_simulation(idea, config, emit=emit)
                    collector.final_report = report
                except Exception as e:
                    logger.error("FAILED: %s / %s rep%d: %s", rc.label, name, rep + 1, e, exc_info=True)
                    print(f"    *** FAILED: {e}")
                    continue
                elapsed = time.time() - start
                collector.elapsed_seconds = elapsed

                metrics = report.get("metrics", {})
                adoption = report.get("adoption_breakdown", {})
                print(f"    {elapsed:.0f}s | aware={metrics.get('aware_count', '?')}/30 "
                      f"| recommend={sum(1 for n in report.get('npc_results', []) if n.get('would_recommend'))} "
                      f"| concern={len(collector.concern_events)} "
                      f"| adopt={adoption.get('adopted_count', 0)}/{adoption.get('aware_count', 0)} "
                      f"| spread={len(collector.spread_events)}")

                result = analyze_scenario(collector)
                rep_results.append(result)

            replica_results.append(rep_results)

        # Aggregate across replicas
        if num_replicas > 1:
            all_results[rc.label] = aggregate_replicas(replica_results)
        else:
            all_results[rc.label] = replica_results[0] if replica_results else []

        # Save checkpoint after each config completes
        checkpoint_path.write_text(
            json.dumps({"replicas": num_replicas, "results": all_results},
                       indent=2, default=str, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\n  >> Checkpoint saved ({len(all_results)}/{len(RUN_CONFIGS)} configs done)")

    # Generate final report
    print("\n" + "=" * 70)
    print("Generating matrix report...")
    report_text = generate_matrix_report(all_results, replicas=num_replicas)

    report_path = output_dir / "dynamics_matrix_results.md"
    report_path.write_text(report_text, encoding="utf-8")
    print(f"Report: {report_path}")

    raw_path = output_dir / "dynamics_matrix_raw.json"
    raw_path.write_text(
        json.dumps(all_results, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Raw data: {raw_path}")

    # Clean up checkpoint on successful completion
    if checkpoint_path.exists() and len(all_results) == len(RUN_CONFIGS):
        checkpoint_path.unlink()
        print("Checkpoint cleaned up (all configs complete).")

    print("\n" + "=" * 70)
    print(report_text)


if __name__ == "__main__":
    main()
