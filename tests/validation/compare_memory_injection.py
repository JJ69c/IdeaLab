"""A/B comparison: simulation quality with vs without prompt memory injection.

Runs the same product idea twice:
  A) With memory injection (current code) — NPCs carry peer warnings and
     discussion history into discussion prompts
  B) Without memory injection — empty memory strings (simulates pre-Phase-2)

Compares:
  1. Discussion content quality — do discussions reference specific concerns?
  2. Interest trajectory differences — do NPCs shift differently?
  3. Convergence — does the outcome class differ?
  4. Objection theme diversity — does memory produce richer theme spread?

Usage:
    cd idealab
    python -m tests.validation.compare_memory_injection
"""

from __future__ import annotations

import json
import logging
import re
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.simulation.engine import run_simulation
from backend.simulation.world import InjectedIdea, SimConfig


def run_with_memory(idea: InjectedIdea, config: SimConfig) -> tuple[dict, list]:
    """Run simulation with memory injection enabled (default behavior)."""
    events: list[dict] = []
    result = run_simulation(idea, config, emit=lambda e: events.append(e))
    return result, events


def run_without_memory(idea: InjectedIdea, config: SimConfig) -> tuple[dict, list]:
    """Run simulation with memory injection disabled (empty strings)."""
    from backend.llm import prompts

    original_fn = prompts.format_social_memory

    def no_memory(*args, **kwargs):
        return ""

    events: list[dict] = []
    with patch.object(prompts, "format_social_memory", no_memory):
        result = run_simulation(idea, config, emit=lambda e: events.append(e))
    return result, events


def extract_metrics(events: list[dict]) -> dict:
    """Extract comparison metrics from event stream."""
    discussions = [e for e in events if e["type"] == "discussion_end"]
    concerns = [e for e in events if e["type"] == "concern_applied"]
    reactions = [e for e in events if e["type"] == "npc_reaction"]
    state_changes = [e for e in events if e["type"] == "npc_state_change"]

    # Discussion analysis
    all_exchanges = []
    key_points = []
    for d in discussions:
        data = d["data"]
        for ex in data.get("exchanges", []):
            all_exchanges.append(ex.get("message", ""))
        key_points.append(data.get("key_point", ""))

    # Count theme-related words in discussions (evidence of memory influencing content)
    theme_words = {
        "price": ["price", "cost", "expensive", "afford", "dollar", "subscription", "pay"],
        "evidence": ["evidence", "proof", "study", "clinical", "data", "proven", "research"],
        "complexity": ["complex", "difficult", "friction", "setup", "hassle", "learning"],
        "social_proof": ["everyone", "nobody", "peers", "mainstream", "popular", "adoption"],
        "ethics": ["ethical", "sustainability", "environmental", "greenwashing"],
        "privacy": ["privacy", "data collection", "surveillance", "personal data"],
    }

    theme_mentions: dict[str, int] = {}
    all_text = " ".join(all_exchanges).lower()
    for theme, words in theme_words.items():
        count = sum(1 for w in words if w in all_text)
        if count > 0:
            theme_mentions[theme] = count

    # Concern propagation
    total_concern_sources = sum(
        len(c["data"].get("sources", [])) for c in concerns
    )

    # Interest trajectories
    final_interests = []
    for r in reactions:
        final_interests.append(r["data"].get("interest_score", 0.5))

    # Stance distribution from final state changes
    final_stances: dict[str, int] = Counter()
    npc_final: dict[str, str] = {}
    for sc in state_changes:
        npc_id = sc["data"]["npc_id"]
        stance = sc["data"]["new_stance"]
        npc_final[npc_id] = stance
    for stance in npc_final.values():
        final_stances[stance] += 1

    return {
        "num_discussions": len(discussions),
        "num_exchanges": len(all_exchanges),
        "num_concerns": len(concerns),
        "num_concern_sources": total_concern_sources,
        "theme_mentions_in_discussions": theme_mentions,
        "total_theme_mentions": sum(theme_mentions.values()),
        "avg_exchange_length": (
            sum(len(ex) for ex in all_exchanges) / len(all_exchanges)
            if all_exchanges else 0
        ),
        "num_key_points": len([kp for kp in key_points if kp]),
        "mean_interest": (
            sum(final_interests) / len(final_interests) if final_interests else 0
        ),
        "stance_distribution": dict(final_stances),
    }


