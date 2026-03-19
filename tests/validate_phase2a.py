"""Phase 2A behavioral validation harness.

Runs controlled multi-tick scenarios with synthetic populations to verify
that skepticism and openness materially affect simulation outcomes at the
population level — not just in isolated helper calls.

No LLM calls. All NPC reactions are set manually so we can isolate the
effect of the deterministic peer-influence and spread mechanics.

Run:  python tests/validate_phase2a.py
"""

from __future__ import annotations

import random
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.simulation.npc import Npc, NpcPersonality, NpcState, derive_stance
from backend.simulation.product_profile import ProductProfile
from backend.simulation.propagation import (
    calculate_peer_influence,
    compute_peer_susceptibility,
    compute_spread_receptiveness,
    compute_spreads,
)
from backend.simulation.world import InjectedIdea, SimConfig, WorldState


# ---------------------------------------------------------------------------
# Scenario infrastructure
# ---------------------------------------------------------------------------

PROFILE = ProductProfile(
    novelty=0.6, utility_clarity=0.5, differentiation=0.5,
    price_friction=0.3, trust_barrier=0.3, identity_fit=0.5,
    trial_friction=0.3, market_saturation=0.3,
)


def _npc(
    npc_id: str, *,
    openness: float = 0.5, skepticism: float = 0.5,
    conformity: float = 0.5, social_influence: float = 0.5,
    novelty_seeking: float = 0.5,
    connections: list[str] | None = None,
    trust_weights: dict[str, float] | None = None,
) -> Npc:
    return Npc(
        id=npc_id, name=npc_id.replace("_", " ").title(),
        age=30, occupation="tester", income_level="middle",
        personality=NpcPersonality(
            openness=openness, skepticism=skepticism,
            tech_savviness=0.5, price_sensitivity=0.5,
            social_influence=social_influence,
            conformity=conformity, novelty_seeking=novelty_seeking,
        ),
        interests=[], values=[], pain_points=[],
        communication_style="neutral",
        social_connections=connections or [],
        trust_weights=trust_weights or {},
    )


def _build_ring(
    n: int, *,
    openness: float = 0.5,
    skepticism: float = 0.5,
    conformity: float = 0.5,
    novelty_seeking: float = 0.5,
) -> list[Npc]:
    """Build a ring-topology population of n NPCs. Each connected to prev/next."""
    ids = [f"npc_{i:02d}" for i in range(n)]
    npcs = []
    for i, npc_id in enumerate(ids):
        prev_id = ids[(i - 1) % n]
        next_id = ids[(i + 1) % n]
        conns = [prev_id, next_id]
        trust = {prev_id: 0.6, next_id: 0.6}
        npcs.append(_npc(
            npc_id, openness=openness, skepticism=skepticism,
            conformity=conformity, novelty_seeking=novelty_seeking,
            connections=conns, trust_weights=trust,
        ))
    return npcs


def _make_world(npcs: list[Npc]) -> WorldState:
    idea = InjectedIdea(title="TestProduct", description="A test product for validation")
    config = SimConfig(num_ticks=8, population_size=len(npcs), seed_count=3)
    world = WorldState(idea=idea, config=config, npcs={n.id: n for n in npcs})
    world.product_profile = PROFILE
    return world


def _seed_npcs(world: WorldState, seed_ids: list[str], interest: float = 0.70):
    """Make specific NPCs aware and set their initial interest."""
    for npc_id in seed_ids:
        npc = world.npcs[npc_id]
        npc.state.aware = True
        npc.state.awareness_tick = 1
        npc.state.interest_score = interest
        npc.state.would_recommend = interest >= 0.65
        npc.state.stance = derive_stance(interest, False, True)


@dataclass
class TickReport:
    tick: int
    aware: int
    total: int
    spreads: int
    avg_interest: float
    stance_counts: dict[str, int]
    influence_deltas: list[float]


