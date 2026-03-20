"""Archetype Diversity Validation Tests.

Proves that the 8 archetypes produce genuinely diverse simulation outcomes,
not just superficially different labels.

Tests cover:
1. Weight separation — no two archetypes have similar evaluation weight profiles
2. Baseline divergence — different product profiles activate different archetypes
3. Population trait separation — archetype trait signatures are measurably distinct
4. Propagation behavior — susceptibility and credibility differ meaningfully
5. Adoption outcome divergence — archetypes gate on different product dimensions
6. End-to-end — no single archetype dominates all product types
"""

import math
import sys
from pathlib import Path
from collections import defaultdict

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.simulation.evaluation import (
    compute_archetype_baseline,
    compute_individual_delta,
    get_archetype_evaluation,
    reload_evaluations,
)
from backend.simulation.population import generate_population
from backend.simulation.product_profile import ProductProfile
from backend.simulation.npc import NpcPersonality
from backend.simulation.propagation import _SOURCE_CREDIBILITY

# Force fresh load of archetype definitions
reload_evaluations()

ARCHETYPE_IDS = [
    "analytical_skeptic",
    "trend_adopter",
    "price_pragmatist",
    "health_evaluator",
    "brand_buyer",
    "social_follower",
    "convenience_user",
    "values_buyer",
]

# Representative product profiles for testing
PROFILES = {
    "cheap_novel": ProductProfile(
        novelty=0.90, utility_clarity=0.50, differentiation=0.70,
        price_friction=0.10, trust_barrier=0.60, identity_fit=0.40,
        trial_friction=0.30, market_saturation=0.15,
    ),
    "expensive_proven": ProductProfile(
        novelty=0.20, utility_clarity=0.85, differentiation=0.50,
        price_friction=0.80, trust_barrier=0.15, identity_fit=0.60,
        trial_friction=0.20, market_saturation=0.70,
    ),
    "high_trust_barrier": ProductProfile(
        novelty=0.50, utility_clarity=0.60, differentiation=0.50,
        price_friction=0.40, trust_barrier=0.90, identity_fit=0.50,
        trial_friction=0.40, market_saturation=0.30,
    ),
    "high_friction": ProductProfile(
        novelty=0.60, utility_clarity=0.70, differentiation=0.55,
        price_friction=0.50, trust_barrier=0.40, identity_fit=0.50,
        trial_friction=0.85, market_saturation=0.25,
    ),
    "identity_aligned": ProductProfile(
        novelty=0.40, utility_clarity=0.50, differentiation=0.60,
        price_friction=0.30, trust_barrier=0.30, identity_fit=0.90,
        trial_friction=0.25, market_saturation=0.20,
    ),
}


def _euclidean_distance(w1: dict, w2: dict) -> float:
    """Euclidean distance between two weight dictionaries."""
    all_keys = set(w1.keys()) | set(w2.keys())
    return math.sqrt(sum((w1.get(k, 0) - w2.get(k, 0)) ** 2 for k in all_keys))


def test_weight_separation():
    """Every pair of archetypes must have weight distance > 0.15."""
    print("\n=== Test 1: Evaluation Weight Separation ===")
    evals = {aid: get_archetype_evaluation(aid) for aid in ARCHETYPE_IDS}
    min_dist = float("inf")
    min_pair = ("", "")

    for i, a1 in enumerate(ARCHETYPE_IDS):
        for a2 in ARCHETYPE_IDS[i + 1:]:
            d = _euclidean_distance(evals[a1].weights, evals[a2].weights)
            if d < min_dist:
                min_dist = d
                min_pair = (a1, a2)
            print(f"  {a1:22s} vs {a2:22s} = {d:.4f}")

    print(f"\n  Minimum distance: {min_dist:.4f} ({min_pair[0]} vs {min_pair[1]})")
    assert min_dist > 0.15, (
        f"Weight distance too small: {min_pair[0]} vs {min_pair[1]} = {min_dist:.4f}"
    )
    print("  PASSED: All archetype pairs have weight distance > 0.15")


def test_baseline_divergence():
    """For each product profile, archetypes must spread across a range > 0.20."""
    print("\n=== Test 2: Baseline Divergence Across Product Profiles ===")
    evals = {aid: get_archetype_evaluation(aid) for aid in ARCHETYPE_IDS}

    for profile_name, profile in PROFILES.items():
        baselines = {}
        for aid in ARCHETYPE_IDS:
            baselines[aid] = compute_archetype_baseline(profile, evals[aid])

        sorted_baselines = sorted(baselines.items(), key=lambda x: x[1])
        spread = sorted_baselines[-1][1] - sorted_baselines[0][1]

        print(f"\n  Profile: {profile_name} (spread = {spread:.3f})")
        for aid, bl in sorted_baselines:
            print(f"    {aid:22s} = {bl:.3f}")

        assert spread > 0.20, (
            f"Baseline spread too narrow for {profile_name}: {spread:.3f}"
        )

    print("\n  PASSED: All profiles produce archetype spread > 0.20")


