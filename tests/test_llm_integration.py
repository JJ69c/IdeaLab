"""Full LLM-enabled integration validation at recommendation threshold 0.72.

Runs 4-6 representative scenarios through the REAL simulation engine with
real LLM calls (Haiku for reactions/discussions, Sonnet for reports).
Captures events via emit callback to answer 5 questions:

1. Does awareness still get stuck at the seed group?
2. Is recommendation still too rare?
3. Does concern propagation start to appear?
4. Do strong products evolve beyond the seed group?
5. Does 0.72 still look too strict after real discussions?

Usage:
    cd idealab
    python -m tests.test_llm_integration

Cost estimate: ~$0.30-0.80 total (6 scenarios × 30 NPCs × Haiku reactions + discussions + Sonnet reports)
"""

from __future__ import annotations

import json
import logging
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# Ensure the project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.simulation.engine import run_simulation
from backend.simulation.npc import derive_stance
from backend.simulation.world import InjectedIdea, SimConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Suppress noisy HTTP logs from anthropic/httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Event collector
# ---------------------------------------------------------------------------

@dataclass
class ScenarioMetrics:
    """Collects events from a single simulation run."""
    name: str
    awareness_per_tick: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    recommenders_per_tick: dict[int, int] = field(default_factory=lambda: defaultdict(int))
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
        """Return an emit callback that captures events."""
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
                # Count recommenders from aware NPCs (tracked via npc_reaction)
                # We'll derive this from the reaction data instead

            elif etype == "npc_reaction":
                self.reactions.append({
                    "tick": tick,
                    "npc_id": data.get("npc_id"),
                    "name": data.get("name"),
                    "stance": data.get("stance"),
                    "interest_score": data.get("interest_score"),
                    "baseline": data.get("baseline"),
                    "llm_hint": data.get("llm_hint"),
                    "would_pay": data.get("would_pay"),
                    "objections": data.get("objections", []),
                })

            elif etype == "npc_state_change":
                reason = data.get("reason", "")
                self.stance_changes.append({
                    "tick": tick,
                    "npc_id": data.get("npc_id"),
                    "name": data.get("name"),
                    "new_stance": data.get("new_stance"),
                    "interest_score": data.get("interest_score"),
                    "reason": reason,
                })
                if reason == "concern_influence":
                    self.concern_events.append({
                        "tick": tick,
                        "npc_id": data.get("npc_id"),
                        "name": data.get("name"),
                        "interest_score": data.get("interest_score"),
                    })

            elif etype == "npc_spread":
                self.spread_events.append({
                    "tick": tick,
                    "source_id": data.get("source_id"),
                    "source_name": data.get("source_name"),
                    "target_id": data.get("target_id"),
                    "target_name": data.get("target_name"),
                })

            elif etype == "discussion_end":
                self.discussions.append({
                    "tick": tick,
                    "npc_a": data.get("npc_a_name"),
                    "npc_b": data.get("npc_b_name"),
                    "a_delta": data.get("a_delta"),
                    "b_delta": data.get("b_delta"),
                    "a_interest": data.get("a_interest"),
                    "b_interest": data.get("b_interest"),
                    "a_stance": data.get("a_stance"),
                    "b_stance": data.get("b_stance"),
                    "key_point": data.get("key_point"),
                })

            elif etype == "simulation_complete":
                self.final_report = data.get("report", {})

        return emit


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

