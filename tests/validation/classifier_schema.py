"""Schema for labeled objection-theme validation corpus.

Each entry represents one LLM-generated objection from a simulation run,
paired with the auto-classifier's output and human-annotated ground truth.

The schema is designed for downstream simulation-validity scoring:
- harmful misclassification is defined in terms of resonance matrix impact,
  not generic classification error
- secondary themes are tracked because partial matches degrade less than
  full mismatches
- product_category is required because theme distributions should vary by
  product type (a health product should produce more 'evidence' objections
  than a social app)

Usage:
    # Validate a JSONL file
    cd idealab
    python -m tests.validation.classifier_schema data/corpus.jsonl

    # Load in scoring script
    from tests.validation.classifier_schema import load_corpus
    entries = load_corpus("path/to/corpus.jsonl")
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Valid values
# ---------------------------------------------------------------------------

VALID_THEMES: frozenset[str] = frozenset({
    "price", "complexity", "differentiation", "evidence",
    "legitimacy", "privacy", "social_proof", "ethics",
    "relevance", "general",
})

VALID_MATCH_TYPES: frozenset[str] = frozenset({
    "exact_match", "partial_match", "mismatch",
})

VALID_PRODUCTS: frozenset[str] = frozenset({
    # Extend as new products are tested
    "budget_meal_planner", "ai_vitamin_pack", "designer_network",
    "smart_energy_monitor", "fitness_tracker", "crypto_wallet",
    "meditation_app", "fast_fashion_marketplace", "code_review_tool",
    "organic_snack_box",
})


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class LabeledObjection:
    """One labeled objection for classifier validation.

    Fields:
        objection_id:        Sequential ID within the corpus.
        product:             Product name / slug from the simulation run.
        product_category:    IdeaLab category (health_wellness, saas, etc.).
        npc_archetype:       Archetype of the NPC that generated this objection.
        objection_text:      Full objection string from the LLM.
        auto_theme:          Theme returned by classify_objection_theme().
        human_primary:       Human-annotated primary theme.
        human_secondary:     Human-annotated secondary theme, or "none".
        match_type:          exact_match | partial_match | mismatch.
        confusion_note:      Annotator's note on why a mismatch occurred.
    """
    objection_id: int
    product: str
    product_category: str
    npc_archetype: str
    objection_text: str
    auto_theme: str
    human_primary: str
    human_secondary: str = "none"
    match_type: str = ""          # computed by scoring script if empty
    confusion_note: str = ""

    def __post_init__(self):
        errors: list[str] = []
        if self.auto_theme not in VALID_THEMES:
            errors.append(f"auto_theme '{self.auto_theme}' not in {VALID_THEMES}")
        if self.human_primary not in VALID_THEMES:
            errors.append(f"human_primary '{self.human_primary}' not in {VALID_THEMES}")
        if self.human_secondary != "none" and self.human_secondary not in VALID_THEMES:
            errors.append(f"human_secondary '{self.human_secondary}' not in {VALID_THEMES}")
        if self.match_type and self.match_type not in VALID_MATCH_TYPES:
            errors.append(f"match_type '{self.match_type}' not in {VALID_MATCH_TYPES}")
        if errors:
            raise ValueError(
                f"LabeledObjection #{self.objection_id} validation failed: "
                + "; ".join(errors)
            )

    def compute_match_type(self) -> str:
        """Derive match_type from auto_theme vs human labels."""
        if self.auto_theme == self.human_primary:
            return "exact_match"
        if self.human_secondary != "none" and self.auto_theme == self.human_secondary:
            return "partial_match"
        return "mismatch"

    def to_dict(self) -> dict:
        return {
            "objection_id": self.objection_id,
            "product": self.product,
            "product_category": self.product_category,
            "npc_archetype": self.npc_archetype,
            "objection_text": self.objection_text,
            "auto_theme": self.auto_theme,
            "human_primary": self.human_primary,
            "human_secondary": self.human_secondary,
            "match_type": self.match_type or self.compute_match_type(),
            "confusion_note": self.confusion_note,
        }


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def load_corpus(path: str | Path) -> list[LabeledObjection]:
    """Load a JSONL corpus file into validated LabeledObjection instances."""
    entries: list[LabeledObjection] = []
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                raw = json.loads(line)
                entry = LabeledObjection(**raw)
                entries.append(entry)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                print(f"  [ERROR] Line {line_num}: {exc}")
                continue
    return entries


def save_corpus(entries: list[LabeledObjection], path: str | Path) -> None:
    """Write LabeledObjection instances to a JSONL file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# CLI: validate a JSONL file
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m tests.validation.classifier_schema <path.jsonl>")
        return 1

    path = sys.argv[1]
    print(f"Validating {path}...")
    entries = load_corpus(path)
    print(f"  Loaded {len(entries)} valid entries")

    # Check theme distribution
    from collections import Counter
    primary_dist = Counter(e.human_primary for e in entries)
    auto_dist = Counter(e.auto_theme for e in entries)

    print(f"\n  Human primary theme distribution:")
    for theme, count in primary_dist.most_common():
        print(f"    {theme:20s} {count:4d} ({count/len(entries)*100:.1f}%)")

    print(f"\n  Auto-classified theme distribution:")
    for theme, count in auto_dist.most_common():
        print(f"    {theme:20s} {count:4d} ({count/len(entries)*100:.1f}%)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
