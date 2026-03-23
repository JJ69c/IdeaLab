"""Focused validation: DISCUSSION_UPLIFT_CAP = 0.30 vs 0.40

Baseline: Run C config (seed=8, threshold=0.68, prompt=reverted)
Scenarios: strong_free_saas, weak_vague_crypto, premium_hardware
Replicas: 2 per cell (12 total LLM runs)

Usage:
    cd idealab
    python -m tests.test_cap_comparison
"""

from __future__ import annotations

import json
import logging
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
# Event collector (same as matrix script)
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
                })
            elif etype == "npc_state_change":
                reason = data.get("reason", "")
                self.stance_changes.append({"tick": tick, "reason": reason})
                if reason == "concern_influence":
                    self.concern_events.append({"tick": tick})
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
# 3 scenarios (subset of matrix)
# ---------------------------------------------------------------------------

def make_scenarios() -> list[tuple[str, InjectedIdea, SimConfig]]:
    config = SimConfig(num_ticks=8, population_size=30, seed_count=8)
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
# Analysis helpers
# ---------------------------------------------------------------------------

def _analyze(collector: ScenarioMetrics) -> dict:
    report = collector.final_report
    metrics = report.get("metrics", {})
    adoption = report.get("adoption_breakdown", {})
    npc_results = report.get("npc_results", [])

    hints = [r["llm_hint"] for r in collector.reactions if r.get("llm_hint") is not None]
    pos_deltas = [d["a_delta"] for d in collector.discussions if (d.get("a_delta") or 0) > 0]
    pos_deltas += [d["b_delta"] for d in collector.discussions if (d.get("b_delta") or 0) > 0]

    stances = defaultdict(int)
    for n in npc_results:
        stances[n.get("stance", "unknown")] += 1

    trajectory = []
    for t in sorted(collector.awareness_per_tick.keys()):
        trajectory.append(collector.awareness_per_tick[t])

    return {
        "name": collector.name,
        "aware": metrics.get("aware_count", 0),
        "recommend": sum(1 for n in npc_results if n.get("would_recommend")),
        "adopted": adoption.get("adopted_count", 0),
        "concern": len(collector.concern_events),
        "spread": len(collector.spread_events),
        "llm_hint_avg": sum(hints) / len(hints) if hints else 0,
        "stances": dict(stances),
        "trajectory": trajectory,
        "discussion_pos_deltas": len(pos_deltas),
        "discussion_pos_avg": sum(pos_deltas) / len(pos_deltas) if pos_deltas else 0,
    }


def _avg(values):
    return sum(values) / len(values) if values else 0