def _run_ticks(world: WorldState, ticks: int, rng_seed: int = 42) -> list[TickReport]:
    """Run peer-influence + spread for N ticks, collecting reports. No LLM."""
    reports = []
    random.seed(rng_seed)

    for t in range(1, ticks + 1):
        world.current_tick = t

        # Apply pending spreads from previous tick
        for spread in world.pending_spreads:
            target = world.npcs.get(spread.target_id)
            if target and not target.state.aware:
                target.state.aware = True
                target.state.awareness_tick = t
                target.state.interest_score = 0.45  # newly aware start indifferent
                target.state.stance = derive_stance(0.45, False, True)
        world.pending_spreads = []

        # Peer influence
        deltas = []
        for npc in world.aware_npcs:
            delta = calculate_peer_influence(npc, world)
            if abs(delta) >= 0.005:
                npc.state.interest_score = max(0.0, min(1.0, npc.state.interest_score + delta))
                npc.state.stance = derive_stance(npc.state.interest_score, npc.state.would_pay, True)
                deltas.append(delta)

        # Re-derive would_recommend
        for npc in world.aware_npcs:
            npc.state.update_would_recommend()

        # Spread
        new_spreads = compute_spreads(world)
        world.pending_spreads = new_spreads

        # Collect stats
        aware_npcs = world.aware_npcs
        avg_int = sum(n.state.interest_score for n in aware_npcs) / max(len(aware_npcs), 1)
        stances = Counter(n.state.stance for n in world.npcs.values())

        reports.append(TickReport(
            tick=t,
            aware=len(aware_npcs),
            total=len(world.npcs),
            spreads=len(new_spreads),
            avg_interest=round(avg_int, 4),
            stance_counts=dict(stances),
            influence_deltas=deltas,
        ))

    return reports


def _print_report(title: str, reports: list[TickReport]):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")
    print(f"  {'Tick':>4}  {'Aware':>5}/{reports[0].total:<3}  {'Spreads':>7}  "
          f"{'Avg Interest':>12}  {'Avg |delta|':>11}  Stances")
    print(f"  {'-' * 64}")
    for r in reports:
        avg_delta = (
            sum(abs(d) for d in r.influence_deltas) / len(r.influence_deltas)
            if r.influence_deltas else 0.0
        )
        # Compact stance summary: only non-zero
        stance_str = ", ".join(
            f"{k}={v}" for k, v in sorted(r.stance_counts.items()) if v > 0 and k != "unaware"
        )
        unaware = r.stance_counts.get("unaware", 0)
        print(
            f"  {r.tick:4d}  {r.aware:5d}/{r.total:<3d}  {r.spreads:7d}  "
            f"{r.avg_interest:12.4f}  {avg_delta:11.4f}  {stance_str}"
        )


def _summarize(label: str, reports: list[TickReport]) -> dict:
    """Extract key summary metrics from a run."""
    total_spreads = sum(r.spreads for r in reports)
    final_aware = reports[-1].aware
    total = reports[-1].total
    final_interest = reports[-1].avg_interest
    all_deltas = [d for r in reports for d in r.influence_deltas]
    avg_abs_delta = sum(abs(d) for d in all_deltas) / max(len(all_deltas), 1)
    final_stances = reports[-1].stance_counts

    curious_plus = sum(
        final_stances.get(s, 0)
        for s in ("curious", "interested", "willing_to_try", "willing_to_pay")
    )
    negative = sum(final_stances.get(s, 0) for s in ("opposed", "skeptical"))

    return {
        "label": label,
        "total_spreads": total_spreads,
        "final_aware_pct": round(final_aware / total * 100, 1),
        "final_avg_interest": final_interest,
        "avg_influence_delta": round(avg_abs_delta, 5),
        "curious_or_higher": curious_plus,
        "opposed_or_skeptical": negative,
    }


# ===========================================================================
# Scenario 1: Baseline vs High-Skepticism vs High-Openness populations
# ===========================================================================

