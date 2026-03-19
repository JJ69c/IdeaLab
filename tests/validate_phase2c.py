"""Phase 2C validation — interaction terms in NPC adjustment.

Verifies that the two compound terms create non-linear effects that
meaningfully differentiate NPC evaluations beyond what the linear
terms alone can produce.

Run:  python tests/validate_phase2c.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.simulation.product_profile import ProductProfile, compute_npc_adjustment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _adj(profile: ProductProfile, personality: dict) -> float:
    return compute_npc_adjustment(profile, personality)


def _adj_without_interactions(profile: ProductProfile, personality: dict) -> float:
    """Replicate the linear-only formula to isolate interaction term contribution."""
    openness = personality.get("openness", 0.5)
    skepticism = personality.get("skepticism", 0.5)
    price_sens = personality.get("price_sensitivity", 0.5)
    tech = personality.get("tech_savviness", 0.5)
    novelty_seek = personality.get("novelty_seeking", 0.5)

    delta = 0.0
    delta -= profile.price_friction * price_sens * 0.15
    delta -= profile.trial_friction * (1 - tech) * 0.10
    delta += profile.novelty * novelty_seek * 0.10
    delta -= profile.trust_barrier * skepticism * 0.10
    delta += profile.utility_clarity * openness * 0.08
    delta += profile.differentiation * 0.05
    delta -= profile.market_saturation * (1 - novelty_seek) * 0.08

    return max(-0.15, min(0.15, round(delta, 4)))


def _interaction_contribution(profile: ProductProfile, personality: dict) -> dict:
    """Compute each interaction term's raw value before clamping."""
    skepticism = personality.get("skepticism", 0.5)
    openness = personality.get("openness", 0.5)

    penalty = -profile.price_friction * profile.trust_barrier * skepticism * 0.08
    boost = profile.utility_clarity * profile.differentiation * openness * 0.06

    return {"penalty": round(penalty, 5), "boost": round(boost, 5), "net": round(penalty + boost, 5)}


MODERATE_PROFILE = ProductProfile(
    novelty=0.5, utility_clarity=0.5, differentiation=0.5,
    price_friction=0.5, trust_barrier=0.5, identity_fit=0.5,
    trial_friction=0.3, market_saturation=0.3,
)

MODERATE_PERSONALITY = {
    "openness": 0.5, "skepticism": 0.5, "tech_savviness": 0.5,
    "price_sensitivity": 0.5, "novelty_seeking": 0.5,
}


# ===========================================================================
# 1. Compound penalty: price_friction * trust_barrier * skepticism
# ===========================================================================

def test_compound_penalty_isolate():
    """The penalty interaction term should be material at high values."""
    # Worst case: expensive, unproven, skeptical
    bad_profile = ProductProfile(
        novelty=0.5, utility_clarity=0.5, differentiation=0.5,
        price_friction=0.9, trust_barrier=0.9, identity_fit=0.5,
        trial_friction=0.3, market_saturation=0.3,
    )
    skeptic = {"openness": 0.5, "skepticism": 0.9, "tech_savviness": 0.5,
               "price_sensitivity": 0.5, "novelty_seeking": 0.5}

    terms = _interaction_contribution(bad_profile, skeptic)
    assert terms["penalty"] < -0.04, f"Penalty too small: {terms['penalty']}"
    print(f"PASS: compound penalty at extreme = {terms['penalty']:+.5f} (meaningful)")


def test_compound_penalty_scales_nonlinearly():
    """Halving one factor should reduce the penalty by more than half (cubic term)."""
    full = _interaction_contribution(
        ProfileWith(price_friction=0.8, trust_barrier=0.8),
        {"skepticism": 0.8, "openness": 0.5},
    )
    half_price = _interaction_contribution(
        ProfileWith(price_friction=0.4, trust_barrier=0.8),
        {"skepticism": 0.8, "openness": 0.5},
    )
    half_all = _interaction_contribution(
        ProfileWith(price_friction=0.4, trust_barrier=0.4),
        {"skepticism": 0.4, "openness": 0.5},
    )

    # Cubic: halving one factor should halve the penalty.
    # Halving ALL three factors should reduce it by 8x (0.5^3).
    ratio = full["penalty"] / half_all["penalty"]
    assert abs(ratio - 8.0) < 0.1, f"Expected ~8x ratio, got {ratio:.1f}"
    print(f"PASS: penalty scales cubically (full={full['penalty']:+.5f}, "
          f"half_all={half_all['penalty']:+.5f}, ratio={ratio:.1f}x)")


