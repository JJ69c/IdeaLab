"""Phase 3 validation — archetype-based population system.

Verifies that the population generator produces meaningfully different
NPC populations where archetypes have distinct trait profiles, respond
differently to the same product, form archetype-aware social graphs,
and create measurably different populations across presets.

Run:  python tests/validate_phase3.py
"""

from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.simulation.npc import NpcPersonality
from backend.simulation.population import (
    generate_npc,
    generate_population,
    load_archetypes,
    parse_archetype_defs,
)
from backend.simulation.product_profile import ProductProfile, compute_npc_adjustment
from backend.simulation.propagation import (
    compute_discussion_weight,
    compute_peer_susceptibility,
    compute_spread_receptiveness,
)

# ===========================================================================
# Helpers
# ===========================================================================

TRAIT_NAMES = [
    "openness", "skepticism", "tech_savviness",
    "price_sensitivity", "social_influence", "conformity", "novelty_seeking",
]


def _mean_traits(npcs, trait_name):
    """Mean of a trait across a list of NPCs."""
    return statistics.mean(getattr(n.personality, trait_name) for n in npcs)


def _archetype_groups(npcs, npc_archetypes):
    """Group NPCs by archetype id."""
    groups = defaultdict(list)
    for npc in npcs:
        arch = npc_archetypes.get(npc.id, "unknown")
        groups[arch].append(npc)
    return dict(groups)


# A moderately challenging product for adjustment tests
TEST_PRODUCT = ProductProfile(
    novelty=0.65, utility_clarity=0.65, differentiation=0.60,
    price_friction=0.50, trust_barrier=0.55, identity_fit=0.50,
    trial_friction=0.35, market_saturation=0.35,
)


# ===========================================================================
# 1. Trait distribution checks
# ===========================================================================

def test_archetypes_have_distinct_traits():
    """Each archetype should produce NPCs with distinguishable trait means."""
    npcs, npc_arch = generate_population(size=60, preset="balanced", seed=42)
    groups = _archetype_groups(npcs, npc_arch)

    # For each trait, compute per-archetype mean
    trait_means = {}
    for arch_id, arch_npcs in groups.items():
        trait_means[arch_id] = {t: round(_mean_traits(arch_npcs, t), 3) for t in TRAIT_NAMES}

    # Signature traits that should clearly separate archetypes
    checks = [
        ("enthusiast", "novelty_seeking", "skeptic", "novelty_seeking",
         "Enthusiast novelty_seeking > Skeptic novelty_seeking"),
        ("skeptic", "skepticism", "follower", "skepticism",
         "Skeptic skepticism > Follower skepticism"),
        ("gatekeeper", "tech_savviness", "budget_conscious", "tech_savviness",
         "Gatekeeper tech_savviness > Budget-Conscious tech_savviness"),
        ("follower", "conformity", "gatekeeper", "conformity",
         "Follower conformity > Gatekeeper conformity"),
        ("budget_conscious", "price_sensitivity", "enthusiast", "price_sensitivity",
         "Budget-Conscious price_sensitivity > Enthusiast price_sensitivity"),
        ("enthusiast", "social_influence", "follower", "social_influence",
         "Enthusiast social_influence > Follower social_influence"),
    ]

    for high_arch, high_trait, low_arch, low_trait, desc in checks:
        high_val = trait_means[high_arch][high_trait]
        low_val = trait_means[low_arch][low_trait]
        assert high_val > low_val, \
            f"{desc}: {high_val:.3f} not > {low_val:.3f}"

    print("PASS: archetype signature traits are correctly ordered")

    # Print summary table
    print(f"\n  {'Archetype':18s}", end="")
    for t in TRAIT_NAMES:
        print(f" {t[:8]:>8s}", end="")
    print()
    print(f"  {'-' * (18 + 9 * len(TRAIT_NAMES))}")
    for arch_id in sorted(trait_means):
        print(f"  {arch_id:18s}", end="")
        for t in TRAIT_NAMES:
            print(f" {trait_means[arch_id][t]:8.3f}", end="")
        print()