SCENARIOS: list[tuple[str, InjectedIdea, SimConfig]] = [
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
        SimConfig(num_ticks=8, population_size=30, seed_count=5),
    ),
    (
        "strong_health_app",
        InjectedIdea(
            title="NutriScan",
            description=(
                "A mobile app that uses your phone camera to scan meals and "
                "instantly provides detailed nutritional breakdown, allergen warnings, "
                "and personalized health recommendations based on your dietary goals "
                "and medical conditions."
            ),
            category="health_wellness",
            stage="prototype",
            target_audience="Health-conscious adults managing dietary restrictions or fitness goals",
            problem_statement=(
                "People with dietary restrictions spend 15+ minutes per meal researching "
                "ingredients and nutritional content. Existing calorie counters require "
                "manual entry and miss allergen interactions."
            ),
            price_point="$5-$20/mo",
            existing_alternatives="MyFitnessPal, Cronometer, Yazio",
            differentiator=(
                "Camera-based instant scan with allergen cross-referencing — no manual "
                "entry, real-time warnings for drug-food interactions"
            ),
            known_strengths="Accuracy rate of 94% on common meals in testing",
            known_risks="Medical liability if nutritional advice is wrong, FDA compliance",
        ),
        SimConfig(num_ticks=8, population_size=30, seed_count=5),
    ),
    (
        "weak_vague_crypto",
        InjectedIdea(
            title="CryptoGuard",
            description=(
                "A blockchain-based security platform that protects your digital assets."
            ),
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
        SimConfig(num_ticks=8, population_size=30, seed_count=5),
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
        SimConfig(num_ticks=8, population_size=30, seed_count=5),
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
        SimConfig(num_ticks=8, population_size=30, seed_count=5),
    ),
    (
        "high_utility_devtool",
        InjectedIdea(
            title="QueryLens",
            description=(
                "A developer tool that sits between your application and database, "
                "intercepting every query to provide real-time performance analysis, "
                "automatic index suggestions, and N+1 query detection. Shows exactly "
                "which line of code generated each slow query."
            ),
            category="developer_tool",
            stage="mvp",
            target_audience="Backend developers and DevOps engineers working with SQL databases",
            problem_statement=(
                "Developers spend hours debugging slow queries and discovering N+1 problems "
                "only in production. Existing tools like EXPLAIN require manual invocation "
                "and don't connect queries to source code."
            ),
            price_point="$5-$20/mo",
            existing_alternatives="pganalyze, Datadog APM, Django Debug Toolbar",
            differentiator=(
                "Source-code-to-query mapping with auto-fix suggestions — shows the exact "
                "line of code causing each slow query and suggests ORM-level fixes"
            ),
            known_strengths="Reduced debug time by 60% in pilot team",
            known_risks="Performance overhead concern, security of query interception",
        ),
        SimConfig(num_ticks=8, population_size=30, seed_count=5),
    ),
]


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_scenario(m: ScenarioMetrics) -> dict:
    """Analyze a single scenario's collected metrics."""
    report = m.final_report
    metrics = report.get("metrics", {})
    adoption = report.get("adoption_breakdown", {})

    # Awareness trajectory
    max_tick = max(m.awareness_per_tick.keys()) if m.awareness_per_tick else 0
    awareness_trajectory = [
        m.awareness_per_tick.get(t, 0) for t in range(1, max_tick + 1)
    ]
    final_awareness = awareness_trajectory[-1] if awareness_trajectory else 0
    awareness_grew = final_awareness > 5  # Beyond seed group

    # Recommendation: count NPCs with interest >= 0.72 from final results
    npc_results = report.get("npc_results", [])
    recommenders = [
        n for n in npc_results
        if n.get("interest_score", 0) >= 0.72 and n.get("aware", False)
    ]
    would_recommend_count = sum(
        1 for n in npc_results if n.get("would_recommend", False)
    )

    # Concern propagation
    concern_count = len(m.concern_events)

    # Discussion impact
    positive_discussions = sum(1 for d in m.discussions if (d.get("a_delta", 0) + d.get("b_delta", 0)) > 0)
    negative_discussions = sum(1 for d in m.discussions if (d.get("a_delta", 0) + d.get("b_delta", 0)) < 0)
    total_discussions = len(m.discussions)
    avg_abs_delta = 0.0
    if m.discussions:
        avg_abs_delta = sum(
            abs(d.get("a_delta", 0)) + abs(d.get("b_delta", 0))
            for d in m.discussions
        ) / len(m.discussions)

    # Stance distribution from final results
    stance_counts = defaultdict(int)
    for n in npc_results:
        if n.get("aware", False):
            stance_counts[n.get("stance", "unknown")] += 1

    # Archetype breakdown
    archetype_scores = defaultdict(list)
    for n in npc_results:
        arch = n.get("archetype", "unknown")
        if n.get("aware", False):
            archetype_scores[arch].append(n.get("interest_score", 0))

    archetype_summary = {}
    for arch, scores in sorted(archetype_scores.items()):
        archetype_summary[arch] = {
            "count": len(scores),
            "mean": round(sum(scores) / len(scores), 3) if scores else 0,
            "min": round(min(scores), 3) if scores else 0,
            "max": round(max(scores), 3) if scores else 0,
        }

    # LLM hint distribution from reactions
    llm_hints = [r.get("llm_hint", 0) for r in m.reactions]
    avg_llm_hint = sum(llm_hints) / len(llm_hints) if llm_hints else 0
    positive_hints = sum(1 for h in llm_hints if h > 0.02)
    negative_hints = sum(1 for h in llm_hints if h < -0.02)

    return {
        "name": m.name,
        "elapsed_seconds": round(m.elapsed_seconds, 1),
        "awareness": {
            "trajectory": awareness_trajectory,
            "final": final_awareness,
            "grew_beyond_seeds": awareness_grew,
            "awareness_rate": metrics.get("awareness_rate", 0),
        },
        "recommendations": {
            "would_recommend_count": would_recommend_count,
            "above_072_count": len(recommenders),
            "total_aware": metrics.get("aware_count", 0),
        },
        "concern_propagation": {
            "events": concern_count,
            "details": m.concern_events[:5],
        },
        "discussions": {
            "total": total_discussions,
            "positive": positive_discussions,
            "negative": negative_discussions,
            "avg_abs_delta": round(avg_abs_delta, 4),
        },
        "llm_hints": {
            "avg": round(avg_llm_hint, 4),
            "positive_count": positive_hints,
            "negative_count": negative_hints,
            "total": len(llm_hints),
        },
        "stance_distribution": dict(stance_counts),
        "archetype_breakdown": archetype_summary,
        "adoption": {
            "rate": adoption.get("adoption_rate", 0),
            "adopted_count": adoption.get("adopted_count", 0),
            "aware_count": adoption.get("aware_count", 0),
            "top_blockers": adoption.get("top_blockers", []),
        },
        "metrics": {
            "interest_rate": metrics.get("interest_rate", 0),
            "rejection_rate": metrics.get("rejection_rate", 0),
            "net_sentiment": metrics.get("net_sentiment", 0),
            "would_pay_rate": metrics.get("would_pay_rate", 0),
            "viral_coefficient": metrics.get("viral_coefficient", 0),
        },
        "spread_events": len(m.spread_events),
    }