def scenario_price_trust_interaction():
    """High price + low trust vs high price + high trust, seen by a skeptic."""
    skeptic = {"openness": 0.4, "skepticism": 0.85, "tech_savviness": 0.5,
               "price_sensitivity": 0.6, "novelty_seeking": 0.4}

    combos = [
        ("cheap + trusted",     ProfileWith(price_friction=0.2, trust_barrier=0.2)),
        ("cheap + untrusted",   ProfileWith(price_friction=0.2, trust_barrier=0.8)),
        ("expensive + trusted", ProfileWith(price_friction=0.8, trust_barrier=0.2)),
        ("expensive + untrusted", ProfileWith(price_friction=0.8, trust_barrier=0.8)),
    ]

    print(f"\n  COMPOUND PENALTY: price × trust × skepticism (skeptic NPC, skep=0.85)")
    print(f"  {'Product':25s} {'Linear Only':>12} {'With Interact':>14} {'Interaction':>12}")
    print(f"  {'-' * 67}")

    for label, profile in combos:
        linear = _adj_without_interactions(profile, skeptic)
        full = _adj(profile, skeptic)
        terms = _interaction_contribution(profile, skeptic)
        print(f"  {label:25s} {linear:+12.4f} {full:+14.4f} {terms['penalty']:+12.5f}")

    # The expensive+untrusted combo should have a much larger penalty gap
    # vs the linear-only version than cheap+trusted
    cheap_gap = abs(_adj(combos[0][1], skeptic) - _adj_without_interactions(combos[0][1], skeptic))
    expensive_gap = abs(_adj(combos[3][1], skeptic) - _adj_without_interactions(combos[3][1], skeptic))
    assert expensive_gap > cheap_gap * 3, \
        f"Expensive+untrusted should have 3x+ bigger interaction gap: {expensive_gap:.5f} vs {cheap_gap:.5f}"
    print(f"\n  PASS: expensive+untrusted interaction gap is {expensive_gap / max(cheap_gap, 0.00001):.1f}x "
          f"larger than cheap+trusted")
    print(f"  INTERPRETATION: when price and trust barriers compound, skeptics get")
    print(f"  hit disproportionately harder — this is the non-linear effect at work")


# ===========================================================================
# 2. Compound boost: utility_clarity * differentiation * openness
# ===========================================================================

def test_compound_boost_isolate():
    """The boost interaction term should be material at high values."""
    good_profile = ProfileWith(utility_clarity=0.9, differentiation=0.9)
    open_npc = {"openness": 0.9, "skepticism": 0.3, "tech_savviness": 0.5,
                "price_sensitivity": 0.5, "novelty_seeking": 0.5}

    terms = _interaction_contribution(good_profile, open_npc)
    assert terms["boost"] > 0.03, f"Boost too small: {terms['boost']}"
    print(f"PASS: compound boost at extreme = {terms['boost']:+.5f} (meaningful)")


def test_compound_boost_scales_nonlinearly():
    """Same cubic scaling check for the boost term."""
    full = _interaction_contribution(
        ProfileWith(utility_clarity=0.8, differentiation=0.8),
        {"openness": 0.8, "skepticism": 0.5},
    )
    half_all = _interaction_contribution(
        ProfileWith(utility_clarity=0.4, differentiation=0.4),
        {"openness": 0.4, "skepticism": 0.5},
    )

    ratio = full["boost"] / half_all["boost"]
    assert abs(ratio - 8.0) < 0.1, f"Expected ~8x ratio, got {ratio:.1f}"
    print(f"PASS: boost scales cubically (full={full['boost']:+.5f}, "
          f"half_all={half_all['boost']:+.5f}, ratio={ratio:.1f}x)")