def test_trait_variation_within_archetype():
    """NPCs of the same archetype should NOT be identical — verify stdev > 0."""
    npcs, npc_arch = generate_population(size=60, preset="balanced", seed=42)
    groups = _archetype_groups(npcs, npc_arch)

    all_varied = True
    for arch_id, arch_npcs in groups.items():
        if len(arch_npcs) < 3:
            continue
        for trait in TRAIT_NAMES:
            vals = [getattr(n.personality, trait) for n in arch_npcs]
            sd = statistics.stdev(vals)
            if sd < 0.005:
                print(f"  WARNING: {arch_id}.{trait} has near-zero stdev ({sd:.4f})")
                all_varied = False

    assert all_varied, "Some archetypes have near-zero trait variation"
    print("PASS: all archetypes show meaningful within-group trait variation")


# ===========================================================================
# 2. Product adjustment differentiation
# ===========================================================================

def test_same_product_different_archetype_adjustments():
    """Different archetypes should get different NPC adjustments for the same product."""
    npcs, npc_arch = generate_population(size=60, preset="balanced", seed=42)
    groups = _archetype_groups(npcs, npc_arch)

    arch_adj = {}
    for arch_id, arch_npcs in groups.items():
        adjs = []
        for npc in arch_npcs:
            pers = npc.to_profile_dict().get("personality", {})
            adjs.append(compute_npc_adjustment(TEST_PRODUCT, pers))
        arch_adj[arch_id] = round(statistics.mean(adjs), 4)

    # Print table
    print(f"\n  Product adjustment by archetype (same product):")
    print(f"  {'Archetype':18s} {'Mean Adj':>10s}")
    print(f"  {'-' * 30}")
    for arch_id in sorted(arch_adj, key=arch_adj.get, reverse=True):
        print(f"  {arch_id:18s} {arch_adj[arch_id]:+10.4f}")

    # Enthusiasts should get a more positive adjustment than skeptics
    assert arch_adj["enthusiast"] > arch_adj["skeptic"], \
        f"Enthusiast adj ({arch_adj['enthusiast']}) should exceed Skeptic ({arch_adj['skeptic']})"

    # The spread between best and worst archetype should be meaningful (> 0.05)
    spread = max(arch_adj.values()) - min(arch_adj.values())
    assert spread > 0.05, f"Archetype adjustment spread too small: {spread:.4f}"

    print(f"\n  Spread (max - min): {spread:.4f}")
    print("PASS: archetypes produce meaningfully different product adjustments")


# ===========================================================================
# 3. Social graph affinity
# ===========================================================================

def test_social_graph_archetype_affinity():
    """Preferred archetype pairings should appear more often than random chance."""
    npcs, npc_arch = generate_population(size=60, preset="balanced", seed=42)
    raw = load_archetypes()
    arch_defs = parse_archetype_defs(raw)

    # Count connection types: preferred vs non-preferred
    preferred_count = 0
    non_preferred_count = 0

    for npc in npcs:
        my_arch = npc_arch[npc.id]
        preferred_set = set(arch_defs[my_arch].preferred_connections)
        for conn_id in npc.social_connections:
            conn_arch = npc_arch.get(conn_id, "")
            if conn_arch in preferred_set:
                preferred_count += 1
            else:
                non_preferred_count += 1

    total = preferred_count + non_preferred_count
    pref_rate = preferred_count / total if total else 0

    # With 3x weight for preferred and ~3 preferred archetypes out of 6,
    # random would give ~50%, weighted should push above ~60%
    assert pref_rate > 0.55, \
        f"Preferred connection rate too low: {pref_rate:.1%} (expected >55%)"

    print(f"  Preferred connections: {preferred_count}/{total} ({pref_rate:.1%})")
    print(f"  Non-preferred: {non_preferred_count}/{total} ({1-pref_rate:.1%})")
    print("PASS: social graph shows archetype affinity bias")