def _sd(values):
    if len(values) < 2:
        return 0
    m = _avg(values)
    return (sum((v - m) ** 2 for v in values) / (len(values) - 1)) ** 0.5


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import backend.simulation.engine as engine_mod
    from backend.simulation.engine import run_simulation

    NUM_REPLICAS = 2
    CAP_VALUES = [0.30, 0.40]
    scenarios_spec = make_scenarios()
    scenario_names = [s[0] for s in scenarios_spec]

    total = len(CAP_VALUES) * len(scenarios_spec) * NUM_REPLICAS
    print("=" * 70)
    print("Cap Comparison Validation")
    print(f"  Baseline: seed=8, threshold=0.68, prompt=reverted")
    print(f"  Caps: {CAP_VALUES}")
    print(f"  Scenarios: {scenario_names}")
    print(f"  Replicas: {NUM_REPLICAS}")
    print(f"  Total runs: {total}")
    print("=" * 70)

    all_results: dict[str, list[dict]] = {}  # "cap_0.30" -> [results...]

    for cap in CAP_VALUES:
        label = f"cap_{cap:.2f}"
        engine_mod.DISCUSSION_UPLIFT_CAP = cap
        print(f"\n{'=' * 60}")
        print(f"  CAP = {cap}")
        print(f"{'=' * 60}")

        replica_raw: list[list[dict]] = []

        for rep in range(NUM_REPLICAS):
            rep_results = []
            scenarios = make_scenarios()

            for i, (name, idea, config) in enumerate(scenarios, 1):
                print(f"\n  [rep{rep+1}] [{i}/{len(scenarios)}] {name}")

                collector = ScenarioMetrics(name=name, config_label=label)
                emit = collector.make_emit()

                start = time.time()
                try:
                    report = run_simulation(idea, config, emit=emit)
                    collector.final_report = report
                except Exception as e:
                    logger.error("FAILED: %s", e, exc_info=True)
                    print(f"    *** FAILED: {e}")
                    continue
                elapsed = time.time() - start
                collector.elapsed_seconds = elapsed

                result = _analyze(collector)
                print(f"    {elapsed:.0f}s | aware={result['aware']}/30 "
                      f"| recommend={result['recommend']} "
                      f"| spread={result['spread']} "
                      f"| hint={result['llm_hint_avg']:+.3f} "
                      f"| disc_pos={result['discussion_pos_deltas']}")
                rep_results.append(result)

            replica_raw.append(rep_results)

        # Aggregate across replicas
        aggregated = []
        for name in scenario_names:
            per_rep = []
            for rep_results in replica_raw:
                r = next((x for x in rep_results if x["name"] == name), None)
                if r:
                    per_rep.append(r)

            if not per_rep:
                continue

            awares = [r["aware"] for r in per_rep]
            recommends = [r["recommend"] for r in per_rep]
            hints = [r["llm_hint_avg"] for r in per_rep]
            spreads = [r["spread"] for r in per_rep]
            disc_pos = [r["discussion_pos_deltas"] for r in per_rep]
            disc_avg = [r["discussion_pos_avg"] for r in per_rep]

            aggregated.append({
                "name": name,
                "aware_avg": _avg(awares),
                "aware_sd": _sd(awares),
                "aware_values": awares,
                "recommend_avg": _avg(recommends),
                "recommend_sd": _sd(recommends),
                "spread_avg": _avg(spreads),
                "hint_avg": _avg(hints),
                "hint_sd": _sd(hints),
                "disc_pos_avg": _avg(disc_pos),
                "disc_delta_avg": _avg(disc_avg),
                "stances": per_rep[0]["stances"],  # last replica stances
                "trajectories": [r["trajectory"] for r in per_rep],
            })

        all_results[label] = aggregated

    # Generate report
    print("\n" + "=" * 70)
    print("Generating comparison report...")

    lines = [
        "# Cap Comparison: 0.30 vs 0.40",
        "",
        "Date: 2026-03-23",
        "Baseline: seed=8, threshold=0.68, prompt=reverted (no calibration guidance)",
        f"Replicas: {NUM_REPLICAS} per cell",
        "",
    ]

    # Summary table
    cap_labels = [f"cap_{c:.2f}" for c in CAP_VALUES]
    lines.append("## Summary")
    lines.append("")
    lines.append("| Scenario | Metric | cap=0.30 | cap=0.40 | Delta |")
    lines.append("|----------|--------|----------|----------|-------|")

    for name in scenario_names:
        r30 = next((x for x in all_results.get("cap_0.30", []) if x["name"] == name), None)
        r40 = next((x for x in all_results.get("cap_0.40", []) if x["name"] == name), None)
        if r30 and r40:
            # Awareness
            a30 = f"{r30['aware_avg']:.1f}+/-{r30['aware_sd']:.1f}"
            a40 = f"{r40['aware_avg']:.1f}+/-{r40['aware_sd']:.1f}"
            d_a = f"{r40['aware_avg'] - r30['aware_avg']:+.1f}"
            lines.append(f"| {name} | Awareness | {a30} | {a40} | {d_a} |")

            # Recommenders
            rec30 = f"{r30['recommend_avg']:.1f}"
            rec40 = f"{r40['recommend_avg']:.1f}"
            d_r = f"{r40['recommend_avg'] - r30['recommend_avg']:+.1f}"
            lines.append(f"| | Recommenders | {rec30} | {rec40} | {d_r} |")

            # Spread
            s30 = f"{r30['spread_avg']:.1f}"
            s40 = f"{r40['spread_avg']:.1f}"
            d_s = f"{r40['spread_avg'] - r30['spread_avg']:+.1f}"
            lines.append(f"| | Spread events | {s30} | {s40} | {d_s} |")

            # LLM hint
            h30 = f"{r30['hint_avg']:+.3f}"
            h40 = f"{r40['hint_avg']:+.3f}"
            lines.append(f"| | LLM hint avg | {h30} | {h40} | |")

            # Discussion positive deltas
            dp30 = f"{r30['disc_pos_avg']:.1f}"
            dp40 = f"{r40['disc_pos_avg']:.1f}"
            lines.append(f"| | Pos. disc. deltas | {dp30} | {dp40} | |")

            # Seed sensitivity
            cov30 = (r30['aware_sd'] / r30['aware_avg'] * 100) if r30['aware_avg'] > 0 else 0
            cov40 = (r40['aware_sd'] / r40['aware_avg'] * 100) if r40['aware_avg'] > 0 else 0
            lines.append(f"| | Seed sens (CoV%) | {cov30:.0f}% | {cov40:.0f}% | |")
            lines.append(f"| | | | | |")

    lines.append("")

    # Trajectories
    lines.append("## Awareness Trajectories")
    lines.append("")
    for name in scenario_names:
        lines.append(f"### {name}")
        for cl in cap_labels:
            r = next((x for x in all_results.get(cl, []) if x["name"] == name), None)
            if r:
                for i, traj in enumerate(r["trajectories"]):
                    lines.append(f"  {cl} rep{i+1}: {traj}")
        lines.append("")

    # Per-replica awareness
    lines.append("## Per-Replica Awareness")
    lines.append("")
    for name in scenario_names:
        lines.append(f"**{name}**:")
        for cl in cap_labels:
            r = next((x for x in all_results.get(cl, []) if x["name"] == name), None)
            if r:
                lines.append(f"  {cl}: {r['aware_values']}")
        lines.append("")

    # Verdict
    lines.append("## Verdict")
    lines.append("")
    lines.append("_(To be filled after analysis)_")
    lines.append("")

    report_text = "\n".join(lines)
    output_dir = PROJECT_ROOT / "process_doc"
    output_dir.mkdir(exist_ok=True)

    report_path = output_dir / "cap_comparison_results.md"
    report_path.write_text(report_text, encoding="utf-8")
    print(f"Report: {report_path}")

    raw_path = output_dir / "cap_comparison_raw.json"
    raw_path.write_text(
        json.dumps(all_results, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Raw data: {raw_path}")

    print("\n" + "=" * 70)
    print(report_text)


if __name__ == "__main__":
    main()