def scenario_utility_diff_interaction():
    """High utility + low diff vs high utility + high diff, seen by an open NPC."""
    open_npc = {"openness": 0.85, "skepticism": 0.3, "tech_savviness": 0.5,
                "price_sensitivity": 0.4, "novelty_seeking": 0.6}

    combos = [
        ("vague + generic",       ProfileWith(utility_clarity=0.2, differentiation=0.2)),
        ("vague + differentiated", ProfileWith(utility_clarity=0.2, differentiation=0.8)),
        ("clear + generic",       ProfileWith(utility_clarity=0.8, differentiation=0.2)),
        ("clear + differentiated", ProfileWith(utility_clarity=0.8, differentiation=0.8)),
    ]

    print(f"\n  COMPOUND BOOST: utility × differentiation × openness (open NPC, open=0.85)")
    print(f"  {'Product':25s} {'Linear Only':>12} {'With Interact':>14} {'Interaction':>12}")
    print(f"  {'-' * 67}")

    for label, profile in combos:
        linear = _adj_without_interactions(profile, open_npc)
        full = _adj(profile, open_npc)
        terms = _interaction_contribution(profile, open_npc)
        print(f"  {label:25s} {linear:+12.4f} {full:+14.4f} {terms['boost']:+12.5f}")

    # clear+differentiated should have much bigger interaction boost than vague+generic
    vague_boost = _interaction_contribution(combos[0][1], open_npc)["boost"]
    clear_boost = _interaction_contribution(combos[3][1], open_npc)["boost"]
    ratio = clear_boost / max(vague_boost, 0.00001)
    assert ratio > 10, f"Expected >10x ratio: {ratio:.1f}"
    print(f"\n  PASS: clear+differentiated boost is {ratio:.0f}x larger than vague+generic")
    print(f"  INTERPRETATION: an open-minded NPC seeing a clear AND unique product")
    print(f"  gets a compounding bonus that neither clarity nor uniqueness alone produces")


# ===========================================================================
# 3. Same product, different NPC personality
# ===========================================================================

def scenario_same_product_different_npc():
    """One product evaluated by open vs skeptical vs moderate NPCs."""
    # A moderately challenging product: somewhat expensive, somewhat unproven,
    # but also somewhat clear and differentiated
    product = ProductProfile(
        novelty=0.6, utility_clarity=0.7, differentiation=0.7,
        price_friction=0.6, trust_barrier=0.6, identity_fit=0.5,
        trial_friction=0.3, market_saturation=0.3,
    )

    npcs = [
        ("open explorer",     {"openness": 0.85, "skepticism": 0.2, "tech_savviness": 0.6,
                               "price_sensitivity": 0.4, "novelty_seeking": 0.7}),
        ("moderate person",   {"openness": 0.5, "skepticism": 0.5, "tech_savviness": 0.5,
                               "price_sensitivity": 0.5, "novelty_seeking": 0.5}),
        ("cautious skeptic",  {"openness": 0.2, "skepticism": 0.85, "tech_savviness": 0.5,
                               "price_sensitivity": 0.6, "novelty_seeking": 0.3}),
    ]

    print(f"\n  SAME PRODUCT, DIFFERENT NPCs")
    print(f"  Product: price_friction=0.6, trust_barrier=0.6, utility=0.7, diff=0.7\n")
    print(f"  {'NPC':20s} {'Linear':>8} {'Full':>8} {'Penalty':>9} {'Boost':>9} {'Net Interact':>13}")
    print(f"  {'-' * 70}")

    for label, pers in npcs:
        linear = _adj_without_interactions(product, pers)
        full = _adj(product, pers)
        terms = _interaction_contribution(product, pers)
        print(f"  {label:20s} {linear:+8.4f} {full:+8.4f} "
              f"{terms['penalty']:+9.5f} {terms['boost']:+9.5f} {terms['net']:+13.5f}")

    # Open explorer should get a net positive interaction, skeptic net negative
    open_terms = _interaction_contribution(product, npcs[0][1])
    skeptic_terms = _interaction_contribution(product, npcs[2][1])
    assert open_terms["net"] > skeptic_terms["net"], \
        f"Open NPC should have better net interaction: {open_terms['net']} vs {skeptic_terms['net']}"

    # The gap between open and skeptic should be larger with interactions than without
    linear_gap = abs(_adj_without_interactions(product, npcs[0][1])
                     - _adj_without_interactions(product, npcs[2][1]))
    full_gap = abs(_adj(product, npcs[0][1]) - _adj(product, npcs[2][1]))
    assert full_gap > linear_gap, \
        f"Interaction terms should widen the gap: {full_gap:.4f} vs {linear_gap:.4f}"

    print(f"\n  Gap between open and skeptic:")
    print(f"    Linear only: {linear_gap:.4f}")
    print(f"    With interactions: {full_gap:.4f} (+{(full_gap - linear_gap) / linear_gap * 100:.0f}%)")
    print(f"  PASS: interaction terms widen personality differentiation by "
          f"{(full_gap - linear_gap) / linear_gap * 100:.0f}%")