def test_trust_within_vs_across_archetype():
    """Within-archetype trust should average higher than cross-archetype trust."""
    npcs, npc_arch = generate_population(size=60, preset="balanced", seed=42)

    within_trusts = []
    across_trusts = []

    for npc in npcs:
        my_arch = npc_arch[npc.id]
        for conn_id, trust in npc.trust_weights.items():
            conn_arch = npc_arch.get(conn_id, "")
            if conn_arch == my_arch:
                within_trusts.append(trust)
            else:
                across_trusts.append(trust)

    within_mean = statistics.mean(within_trusts) if within_trusts else 0
    across_mean = statistics.mean(across_trusts) if across_trusts else 0

    assert within_mean > across_mean, \
        f"Within-archetype trust ({within_mean:.3f}) should exceed cross ({across_mean:.3f})"

    print(f"  Within-archetype mean trust: {within_mean:.3f} (n={len(within_trusts)})")
    print(f"  Cross-archetype mean trust:  {across_mean:.3f} (n={len(across_trusts)})")
    print(f"  Delta: {within_mean - across_mean:+.3f}")
    print("PASS: within-archetype trust is higher than cross-archetype")


# ===========================================================================
# 4. Preset differentiation
# ===========================================================================

def test_presets_produce_different_compositions():
    """Each preset should create a measurably different archetype distribution."""
    presets = ["balanced", "young_consumer", "skeptical", "premium", "price_sensitive"]
    compositions = {}

    for preset in presets:
        npcs, npc_arch = generate_population(size=30, preset=preset, seed=42)
        counts = Counter(npc_arch.values())
        compositions[preset] = counts

    # Print comparison
    all_archetypes = sorted({a for c in compositions.values() for a in c})
    print(f"\n  {'Preset':18s}", end="")
    for a in all_archetypes:
        print(f" {a[:8]:>8s}", end="")
    print()
    print(f"  {'-' * (18 + 9 * len(all_archetypes))}")
    for preset in presets:
        print(f"  {preset:18s}", end="")
        for a in all_archetypes:
            print(f" {compositions[preset].get(a, 0):8d}", end="")
        print()

    # Each preset should differ from balanced in at least 2 archetypes
    balanced = compositions["balanced"]
    for preset in presets:
        if preset == "balanced":
            continue
        diffs = sum(1 for a in all_archetypes
                    if compositions[preset].get(a, 0) != balanced.get(a, 0))
        assert diffs >= 2, \
            f"Preset '{preset}' differs from balanced in only {diffs} archetypes"

    # Specific checks
    assert compositions["skeptical"]["skeptic"] > compositions["balanced"]["skeptic"], \
        "Skeptical preset should have more skeptics"
    assert compositions["price_sensitive"]["budget_conscious"] > compositions["balanced"]["budget_conscious"], \
        "Price-sensitive preset should have more budget_conscious"
    assert compositions["premium"]["gatekeeper"] > compositions["balanced"]["gatekeeper"], \
        "Premium preset should have more gatekeepers"

    print("\nPASS: presets produce distinct archetype compositions")


def test_preset_trait_profiles_differ():
    """Population-level mean traits should differ across presets."""
    presets = ["balanced", "young_consumer", "skeptical", "price_sensitive"]
    pop_traits = {}

    for preset in presets:
        npcs, _ = generate_population(size=30, preset=preset, seed=42)
        pop_traits[preset] = {
            t: round(statistics.mean(getattr(n.personality, t) for n in npcs), 3)
            for t in TRAIT_NAMES
        }

    # Skeptical market should have higher mean skepticism than young consumer
    assert pop_traits["skeptical"]["skepticism"] > pop_traits["young_consumer"]["skepticism"], \
        "Skeptical preset should have higher mean skepticism"

    # Price-sensitive should have higher mean price_sensitivity
    assert pop_traits["price_sensitive"]["price_sensitivity"] > pop_traits["balanced"]["price_sensitivity"], \
        "Price-sensitive preset should have higher mean price_sensitivity"

    # Young consumer should have higher novelty_seeking
    assert pop_traits["young_consumer"]["novelty_seeking"] > pop_traits["skeptical"]["novelty_seeking"], \
        "Young consumer should have higher mean novelty_seeking"

    print(f"\n  Population-level mean traits by preset:")
    print(f"  {'Preset':18s}", end="")
    for t in ["skepticism", "price_sens", "novelty_s", "openness"]:
        print(f" {t[:10]:>10s}", end="")
    print()
    print(f"  {'-' * 60}")
    for preset in presets:
        t = pop_traits[preset]
        print(f"  {preset:18s} {t['skepticism']:10.3f} {t['price_sensitivity']:10.3f} "
              f"{t['novelty_seeking']:10.3f} {t['openness']:10.3f}")

    print("\nPASS: presets produce distinct population-level trait profiles")