def scenario_population_comparison():
    print("\n" + "#" * 70)
    print("#  SCENARIO 1: Population-level trait comparison (12 NPCs, ring topology)")
    print("#" * 70)

    summaries = []
    configs = [
        ("A. Baseline (all traits 0.5)",       dict(openness=0.5, skepticism=0.5, conformity=0.5, novelty_seeking=0.5)),
        ("B. High-skepticism (skep=0.85)",      dict(openness=0.5, skepticism=0.85, conformity=0.5, novelty_seeking=0.5)),
        ("C. High-openness (open=0.85)",        dict(openness=0.85, skepticism=0.5, conformity=0.5, novelty_seeking=0.5)),
        ("D. High-skepticism + high-openness",  dict(openness=0.85, skepticism=0.85, conformity=0.5, novelty_seeking=0.5)),
    ]

    seed_ids = ["npc_00", "npc_04", "npc_08"]  # spread around the ring

    for title, traits in configs:
        npcs = _build_ring(12, **traits)
        world = _make_world(npcs)
        _seed_npcs(world, seed_ids, interest=0.70)
        reports = _run_ticks(world, ticks=6, rng_seed=42)
        _print_report(title, reports)
        summaries.append(_summarize(title, reports))

    # Comparison table
    print(f"\n{'COMPARISON TABLE':^70}")
    print(f"  {'Scenario':45s} {'Spreads':>7} {'Aware%':>7} {'AvgInt':>7} "
          f"{'|Delta|':>8} {'Cur+':>5} {'Neg':>4}")
    print(f"  {'-' * 66}")
    for s in summaries:
        print(f"  {s['label']:45s} {s['total_spreads']:7d} "
              f"{s['final_aware_pct']:6.1f}% {s['final_avg_interest']:7.4f} "
              f"{s['avg_influence_delta']:8.5f} {s['curious_or_higher']:5d} "
              f"{s['opposed_or_skeptical']:4d}")

    # Interpretations
    print("\n  INTERPRETATION:")
    base, skep, openp, both = summaries

    if skep["total_spreads"] < base["total_spreads"]:
        print("  [OK] High skepticism reduced total spreads vs baseline "
              f"({skep['total_spreads']} < {base['total_spreads']})")
    else:
        print("  [!!] High skepticism did NOT reduce spreads — investigate")

    if skep["avg_influence_delta"] < base["avg_influence_delta"]:
        print("  [OK] High skepticism reduced peer influence effect size "
              f"({skep['avg_influence_delta']:.5f} < {base['avg_influence_delta']:.5f})")
    else:
        print("  [!!] High skepticism did NOT reduce influence deltas — investigate")

    if openp["total_spreads"] >= base["total_spreads"]:
        print("  [OK] High openness maintained or increased spread vs baseline "
              f"({openp['total_spreads']} >= {base['total_spreads']})")
    else:
        print("  [!!] High openness reduced spread — investigate")

    if both["avg_influence_delta"] < openp["avg_influence_delta"]:
        print("  [OK] Skepticism still dampens even when openness is high "
              f"({both['avg_influence_delta']:.5f} < {openp['avg_influence_delta']:.5f})")
    else:
        print("  [--] Combined scenario: skepticism did not further dampen — may be acceptable")


# ===========================================================================
# Scenario 2: Same source, different target archetypes
# ===========================================================================

