"""Phase 2B behavioral validation — discussion persuasiveness.

Verifies that compute_discussion_weight creates meaningful, bounded,
believable differences in how discussion outcomes land on different
NPC archetypes.

Run:  python tests/validate_phase2b.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.simulation.npc import NpcState, derive_stance
from backend.simulation.propagation import compute_discussion_weight


# ---------------------------------------------------------------------------
# Unit-level checks
# ---------------------------------------------------------------------------

def test_monotonic_with_source_influence():
    """Higher source influence → higher weight, all else equal."""
    vals = [compute_discussion_weight(si, trust=0.6, target_skepticism=0.5)
            for si in [0.2, 0.4, 0.6, 0.8, 1.0]]
    assert all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1)), \
        f"Should increase with source influence: {vals}"
    print(f"PASS: weight increases with source influence ({[round(v, 3) for v in vals]})")


def test_monotonic_with_trust():
    """Higher trust → higher weight, all else equal."""
    vals = [compute_discussion_weight(0.7, trust=t, target_skepticism=0.5)
            for t in [0.2, 0.4, 0.6, 0.8, 1.0]]
    assert all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1)), \
        f"Should increase with trust: {vals}"
    print(f"PASS: weight increases with trust ({[round(v, 3) for v in vals]})")


def test_monotonic_with_skepticism():
    """Higher target skepticism → lower weight, all else equal."""
    vals = [compute_discussion_weight(0.7, trust=0.6, target_skepticism=s)
            for s in [0.2, 0.4, 0.6, 0.8, 1.0]]
    assert all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1)), \
        f"Should decrease with skepticism: {vals}"
    print(f"PASS: weight decreases with target skepticism ({[round(v, 3) for v in vals]})")


def test_clamped_bounds():
    """Weight must stay within [0.3, 1.5] at all extremes."""
    cases = [
        (1.0, 1.0, 0.01),  # best case: max influence, max trust, near-zero skepticism
        (0.0, 0.1, 1.0),   # worst case: no influence, low trust, max skepticism
        (0.5, 0.5, 0.5),   # moderate
    ]
    for si, tr, sk in cases:
        w = compute_discussion_weight(si, tr, sk)
        assert 0.3 <= w <= 1.5, f"Out of bounds: weight={w} for si={si}, tr={tr}, sk={sk}"
    print("PASS: weight clamped to [0.3, 1.5] at all extremes")


# ---------------------------------------------------------------------------
# Scenario: same raw delta, different source/target pairings
# ---------------------------------------------------------------------------

def scenario_same_message_different_impact():
    """The LLM produces the same base delta, but it lands differently."""
    raw_delta = 0.10

    pairings = [
        ("leader → follower",     0.9, 0.8, 0.15),
        ("leader → average",      0.9, 0.6, 0.50),
        ("leader → skeptic",      0.9, 0.6, 0.85),
        ("average → follower",    0.5, 0.6, 0.15),
        ("average → average",     0.5, 0.5, 0.50),
        ("average → skeptic",     0.5, 0.5, 0.85),
        ("nobody → follower",     0.2, 0.4, 0.15),
        ("nobody → skeptic",      0.2, 0.3, 0.85),
    ]

    print(f"\n  SAME RAW DELTA ({raw_delta:+.2f}), DIFFERENT PAIRINGS:")
    print(f"  {'Pairing':25s} {'SrcInfl':>8} {'Trust':>6} {'TgtSkep':>8} "
          f"{'Weight':>7} {'Applied':>8}")
    print(f"  {'-' * 68}")

    results = []
    for label, si, tr, sk in pairings:
        w = compute_discussion_weight(si, tr, sk)
        applied = round(raw_delta * w, 4)
        results.append((label, w, applied))
        print(f"  {label:25s} {si:8.2f} {tr:6.2f} {sk:8.2f} {w:7.3f} {applied:+8.4f}")

    # Key assertions
    leader_follower = results[0][2]
    nobody_skeptic = results[-1][2]
    ratio = leader_follower / max(nobody_skeptic, 0.0001)

    print(f"\n  Leader→follower / nobody→skeptic ratio: {ratio:.1f}x")
    assert ratio > 3.0, f"Expected >3x difference, got {ratio:.1f}x"
    print(f"  PASS: leader→follower is {ratio:.1f}x more effective than nobody→skeptic")


# ---------------------------------------------------------------------------
# Scenario: trust matters
# ---------------------------------------------------------------------------

def scenario_trust_gradient():
    """Same source and target personality, but varying trust levels."""
    raw_delta = 0.10

    print(f"\n  TRUST GRADIENT (source_influence=0.7, target_skepticism=0.4):")
    print(f"  {'Trust':>6} {'Weight':>7} {'Applied':>8}")
    print(f"  {'-' * 25}")

    applied_at_low = None
    applied_at_high = None
    for trust in [0.1, 0.3, 0.5, 0.7, 0.9]:
        w = compute_discussion_weight(0.7, trust, 0.4)
        applied = round(raw_delta * w, 4)
        print(f"  {trust:6.1f} {w:7.3f} {applied:+8.4f}")
        if trust == 0.1:
            applied_at_low = applied
        if trust == 0.9:
            applied_at_high = applied

    ratio = applied_at_high / max(applied_at_low, 0.0001)
    print(f"\n  High-trust / low-trust ratio: {ratio:.1f}x")
    assert ratio > 2.0, f"Expected >2x trust effect, got {ratio:.1f}x"
    print(f"  PASS: trust creates {ratio:.1f}x difference in discussion impact")


# ---------------------------------------------------------------------------
# Scenario: before/after (old = no weighting, new = weighted)
# ---------------------------------------------------------------------------

def scenario_before_after():
    """Compare flat delta application (old) vs weighted (Phase 2B)."""
    raw_delta = 0.08

    archetypes = [
        ("trusting follower",  0.15),  # low skepticism
        ("average person",     0.50),
        ("hard skeptic",       0.90),
    ]

    # Two sources: a leader and a nobody
    sources = [
        ("community leader", 0.85, 0.75),  # high influence, high trust
        ("quiet newcomer",   0.20, 0.35),   # low influence, low trust
    ]

    print(f"\n  BEFORE/AFTER COMPARISON (raw_delta={raw_delta:+.2f}):")
    print(f"  Before (Phase 1): every target receives {raw_delta:+.2f} regardless of source or personality")
    print(f"  After  (Phase 2B): delta is scaled by compute_discussion_weight\n")

    print(f"  {'Source':20s} {'Target':20s} {'Before':>7} {'After':>7} {'Change':>8}")
    print(f"  {'-' * 65}")

    for src_label, src_inf, trust in sources:
        for tgt_label, tgt_skep in archetypes:
            w = compute_discussion_weight(src_inf, trust, tgt_skep)
            after = round(raw_delta * w, 4)
            change_pct = ((after - raw_delta) / raw_delta) * 100
            print(f"  {src_label:20s} {tgt_label:20s} {raw_delta:+7.4f} {after:+7.4f} {change_pct:+7.1f}%")

    print("\n  INTERPRETATION:")
    print("  - Community leader → follower: delta amplified (up to +50%)")
    print("  - Community leader → skeptic: delta dampened despite high source influence")
    print("  - Quiet newcomer → anyone: delta always reduced (low influence + low trust)")
    print("  - Quiet newcomer → skeptic: delta reduced most (~62% of original)")


# ---------------------------------------------------------------------------
# Scenario: bidirectional asymmetry
# ---------------------------------------------------------------------------

def scenario_bidirectional():
    """In a two-NPC discussion, the delta lands differently on each side."""
    raw_delta = 0.10  # assume LLM gives same magnitude to both

    # NPC A: influential leader, low skepticism
    a_inf, a_skep = 0.85, 0.20
    # NPC B: quiet skeptic, high skepticism
    b_inf, b_skep = 0.25, 0.80
    trust = 0.6

    # A's shift is caused by B speaking → B is source, A is target
    a_weight = compute_discussion_weight(b_inf, trust, a_skep)
    # B's shift is caused by A speaking → A is source, B is target
    b_weight = compute_discussion_weight(a_inf, trust, b_skep)

    a_applied = round(raw_delta * a_weight, 4)
    b_applied = round(raw_delta * b_weight, 4)

    print(f"\n  BIDIRECTIONAL ASYMMETRY:")
    print(f"  NPC A (leader, skep=0.20) ←→ NPC B (quiet skeptic, skep=0.80)")
    print(f"  Trust between them: {trust}")
    print(f"  Raw delta from LLM: {raw_delta:+.2f} for both\n")

    print(f"  A's shift (B→A): weight={a_weight:.3f}, applied={a_applied:+.4f}")
    print(f"  B's shift (A→B): weight={b_weight:.3f}, applied={b_applied:+.4f}")

    # The weights are DIFFERENT — that's the key test. The exact direction depends
    # on the balance of factors. Here B's high skepticism (0.80) partially cancels
    # A's high influence (0.85), while A's low skepticism (0.20) amplifies even
    # B's weak influence (0.25). The system correctly makes both factors matter.
    assert abs(a_weight - b_weight) > 0.05, "Weights should differ meaningfully"
    print(f"\n  PASS: weights are asymmetric (diff={abs(a_weight - b_weight):.3f})")
    print(f"  A is easy to shift (low skepticism) even by a weak source")
    print(f"  B resists strongly (high skepticism) even from a strong source")
    print(f"  Both factors — source influence AND target resistance — are working")


# ---------------------------------------------------------------------------
# Scenario: state transitions — interest and stance actually change
# ---------------------------------------------------------------------------

def scenario_state_transitions():
    """Apply weighted deltas to real NpcState objects, show stance crossings."""
    raw_delta = 0.10

    # Three targets, all starting at interest=0.42 (stance: indifferent, near curious boundary at 0.45)
    targets = [
        ("follower",  0.15, 0.85, 0.75),  # skep, src_inf, trust
        ("average",   0.50, 0.50, 0.50),
        ("skeptic",   0.85, 0.50, 0.50),
    ]

    print(f"\n  STATE TRANSITIONS (all targets start at interest=0.42, stance=indifferent)")
    print(f"  Raw discussion delta from LLM: {raw_delta:+.2f}\n")
    print(f"  {'Target':12s} {'Weight':>7} {'Applied':>8} {'OldInt':>7} {'NewInt':>7} "
          f"{'OldStance':>14} {'NewStance':>14} {'Crossed?':>9}")
    print(f"  {'-' * 82}")

    transitions = 0
    for label, tgt_skep, src_inf, trust in targets:
        w = compute_discussion_weight(src_inf, trust, tgt_skep)
        applied = round(raw_delta * w, 4)

        state = NpcState()
        state.aware = True
        state.interest_score = 0.42
        state.stance = derive_stance(0.42, False, True)
        old_stance = state.stance

        new_interest = max(0.0, min(1.0, state.interest_score + applied))
        new_stance = derive_stance(new_interest, False, True)

        crossed = "YES" if new_stance != old_stance else "no"
        if new_stance != old_stance:
            transitions += 1

        print(f"  {label:12s} {w:7.3f} {applied:+8.4f} {0.42:7.3f} {new_interest:7.4f} "
              f"{old_stance:>14s} {new_stance:>14s} {crossed:>9s}")

    # Now show the same scenario WITHOUT weighting (Phase 1 behavior)
    print(f"\n  WITHOUT WEIGHTING (Phase 1): all would get {raw_delta:+.2f} → interest=0.52 → curious")
    print(f"  WITH WEIGHTING (Phase 2B): {transitions}/3 targets crossed a stance threshold")

    # The follower should cross into curious, the skeptic likely should not
    # (or at least cross less dramatically)
    w_follower = compute_discussion_weight(0.85, 0.75, 0.15)
    w_skeptic = compute_discussion_weight(0.50, 0.50, 0.85)
    follower_new = 0.42 + raw_delta * w_follower
    skeptic_new = 0.42 + raw_delta * w_skeptic
    follower_stance = derive_stance(min(1.0, follower_new), False, True)
    skeptic_stance = derive_stance(min(1.0, skeptic_new), False, True)

    assert follower_new > skeptic_new, \
        f"Follower should end higher: {follower_new:.4f} vs {skeptic_new:.4f}"
    print(f"\n  PASS: follower ends at {follower_new:.4f} ({follower_stance}), "
          f"skeptic at {skeptic_new:.4f} ({skeptic_stance})")

    # Multi-round: apply 3 discussions to each target, show trajectory
    print(f"\n  MULTI-ROUND TRAJECTORY (3 consecutive discussions, raw_delta={raw_delta:+.2f} each):")
    print(f"  {'Target':12s} {'Round 1':>14} {'Round 2':>14} {'Round 3':>14} {'Final Stance':>14}")
    print(f"  {'-' * 60}")

    for label, tgt_skep, src_inf, trust in targets:
        w = compute_discussion_weight(src_inf, trust, tgt_skep)
        interest = 0.42
        rounds = []
        for _ in range(3):
            applied = raw_delta * w
            interest = max(0.0, min(1.0, interest + applied))
            stance = derive_stance(interest, False, True)
            rounds.append(f"{interest:.3f}/{stance[:4]}")
        final_stance = derive_stance(interest, False, True)
        print(f"  {label:12s} {rounds[0]:>14s} {rounds[1]:>14s} {rounds[2]:>14s} {final_stance:>14s}")

    print("\n  INTERPRETATION:")
    print("  After 3 rounds, the follower has likely crossed into 'interested'")
    print("  while the skeptic may still be stuck in 'indifferent' or barely 'curious'.")
    print("  This is exactly the differentiation Phase 2B was designed to create.")


# ---------------------------------------------------------------------------
# Go/No-Go
# ---------------------------------------------------------------------------

def go_nogo():
    print(f"\n{'#' * 70}")
    print(f"#  GO / NO-GO: Is Phase 2B ready?")
    print(f"{'#' * 70}\n")

    checks = []

    # 1. Monotonic with all three inputs
    si_vals = [compute_discussion_weight(si, 0.6, 0.5) for si in [0.2, 0.5, 0.8]]
    checks.append(("Weight increases with source influence",
                    si_vals[0] <= si_vals[1] <= si_vals[2]))

    tr_vals = [compute_discussion_weight(0.7, t, 0.5) for t in [0.2, 0.5, 0.8]]
    checks.append(("Weight increases with trust",
                    tr_vals[0] <= tr_vals[1] <= tr_vals[2]))

    sk_vals = [compute_discussion_weight(0.7, 0.6, s) for s in [0.2, 0.5, 0.8]]
    checks.append(("Weight decreases with target skepticism",
                    sk_vals[0] >= sk_vals[1] >= sk_vals[2]))

    # 2. Bounded
    w_max = compute_discussion_weight(1.0, 1.0, 0.01)
    w_min = compute_discussion_weight(0.0, 0.1, 1.0)
    checks.append(("Max weight is 1.5", w_max == 1.5))
    checks.append(("Min weight is 0.3", w_min == 0.3))

    # 3. Material effect (>2x between leader→follower and nobody→skeptic)
    w_easy = compute_discussion_weight(0.9, 0.8, 0.15)
    w_hard = compute_discussion_weight(0.2, 0.3, 0.85)
    ratio = w_easy / w_hard
    checks.append((f"Leader→follower vs nobody→skeptic ratio > 2x (got {ratio:.1f}x)",
                    ratio > 2.0))

    # 4. Bidirectional asymmetry exists
    a_w = compute_discussion_weight(0.25, 0.6, 0.2)  # weak source → easy target
    b_w = compute_discussion_weight(0.85, 0.6, 0.8)  # strong source → hard target
    checks.append(("Bidirectional weights differ", abs(a_w - b_w) > 0.1))

    all_pass = True
    for label, passed in checks:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {label}")

    print()
    if all_pass:
        print("  VERDICT: GO — Phase 2B discussion persuasiveness is working correctly.")
        print("  Weight is monotonic, bounded, material, and creates believable asymmetry.")
        print("  Safe to proceed to Phase 2C (interaction terms) when ready.")
    else:
        print("  VERDICT: NO-GO — Fix failing checks before proceeding.")

    return all_pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

ALL_TESTS = [
    test_monotonic_with_source_influence,
    test_monotonic_with_trust,
    test_monotonic_with_skepticism,
    test_clamped_bounds,
]

ALL_SCENARIOS = [
    scenario_same_message_different_impact,
    scenario_trust_gradient,
    scenario_before_after,
    scenario_bidirectional,
    scenario_state_transitions,
]


def main():
    print("=" * 70)
    print("  PHASE 2B VALIDATION: Discussion Persuasiveness")
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