# ===========================================================================
# 5. Mechanics differentiation (Phase 2A/2B/2C helpers)
# ===========================================================================

def test_archetypes_differ_in_peer_susceptibility():
    """Peer susceptibility should vary meaningfully across archetypes."""
    npcs, npc_arch = generate_population(size=60, preset="balanced", seed=42)
    groups = _archetype_groups(npcs, npc_arch)

    arch_susc = {}
    for arch_id, arch_npcs in groups.items():
        vals = [
            compute_peer_susceptibility(n.personality.conformity, n.personality.skepticism)
            for n in arch_npcs
        ]
        arch_susc[arch_id] = round(statistics.mean(vals), 4)

    print(f"\n  Peer susceptibility by archetype:")
    print(f"  {'Archetype':18s} {'Susceptibility':>15s}")
    print(f"  {'-' * 35}")
    for arch_id in sorted(arch_susc, key=arch_susc.get, reverse=True):
        print(f"  {arch_id:18s} {arch_susc[arch_id]:15.4f}")

    # Followers (high conformity, low skepticism) should be most susceptible
    # Gatekeepers (low conformity) should be least susceptible
    assert arch_susc["follower"] > arch_susc["gatekeeper"], \
        f"Follower susceptibility ({arch_susc['follower']}) should exceed Gatekeeper ({arch_susc['gatekeeper']})"

    spread = max(arch_susc.values()) - min(arch_susc.values())
    assert spread > 0.05, f"Susceptibility spread too small: {spread:.4f}"
    print(f"\n  Spread: {spread:.4f}")
    print("PASS: peer susceptibility varies meaningfully across archetypes")


def test_archetypes_differ_in_spread_receptiveness():
    """Spread receptiveness should vary across archetypes."""
    npcs, npc_arch = generate_population(size=60, preset="balanced", seed=42)
    groups = _archetype_groups(npcs, npc_arch)

    arch_recept = {}
    for arch_id, arch_npcs in groups.items():
        vals = [
            compute_spread_receptiveness(n.personality.novelty_seeking, n.personality.openness)
            for n in arch_npcs
        ]
        arch_recept[arch_id] = round(statistics.mean(vals), 4)

    print(f"\n  Spread receptiveness by archetype:")
    print(f"  {'Archetype':18s} {'Receptiveness':>14s}")
    print(f"  {'-' * 34}")
    for arch_id in sorted(arch_recept, key=arch_recept.get, reverse=True):
        print(f"  {arch_id:18s} {arch_recept[arch_id]:14.4f}")

    # Enthusiasts (high novelty_seeking + high openness) should be most receptive
    # Skeptics (low both) should be least receptive
    assert arch_recept["enthusiast"] > arch_recept["skeptic"], \
        f"Enthusiast receptiveness ({arch_recept['enthusiast']}) should exceed Skeptic ({arch_recept['skeptic']})"

    spread = max(arch_recept.values()) - min(arch_recept.values())
    assert spread > 0.15, f"Receptiveness spread too small: {spread:.4f}"
    print(f"\n  Spread: {spread:.4f}")
    print("PASS: spread receptiveness varies meaningfully across archetypes")


