"""Extract objection-theme data from a simulation run into a JSONL corpus.

Runs a simulation against a product idea, captures every NPC objection and
its auto-classified theme, and writes a JSONL file ready for human annotation.

The output file has human_primary and human_secondary set to empty strings —
fill these in manually using the annotation guide before scoring.

Usage:
    cd idealab
    python -m tests.validation.extract_classifier_corpus \
        --product "AI Vitamin Pack" \
        --description "Monthly personalized vitamin subscription using AI health questionnaire, $89/mo" \
        --category health_wellness \
        --price "$89/month" \
        --alternatives "Care/of, Ritual, generic pharmacy vitamins" \
        --output tests/validation/data/vitamin_corpus.jsonl

    # Quick mode with defaults:
    python -m tests.validation.extract_classifier_corpus \
        --product "Budget Meal Planner" \
        --description "AI-powered weekly meal planning app for $5/month" \
        --category mobile_app
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.simulation.engine import create_world, _batch_react
from backend.simulation.npc import Npc
from backend.simulation.resonance import classify_objection_theme
from backend.simulation.world import InjectedIdea, SimConfig

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def extract_objections(
    idea: InjectedIdea,
    config: SimConfig,
) -> list[dict]:
    """Run a simulation through Phase 2 (reaction) and extract all objections.

    Returns a list of raw objection records with auto-classified themes.
    Only runs tick 1 (awareness + reaction) — no discussions or propagation
    needed for corpus extraction.
    """
    world = create_world(idea, config)

    # Phase 1: Make all NPCs aware
    tick = 1
    world.current_tick = tick
    for npc in world.npcs.values():
        if not npc.state.aware:
            npc.state.become_aware(tick, source="corpus_extraction")
        npc.state.increment_exposure()

    # Phase 2: Get LLM reactions (this generates objections)
    newly_aware = list(world.npcs.values())
    _batch_react(world, newly_aware, tick, emit=lambda e: None)

    # Extract objections
    records = []
    for npc in world.npcs.values():
        archetype = getattr(npc, "archetype", None) or "unknown"
        for objection_text in npc.state.objections:
            auto_theme = classify_objection_theme(objection_text)
            records.append({
                "npc_id": npc.id,
                "npc_name": npc.name,
                "npc_archetype": archetype,
                "objection_text": objection_text,
                "auto_theme": auto_theme,
                "interest_score": round(npc.state.interest_score, 3),
                "stance": npc.state.stance,
            })

    return records


def build_corpus_entries(
    records: list[dict],
    product: str,
    product_category: str,
    start_id: int = 1,
) -> list[dict]:
    """Convert raw objection records into LabeledObjection-compatible JSONL entries."""
    entries = []
    for i, rec in enumerate(records):
        entries.append({
            "objection_id": start_id + i,
            "product": product.lower().replace(" ", "_"),
            "product_category": product_category,
            "npc_archetype": rec["npc_archetype"],
            "objection_text": rec["objection_text"],
            "auto_theme": rec["auto_theme"],
            "human_primary": "",   # TO BE FILLED BY ANNOTATOR
            "human_secondary": "none",
            "match_type": "",
            "confusion_note": "",
        })
    return entries


def main():
    parser = argparse.ArgumentParser(
        description="Extract objection-theme corpus from a simulation run"
    )
    parser.add_argument("--product", required=True, help="Product name")
    parser.add_argument("--description", required=True, help="Product description")
    parser.add_argument("--category", required=True, help="IdeaLab category (health_wellness, saas, etc.)")
    parser.add_argument("--price", default="", help="Price point (e.g., '$89/month')")
    parser.add_argument("--alternatives", default="", help="Existing alternatives")
    parser.add_argument("--differentiator", default="", help="Key differentiator")
    parser.add_argument("--population", type=int, default=30, help="Population size (default: 30)")
    parser.add_argument("--seeds", type=int, default=30, help="Seed count — set equal to population for full coverage (default: 30)")
    parser.add_argument("--output", default="", help="Output JSONL path")
    parser.add_argument("--start-id", type=int, default=1, help="Starting objection_id (for appending to existing corpus)")
    args = parser.parse_args()

    idea = InjectedIdea(
        title=args.product,
        description=args.description,
        category=args.category,
        price_point=args.price,
        existing_alternatives=args.alternatives,
        differentiator=args.differentiator,
    )
    config = SimConfig(
        num_ticks=1,  # Only need tick 1 for reactions
        population_size=args.population,
        seed_count=args.seeds,
    )

    product_slug = args.product.lower().replace(" ", "_")
    output_path = args.output or f"tests/validation/data/{product_slug}_corpus.jsonl"

    print(f"Running simulation for: {args.product}")
    print(f"  Category: {args.category}")
    print(f"  Population: {args.population}")
    print(f"  Output: {output_path}")

    records = extract_objections(idea, config)
    print(f"  Extracted {len(records)} objections from {args.population} NPCs")

    # Print theme distribution
    from collections import Counter
    theme_dist = Counter(r["auto_theme"] for r in records)
    print(f"\n  Auto-classified theme distribution:")
    for theme, count in theme_dist.most_common():
        print(f"    {theme:20s} {count:3d} ({count/len(records)*100:.1f}%)")

    general_rate = theme_dist.get("general", 0) / len(records) if records else 0
    print(f"\n  General fallback rate: {general_rate:.1%}")

    # Write JSONL
    entries = build_corpus_entries(records, product_slug, args.category, start_id=args.start_id)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\n  Wrote {len(entries)} entries to {output_path}")
    print(f"  Next step: annotate human_primary and human_secondary using the annotation guide")
    print(f"  Then run: python -m tests.validation.score_classifier {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