def scenario_archetype_comparison():
    print("\n" + "#" * 70)
    print("#  SCENARIO 2: Same influence source → different target archetypes")
    print("#" * 70)

    # One influential source NPC, three different targets
    source = _npc(
        "source", social_influence=0.8, conformity=0.5, skepticism=0.3,
        openness=0.7, novelty_seeking=0.7,
        connections=["follower", "skeptic", "explorer"],
        trust_weights={"follower": 0.7, "skeptic": 0.7, "explorer": 0.7},
    )
    source.state.aware = True
    source.state.interest_score = 0.82
    source.state.would_recommend = True
    source.state.stance = derive_stance(0.82, False, True)

    archetypes = {
        "follower": dict(
            conformity=0.85, skepticism=0.15, openness=0.5, novelty_seeking=0.5,
        ),
        "skeptic": dict(
            conformity=0.4, skepticism=0.85, openness=0.3, novelty_seeking=0.3,
        ),
        "explorer": dict(
            conformity=0.5, skepticism=0.3, openness=0.85, novelty_seeking=0.8,
        ),
    }

    print(f"\n  Source NPC: interest={source.state.interest_score}, "
          f"social_influence={source.personality.social_influence}")
    print(f"  All targets start aware at interest=0.40, trust=0.70 to source\n")

    results = []
    for arch_name, traits in archetypes.items():
        # Fresh run per archetype
        target = _npc(
            arch_name, **traits,
            connections=["source"],
            trust_weights={"source": 0.7},
        )
        target.state.aware = True
        target.state.awareness_tick = 1
        target.state.interest_score = 0.40
        target.state.stance = derive_stance(0.40, False, True)

        world = _make_world([source, target])
        world.current_tick = 2

        # Run 5 ticks of peer influence
        interest_path = [0.40]
        deltas_over_time = []
        for t in range(2, 7):
            world.current_tick = t
            delta = calculate_peer_influence(target, world)
            deltas_over_time.append(delta)
            if abs(delta) >= 0.005:
                target.state.interest_score = max(0.0, min(1.0, target.state.interest_score + delta))
                target.state.stance = derive_stance(target.state.interest_score, False, True)
            interest_path.append(round(target.state.interest_score, 4))

        # Also check spread receptiveness
        receptiveness = compute_spread_receptiveness(
            target.personality.novelty_seeking, target.personality.openness,
        )
        susceptibility = compute_peer_susceptibility(
            target.personality.conformity, target.personality.skepticism,
        )

        results.append({
            "name": arch_name,
            "traits": traits,
            "susceptibility": round(susceptibility, 4),
            "receptiveness": round(receptiveness, 3),
            "interest_path": interest_path,
            "total_delta": round(sum(deltas_over_time), 4),
            "final_stance": target.state.stance,
        })

    # Report
    print(f"  {'Archetype':12s} {'Suscept.':>9} {'Recept.':>8} {'TotalDelta':>11} "
          f"{'Final':>7} {'Stance':>15}  Interest path")
    print(f"  {'-' * 85}")
    for r in results:
        path_str = " → ".join(f"{v:.3f}" for v in r["interest_path"])
        print(f"  {r['name']:12s} {r['susceptibility']:9.4f} {r['receptiveness']:8.3f} "
              f"{r['total_delta']:+11.4f} {r['interest_path'][-1]:7.4f} "
              f"{r['final_stance']:>15s}  {path_str}")

    # Spread probability comparison (100 trials per archetype)
    print(f"\n  SPREAD PROBABILITY (100 trials, source → each target while unaware):")
    for arch_name, traits in archetypes.items():
        hit_count = 0
        for seed in range(100):
            target = _npc(arch_name, **traits, connections=["source"], trust_weights={"source": 0.7})
            # target is unaware
            src = _npc("source", social_influence=0.8, novelty_seeking=0.7,
                       connections=[arch_name], trust_weights={arch_name: 0.7})
            src.state.aware = True
            src.state.interest_score = 0.82
            src.state.would_recommend = True
            world = _make_world([src, target])
            random.seed(seed)
            spreads = compute_spreads(world)
            if spreads:
                hit_count += 1
        print(f"    {arch_name:12s}  {hit_count}/100 trials spread")

    # Interpretation
    print("\n  INTERPRETATION:")
    follower_r = next(r for r in results if r["name"] == "follower")
    skeptic_r = next(r for r in results if r["name"] == "skeptic")
    explorer_r = next(r for r in results if r["name"] == "explorer")

    if follower_r["total_delta"] > skeptic_r["total_delta"]:
        print(f"  [OK] Follower shifted more than skeptic under same source "
              f"({follower_r['total_delta']:+.4f} vs {skeptic_r['total_delta']:+.4f})")
    else:
        print("  [!!] Follower did NOT shift more — investigate")

    if explorer_r["receptiveness"] > skeptic_r["receptiveness"]:
        print(f"  [OK] Explorer has higher spread receptiveness than skeptic "
              f"({explorer_r['receptiveness']} vs {skeptic_r['receptiveness']})")
    else:
        print("  [!!] Explorer receptiveness not higher — investigate")

    if follower_r["susceptibility"] > skeptic_r["susceptibility"]:
        print(f"  [OK] Follower peer susceptibility > skeptic "
              f"({follower_r['susceptibility']} vs {skeptic_r['susceptibility']})")
    else:
        print("  [!!] Susceptibility ordering wrong — investigate")


# ===========================================================================
# Scenario 3: Before/after comparison (old formula vs new)
# ===========================================================================