def test_population_trait_separation():
    """Generated population must show measurable trait differences between archetypes."""
    print("\n=== Test 3: Population Trait Separation ===")
    npcs, npc_archetypes = generate_population(size=80, preset="balanced")

    # Group by archetype
    arch_traits: dict[str, list[dict]] = defaultdict(list)
    for npc in npcs:
        arch_id = npc_archetypes.get(npc.id, "unknown")
        arch_traits[arch_id].append({
            "openness": npc.personality.openness,
            "skepticism": npc.personality.skepticism,
            "tech_savviness": npc.personality.tech_savviness,
            "price_sensitivity": npc.personality.price_sensitivity,
            "social_influence": npc.personality.social_influence,
            "conformity": npc.personality.conformity,
            "novelty_seeking": npc.personality.novelty_seeking,
        })

    # Compute per-archetype means for each trait
    trait_names = ["openness", "skepticism", "price_sensitivity", "conformity", "novelty_seeking"]

    # Signature traits: each archetype should be extreme on at least one
    signature_checks = {
        "analytical_skeptic": ("skepticism", "max"),
        "trend_adopter": ("novelty_seeking", "max"),
        "price_pragmatist": ("price_sensitivity", "max"),
        "social_follower": ("conformity", "max"),
    }

    print("\n  Per-archetype trait means:")
    arch_means: dict[str, dict[str, float]] = {}
    for arch_id in sorted(arch_traits.keys()):
        traits_list = arch_traits[arch_id]
        if not traits_list:
            continue
        means = {}
        for t in trait_names:
            means[t] = sum(d[t] for d in traits_list) / len(traits_list)
        arch_means[arch_id] = means
        print(f"    {arch_id:22s} (n={len(traits_list):2d}): " +
              ", ".join(f"{t[:4]}={means[t]:.2f}" for t in trait_names))

    # Check signature traits
    print("\n  Signature trait checks:")
    for arch_id, (trait, direction) in signature_checks.items():
        if arch_id not in arch_means:
            continue
        arch_val = arch_means[arch_id][trait]
        if direction == "max":
            is_max = all(
                arch_val >= arch_means[other][trait] - 0.05
                for other in arch_means if other != arch_id
            )
            status = "PASS" if is_max else "FAIL"
            print(f"    {arch_id:22s} should have highest {trait}: {arch_val:.2f} [{status}]")
            assert is_max, (
                f"{arch_id} should have highest mean {trait} but got {arch_val:.2f}"
            )

    print("\n  PASSED: Signature traits verified")


def test_propagation_parameter_divergence():
    """Susceptibility and source credibility must differ meaningfully across archetypes."""
    print("\n=== Test 4: Propagation Parameter Divergence ===")
    evals = {aid: get_archetype_evaluation(aid) for aid in ARCHETYPE_IDS}

    susceptibilities = {aid: evals[aid].susceptibility_multiplier for aid in ARCHETYPE_IDS}
    credibilities = {aid: _SOURCE_CREDIBILITY.get(aid, 1.0) for aid in ARCHETYPE_IDS}

    print("\n  Susceptibility multipliers:")
    for aid in sorted(susceptibilities, key=susceptibilities.get):
        print(f"    {aid:22s} = {susceptibilities[aid]:.2f}")

    print("\n  Source credibilities:")
    for aid in sorted(credibilities, key=credibilities.get):
        print(f"    {aid:22s} = {credibilities[aid]:.2f}")

    # Social follower must have highest susceptibility
    max_susc_arch = max(susceptibilities, key=susceptibilities.get)
    assert max_susc_arch == "social_follower", (
        f"Expected social_follower to have highest susceptibility, got {max_susc_arch}"
    )

    # Analytical skeptic must have highest source credibility
    max_cred_arch = max(credibilities, key=credibilities.get)
    assert max_cred_arch == "analytical_skeptic", (
        f"Expected analytical_skeptic to have highest credibility, got {max_cred_arch}"
    )

    # Social follower must have lowest source credibility
    min_cred_arch = min(credibilities, key=credibilities.get)
    assert min_cred_arch == "social_follower", (
        f"Expected social_follower to have lowest credibility, got {min_cred_arch}"
    )

    # Susceptibility range must be substantial
    susc_range = max(susceptibilities.values()) - min(susceptibilities.values())
    assert susc_range >= 0.50, f"Susceptibility range too narrow: {susc_range:.2f}"

    print(f"\n  Susceptibility range: {susc_range:.2f}")
    print("  PASSED: Propagation parameters show meaningful divergence")


