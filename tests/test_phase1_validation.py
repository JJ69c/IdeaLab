"""Phase 1 validation tests — deterministic checks for foundation fixes.

Tests the 5 changes from SIMULATION_FOUNDATION.md Phase 1:
1. would_recommend re-derivation
2. Per-pair discussion cooldown
3. Convergence includes polarization
4. NPC adjustment cap reduced to ±0.15
5. Stratified seed selection

Run:  python -m pytest tests/test_phase1_validation.py -v
  or: python tests/test_phase1_validation.py  (standalone)
"""

from __future__ import annotations

import random
import sys
from collections import Counter
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.simulation.npc import Npc, NpcPersonality, NpcState, derive_stance
from backend.simulation.convergence import ConvergenceTracker
from backend.simulation.product_profile import (
    ProductProfile,
    compute_npc_adjustment,
)
from backend.simulation.propagation import (
    DISCUSSION_COOLDOWN_TICKS,
    compute_spreads,
    select_discussion_pairs,
)
from backend.simulation.world import InjectedIdea, SimConfig, SpreadEvent, WorldState


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
# Test 1: would_recommend re-derivation
# ===========================================================================

def test_would_recommend_rederived():
    """would_recommend should update when interest_score crosses 0.65."""
    npc = _make_npc("npc_1")
    npc.state.aware = True
    npc.state.interest_score = 0.40
    npc.state.would_recommend = False

    # Simulate interest rising through discussion
    npc.state.apply_discussion_outcome(0.30, tick=2, partner_id="npc_2")
    # interest is now 0.70
    npc.state.update_would_recommend()

    assert npc.state.would_recommend is True, (
        f"NPC with interest {npc.state.interest_score:.2f} should recommend"
    )

    # Interest drops below threshold
    npc.state.apply_discussion_outcome(-0.10, tick=3, partner_id="npc_3")
    # interest is now 0.60
    npc.state.update_would_recommend()

    assert npc.state.would_recommend is False, (
        f"NPC with interest {npc.state.interest_score:.2f} should NOT recommend"
    )
    print("PASS: would_recommend correctly re-derived from interest_score")


def test_would_recommend_unblocks_spread():
    """An NPC whose LLM initially set would_recommend=False can still spread
    after interest rises above 0.65 and would_recommend is re-derived."""
    spreader = _make_npc("s1", social_influence=0.95, novelty_seeking=0.9, connections=["t1"])
    spreader.trust_weights = {"t1": 0.95}
    spreader.state.aware = True
    spreader.state.interest_score = 0.90
    spreader.state.would_recommend = False  # LLM said no initially

    target = _make_npc("t1", novelty_seeking=0.9, connections=["s1"])
    target.trust_weights = {"s1": 0.95}
    # target is unaware

    world = _make_world([spreader, target])

    # Before re-derivation: no spreads because would_recommend is False
    spreads_before = compute_spreads(world)
    assert len(spreads_before) == 0, "Should not spread when would_recommend=False"

    # Re-derive
    spreader.state.update_would_recommend()
    assert spreader.state.would_recommend is True

    # After re-derivation: run multiple attempts to confirm spread is possible
    # prob ~ 0.90 * 0.95 * 0.95 * 0.9 * 0.5 * profile_mods ≈ 0.44+
    spread_found = False
    for seed in range(20):
        random.seed(seed)
        spreads_after = compute_spreads(world)
        if len(spreads_after) > 0:
            spread_found = True
            break

    assert spread_found, (
        "After re-deriving would_recommend, NPC with interest 0.90 should spread "
        "in at least 1 of 20 attempts"
    )
    print("PASS: would_recommend re-derivation unblocks spread")


# ===========================================================================
# Test 2: Per-pair discussion cooldown
# ===========================================================================

def test_discussion_cooldown():
    """Same pair should be skipped if they discussed within last 2 ticks."""
    a = _make_npc("a", connections=["b"])
    a.trust_weights = {"b": 0.7}
    a.state.aware = True
    a.state.interest_score = 0.8  # high passion

    b = _make_npc("b", connections=["a"])
    b.trust_weights = {"a": 0.7}
    b.state.aware = True
    b.state.interest_score = 0.3  # big opinion gap

    world = _make_world([a, b], tick=3)

    # No cooldown yet — pair should be selected
    pairs = select_discussion_pairs(world, max_pairs=5)
    assert len(pairs) == 1, "Pair should be selected when no cooldown"

    # Record that they discussed at tick 3
    world.discussion_cooldowns[frozenset({"a", "b"})] = 3

    # At tick 4 (1 tick later, within cooldown) — should be skipped
    world.current_tick = 4
    pairs = select_discussion_pairs(world, max_pairs=5)
    assert len(pairs) == 0, "Pair should be SKIPPED within cooldown window"

    # At tick 5 (2 ticks later, cooldown expired) — should be selected
    world.current_tick = 5
    pairs = select_discussion_pairs(world, max_pairs=5)
    assert len(pairs) == 1, "Pair should be selected after cooldown expires"
    print("PASS: per-pair discussion cooldown works correctly")


