"""Focused validation: concern propagation structural fix.

Validates that the concern propagation redesign (removing the objections gate,
adding objection_bonus multiplier) actually produces concern events in scenarios
where NPCs should be skeptical.

Scenarios:
  - weak_vague_crypto: most NPCs should be low-interest → lots of concern sharing
  - premium_hardware: mixed — some NPCs concerned about price → moderate concern
  - strong_free_saas: most NPCs positive → minimal concern (control case)

Replicas: 2 per scenario (6 total LLM runs)

Usage:
    cd idealab
    python -m tests.test_concern_validation
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
# Event collector with concern tracking
# ---------------------------------------------------------------------------

@dataclass
class ConcernMetrics:
    name: str
    awareness_per_tick: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    concern_applied: list[dict] = field(default_factory=list)
    concern_stance_changes: list[dict] = field(default_factory=list)
    spread_events: list[dict] = field(default_factory=list)
    discussions: list[dict] = field(default_factory=list)
    reactions: list[dict] = field(default_factory=list)
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
            elif etype == "concern_applied":
                self.concern_applied.append({
                    "tick": tick,
                    "npc_id": data.get("npc_id"),
                    "name": data.get("name"),
                    "delta": data.get("delta"),
                    "old_interest": data.get("old_interest"),
                    "new_interest": data.get("new_interest"),
                })
            elif etype == "npc_state_change":
                reason = data.get("reason", "")
                if reason == "concern_influence":
                    self.concern_stance_changes.append({
                        "tick": tick,
                        "npc_id": data.get("npc_id"),
                        "new_stance": data.get("new_stance"),
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
# Scenarios
# ---------------------------------------------------------------------------

def make_scenarios() -> list[tuple[str, InjectedIdea, SimConfig]]:
    config = SimConfig(num_ticks=8, population_size=30, seed_count=8)
    return [
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
                    "Direct HVAC integration with auto-purification -- when PM2.5 spikes, it "
                    "triggers your HVAC system automatically"
                ),
                known_strengths="Patent-pending HVAC integration protocol",
                known_risks="High price point, requires professional installation",
            ),
            config,
        ),
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
                    "AI-driven pattern recognition -- learns when you're most productive "
                    "and proactively manages distractions without manual setup"
                ),
                known_strengths="Strong retention in beta (72% DAU/MAU), low churn",
                known_risks="Privacy concerns with monitoring work patterns",
            ),
            config,
        ),
    ]


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _analyze(collector: ConcernMetrics) -> dict:
    report = collector.final_report
    metrics = report.get("metrics", {})
    npc_results = report.get("npc_results", [])

    hints = [r["llm_hint"] for r in collector.reactions if r.get("llm_hint") is not None]

    stances = defaultdict(int)
    for n in npc_results:
        stances[n.get("stance", "unknown")] += 1

    trajectory = []
    for t in sorted(collector.awareness_per_tick.keys()):
        trajectory.append(collector.awareness_per_tick[t])

    # Concern analysis
    concern_per_tick = defaultdict(int)
    total_concern_delta = 0.0
    for c in collector.concern_applied:
        concern_per_tick[c["tick"]] += 1
        total_concern_delta += c["delta"]

    return {
        "name": collector.name,
        "aware": metrics.get("aware_count", 0),
        "recommend": sum(1 for n in npc_results if n.get("would_recommend")),
        "spread": len(collector.spread_events),
        "concern_events": len(collector.concern_applied),
        "concern_stance_changes": len(collector.concern_stance_changes),
        "concern_total_delta": round(total_concern_delta, 4),
        "concern_per_tick": dict(concern_per_tick),
        "concern_details": collector.concern_applied[:10],  # first 10 for inspection
        "llm_hint_avg": sum(hints) / len(hints) if hints else 0,
        "stances": dict(stances),
        "trajectory": trajectory,
    }


def _avg(values):
    return sum(values) / len(values) if values else 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    from backend.simulation.engine import run_simulation

    NUM_REPLICAS = 2
    scenarios_spec = make_scenarios()
    scenario_names = [s[0] for s in scenarios_spec]

    total = len(scenarios_spec) * NUM_REPLICAS
    print("=" * 70, flush=True)
    print("Concern Propagation Validation", flush=True)
    print(f"  Baseline: seed=8, threshold=0.68, cap=0.40", flush=True)
    print(f"  Scenarios: {scenario_names}", flush=True)
    print(f"  Replicas: {NUM_REPLICAS}", flush=True)
    print(f"  Total runs: {total}", flush=True)
    print("=" * 70, flush=True)

    all_results: list[list[dict]] = []  # per-replica results

    for rep in range(NUM_REPLICAS):
        rep_results = []
        scenarios = make_scenarios()

        for i, (name, idea, config) in enumerate(scenarios, 1):
            print(f"\n  [rep{rep+1}] [{i}/{len(scenarios)}] {name}", flush=True)

            collector = ConcernMetrics(name=name)
            emit = collector.make_emit()

            start = time.time()
            try:
                report = run_simulation(idea, config, emit=emit)
                collector.final_report = report
            except Exception as e:
                logger.error("FAILED: %s", e, exc_info=True)
                print(f"    *** FAILED: {e}", flush=True)
                continue
            elapsed = time.time() - start
            collector.elapsed_seconds = elapsed

            result = _analyze(collector)
            print(
                f"    {elapsed:.0f}s | aware={result['aware']}/30 "
                f"| recommend={result['recommend']} "
                f"| concern_events={result['concern_events']} "
                f"| concern_stance_changes={result['concern_stance_changes']} "
                f"| concern_delta={result['concern_total_delta']:+.4f}",
                flush=True,
            )

            # Print per-tick concern breakdown
            if result["concern_per_tick"]:
                tick_str = ", ".join(
                    f"t{t}:{c}" for t, c in sorted(result["concern_per_tick"].items())
                )
                print(f"    Concern per tick: {tick_str}", flush=True)
            else:
                print(f"    Concern per tick: (none)", flush=True)

            rep_results.append(result)

        all_results.append(rep_results)

    # Aggregate and report
    print("\n" + "=" * 70, flush=True)
    print("CONCERN PROPAGATION VALIDATION RESULTS", flush=True)
    print("=" * 70, flush=True)

    lines = [
        "# Concern Propagation Validation",
        "",
        "Date: 2026-03-23",
        "Baseline: seed=8, threshold=0.68, cap=0.40, prompt=reverted",
        f"Replicas: {NUM_REPLICAS} per scenario",
        "",
        "## Summary",
        "",
        "| Scenario | Concern Events | Stance Changes | Total Delta | Awareness | Recommenders |",
        "|----------|---------------|----------------|-------------|-----------|--------------|",
    ]

    for name in scenario_names:
        per_rep = []
        for rep_results in all_results:
            r = next((x for x in rep_results if x["name"] == name), None)
            if r:
                per_rep.append(r)

        if not per_rep:
            continue

        avg_concern = _avg([r["concern_events"] for r in per_rep])
        avg_stance = _avg([r["concern_stance_changes"] for r in per_rep])
        avg_delta = _avg([r["concern_total_delta"] for r in per_rep])
        avg_aware = _avg([r["aware"] for r in per_rep])
        avg_rec = _avg([r["recommend"] for r in per_rep])

        values_concern = [r["concern_events"] for r in per_rep]
        values_stance = [r["concern_stance_changes"] for r in per_rep]
        values_delta = [r["concern_total_delta"] for r in per_rep]
        values_aware = [r["aware"] for r in per_rep]
        values_rec = [r["recommend"] for r in per_rep]

        lines.append(
            f"| {name} | {avg_concern:.1f} ({values_concern}) | "
            f"{avg_stance:.1f} ({values_stance}) | "
            f"{avg_delta:+.4f} ({[round(d,4) for d in values_delta]}) | "
            f"{avg_aware:.1f} ({values_aware}) | "
            f"{avg_rec:.1f} ({values_rec}) |"
        )

    lines.append("")

    # Per-tick detail
    lines.append("## Per-Tick Concern Events")
    lines.append("")
    for name in scenario_names:
        lines.append(f"### {name}")
        for rep_idx, rep_results in enumerate(all_results):
            r = next((x for x in rep_results if x["name"] == name), None)
            if r:
                tick_str = ", ".join(
                    f"t{t}: {c}" for t, c in sorted(r["concern_per_tick"].items())
                ) if r["concern_per_tick"] else "(none)"
                lines.append(f"  rep{rep_idx+1}: {tick_str}")
        lines.append("")

    # Stance distribution
    lines.append("## Stance Distribution")
    lines.append("")
    for name in scenario_names:
        lines.append(f"### {name}")
        for rep_idx, rep_results in enumerate(all_results):
            r = next((x for x in rep_results if x["name"] == name), None)
            if r:
                lines.append(f"  rep{rep_idx+1}: {r['stances']}")
        lines.append("")

    # Sample concern events
    lines.append("## Sample Concern Events (first 10 per run)")
    lines.append("")
    for name in scenario_names:
        lines.append(f"### {name}")
        for rep_idx, rep_results in enumerate(all_results):
            r = next((x for x in rep_results if x["name"] == name), None)
            if r and r.get("concern_details"):
                lines.append(f"  rep{rep_idx+1}:")
                for c in r["concern_details"]:
                    lines.append(
                        f"    tick {c['tick']}: {c.get('name','?')} "
                        f"delta={c['delta']:+.4f} "
                        f"({c['old_interest']:.3f} -> {c['new_interest']:.3f})"
                    )
            else:
                lines.append(f"  rep{rep_idx+1}: (no concern events)")
        lines.append("")

    # Verdict
    lines.append("## Verdict")
    lines.append("")

    # Auto-generate verdict
    crypto_concerns = []
    saas_concerns = []
    hw_concerns = []
    for rep_results in all_results:
        for r in rep_results:
            if r["name"] == "weak_vague_crypto":
                crypto_concerns.append(r["concern_events"])
            elif r["name"] == "strong_free_saas":
                saas_concerns.append(r["concern_events"])
            elif r["name"] == "premium_hardware":
                hw_concerns.append(r["concern_events"])

    crypto_avg = _avg(crypto_concerns) if crypto_concerns else 0
    saas_avg = _avg(saas_concerns) if saas_concerns else 0
    hw_avg = _avg(hw_concerns) if hw_concerns else 0

    if crypto_avg > 0:
        lines.append(f"PASS: Concern propagation is firing. Crypto avg={crypto_avg:.1f} events.")
    else:
        lines.append(f"FAIL: Concern propagation still not firing for crypto (0 events).")

    if crypto_avg > saas_avg:
        lines.append(f"PASS: Weak products generate more concern ({crypto_avg:.1f}) than strong products ({saas_avg:.1f}).")
    else:
        lines.append(f"WARNING: Weak product concern ({crypto_avg:.1f}) not higher than strong product ({saas_avg:.1f}).")

    if hw_avg >= saas_avg:
        lines.append(f"PASS: Premium hardware ({hw_avg:.1f}) generates >= concern than free SaaS ({saas_avg:.1f}).")
    else:
        lines.append(f"INFO: Hardware concern ({hw_avg:.1f}) < SaaS concern ({saas_avg:.1f}). May be OK depending on interest distribution.")

    lines.append("")

    report_text = "\n".join(lines)
    output_dir = PROJECT_ROOT / "process_doc"
    output_dir.mkdir(exist_ok=True)

    report_path = output_dir / "concern_validation_results.md"
    report_path.write_text(report_text, encoding="utf-8")

    raw_path = output_dir / "concern_validation_raw.json"
    raw_data = {}
    for rep_idx, rep_results in enumerate(all_results):
        for r in rep_results:
            key = f"{r['name']}_rep{rep_idx+1}"
            raw_data[key] = r
    raw_path.write_text(
        json.dumps(raw_data, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nReport: {report_path}", flush=True)
    print(f"Raw data: {raw_path}", flush=True)
    print("\n" + report_text, flush=True)


if __name__ == "__main__":
    main()
