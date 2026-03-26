"""Scoring script for objection-theme classifier validation.

Computes simulation-aware metrics: harmful misclassification is defined by
resonance matrix impact, not generic classification error. A mismatch that
swaps two themes with similar resonance across all archetypes is cosmetic.
A mismatch that swaps themes with >1.5x resonance difference for ANY
archetype corrupts simulation outcomes.

Usage:
    cd idealab
    python -m tests.validation.score_classifier tests/validation/data/classifier_corpus.jsonl

    # With auto-reclassification (re-runs classifier on objection_text):
    python -m tests.validation.score_classifier corpus.jsonl --reclassify

Output:
    Prints scored report to stdout.
    Writes JSON report to tests/validation/data/classifier_report.json.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.simulation.evaluation import reload_evaluations
from backend.simulation.resonance import (
    ARCHETYPES,
    build_resonance_matrix,
    classify_objection_theme,
    get_resonance,
)
from tests.validation.classifier_schema import LabeledObjection, load_corpus

# Force evaluation cache load
reload_evaluations()

# ---------------------------------------------------------------------------
# Harmful misclassification threshold
# ---------------------------------------------------------------------------
# A misclassification is "harmful" if, for ANY archetype, the resonance
# ratio between the correct theme and the classified theme exceeds this.
# At 1.5x, swapping price (1.70) for complexity (1.20) on price_pragmatist
# yields ratio 1.42 — borderline. Swapping ethics (1.80) for ethics (0.50)
# on values_buyer vs trend_adopter is clearly harmful.

HARMFUL_RATIO_THRESHOLD: float = 1.5


# ---------------------------------------------------------------------------
# Core metric computations
# ---------------------------------------------------------------------------

@dataclass
class ThemeMetrics:
    """Per-theme precision/recall/f1 and harmful error count."""
    theme: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    harmful_as_fp: int = 0  # FP where the swap is harmful
    harmful_as_fn: int = 0  # FN where the swap is harmful

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    @property
    def support(self) -> int:
        return self.true_positives + self.false_negatives

    def to_dict(self) -> dict:
        return {
            "theme": self.theme,
            "precision": round(self.precision, 3),
            "recall": round(self.recall, 3),
            "f1": round(self.f1, 3),
            "support": self.support,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "harmful_as_fp": self.harmful_as_fp,
            "harmful_as_fn": self.harmful_as_fn,
        }


def compute_max_resonance_ratio(theme_a: str, theme_b: str) -> float:
    """Max resonance ratio between two themes across all archetypes.

    Returns the worst-case ratio: max over all archetypes of
    max(r_a/r_b, r_b/r_a). A ratio of 1.0 means the swap is invisible
    to the simulation. Higher = more damaging.
    """
    if theme_a == theme_b:
        return 1.0

    max_ratio = 1.0
    for arch_id in ARCHETYPES:
        r_a = get_resonance(arch_id, theme_a)
        r_b = get_resonance(arch_id, theme_b)
        if r_a > 0 and r_b > 0:
            ratio = max(r_a / r_b, r_b / r_a)
            max_ratio = max(max_ratio, ratio)
    return round(max_ratio, 3)


def is_harmful_swap(classified_theme: str, correct_theme: str) -> bool:
    """Whether swapping these two themes corrupts simulation outcomes."""
    if classified_theme == correct_theme:
        return False
    return compute_max_resonance_ratio(classified_theme, correct_theme) > HARMFUL_RATIO_THRESHOLD


def compute_exact_accuracy(entries: list[LabeledObjection]) -> float:
    """Fraction where auto_theme == human_primary."""
    if not entries:
        return 0.0
    exact = sum(1 for e in entries if e.auto_theme == e.human_primary)
    return round(exact / len(entries), 4)


def compute_primary_secondary_match_rate(entries: list[LabeledObjection]) -> float:
    """Fraction where auto_theme matches primary OR secondary."""
    if not entries:
        return 0.0
    matches = sum(
        1 for e in entries
        if e.auto_theme == e.human_primary
        or (e.human_secondary != "none" and e.auto_theme == e.human_secondary)
    )
    return round(matches / len(entries), 4)


def compute_harmful_misclassification_rate(entries: list[LabeledObjection]) -> float:
    """Fraction of ALL entries where the misclassification is harmful.

    An entry counts as harmful if:
    1. auto_theme != human_primary (it's a mismatch)
    2. The resonance ratio between auto_theme and human_primary exceeds
       HARMFUL_RATIO_THRESHOLD for at least one archetype

    This is the metric that matters most for simulation validity.
    """
    if not entries:
        return 0.0
    harmful = sum(
        1 for e in entries
        if e.auto_theme != e.human_primary
        and is_harmful_swap(e.auto_theme, e.human_primary)
    )
    return round(harmful / len(entries), 4)


def compute_general_fallback_rate(entries: list[LabeledObjection]) -> float:
    """Fraction of entries where auto-classifier returned 'general'."""
    if not entries:
        return 0.0
    general = sum(1 for e in entries if e.auto_theme == "general")
    return round(general / len(entries), 4)


def compute_per_theme_metrics(entries: list[LabeledObjection]) -> dict[str, ThemeMetrics]:
    """Per-theme precision, recall, F1, and harmful error counts."""
    metrics: dict[str, ThemeMetrics] = {}
    all_themes = set(e.human_primary for e in entries) | set(e.auto_theme for e in entries)

    for theme in sorted(all_themes):
        metrics[theme] = ThemeMetrics(theme=theme)

    for e in entries:
        predicted = e.auto_theme
        actual = e.human_primary

        if predicted == actual:
            metrics[actual].true_positives += 1
        else:
            # False negative for actual theme (should have been predicted)
            metrics[actual].false_negatives += 1
            if is_harmful_swap(predicted, actual):
                metrics[actual].harmful_as_fn += 1

            # False positive for predicted theme (shouldn't have been predicted)
            if predicted in metrics:
                metrics[predicted].false_positives += 1
                if is_harmful_swap(predicted, actual):
                    metrics[predicted].harmful_as_fp += 1

    return metrics


def build_confusion_matrix(
    entries: list[LabeledObjection],
) -> dict[str, dict[str, int]]:
    """Row = human_primary (actual), Column = auto_theme (predicted).

    Returns: {actual_theme: {predicted_theme: count}}
    """
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for e in entries:
        matrix[e.human_primary][e.auto_theme] += 1
    return {k: dict(v) for k, v in matrix.items()}


def compute_theme_distribution_by_product(
    entries: list[LabeledObjection],
) -> dict[str, dict[str, int]]:
    """Theme distribution per product. Used to verify products produce
    different theme profiles (a health product should NOT look like a social app).
    """
    dist: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for e in entries:
        dist[e.product][e.human_primary] += 1
    return {k: dict(v) for k, v in dist.items()}


# ---------------------------------------------------------------------------
# Resonance impact analysis
# ---------------------------------------------------------------------------

def compute_swap_severity_table() -> list[dict]:
    """Pre-compute resonance ratios for all theme pairs.

    Returns sorted list of (theme_a, theme_b, max_ratio, worst_archetype, harmful).
    Useful for understanding which misclassifications matter.
    """
    from backend.simulation.resonance import OBJECTION_THEMES

    all_themes = list(OBJECTION_THEMES.keys()) + ["general"]
    pairs: list[dict] = []
    seen: set[frozenset] = set()

    for a in all_themes:
        for b in all_themes:
            if a == b:
                continue
            key = frozenset({a, b})
            if key in seen:
                continue
            seen.add(key)

            max_ratio = 1.0
            worst_arch = ""
            for arch_id in ARCHETYPES:
                r_a = get_resonance(arch_id, a)
                r_b = get_resonance(arch_id, b)
                if r_a > 0 and r_b > 0:
                    ratio = max(r_a / r_b, r_b / r_a)
                    if ratio > max_ratio:
                        max_ratio = ratio
                        worst_arch = arch_id

            pairs.append({
                "theme_a": a,
                "theme_b": b,
                "max_ratio": round(max_ratio, 3),
                "worst_archetype": worst_arch,
                "harmful": max_ratio > HARMFUL_RATIO_THRESHOLD,
            })

    pairs.sort(key=lambda x: x["max_ratio"], reverse=True)
    return pairs


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

@dataclass
class ClassifierReport:
    """Full scoring report for the classifier validation corpus."""
    corpus_size: int
    exact_accuracy: float
    primary_secondary_match_rate: float
    harmful_misclassification_rate: float
    general_fallback_rate: float
    per_theme: dict[str, dict]
    confusion_matrix: dict[str, dict[str, int]]
    theme_distribution_by_product: dict[str, dict[str, int]]
    top_harmful_swaps: list[dict]
    mismatch_details: list[dict]
    pass_fail: dict[str, dict]

    def to_dict(self) -> dict:
        return {
            "corpus_size": self.corpus_size,
            "exact_accuracy": self.exact_accuracy,
            "primary_secondary_match_rate": self.primary_secondary_match_rate,
            "harmful_misclassification_rate": self.harmful_misclassification_rate,
            "general_fallback_rate": self.general_fallback_rate,
            "per_theme": self.per_theme,
            "confusion_matrix": self.confusion_matrix,
            "theme_distribution_by_product": self.theme_distribution_by_product,
            "top_harmful_swaps": self.top_harmful_swaps,
            "mismatch_details": self.mismatch_details,
            "pass_fail": self.pass_fail,
        }


# Pass/fail thresholds — these match the exit criteria in next_step_decision.md
THRESHOLDS = {
    "exact_accuracy":                {"min": 0.75, "label": "Exact accuracy >= 75%"},
    "harmful_misclassification_rate": {"max": 0.10, "label": "Harmful misclassification <= 10%"},
    "general_fallback_rate":          {"max": 0.25, "label": "General fallback <= 25%"},
}


def evaluate_pass_fail(report: ClassifierReport) -> dict[str, dict]:
    """Evaluate each threshold and return pass/fail status."""
    results = {}
    for metric_name, threshold in THRESHOLDS.items():
        value = getattr(report, metric_name)
        if "min" in threshold:
            passed = value >= threshold["min"]
            results[metric_name] = {
                "value": value,
                "threshold": f">= {threshold['min']}",
                "passed": passed,
                "label": threshold["label"],
            }
        elif "max" in threshold:
            passed = value <= threshold["max"]
            results[metric_name] = {
                "value": value,
                "threshold": f"<= {threshold['max']}",
                "passed": passed,
                "label": threshold["label"],
            }
    return results


def generate_report(entries: list[LabeledObjection]) -> ClassifierReport:
    """Generate the full scoring report from a labeled corpus."""
    exact_acc = compute_exact_accuracy(entries)
    ps_match = compute_primary_secondary_match_rate(entries)
    harmful_rate = compute_harmful_misclassification_rate(entries)
    general_rate = compute_general_fallback_rate(entries)
    per_theme = compute_per_theme_metrics(entries)
    confusion = build_confusion_matrix(entries)
    dist_by_product = compute_theme_distribution_by_product(entries)
    swap_table = compute_swap_severity_table()

    # Collect mismatch details for review
    mismatches = []
    for e in entries:
        if e.auto_theme != e.human_primary:
            harmful = is_harmful_swap(e.auto_theme, e.human_primary)
            ratio = compute_max_resonance_ratio(e.auto_theme, e.human_primary)
            mismatches.append({
                "objection_id": e.objection_id,
                "text": e.objection_text[:100],
                "auto": e.auto_theme,
                "human_primary": e.human_primary,
                "human_secondary": e.human_secondary,
                "harmful": harmful,
                "resonance_ratio": ratio,
                "confusion_note": e.confusion_note,
            })

    # Sort mismatches: harmful first, then by ratio descending
    mismatches.sort(key=lambda x: (-x["harmful"], -x["resonance_ratio"]))

    report = ClassifierReport(
        corpus_size=len(entries),
        exact_accuracy=exact_acc,
        primary_secondary_match_rate=ps_match,
        harmful_misclassification_rate=harmful_rate,
        general_fallback_rate=general_rate,
        per_theme={k: v.to_dict() for k, v in per_theme.items()},
        confusion_matrix=confusion,
        theme_distribution_by_product=dist_by_product,
        top_harmful_swaps=[s for s in swap_table if s["harmful"]][:15],
        mismatch_details=mismatches,
        pass_fail={},
    )
    report.pass_fail = evaluate_pass_fail(report)
    return report


# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------

def print_report(report: ClassifierReport) -> None:
    """Print scored report to stdout."""
    print("=" * 74)
    print("  CLASSIFIER VALIDATION REPORT")
    print("=" * 74)

    # --- Summary ---
    print(f"\n  Corpus size:                   {report.corpus_size}")
    print(f"  Exact accuracy:                {report.exact_accuracy:.1%}")
    print(f"  Primary+secondary match rate:  {report.primary_secondary_match_rate:.1%}")
    print(f"  Harmful misclassification:     {report.harmful_misclassification_rate:.1%}")
    print(f"  General fallback rate:         {report.general_fallback_rate:.1%}")

    # --- Pass/Fail ---
    print(f"\n{'  PASS/FAIL GATES':=<74}")
    all_pass = True
    for metric_name, result in report.pass_fail.items():
        status = "PASS" if result["passed"] else "FAIL"
        if not result["passed"]:
            all_pass = False
        print(f"  [{status}] {result['label']:45s} "
              f"actual={result['value']:.1%}  threshold={result['threshold']}")

    verdict = "ALL GATES PASSED — safe to proceed" if all_pass else "GATES FAILED — fix classifier before proceeding"
    print(f"\n  VERDICT: {verdict}")

    # --- Per-theme metrics ---
    print(f"\n{'  PER-THEME METRICS':=<74}")
    header = f"  {'Theme':20s} {'Prec':>6s} {'Recall':>7s} {'F1':>6s} {'Support':>8s} {'Harm FP':>8s} {'Harm FN':>8s}"
    print(header)
    print("  " + "-" * 65)
    for theme_name in sorted(report.per_theme.keys()):
        m = report.per_theme[theme_name]
        print(f"  {m['theme']:20s} {m['precision']:6.3f} {m['recall']:7.3f} "
              f"{m['f1']:6.3f} {m['support']:8d} {m['harmful_as_fp']:8d} {m['harmful_as_fn']:8d}")

    # --- Confusion matrix ---
    print(f"\n{'  CONFUSION MATRIX (rows=actual, cols=predicted)':=<74}")
    all_themes = sorted(set(
        list(report.confusion_matrix.keys())
        + [t for row in report.confusion_matrix.values() for t in row]
    ))

    # Header row
    header = f"  {'':14s}"
    for t in all_themes:
        header += f" {t[:5]:>5s}"
    print(header)
    print("  " + "-" * (14 + 6 * len(all_themes)))

    for actual in all_themes:
        row = report.confusion_matrix.get(actual, {})
        line = f"  {actual[:13]:14s}"
        for predicted in all_themes:
            count = row.get(predicted, 0)
            cell = f"{count:5d}" if count > 0 else "    ."
            line += f" {cell}"
        print(line)

    # --- Theme distribution by product ---
    print(f"\n{'  THEME DISTRIBUTION BY PRODUCT':=<74}")
    for product, dist in sorted(report.theme_distribution_by_product.items()):
        total = sum(dist.values())
        print(f"\n  {product} (n={total}):")
        for theme, count in sorted(dist.items(), key=lambda x: -x[1]):
            bar = "#" * int(count / total * 30)
            print(f"    {theme:20s} {count:3d} ({count/total*100:5.1f}%) {bar}")

    # --- Top harmful swap pairs (from resonance matrix) ---
    if report.top_harmful_swaps:
        print(f"\n{'  TOP HARMFUL THEME SWAPS (resonance ratio > 1.5x)':=<74}")
        print(f"  {'Theme A':18s} {'Theme B':18s} {'Max ratio':>10s} {'Worst archetype':>20s}")
        print("  " + "-" * 68)
        for s in report.top_harmful_swaps[:10]:
            print(f"  {s['theme_a']:18s} {s['theme_b']:18s} "
                  f"{s['max_ratio']:10.2f}x {s['worst_archetype']:>20s}")

    # --- Mismatch details ---
    mismatches = report.mismatch_details
    if mismatches:
        harmful_count = sum(1 for m in mismatches if m["harmful"])
        cosmetic_count = len(mismatches) - harmful_count
        print(f"\n{'  MISMATCHES':=<74}")
        print(f"  Total: {len(mismatches)}  (harmful: {harmful_count}, cosmetic: {cosmetic_count})")

        print(f"\n  HARMFUL mismatches:")
        for m in mismatches:
            if not m["harmful"]:
                continue
            print(f"    #{m['objection_id']:03d} auto={m['auto']:15s} actual={m['human_primary']:15s} "
                  f"ratio={m['resonance_ratio']:.2f}x")
            print(f"         \"{m['text']}\"")
            if m["confusion_note"]:
                print(f"         note: {m['confusion_note']}")

        if cosmetic_count > 0:
            print(f"\n  COSMETIC mismatches (ratio <= {HARMFUL_RATIO_THRESHOLD}x):")
            for m in mismatches:
                if m["harmful"]:
                    continue
                print(f"    #{m['objection_id']:03d} auto={m['auto']:15s} actual={m['human_primary']:15s} "
                      f"ratio={m['resonance_ratio']:.2f}x")

    print("\n" + "=" * 74)


# ---------------------------------------------------------------------------
# Reclassify mode: re-run the classifier on objection_text
# ---------------------------------------------------------------------------

def reclassify_corpus(entries: list[LabeledObjection]) -> list[LabeledObjection]:
    """Re-run classify_objection_theme() on each entry and update auto_theme.

    Returns new LabeledObjection instances with updated auto_theme.
    Useful when the classifier has been modified and you want to re-score.
    """
    updated = []
    for e in entries:
        new_auto = classify_objection_theme(e.objection_text)
        # Create new frozen instance with updated auto_theme
        updated.append(LabeledObjection(
            objection_id=e.objection_id,
            product=e.product,
            product_category=e.product_category,
            npc_archetype=e.npc_archetype,
            objection_text=e.objection_text,
            auto_theme=new_auto,
            human_primary=e.human_primary,
            human_secondary=e.human_secondary,
            match_type="",  # will be recomputed
            confusion_note=e.confusion_note,
        ))
    return updated


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Score objection-theme classifier against human-labeled corpus"
    )
    parser.add_argument("corpus", help="Path to JSONL corpus file")
    parser.add_argument(
        "--reclassify", action="store_true",
        help="Re-run classifier on objection_text (ignores stored auto_theme)",
    )
    parser.add_argument(
        "--json-out", type=str, default="",
        help="Path for JSON report output (default: <corpus_dir>/classifier_report.json)",
    )
    args = parser.parse_args()

    corpus_path = Path(args.corpus)
    print(f"Loading corpus from {corpus_path}...")
    entries = load_corpus(corpus_path)
    print(f"  Loaded {len(entries)} entries")

    if not entries:
        print("  [ERROR] No valid entries found. Exiting.")
        return 1

    if args.reclassify:
        print("  Re-running classifier on all entries...")
        entries = reclassify_corpus(entries)

    report = generate_report(entries)
    print_report(report)

    # Write JSON report
    json_path = args.json_out or str(corpus_path.parent / "classifier_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
    print(f"\n  JSON report written to {json_path}")

    # Exit code: 0 if all gates pass, 1 if any fail
    all_pass = all(r["passed"] for r in report.pass_fail.values())
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