# ===========================================================================
# Test 3: Convergence includes polarization
# ===========================================================================

def test_convergence_blocks_when_polarized():
    """A stable but polarized population should NOT be declared converged."""
    tracker = ConvergenceTracker()

    class FakeNpc:
        def __init__(self, interest: float, stance: str):
            self.state = type("S", (), {
                "interest_score": interest,
                "stance": stance,
                "objections": [],
            })()

    # Build a polarized population: half very low, half very high, stable mean
    low_group = [FakeNpc(0.15, "skeptical") for _ in range(10)]
    high_group = [FakeNpc(0.85, "willing_to_try") for _ in range(10)]
    population = low_group + high_group

    # Run several ticks with identical distribution (stable mean ~0.50)
    converged_at_any_tick = False
    for tick in range(1, 6):
        state = tracker.record_tick(tick, population)
        if state.converged:
            converged_at_any_tick = True

    assert state.polarized is True, (
        f"Population should be polarized (score={state.polarization_score:.3f})"
    )
    assert state.interest_stable is True, "Mean interest should be stable"
    assert converged_at_any_tick is False, (
        "Polarized population should NOT be declared converged"
    )
    print(
        f"PASS: polarized population blocked from convergence "
        f"(polarization={state.polarization_score:.3f}, stable={state.interest_stable})"
    )


def test_convergence_allows_consensus():
    """A stable non-polarized population SHOULD converge."""
    tracker = ConvergenceTracker()

    class FakeNpc:
        def __init__(self, interest: float, stance: str):
            self.state = type("S", (), {
                "interest_score": interest,
                "stance": stance,
                "objections": [],
            })()

    # Consensus population: everyone around 0.55-0.65
    population = [FakeNpc(0.55 + i * 0.005, "curious") for i in range(20)]

    for tick in range(1, 6):
        state = tracker.record_tick(tick, population)

    assert state.polarized is False, "Consensus population should not be polarized"
    assert state.converged is True, "Stable consensus population should converge"
    print("PASS: consensus population correctly converges")


# ===========================================================================
# Test 4: NPC adjustment cap
# ===========================================================================

def test_adjustment_cap_is_015():
    """NPC adjustment should be capped at ±0.15, not ±0.20."""
    # Create a profile that maximizes positive adjustment
    profile = ProductProfile(
        novelty=1.0, utility_clarity=1.0, differentiation=1.0,
        price_friction=0.0, trust_barrier=0.0, identity_fit=1.0,
        trial_friction=0.0, market_saturation=0.0,
    )
    # Personality that maximizes boost
    personality = {
        "openness": 1.0, "skepticism": 0.0, "tech_savviness": 1.0,
        "price_sensitivity": 0.0, "novelty_seeking": 1.0,
    }
    adj = compute_npc_adjustment(profile, personality)
    assert adj <= 0.15, f"Positive adjustment {adj} exceeds +0.15 cap"

    # Profile that maximizes negative adjustment
    profile_neg = ProductProfile(
        novelty=0.0, utility_clarity=0.0, differentiation=0.0,
        price_friction=1.0, trust_barrier=1.0, identity_fit=0.0,
        trial_friction=1.0, market_saturation=1.0,
    )
    personality_neg = {
        "openness": 0.0, "skepticism": 1.0, "tech_savviness": 0.0,
        "price_sensitivity": 1.0, "novelty_seeking": 0.0,
    }
    adj_neg = compute_npc_adjustment(profile_neg, personality_neg)
    assert adj_neg >= -0.15, f"Negative adjustment {adj_neg} exceeds -0.15 cap"

    print(f"PASS: adjustment cap is ±0.15 (max={adj:+.4f}, min={adj_neg:+.4f})")


# ===========================================================================
# Test 5: Stratified seed selection
# ===========================================================================

def test_stratified_seeds():
    """Seed group should contain at least 1 high and 1 low novelty_seeking NPC."""
    from backend.simulation.engine import _stratified_seed_selection

    # Create 20 NPCs with varying novelty_seeking
    npcs = []
    for i in range(20):
        ns = i / 19.0  # 0.0 to 1.0
        npcs.append(_make_npc(f"npc_{i}", name=f"NPC {i}", novelty_seeking=ns))

    # Run 50 trials to check stratification
    high_present = 0
    low_present = 0
    trials = 50

    for trial in range(trials):
        random.seed(trial)
        seeds = _stratified_seed_selection(npcs, count=5)
        ns_values = [s.personality.novelty_seeking for s in seeds]

        # Top quartile: ns >= 0.75; bottom quartile: ns <= 0.25
        has_high = any(ns >= 0.75 for ns in ns_values)
        has_low = any(ns <= 0.25 for ns in ns_values)
        if has_high:
            high_present += 1
        if has_low:
            low_present += 1

    assert high_present == trials, (
        f"Top quartile missing in {trials - high_present}/{trials} trials"
    )
    assert low_present == trials, (
        f"Bottom quartile missing in {trials - low_present}/{trials} trials"
    )
    print(
        f"PASS: stratified seeds always include high and low novelty_seeking "
        f"({trials}/{trials} trials)"
    )