def generate_summary(results: list[dict]) -> str:
    """Generate the final analysis answering the 5 questions."""
    lines = []
    lines.append("# LLM-Enabled Integration Validation — Threshold 0.72")
    lines.append("")
    lines.append(f"Date: 2026-03-21")
    lines.append(f"Scenarios: {len(results)}")
    lines.append("Engine: Full LLM (Haiku reactions/discussions, Sonnet reports)")
    lines.append("Config: 8 ticks, 30 NPCs, 5 seeds per scenario")
    lines.append("")

    # --- Per-scenario summary table ---
    lines.append("## Per-Scenario Summary")
    lines.append("")
    lines.append("| Scenario | Aware | Grew? | Recomm | Concern | Discussions | Adopt | Time |")
    lines.append("|----------|-------|-------|--------|---------|-------------|-------|------|")
    for r in results:
        grew = "YES" if r["awareness"]["grew_beyond_seeds"] else "NO"
        lines.append(
            f"| {r['name']} "
            f"| {r['awareness']['final']}/30 "
            f"| {grew} "
            f"| {r['recommendations']['would_recommend_count']} "
            f"| {r['concern_propagation']['events']} "
            f"| {r['discussions']['total']} "
            f"| {r['adoption']['adopted_count']}/{r['adoption']['aware_count']} "
            f"| {r['elapsed_seconds']}s |"
        )
    lines.append("")

    # --- Stance distributions ---
    lines.append("## Stance Distributions")
    lines.append("")
    for r in results:
        stances = r["stance_distribution"]
        total_aware = sum(stances.values())
        parts = []
        for s in ["willing_to_try", "interested", "curious", "indifferent", "skeptical", "opposed"]:
            count = stances.get(s, 0)
            pct = round(100 * count / total_aware) if total_aware else 0
            parts.append(f"{s}={count}({pct}%)")
        lines.append(f"**{r['name']}**: {', '.join(parts)}")
    lines.append("")

    # --- LLM Hint Analysis ---
    lines.append("## LLM Hint Analysis")
    lines.append("")
    lines.append("| Scenario | Avg Hint | Positive | Negative | Total |")
    lines.append("|----------|----------|----------|----------|-------|")
    for r in results:
        h = r["llm_hints"]
        lines.append(
            f"| {r['name']} | {h['avg']:+.4f} | {h['positive_count']} | {h['negative_count']} | {h['total']} |"
        )
    lines.append("")

    # --- Discussion Analysis ---
    lines.append("## Discussion Impact")
    lines.append("")
    lines.append("| Scenario | Total | Net Positive | Net Negative | Avg |delta| |")
    lines.append("|----------|-------|-------------|-------------|-------------|")
    for r in results:
        d = r["discussions"]
        lines.append(
            f"| {r['name']} | {d['total']} | {d['positive']} | {d['negative']} | {d['avg_abs_delta']:.4f} |"
        )
    lines.append("")

    # --- Archetype breakdown for strong product ---
    lines.append("## Archetype Breakdown (strong_free_saas)")
    lines.append("")
    strong = next((r for r in results if r["name"] == "strong_free_saas"), None)
    if strong:
        lines.append("| Archetype | Count | Mean | Min | Max |")
        lines.append("|-----------|-------|------|-----|-----|")
        for arch, data in sorted(strong["archetype_breakdown"].items()):
            lines.append(
                f"| {arch} | {data['count']} | {data['mean']:.3f} | {data['min']:.3f} | {data['max']:.3f} |"
            )
    lines.append("")

    # --- Adoption breakdown ---
    lines.append("## Adoption Breakdown")
    lines.append("")
    for r in results:
        a = r["adoption"]
        blockers = ", ".join(
            f"{b['blocker']}({b['count']})" for b in a.get("top_blockers", [])[:3]
        )
        lines.append(
            f"**{r['name']}**: {a['adopted_count']}/{a['aware_count']} adopted "
            f"(rate={a['rate']:.2f}). Top blockers: {blockers or 'none'}"
        )
    lines.append("")

    # --- Concern propagation details ---
    lines.append("## Concern Propagation Details")
    lines.append("")
    any_concerns = False
    for r in results:
        cp = r["concern_propagation"]
        if cp["events"] > 0:
            any_concerns = True
            lines.append(f"**{r['name']}**: {cp['events']} events")
            for ev in cp["details"]:
                lines.append(
                    f"  - Tick {ev['tick']}: {ev['name']} interest dropped to {ev['interest_score']:.3f}"
                )
    if not any_concerns:
        lines.append("No concern propagation events observed in any scenario.")
    lines.append("")

    # --- Spread events ---
    lines.append("## Spread Events (awareness growth)")
    lines.append("")
    for r in results:
        lines.append(f"**{r['name']}**: {r['spread_events']} spread events, awareness trajectory: {r['awareness']['trajectory']}")
    lines.append("")

    # === THE 5 QUESTIONS ===
    lines.append("---")
    lines.append("")
    lines.append("## Answering the 5 Questions")
    lines.append("")

    # Q1: Does awareness still get stuck?
    stuck_count = sum(1 for r in results if not r["awareness"]["grew_beyond_seeds"])
    grew_count = sum(1 for r in results if r["awareness"]["grew_beyond_seeds"])
    lines.append("### Q1: Does awareness still get stuck at the seed group?")
    lines.append("")
    lines.append(f"- {grew_count}/{len(results)} scenarios grew beyond the 5-seed group")
    lines.append(f"- {stuck_count}/{len(results)} scenarios remained at or near 5 aware")
    for r in results:
        traj = r["awareness"]["trajectory"]
        lines.append(f"  - {r['name']}: {traj[0] if traj else '?'} → {traj[-1] if traj else '?'} aware")
    lines.append("")

    # Q2: Is recommendation still too rare?
    total_recommenders = sum(r["recommendations"]["would_recommend_count"] for r in results)
    lines.append("### Q2: Is recommendation still too rare?")
    lines.append("")
    lines.append(f"- Total recommenders across all scenarios: {total_recommenders}")
    for r in results:
        rec = r["recommendations"]
        lines.append(
            f"  - {r['name']}: {rec['would_recommend_count']} recommenders, "
            f"{rec['above_072_count']} above 0.72 (of {rec['total_aware']} aware)"
        )
    lines.append("")

    # Q3: Does concern propagation appear?
    total_concerns = sum(r["concern_propagation"]["events"] for r in results)
    lines.append("### Q3: Does concern propagation start to appear?")
    lines.append("")
    lines.append(f"- Total concern events across all scenarios: {total_concerns}")
    if total_concerns > 0:
        for r in results:
            if r["concern_propagation"]["events"] > 0:
                lines.append(f"  - {r['name']}: {r['concern_propagation']['events']} events")
    else:
        lines.append("- No concern propagation events in any scenario.")
        lines.append("  This could indicate: (a) not enough aware NPCs with low interest + objections connected to high-interest NPCs, or (b) the threshold conditions are rarely met even with LLM.")
    lines.append("")

    # Q4: Do strong products evolve beyond seeds?
    lines.append("### Q4: Do strong products evolve beyond the seed group?")
    lines.append("")
    strong_scenarios = [r for r in results if r["name"] in ("strong_free_saas", "strong_health_app", "high_utility_devtool")]
    for r in strong_scenarios:
        lines.append(
            f"- **{r['name']}**: awareness {r['awareness']['trajectory'][0] if r['awareness']['trajectory'] else '?'} → "
            f"{r['awareness']['final']}, spread events={r['spread_events']}, "
            f"recommenders={r['recommendations']['would_recommend_count']}, "
            f"adoption={r['adoption']['adopted_count']}/{r['adoption']['aware_count']}"
        )
    lines.append("")

    # Q5: Does 0.72 still look too strict?
    lines.append("### Q5: Does 0.72 still look too strict after real discussions?")
    lines.append("")
    # Analyze how many NPCs ended up in the 0.65-0.72 band (would recommend at 0.68 but not at 0.72)
    borderline_total = 0
    for r in results:
        # We need to look at the archetype breakdown
        for arch, data in r.get("archetype_breakdown", {}).items():
            if 0.65 <= data["mean"] < 0.72:
                borderline_total += data["count"]

    lines.append(f"- Archetype-means in 0.65-0.72 band (borderline): {borderline_total} NPC-groups")
    lines.append(f"- Total recommenders at 0.72: {total_recommenders}")
    lines.append(f"- Scenarios with awareness growth: {grew_count}/{len(results)}")
    lines.append("")

    # Final verdict
    lines.append("---")
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append("_(To be filled based on results above)_")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("LLM-Enabled Integration Validation — Threshold 0.72")
    print("=" * 70)
    print(f"Running {len(SCENARIOS)} scenarios with real LLM calls...")
    print()

    all_results = []

    for i, (name, idea, config) in enumerate(SCENARIOS, 1):
        print(f"\n{'─' * 60}")
        print(f"[{i}/{len(SCENARIOS)}] Running: {name} ({idea.title})")
        print(f"  Category: {idea.category}, Price: {idea.price_point}")
        print(f"  Config: {config.num_ticks} ticks, {config.population_size} NPCs, {config.seed_count} seeds")
        print(f"{'─' * 60}")

        collector = ScenarioMetrics(name=name)
        emit = collector.make_emit()

        start = time.time()
        try:
            report = run_simulation(idea, config, emit=emit)
            collector.final_report = report
        except Exception as e:
            logger.error("Scenario %s FAILED: %s", name, e, exc_info=True)
            print(f"  *** FAILED: {e}")
            continue
        elapsed = time.time() - start
        collector.elapsed_seconds = elapsed

        # Quick summary
        metrics = report.get("metrics", {})
        adoption = report.get("adoption_breakdown", {})
        print(f"  Completed in {elapsed:.1f}s")
        print(f"  Awareness: {metrics.get('aware_count', '?')}/30 ({metrics.get('awareness_rate', 0):.0%})")
        print(f"  Interest rate: {metrics.get('interest_rate', 0):.0%}")
        print(f"  Rejection rate: {metrics.get('rejection_rate', 0):.0%}")
        print(f"  Discussions: {len(collector.discussions)}")
        print(f"  Spread events: {len(collector.spread_events)}")
        print(f"  Concern events: {len(collector.concern_events)}")
        print(f"  Adoption: {adoption.get('adopted_count', 0)}/{adoption.get('aware_count', 0)}")

        result = analyze_scenario(collector)
        all_results.append(result)

    # Generate report
    print("\n" + "=" * 70)
    print("Generating analysis report...")
    summary = generate_summary(all_results)

    output_path = PROJECT_ROOT / "process_doc" / "llm_integration_validation.md"
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(summary, encoding="utf-8")
    print(f"Report written to: {output_path}")

    # Also dump raw results as JSON for reference
    raw_path = PROJECT_ROOT / "process_doc" / "llm_integration_raw.json"
    raw_path.write_text(
        json.dumps(all_results, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Raw results written to: {raw_path}")

    # Print the summary
    print("\n" + "=" * 70)
    print(summary)


if __name__ == "__main__":
    main()