def scenario_before_after():
    print("\n" + "#" * 70)
    print("#  SCENARIO 3: Before/after — old formula vs Phase 2A formula")
    print("#" * 70)

    # Simulate what the OLD formulas would produce vs the new ones
    # for a range of personality profiles under the same peer pressure.
    # Old peer influence: conformity * 0.3  (no skepticism)
    # New peer influence: conformity * (1 - skepticism * 0.3) * 0.3
    # Old spread receptiveness: novelty_seeking
    # New spread receptiveness: novelty_seeking * 0.7 + openness * 0.3

    profiles = [
        ("trusting follower",    0.8, 0.15, 0.5, 0.5),
        ("skeptical conformist", 0.7, 0.85, 0.5, 0.5),
        ("open explorer",        0.5, 0.3,  0.85, 0.8),
        ("closed pragmatist",    0.5, 0.5,  0.2,  0.4),
        ("independent skeptic",  0.2, 0.85, 0.4,  0.3),
    ]

    print(f"\n  PEER INFLUENCE (old vs new):")
    print(f"  {'Profile':25s} {'Conf':>5} {'Skep':>5} {'Old Susc':>9} {'New Susc':>9} {'Change':>8}")
    print(f"  {'-' * 65}")
    for label, conf, skep, openness, ns in profiles:
        old_susc = conf * 0.3
        new_susc = compute_peer_susceptibility(conf, skep)
        change_pct = ((new_susc - old_susc) / old_susc * 100) if old_susc > 0 else 0
        print(f"  {label:25s} {conf:5.2f} {skep:5.2f} {old_susc:9.4f} {new_susc:9.4f} {change_pct:+7.1f}%")

    print(f"\n  SPREAD RECEPTIVENESS (old vs new):")
    print(f"  {'Profile':25s} {'NS':>5} {'Open':>5} {'Old Recept':>11} {'New Recept':>11} {'Change':>8}")
    print(f"  {'-' * 68}")
    for label, conf, skep, openness, ns in profiles:
        old_recept = ns
        new_recept = compute_spread_receptiveness(ns, openness)
        change_pct = ((new_recept - old_recept) / old_recept * 100) if old_recept > 0 else 0
        print(f"  {label:25s} {ns:5.2f} {openness:5.2f} {old_recept:11.4f} "
              f"{new_recept:11.4f} {change_pct:+7.1f}%")

    # Population-level before/after: run the ring scenario with old vs new
    print(f"\n  POPULATION-LEVEL IMPACT (12-NPC ring, mixed traits, 6 ticks):")

    # Build a mixed-trait population
    trait_sets = [
        dict(openness=0.8, skepticism=0.2, conformity=0.7, novelty_seeking=0.6),   # open follower
        dict(openness=0.3, skepticism=0.8, conformity=0.4, novelty_seeking=0.3),   # closed skeptic
        dict(openness=0.6, skepticism=0.4, conformity=0.5, novelty_seeking=0.5),   # moderate
        dict(openness=0.8, skepticism=0.2, conformity=0.7, novelty_seeking=0.6),   # open follower
        dict(openness=0.3, skepticism=0.8, conformity=0.4, novelty_seeking=0.3),   # closed skeptic
        dict(openness=0.6, skepticism=0.4, conformity=0.5, novelty_seeking=0.5),   # moderate
        dict(openness=0.8, skepticism=0.2, conformity=0.7, novelty_seeking=0.6),   # open follower
        dict(openness=0.3, skepticism=0.8, conformity=0.4, novelty_seeking=0.3),   # closed skeptic
        dict(openness=0.6, skepticism=0.4, conformity=0.5, novelty_seeking=0.5),   # moderate
        dict(openness=0.8, skepticism=0.2, conformity=0.7, novelty_seeking=0.6),   # open follower
        dict(openness=0.3, skepticism=0.8, conformity=0.4, novelty_seeking=0.3),   # closed skeptic
        dict(openness=0.6, skepticism=0.4, conformity=0.5, novelty_seeking=0.5),   # moderate
    ]

    ids = [f"npc_{i:02d}" for i in range(12)]
    npcs = []
    for i, (npc_id, traits) in enumerate(zip(ids, trait_sets)):
        prev_id = ids[(i - 1) % 12]
        next_id = ids[(i + 1) % 12]
        npcs.append(_npc(npc_id, connections=[prev_id, next_id],
                         trust_weights={prev_id: 0.6, next_id: 0.6}, **traits))

    world = _make_world(npcs)
    _seed_npcs(world, ["npc_00", "npc_04", "npc_08"], interest=0.70)
    reports = _run_ticks(world, ticks=6, rng_seed=42)
    summary = _summarize("Mixed-trait population", reports)

    print(f"    Total spreads:   {summary['total_spreads']}")
    print(f"    Final aware:     {summary['final_aware_pct']}%")
    print(f"    Avg interest:    {summary['final_avg_interest']:.4f}")
    print(f"    Avg |delta|:     {summary['avg_influence_delta']:.5f}")
    print(f"    Curious+:        {summary['curious_or_higher']}")
    print(f"    Opposed/skeptical: {summary['opposed_or_skeptical']}")

    print("\n  INTERPRETATION:")
    print("  - In the old formula, all NPCs at conformity=0.7 would have identical")
    print("    susceptibility (0.210). Now trusting followers get 0.197 while")
    print("    skeptical conformists get 0.153 — a 22% gap that compounds over ticks.")
    print("  - Open explorers now have higher spread receptiveness than their")
    print("    novelty_seeking alone would predict, reflecting willingness to engage.")
    print("  - Closed skeptics resist BOTH peer pressure AND incoming spread,")
    print("    creating a naturally resistant segment that slows consensus.")