def test_seed_stability_across_runs():
    """Different random seeds should produce diverse but bounded seed groups."""
    from backend.simulation.engine import _stratified_seed_selection

    npcs = []
    for i in range(30):
        ns = random.Random(i).uniform(0.1, 0.9)
        npcs.append(_make_npc(f"npc_{i}", name=f"NPC {i}", novelty_seeking=ns))

    seed_compositions = []
    for trial in range(20):
        random.seed(trial * 7 + 13)
        seeds = _stratified_seed_selection(npcs, count=5)
        composition = frozenset(s.id for s in seeds)
        seed_compositions.append(composition)

    # Check that we get some variety (not always the same group)
    unique_compositions = len(set(seed_compositions))
    assert unique_compositions >= 5, (
        f"Only {unique_compositions} unique seed compositions in 20 trials — "
        f"should be more diverse"
    )
    print(
        f"PASS: seed selection produces diverse groups "
        f"({unique_compositions} unique compositions in 20 trials)"
    )


# ===========================================================================
# Composite behavior checks
# ===========================================================================

def test_spread_before_vs_after():
    """Compare spread behavior with LLM-locked would_recommend vs re-derived.

    Before: NPCs whose LLM said would_recommend=False cannot spread even at
    high interest. After: they can, because would_recommend is re-derived.
    """
    npcs = []
    for i in range(10):
        npc = _make_npc(
            f"npc_{i}",
            name=f"NPC {i}",
            social_influence=0.7,
            novelty_seeking=0.6,
            connections=[f"npc_{j}" for j in range(10) if j != i],
        )
        npc.trust_weights = {f"npc_{j}": 0.6 for j in range(10) if j != i}
        npcs.append(npc)

    world = _make_world(npcs)

    # Make 5 aware with high interest but would_recommend=False (LLM locked)
    for i in range(5):
        npcs[i].state.aware = True
        npcs[i].state.interest_score = 0.80
        npcs[i].state.would_recommend = False  # LLM said no

    # Remaining 5 are unaware targets

    random.seed(42)
    spreads_locked = compute_spreads(world)

    # Now re-derive would_recommend
    for i in range(5):
        npcs[i].state.update_would_recommend()

    random.seed(42)
    spreads_unlocked = compute_spreads(world)

    print(
        f"SPREAD COMPARISON:\n"
        f"  LLM-locked would_recommend=False: {len(spreads_locked)} spreads\n"
        f"  Re-derived would_recommend=True:  {len(spreads_unlocked)} spreads"
    )
    assert len(spreads_unlocked) > len(spreads_locked), (
        "Re-derived would_recommend should produce more spreads"
    )
    print("PASS: would_recommend re-derivation increases spread")


def test_convergence_before_vs_after():
    """Polarized-but-stable population: old logic converges, new logic doesn't."""
    class FakeNpc:
        def __init__(self, interest: float, stance: str):
            self.state = type("S", (), {
                "interest_score": interest,
                "stance": stance,
                "objections": [],
            })()

    low_group = [FakeNpc(0.10, "opposed") for _ in range(10)]
    high_group = [FakeNpc(0.90, "willing_to_try") for _ in range(10)]
    population = low_group + high_group

    tracker = ConvergenceTracker()
    for tick in range(1, 6):
        state = tracker.record_tick(tick, population)

    # New logic: should NOT converge
    assert state.converged is False, "New logic should block convergence when polarized"
    assert state.polarized is True
    assert state.interest_stable is True

    # Simulate old logic (just stable + 3 ticks)
    old_would_converge = state.interest_stable and len(tracker.snapshots) >= 3
    assert old_would_converge is True, "Old logic would have converged"

    print(
        f"CONVERGENCE COMPARISON:\n"
        f"  Old logic (stable only):         converged={old_would_converge}\n"
        f"  New logic (stable + !polarized):  converged={state.converged}\n"
        f"  Polarization score: {state.polarization_score:.3f}"
    )
    print("PASS: polarized population correctly blocked from convergence")


# ===========================================================================
# Runner
# ===========================================================================

ALL_TESTS = [
    test_would_recommend_rederived,
    test_would_recommend_unblocks_spread,
    test_discussion_cooldown,
    test_convergence_blocks_when_polarized,
    test_convergence_allows_consensus,
    test_adjustment_cap_is_015,
    test_stratified_seeds,
    test_seed_stability_across_runs,
    test_spread_before_vs_after,
    test_convergence_before_vs_after,
]


def main():
    print("=" * 60)
    print("Phase 1 Foundation Validation")
    print("=" * 60)
    passed = 0
    failed = 0
    errors = []

    for test_fn in ALL_TESTS:
        name = test_fn.__name__
        print(f"\n--- {name} ---")
        try:
            test_fn()
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