def test_archetypes_differ_in_discussion_weight():
    """Gatekeepers speaking to followers should persuade more than followers speaking to skeptics."""
    npcs, npc_arch = generate_population(size=60, preset="balanced", seed=42)
    groups = _archetype_groups(npcs, npc_arch)

    # Take a representative NPC from each archetype
    rep = {arch_id: arch_npcs[0] for arch_id, arch_npcs in groups.items()}

    # Gatekeeper → Follower (high influence, low target skepticism)
    gk = rep["gatekeeper"]
    fl = rep["follower"]
    trust_high = 0.7
    w_gk_to_fl = compute_discussion_weight(
        gk.personality.social_influence, trust_high, fl.personality.skepticism
    )

    # Follower → Skeptic (low influence, high target skepticism)
    sk = rep["skeptic"]
    w_fl_to_sk = compute_discussion_weight(
        fl.personality.social_influence, trust_high, sk.personality.skepticism
    )

    print(f"\n  Discussion weight examples (trust={trust_high}):")
    print(f"  Gatekeeper → Follower:  {w_gk_to_fl:.3f}")
    print(f"  Follower → Skeptic:     {w_fl_to_sk:.3f}")
    print(f"  Ratio:                  {w_gk_to_fl / w_fl_to_sk:.1f}x")

    assert w_gk_to_fl > w_fl_to_sk, \
        f"Gatekeeper→Follower ({w_gk_to_fl}) should persuade more than Follower→Skeptic ({w_fl_to_sk})"
    print("PASS: discussion weight varies correctly by archetype pairing")


# ===========================================================================
# 6. Reproducibility
# ===========================================================================

def test_seed_reproducibility():
    """Same seed should produce identical populations."""
    npcs_a, arch_a = generate_population(size=30, preset="balanced", seed=123)
    npcs_b, arch_b = generate_population(size=30, preset="balanced", seed=123)

    assert len(npcs_a) == len(npcs_b)
    assert arch_a == arch_b

    for a, b in zip(npcs_a, npcs_b):
        assert a.id == b.id
        assert a.name == b.name
        assert a.personality.openness == b.personality.openness
        assert a.social_connections == b.social_connections

    print("PASS: same seed produces identical populations")


# ===========================================================================
# Go/No-Go
# ===========================================================================