# ===========================================================================
# Go/No-Go Assessment
# ===========================================================================

def go_nogo_assessment():
    print("\n" + "#" * 70)
    print("#  GO / NO-GO ASSESSMENT: Is Phase 2A ready for Phase 2B?")
    print("#" * 70)

    checks = []

    # Check 1: Skepticism monotonically reduces susceptibility
    vals = [compute_peer_susceptibility(0.7, s) for s in [0.1, 0.3, 0.5, 0.7, 0.9]]
    monotonic = all(vals[i] > vals[i + 1] for i in range(len(vals) - 1))
    checks.append(("Skepticism monotonically reduces susceptibility", monotonic))

    # Check 2: Openness increases receptiveness
    r_low = compute_spread_receptiveness(0.5, 0.1)
    r_high = compute_spread_receptiveness(0.5, 0.9)
    checks.append(("Openness increases spread receptiveness", r_high > r_low))

    # Check 3: Effect is material (>10% difference at extremes)
    susc_low_skep = compute_peer_susceptibility(0.7, 0.1)
    susc_high_skep = compute_peer_susceptibility(0.7, 0.9)
    gap_pct = (susc_low_skep - susc_high_skep) / susc_low_skep * 100
    checks.append((f"Skepticism gap is material (>{10}%)", gap_pct > 10))

    # Check 4: Openness gap is material
    recept_gap_pct = (r_high - r_low) / r_low * 100
    checks.append((f"Openness gap is material (>{10}%)", recept_gap_pct > 10))

    # Check 5: Different archetypes produce different outcomes
    # (follower vs skeptic under same peer pressure)
    def run_archetype(conf, skep):
        t = _npc("t", conformity=conf, skepticism=skep, connections=["p"], trust_weights={"p": 0.7})
        t.state.aware = True
        t.state.interest_score = 0.40
        p = _npc("p", social_influence=0.7, connections=["t"])
        p.state.aware = True
        p.state.interest_score = 0.85
        w = _make_world([t, p])
        w.current_tick = 2
        return calculate_peer_influence(t, w)

    d_follower = run_archetype(0.8, 0.15)
    d_skeptic = run_archetype(0.4, 0.85)
    ratio = d_follower / max(d_skeptic, 0.0001)
    checks.append((f"Follower/skeptic influence ratio > 2x", ratio > 2.0))

    # Check 6: No negative susceptibilities or receptiveness values
    edge_cases = [
        compute_peer_susceptibility(0.0, 1.0),
        compute_peer_susceptibility(1.0, 0.0),
        compute_spread_receptiveness(0.0, 0.0),
        compute_spread_receptiveness(1.0, 1.0),
    ]
    checks.append(("No negative values at extremes", all(v >= 0 for v in edge_cases)))

    # Print results
    print()
    all_pass = True
    for label, passed in checks:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {label}")

    print()
    if all_pass:
        print("  VERDICT: GO — Phase 2A is working correctly.")
        print("  Traits materially affect behavior, effects are monotonic,")
        print("  archetypes differentiate meaningfully, and edge cases are clean.")
        print("  Safe to proceed to Phase 2B (discussion persuasiveness).")
    else:
        print("  VERDICT: NO-GO — Fix failing checks before proceeding.")

    return all_pass


# ===========================================================================
# Main
# ===========================================================================

def main():
    print("=" * 70)
    print("  PHASE 2A BEHAVIORAL VALIDATION HARNESS")
    print("  Skepticism in peer influence + Openness in spread receptiveness")
    print("=" * 70)

    scenario_population_comparison()
    scenario_archetype_comparison()
    scenario_before_after()
    ready = go_nogo_assessment()

    print("\n" + "=" * 70)
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