def print_comparison(name: str, with_mem: dict, without_mem: dict):
    """Print side-by-side comparison."""
    print(f"\n{'=' * 70}")
    print(f"  {name}")
    print(f"{'=' * 70}")

    rows = [
        ("Discussions", with_mem["num_discussions"], without_mem["num_discussions"]),
        ("Total exchanges", with_mem["num_exchanges"], without_mem["num_exchanges"]),
        ("Avg exchange length (chars)", f"{with_mem['avg_exchange_length']:.0f}", f"{without_mem['avg_exchange_length']:.0f}"),
        ("Concern events", with_mem["num_concerns"], without_mem["num_concerns"]),
        ("Concern sources", with_mem["num_concern_sources"], without_mem["num_concern_sources"]),
        ("Theme mentions in discussions", with_mem["total_theme_mentions"], without_mem["total_theme_mentions"]),
        ("Mean interest (post-reaction)", f"{with_mem['mean_interest']:.3f}", f"{without_mem['mean_interest']:.3f}"),
    ]

    print(f"\n  {'Metric':<35s} {'With Memory':>15s} {'Without Memory':>15s}")
    print(f"  {'-' * 65}")
    for label, a, b in rows:
        print(f"  {label:<35s} {str(a):>15s} {str(b):>15s}")

    # Theme breakdown
    print(f"\n  Theme mentions in discussion text:")
    all_themes = set(with_mem["theme_mentions_in_discussions"]) | set(without_mem["theme_mentions_in_discussions"])
    for theme in sorted(all_themes):
        a = with_mem["theme_mentions_in_discussions"].get(theme, 0)
        b = without_mem["theme_mentions_in_discussions"].get(theme, 0)
        delta = a - b
        marker = " +" if delta > 0 else " " if delta == 0 else " "
        print(f"    {theme:<20s} {a:>5d}  vs  {b:>5d}  ({marker}{delta})")

    # Stance distribution
    print(f"\n  Final stance distribution:")
    all_stances = set(with_mem["stance_distribution"]) | set(without_mem["stance_distribution"])
    for stance in sorted(all_stances):
        a = with_mem["stance_distribution"].get(stance, 0)
        b = without_mem["stance_distribution"].get(stance, 0)
        print(f"    {stance:<20s} {a:>5d}  vs  {b:>5d}")


def main():
    products = [
        InjectedIdea(
            title="AI Vitamin Pack",
            description="Monthly personalized vitamin subscription using AI health questionnaire, $89/mo",
            category="health_wellness",
            price_point="$89/month",
            existing_alternatives="Care/of, Ritual, generic pharmacy vitamins",
        ),
        InjectedIdea(
            title="Budget Meal Planner",
            description="AI-powered weekly meal planning app that optimizes for nutrition and budget, $5/month",
            category="mobile_app",
            price_point="$5/month",
            existing_alternatives="MyFitnessPal, Mealime, spreadsheets",
        ),
        InjectedIdea(
            title="DesignHive",
            description="Professional networking platform for UI/UX designers with AI-powered mentorship matching",
            category="social_platform",
            price_point="Free tier + $12/month premium",
            existing_alternatives="LinkedIn, Dribbble, Behance",
        ),
    ]

    config = SimConfig(num_ticks=4, population_size=15, seed_count=8)

    all_with = {}
    all_without = {}

    for idea in products:
        slug = idea.title.lower().replace(" ", "_")
        print(f"\n--- Running: {idea.title} ---")

        print(f"  With memory injection...")
        _, events_with = run_with_memory(idea, config)
        metrics_with = extract_metrics(events_with)
        all_with[slug] = metrics_with

        print(f"  Without memory injection...")
        _, events_without = run_without_memory(idea, config)
        metrics_without = extract_metrics(events_without)
        all_without[slug] = metrics_without

        print_comparison(idea.title, metrics_with, metrics_without)

    # Overall summary
    print(f"\n{'=' * 70}")
    print(f"  OVERALL SUMMARY")
    print(f"{'=' * 70}")

    total_themes_with = sum(m["total_theme_mentions"] for m in all_with.values())
    total_themes_without = sum(m["total_theme_mentions"] for m in all_without.values())
    total_discussions_with = sum(m["num_discussions"] for m in all_with.values())
    total_discussions_without = sum(m["num_discussions"] for m in all_without.values())

    print(f"\n  Total theme mentions:   {total_themes_with} (with) vs {total_themes_without} (without)")
    print(f"  Total discussions:      {total_discussions_with} (with) vs {total_discussions_without} (without)")

    if total_themes_with > total_themes_without:
        pct = ((total_themes_with - total_themes_without) / max(total_themes_without, 1)) * 100
        print(f"\n  Memory injection increased theme-specific discussion content by {pct:.0f}%")
    elif total_themes_with < total_themes_without:
        print(f"\n  Memory injection did NOT increase theme mentions (unexpected)")
    else:
        print(f"\n  No difference in theme mentions")

    # Save raw data
    output = {
        "config": {"num_ticks": config.num_ticks, "population_size": config.population_size},
        "with_memory": {k: v for k, v in all_with.items()},
        "without_memory": {k: v for k, v in all_without.items()},
    }
    out_path = Path("tests/validation/data/memory_injection_comparison.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Raw data saved to {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