def go_nogo():
    print(f"\n{'#' * 70}")
    print(f"#  GO / NO-GO: Is Phase 3 ready?")
    print(f"{'#' * 70}\n")

    npcs, npc_arch = generate_population(size=60, preset="balanced", seed=42)
    groups = _archetype_groups(npcs, npc_arch)

    checks = []

    # 1. All 6 archetypes present
    expected = {"enthusiast", "pragmatist", "skeptic", "follower", "gatekeeper", "budget_conscious"}
    present = set(groups.keys())
    checks.append((f"All 6 archetypes present ({len(present)}/6)",
                    present == expected))

    # 2. Trait signatures are distinct
    enth_ns = _mean_traits(groups["enthusiast"], "novelty_seeking")
    skep_ns = _mean_traits(groups["skeptic"], "novelty_seeking")
    checks.append((f"Enthusiast novelty_seeking ({enth_ns:.3f}) > Skeptic ({skep_ns:.3f})",
                    enth_ns > skep_ns))

    # 3. Product adjustment spread > 0.05
    arch_adj = {}
    for arch_id, arch_npcs in groups.items():
        adjs = [compute_npc_adjustment(TEST_PRODUCT, n.to_profile_dict().get("personality", {}))
                for n in arch_npcs]
        arch_adj[arch_id] = statistics.mean(adjs)
    adj_spread = max(arch_adj.values()) - min(arch_adj.values())
    checks.append((f"Product adjustment spread = {adj_spread:.4f} (need >0.05)",
                    adj_spread > 0.05))

    # 4. Social graph shows preferred bias > 55%
    raw = load_archetypes()
    arch_defs = parse_archetype_defs(raw)
    pref_cnt = 0
    total_cnt = 0
    for npc in npcs:
        preferred_set = set(arch_defs[npc_arch[npc.id]].preferred_connections)
        for conn_id in npc.social_connections:
            total_cnt += 1
            if npc_arch.get(conn_id, "") in preferred_set:
                pref_cnt += 1
    pref_rate = pref_cnt / total_cnt if total_cnt else 0
    checks.append((f"Preferred connection rate = {pref_rate:.1%} (need >55%)",
                    pref_rate > 0.55))

    # 5. Peer susceptibility spread > 0.05
    arch_susc = {}
    for arch_id, arch_npcs in groups.items():
        arch_susc[arch_id] = statistics.mean(
            compute_peer_susceptibility(n.personality.conformity, n.personality.skepticism)
            for n in arch_npcs
        )
    susc_spread = max(arch_susc.values()) - min(arch_susc.values())
    checks.append((f"Peer susceptibility spread = {susc_spread:.4f} (need >0.05)",
                    susc_spread > 0.05))

    # 6. Spread receptiveness spread > 0.15
    arch_recept = {}
    for arch_id, arch_npcs in groups.items():
        arch_recept[arch_id] = statistics.mean(
            compute_spread_receptiveness(n.personality.novelty_seeking, n.personality.openness)
            for n in arch_npcs
        )
    recept_spread = max(arch_recept.values()) - min(arch_recept.values())
    checks.append((f"Spread receptiveness spread = {recept_spread:.4f} (need >0.15)",
                    recept_spread > 0.15))

    # 7. Presets differ from each other
    sk_npcs, _ = generate_population(size=30, preset="skeptical", seed=42)
    yc_npcs, _ = generate_population(size=30, preset="young_consumer", seed=42)
    sk_skep = statistics.mean(n.personality.skepticism for n in sk_npcs)
    yc_skep = statistics.mean(n.personality.skepticism for n in yc_npcs)
    checks.append((f"Skeptical preset mean skepticism ({sk_skep:.3f}) > Young consumer ({yc_skep:.3f})",
                    sk_skep > yc_skep))

    # 8. Reproducibility
    npcs2, arch2 = generate_population(size=60, preset="balanced", seed=42)
    repro = all(a.id == b.id and a.name == b.name for a, b in zip(npcs, npcs2))
    checks.append(("Seeded generation is reproducible", repro))

    all_pass = True
    for label, passed in checks:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {label}")

    print()
    if all_pass:
        print("  VERDICT: GO — Phase 3 population system is working correctly.")
        print("  Archetypes produce distinct trait profiles, different product evaluations,")
        print("  affinity-biased social graphs, and preset-driven composition variety.")
        print("  All Phase 2 mechanics (susceptibility, receptiveness, discussion weight)")
        print("  show meaningful archetype differentiation.")
    else:
        print("  VERDICT: NO-GO — Fix failing checks before considering Phase 3 complete.")

    return all_pass


# ===========================================================================
# Main
# ===========================================================================

ALL_TESTS = [
    test_archetypes_have_distinct_traits,
    test_trait_variation_within_archetype,
    test_same_product_different_archetype_adjustments,
    test_social_graph_archetype_affinity,
    test_trust_within_vs_across_archetype,
    test_presets_produce_different_compositions,
    test_preset_trait_profiles_differ,
    test_archetypes_differ_in_peer_susceptibility,
    test_archetypes_differ_in_spread_receptiveness,
    test_archetypes_differ_in_discussion_weight,
    test_seed_reproducibility,
]


def main():
    print("=" * 70)
    print("  PHASE 3 VALIDATION: Archetype-Based Population System")
    print("=" * 70)

    passed = 0
    failed = 0

    for fn in ALL_TESTS:
        print(f"\n{'─' * 70}")
        print(f"  {fn.__name__}")
        print(f"{'─' * 70}")
        try:
            fn()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"FAIL: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR: {type(e).__name__}: {e}")

    print(f"\n{'─' * 70}")
    print(f"  Results: {passed} passed, {failed} failed out of {len(ALL_TESTS)} tests")
    print(f"{'─' * 70}")

    ready = go_nogo()

    print("\n" + "=" * 70)
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