def test_adoption_outcome_divergence():
    """A moderate product must produce split outcomes: some adopt, some don't."""
    print("\n=== Test 5: Adoption Outcome Divergence ===")
    evals = {aid: get_archetype_evaluation(aid) for aid in ARCHETYPE_IDS}

    # Moderately priced, moderate trust, moderate friction
    profile = ProductProfile(
        novelty=0.55, utility_clarity=0.60, differentiation=0.50,
        price_friction=0.50, trust_barrier=0.40, identity_fit=0.55,
        trial_friction=0.40, market_saturation=0.35,
    )

    print("\n  Baselines for moderate product:")
    baselines = {}
    for aid in ARCHETYPE_IDS:
        bl = compute_archetype_baseline(profile, evals[aid])
        baselines[aid] = bl

    adopters = []
    non_adopters = []
    for aid in sorted(baselines, key=baselines.get, reverse=True):
        threshold = evals[aid].adoption_threshold
        adopted = baselines[aid] >= threshold
        marker = "ADOPT" if adopted else "REJECT"
        print(f"    {aid:22s} baseline={baselines[aid]:.3f} threshold={threshold:.2f} -> {marker}")
        if adopted:
            adopters.append(aid)
        else:
            non_adopters.append(aid)

    assert len(adopters) >= 2, f"Expected at least 2 adopters, got {len(adopters)}"
    assert len(non_adopters) >= 2, f"Expected at least 2 non-adopters, got {len(non_adopters)}"

    print(f"\n  Adopters: {len(adopters)}, Non-adopters: {len(non_adopters)}")
    print("  PASSED: Moderate product produces split adoption outcomes")


def test_end_to_end_differentiation():
    """No single archetype should dominate across all product types."""
    print("\n=== Test 6: End-to-End Differentiation ===")
    evals = {aid: get_archetype_evaluation(aid) for aid in ARCHETYPE_IDS}

    winners = []
    for profile_name, profile in PROFILES.items():
        baselines = {
            aid: compute_archetype_baseline(profile, evals[aid])
            for aid in ARCHETYPE_IDS
        }
        winner = max(baselines, key=baselines.get)
        winners.append(winner)
        print(f"  {profile_name:25s} -> winner: {winner:22s} ({baselines[winner]:.3f})")

    unique_winners = set(winners)
    print(f"\n  Unique winners across {len(PROFILES)} profiles: {len(unique_winners)}")
    print(f"  Winners: {unique_winners}")

    assert len(unique_winners) >= 3, (
        f"Expected at least 3 different winners across profiles, got {len(unique_winners)}: {unique_winners}"
    )

    # Compute std dev of archetype means across all profiles
    arch_avg_baselines = {}
    for aid in ARCHETYPE_IDS:
        vals = [compute_archetype_baseline(p, evals[aid]) for p in PROFILES.values()]
        arch_avg_baselines[aid] = sum(vals) / len(vals)

    mean_of_means = sum(arch_avg_baselines.values()) / len(arch_avg_baselines)
    variance = sum((v - mean_of_means) ** 2 for v in arch_avg_baselines.values()) / len(arch_avg_baselines)
    std_dev = math.sqrt(variance)

    print(f"\n  Cross-profile archetype mean std dev: {std_dev:.4f}")
    assert std_dev > 0.03, (
        f"Archetype mean standard deviation too low: {std_dev:.4f}"
    )
    print("  PASSED: No single archetype dominates all product types")


def main():
    """Run all archetype diversity validation tests."""
    print("=" * 70)
    print("  ARCHETYPE DIVERSITY VALIDATION")
    print("  8 archetypes × 5 product profiles × 6 test categories")
    print("=" * 70)

    tests = [
        test_weight_separation,
        test_baseline_divergence,
        test_population_trait_separation,
        test_propagation_parameter_divergence,
        test_adoption_outcome_divergence,
        test_end_to_end_differentiation,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"\n  FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"\n  ERROR: {e}")
            failed += 1

    print("\n" + "=" * 70)
    print(f"  RESULTS: {passed}/{passed + failed} tests passed")
    if failed:
        print(f"  {failed} test(s) FAILED")
    else:
        print("  ALL TESTS PASSED — Archetypes are behaviorally diverse")
    print("=" * 70)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