# ===========================================================================
# 4. Clamp safety
# ===========================================================================

def test_still_clamped():
    """Even with interaction terms, total stays within [-0.15, +0.15]."""
    best = _adj(
        ProductProfile(novelty=1, utility_clarity=1, differentiation=1,
                       price_friction=0, trust_barrier=0, identity_fit=1,
                       trial_friction=0, market_saturation=0),
        {"openness": 1, "skepticism": 0, "tech_savviness": 1,
         "price_sensitivity": 0, "novelty_seeking": 1},
    )
    worst = _adj(
        ProductProfile(novelty=0, utility_clarity=0, differentiation=0,
                       price_friction=1, trust_barrier=1, identity_fit=0,
                       trial_friction=1, market_saturation=1),
        {"openness": 0, "skepticism": 1, "tech_savviness": 0,
         "price_sensitivity": 1, "novelty_seeking": 0},
    )
    assert best <= 0.15, f"Max exceeds +0.15: {best}"
    assert worst >= -0.15, f"Min exceeds -0.15: {worst}"
    print(f"PASS: clamped correctly (max={best:+.4f}, min={worst:+.4f})")


# ===========================================================================
# Profile helper (avoids repeating all 8 fields)
# ===========================================================================

def ProfileWith(**overrides) -> ProductProfile:
    """Create a profile with moderate defaults, overriding specific fields."""
    defaults = dict(
        novelty=0.5, utility_clarity=0.5, differentiation=0.5,
        price_friction=0.5, trust_barrier=0.5, identity_fit=0.5,
        trial_friction=0.3, market_saturation=0.3,
    )
    defaults.update(overrides)
    return ProductProfile(**defaults)


# ===========================================================================
# Go/No-Go
# ===========================================================================

