"""Phase 2A validation tests — skepticism in peer influence + openness in spread.

Tests the 2 changes from SIMULATION_FOUNDATION.md Phase 2A:
  1. Skepticism damps peer susceptibility (compute_peer_susceptibility)
  2. Openness increases spread receptiveness (compute_spread_receptiveness)

Run:  python -m pytest tests/test_phase2a_validation.py -v
  or: python tests/test_phase2a_validation.py  (standalone)
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.simulation.npc import Npc, NpcPersonality
from backend.simulation.product_profile import ProductProfile
from backend.simulation.propagation import (
    calculate_peer_influence,
    compute_peer_susceptibility,
    compute_spread_receptiveness,
    compute_spreads,
)
from backend.simulation.world import InjectedIdea, SimConfig, WorldState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_npc(
    npc_id: str,
    name: str = "Test NPC",
    novelty_seeking: float = 0.5,
    social_influence: float = 0.5,
    skepticism: float = 0.5,
    openness: float = 0.5,
    conformity: float = 0.5,
    price_sensitivity: float = 0.5,
    tech_savviness: float = 0.5,
    connections: list[str] | None = None,
    trust_weights: dict[str, float] | None = None,
) -> Npc:
    return Npc(
        id=npc_id,
        name=name,
        age=30,
        occupation="tester",
        income_level="middle",
        personality=NpcPersonality(
            openness=openness,
            skepticism=skepticism,
            tech_savviness=tech_savviness,
            price_sensitivity=price_sensitivity,
            social_influence=social_influence,
            conformity=conformity,
            novelty_seeking=novelty_seeking,
        ),
        interests=[],
        values=[],
        pain_points=[],
        communication_style="neutral",
        social_connections=connections or [],
        trust_weights=trust_weights or {},
    )


def _make_world(npcs: list[Npc], tick: int = 1) -> WorldState:
    idea = InjectedIdea(title="Test", description="A test product")
    config = SimConfig(num_ticks=8, population_size=len(npcs), seed_count=3)
    world = WorldState(
        idea=idea,
        config=config,
        npcs={n.id: n for n in npcs},
        current_tick=tick,
    )
    world.product_profile = ProductProfile(
        novelty=0.5, utility_clarity=0.5, differentiation=0.5,
        price_friction=0.3, trust_barrier=0.3, identity_fit=0.5,
        trial_friction=0.3, market_saturation=0.3,
    )
    return world


# ===========================================================================
# 1. Skepticism in peer influence
# ===========================================================================

def test_susceptibility_helper_monotonic():
    """compute_peer_susceptibility decreases as skepticism rises."""
    low  = compute_peer_susceptibility(conformity=0.7, skepticism=0.2)
    mid  = compute_peer_susceptibility(conformity=0.7, skepticism=0.5)
    high = compute_peer_susceptibility(conformity=0.7, skepticism=0.9)

    assert low > mid > high, (
        f"Should decrease: low={low:.4f} > mid={mid:.4f} > high={high:.4f}"
    )
    assert all(v > 0 for v in [low, mid, high]), "All should remain positive"
    print(f"PASS: susceptibility decreases with skepticism ({low:.4f} > {mid:.4f} > {high:.4f})")


def test_skepticism_reduces_peer_influence_delta():
    """Full integration: higher skepticism → smaller peer influence delta."""
    def run(skep: float) -> float:
        target = _make_npc(
            "target", conformity=0.7, skepticism=skep,
            connections=["peer"], trust_weights={"peer": 0.7},
        )
        target.state.aware = True
        target.state.interest_score = 0.40

        peer = _make_npc("peer", social_influence=0.7, connections=["target"])
        peer.state.aware = True
        peer.state.interest_score = 0.85

        return calculate_peer_influence(target, _make_world([target, peer]))

    d_low  = run(0.1)
    d_mid  = run(0.5)
    d_high = run(0.9)

    assert d_low > d_mid > d_high, (
        f"Delta should shrink: {d_low:.4f} > {d_mid:.4f} > {d_high:.4f}"
    )
    print(f"PASS: peer influence delta shrinks with skepticism ({d_low:.4f} > {d_mid:.4f} > {d_high:.4f})")


def test_susceptibility_before_vs_after():
    """Before/after comparison: old (conformity * 0.3) vs new formula."""
    cases = [
        ("trusting follower",    0.8, 0.2),
        ("average person",       0.5, 0.5),
        ("skeptical conformist", 0.8, 0.8),
        ("independent thinker",  0.3, 0.7),
    ]

    print("SUSCEPTIBILITY BEFORE vs AFTER:")
    for label, conf, skep in cases:
        old = conf * 0.3
        new = compute_peer_susceptibility(conf, skep)
        print(f"  {label:25s}  old={old:.4f}  new={new:.4f}  diff={new - old:+.4f}")

    # Same conformity (0.8): trusting vs skeptical should diverge
    trusting  = compute_peer_susceptibility(0.8, 0.2)
    skeptical = compute_peer_susceptibility(0.8, 0.8)
    gap = trusting - skeptical
    assert gap > 0.02, f"Gap too small: {gap:.4f}"
    print(f"PASS: same conformity, skeptic vs trusting gap = {gap:.4f}")


# ===========================================================================
# 2. Openness in spread receptiveness
# ===========================================================================

def test_receptiveness_helper_blending():
    """Receptiveness blends novelty_seeking (70%) and openness (30%)."""
    ns_only   = compute_spread_receptiveness(novelty_seeking=0.9, openness=0.1)
    open_only = compute_spread_receptiveness(novelty_seeking=0.1, openness=0.9)
    both_high = compute_spread_receptiveness(novelty_seeking=0.9, openness=0.9)
    both_low  = compute_spread_receptiveness(novelty_seeking=0.1, openness=0.1)

    assert both_high > ns_only > both_low
    assert both_high > open_only > both_low
    assert ns_only > open_only, "novelty_seeking should weigh more than openness"

    print(
        f"PASS: receptiveness blends correctly "
        f"(both_high={both_high:.3f}, ns={ns_only:.3f}, open={open_only:.3f}, both_low={both_low:.3f})"
    )


def test_openness_increases_spread_count():
    """Over many trials, high-openness targets receive more spreads."""
    def count(target_openness: float, trials: int = 200) -> int:
        total = 0
        for seed in range(trials):
            src = _make_npc("s1", social_influence=0.7, connections=["t1"])
            src.trust_weights = {"t1": 0.6}
            src.state.aware = True
            src.state.interest_score = 0.75
            src.state.would_recommend = True

            tgt = _make_npc("t1", novelty_seeking=0.5, openness=target_openness, connections=["s1"])
            tgt.trust_weights = {"s1": 0.6}

            random.seed(seed)
            total += len(compute_spreads(_make_world([src, tgt])))
        return total

    low  = count(0.1)
    high = count(0.9)

    assert high > low, f"High openness should spread more: {high} vs {low}"
    print(f"PASS: openness boosts spread (open=0.1: {low}/200, open=0.9: {high}/200)")


def test_spread_before_vs_after():
    """Before/after: old (novelty_seeking only) vs new (novelty_seeking + openness)."""
    # NPC with low novelty_seeking but high openness — old formula would give low
    # receptiveness, new formula should give higher.
    ns = 0.2
    openness = 0.8

    old_receptiveness = ns  # old: just novelty_seeking
    new_receptiveness = compute_spread_receptiveness(ns, openness)

    assert new_receptiveness > old_receptiveness, (
        f"New should be higher for open non-novelty-seeker: {new_receptiveness:.3f} > {old_receptiveness:.3f}"
    )
    boost = (new_receptiveness - old_receptiveness) / old_receptiveness * 100
    print(
        f"PASS: open non-novelty-seeker gets {boost:.0f}% receptiveness boost "
        f"(old={old_receptiveness:.3f}, new={new_receptiveness:.3f})"
    )


# ===========================================================================
# Cross-cutting: Follower vs Skeptic under same influence source
# ===========================================================================

def test_follower_vs_skeptic_peer_influence():
    """Same influence source, same conformity — only skepticism differs."""
    archetypes = [
        ("trusting follower",  0.8, 0.15),
        ("average person",     0.5, 0.50),
        ("skeptical conformist", 0.7, 0.80),
        ("independent skeptic",  0.2, 0.85),
    ]

    print("\nFOLLOWER vs SKEPTIC (same peer at 0.85 interest, trust=0.7):")
    deltas = []
    for label, conf, skep in archetypes:
        target = _make_npc(
            "target", conformity=conf, skepticism=skep,
            connections=["peer"], trust_weights={"peer": 0.7},
        )
        target.state.aware = True
        target.state.interest_score = 0.40

        peer = _make_npc("peer", social_influence=0.7, connections=["target"])
        peer.state.aware = True
        peer.state.interest_score = 0.85

        delta = calculate_peer_influence(target, _make_world([target, peer]))
        deltas.append(delta)
        print(f"  {label:25s}  conf={conf} skep={skep}  delta={delta:+.4f}")

    assert deltas[0] > deltas[-1], "Follower should shift more than skeptic"
    ratio = deltas[0] / max(deltas[-1], 0.0001)
    print(f"PASS: follower shifts {ratio:.1f}x more than independent skeptic")


def test_follower_vs_skeptic_spread_receptiveness():
    """Same novelty_seeking — only openness differs."""
    ns = 0.5
    archetypes = [
        ("open explorer",    0.85),
        ("average openness", 0.50),
        ("closed-minded",    0.15),
    ]

    print("\nSPREAD RECEPTIVENESS by openness (novelty_seeking=0.5):")
    values = []
    for label, op in archetypes:
        r = compute_spread_receptiveness(ns, op)
        values.append(r)
        print(f"  {label:20s}  openness={op}  receptiveness={r:.3f}")

    assert values[0] > values[1] > values[2], "Should decrease with openness"
    print("PASS: receptiveness ranks correctly by openness")


# ===========================================================================
# Runner
# ===========================================================================

ALL_TESTS = [
    # 1. Skepticism in peer influence
    test_susceptibility_helper_monotonic,
    test_skepticism_reduces_peer_influence_delta,
    test_susceptibility_before_vs_after,
    # 2. Openness in spread receptiveness
    test_receptiveness_helper_blending,
    test_openness_increases_spread_count,
    test_spread_before_vs_after,
    # Cross-cutting
    test_follower_vs_skeptic_peer_influence,
    test_follower_vs_skeptic_spread_receptiveness,
]


def main():
    print("=" * 60)
    print("Phase 2A: Personality Effects Validation")
    print("=" * 60)
    passed = 0
    failed = 0
    errors = []

    for fn in ALL_TESTS:
        name = fn.__name__
        print(f"\n--- {name} ---")
        try:
            fn()
            passed += 1
        except AssertionError as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"FAIL: {e}")
        except Exception as e:
            failed += 1
            errors.append((name, f"ERROR: {e}"))
            print(f"ERROR: {e}")

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(ALL_TESTS)}")
    if errors:
        print("\nFailures:")
        for name, msg in errors:
            print(f"  {name}: {msg}")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