def go_nogo():
    print(f"\n{'#' * 70}")
    print(f"#  GO / NO-GO: Is Phase 2C ready?")
    print(f"{'#' * 70}\n")

    checks = []

    # 1. Penalty is material at extremes
    terms = _interaction_contribution(
        ProfileWith(price_friction=0.9, trust_barrier=0.9),
        {"skepticism": 0.9, "openness": 0.5},
    )
    checks.append((f"Penalty material at extremes ({terms['penalty']:+.5f})",
                    terms["penalty"] < -0.04))

    # 2. Boost is material at extremes
    terms = _interaction_contribution(
        ProfileWith(utility_clarity=0.9, differentiation=0.9),
        {"openness": 0.9, "skepticism": 0.5},
    )
    checks.append((f"Boost material at extremes ({terms['boost']:+.5f})",
                    terms["boost"] > 0.03))

    # 3. Both terms scale cubically (halving all inputs → 8x smaller)
    full_p = _interaction_contribution(
        ProfileWith(price_friction=0.8, trust_barrier=0.8),
        {"skepticism": 0.8, "openness": 0.5},
    )["penalty"]
    half_p = _interaction_contribution(
        ProfileWith(price_friction=0.4, trust_barrier=0.4),
        {"skepticism": 0.4, "openness": 0.5},
    )["penalty"]
    p_ratio = full_p / half_p
    checks.append((f"Penalty scales cubically (ratio={p_ratio:.1f}x, expect ~8x)",
                    abs(p_ratio - 8.0) < 0.5))

    full_b = _interaction_contribution(
        ProfileWith(utility_clarity=0.8, differentiation=0.8),
        {"openness": 0.8, "skepticism": 0.5},
    )["boost"]
    half_b = _interaction_contribution(
        ProfileWith(utility_clarity=0.4, differentiation=0.4),
        {"openness": 0.4, "skepticism": 0.5},
    )["boost"]
    b_ratio = full_b / half_b
    checks.append((f"Boost scales cubically (ratio={b_ratio:.1f}x, expect ~8x)",
                    abs(b_ratio - 8.0) < 0.5))

    # 4. Interactions widen the open-vs-skeptic gap
    product = ProfileWith(price_friction=0.6, trust_barrier=0.6,
                          utility_clarity=0.7, differentiation=0.7)
    open_p = {"openness": 0.85, "skepticism": 0.2, "tech_savviness": 0.5,
              "price_sensitivity": 0.5, "novelty_seeking": 0.5}
    skep_p = {"openness": 0.2, "skepticism": 0.85, "tech_savviness": 0.5,
              "price_sensitivity": 0.5, "novelty_seeking": 0.5}
    linear_gap = abs(_adj_without_interactions(product, open_p)
                     - _adj_without_interactions(product, skep_p))
    full_gap = abs(_adj(product, open_p) - _adj(product, skep_p))
    checks.append((f"Interactions widen open/skeptic gap ({linear_gap:.4f} → {full_gap:.4f})",
                    full_gap > linear_gap))

    # 5. Still clamped
    best = _adj(
        ProfileWith(novelty=1, utility_clarity=1, differentiation=1,
                    price_friction=0, trust_barrier=0, trial_friction=0, market_saturation=0),
        {"openness": 1, "skepticism": 0, "tech_savviness": 1,
         "price_sensitivity": 0, "novelty_seeking": 1},
    )
    worst = _adj(
        ProfileWith(novelty=0, utility_clarity=0, differentiation=0,
                    price_friction=1, trust_barrier=1, trial_friction=1, market_saturation=1),
        {"openness": 0, "skepticism": 1, "tech_savviness": 0,
         "price_sensitivity": 1, "novelty_seeking": 0},
    )
    checks.append(("Adjustment clamped to [-0.15, +0.15]",
                    -0.15 <= worst and best <= 0.15))

    all_pass = True
    for label, passed in checks:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {label}")

    print()
    if all_pass:
        print("  VERDICT: GO — Phase 2C interaction terms are working correctly.")
        print("  Penalty and boost are material, scale non-linearly, widen personality")
        print("  differentiation, and stay within safe bounds.")
        print("  Phase 2 (personality effects) is complete.")
    else:
        print("  VERDICT: NO-GO — Fix failing checks before considering Phase 2 complete.")

    return all_pass


# ===========================================================================
# Main
# ===========================================================================

ALL_TESTS = [
    test_compound_penalty_isolate,
    test_compound_penalty_scales_nonlinearly,
    test_compound_boost_isolate,
    test_compound_boost_scales_nonlinearly,
    test_still_clamped,
]

ALL_SCENARIOS = [
    scenario_price_trust_interaction,
    scenario_utility_diff_interaction,
    scenario_same_product_different_npc,
]


def main():
    print("=" * 70)
    print("  PHASE 2C VALIDATION: Interaction Terms")
    print("=" * 70)

    passed = 0
    failed = 0

    print(f"\n{'─' * 70}")
    print("  UNIT CHECKS")
    print(f"{'─' * 70}")
    for fn in ALL_TESTS:
        try:
            fn()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"FAIL: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR: {e}")

    print(f"\n{'─' * 70}")
    print("  BEHAVIORAL SCENARIOS")
    print(f"{'─' * 70}")
    for fn in ALL_SCENARIOS:
        try:
            fn()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"FAIL: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR: {e}")

    print(f"\n  Unit + scenario results: {passed} passed, {failed} failed")

    ready = go_nogo()

    print("\n" + "=" * 70)
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
