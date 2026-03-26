"""Validation harness for the resonance system (Phase 1 hybrid upgrades).

Tests:
1. Theme classification correctness
2. Resonance matrix derivation consistency
3. Resonance matrix behavioral sanity (ranking check)
4. ConcernEvent structure and content-aware deltas
5. Memory recording (PeerWarning, DiscussionMemory)
6. End-to-end: different archetypes receive different deltas from the same concern

No LLM calls. All deterministic.

Run:  cd idealab && python -m tests.test_resonance
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.simulation.npc import (
    ConcernEvent,
    DiscussionMemory,
    ImpactfulExchange,
    Npc,
    NpcPersonality,
    NpcState,
    PeerWarning,
    derive_stance,
)
from backend.simulation.product_profile import ProductProfile
from backend.simulation.propagation import compute_concern_influence
from backend.simulation.resonance import (
    ARCHETYPES,
    OBJECTION_THEMES,
    build_resonance_matrix,
    classify_objection_theme,
    classify_objection_themes,
    get_resonance,
)
from backend.simulation.world import InjectedIdea, SimConfig, WorldState

# Force evaluation cache load
from backend.simulation.evaluation import reload_evaluations
reload_evaluations()

PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        msg = f"  [FAIL] {label}"
        if detail:
            msg += f" — {detail}"
        print(msg)


# ---------------------------------------------------------------------------
# 1. Theme classification
# ---------------------------------------------------------------------------

def test_theme_classification():
    print("\n" + "=" * 70)
    print("  1. THEME CLASSIFICATION")
    print("=" * 70)

    cases = [
        ("This is way too expensive for what it does", "price"),
        ("Too expensive and overpriced", "price"),
        ("Where are the clinical studies to back this up?", "evidence"),
        ("This feels like a scam, who is behind this?", "legitimacy"),
        ("The setup is too complicated, steep learning curve", "complexity"),
        ("Nothing new here, same as existing products", "differentiation"),
        ("I'm worried about data collection and privacy", "privacy"),
        ("Nobody uses this, I'll wait and see", "social_proof"),
        ("Is this company actually ethical or just greenwashing?", "ethics"),
        ("This doesn't solve my problem, not for me", "relevance"),
        ("I love this product, amazing!", "general"),  # no objection keywords
        ("", "general"),  # empty string
    ]

    for text, expected in cases:
        result = classify_objection_theme(text)
        check(
            f"'{text[:50]}...' -> {expected}" if len(text) > 50 else f"'{text}' -> {expected}",
            result == expected,
            f"got {result}",
        )

    # Multi-objection classification
    objections = [
        "Too expensive for what it does",
        "Where are the clinical studies?",
        "I love the design though",
    ]
    themes = classify_objection_themes(objections)
    check(
        "classify_objection_themes returns unique themes in order",
        themes == ["price", "evidence"],
        f"got {themes}",
    )


# ---------------------------------------------------------------------------
# 2. Resonance matrix derivation consistency
# ---------------------------------------------------------------------------

def test_resonance_matrix():
    print("\n" + "=" * 70)
    print("  2. RESONANCE MATRIX DERIVATION")
    print("=" * 70)

    matrix = build_resonance_matrix()

    # All 8 archetypes present
    check(
        "Matrix has all 8 archetypes",
        set(matrix.keys()) == set(ARCHETYPES),
        f"got {set(matrix.keys())}",
    )

    # All 9 themes present for each archetype
    expected_themes = set(OBJECTION_THEMES.keys()) | {"legitimacy"}
    for arch_id in ARCHETYPES:
        row = matrix[arch_id]
        check(
            f"{arch_id} has all 9 themes",
            set(row.keys()) == expected_themes,
            f"missing: {expected_themes - set(row.keys())}",
        )

    # All values within bounds [0.4, 2.0]
    for arch_id in ARCHETYPES:
        row = matrix[arch_id]
        all_in_bounds = all(0.4 <= v <= 2.0 for v in row.values())
        check(
            f"{arch_id} values in [0.4, 2.0]",
            all_in_bounds,
            f"out of bounds: {[(k, v) for k, v in row.items() if v < 0.4 or v > 2.0]}",
        )

    # Derived values should match archetype weights
    # price_pragmatist has price_friction weight = -0.35
    # Derived: 1.0 + 0.35 * 2.0 = 1.70
    pp_price = matrix["price_pragmatist"]["price"]
    check(
        "price_pragmatist price resonance derived correctly (~1.70)",
        1.65 <= pp_price <= 1.75,
        f"got {pp_price}",
    )

    # analytical_skeptic has trust_barrier weight = -0.25
    # Derived evidence: 1.0 + 0.25 * 2.0 = 1.50
    as_evidence = matrix["analytical_skeptic"]["evidence"]
    check(
        "analytical_skeptic evidence resonance derived correctly (~1.50)",
        1.45 <= as_evidence <= 1.55,
        f"got {as_evidence}",
    )

    # convenience_user has trial_friction weight = -0.30
    # Derived complexity: 1.0 + 0.30 * 2.0 = 1.60
    cu_complexity = matrix["convenience_user"]["complexity"]
    check(
        "convenience_user complexity resonance derived correctly (~1.60)",
        1.55 <= cu_complexity <= 1.65,
        f"got {cu_complexity}",
    )


# ---------------------------------------------------------------------------
# 3. Resonance matrix behavioral sanity
# ---------------------------------------------------------------------------

def test_resonance_sanity():
    print("\n" + "=" * 70)
    print("  3. RESONANCE BEHAVIORAL SANITY")
    print("=" * 70)

    matrix = build_resonance_matrix()

    # price_pragmatist should have highest price resonance
    price_values = {a: matrix[a]["price"] for a in ARCHETYPES}
    top_price = max(price_values, key=price_values.get)
    check(
        "price_pragmatist has highest price resonance",
        top_price == "price_pragmatist",
        f"top is {top_price} ({price_values[top_price]:.2f})",
    )

    # social_follower should have highest social_proof resonance
    sp_values = {a: matrix[a]["social_proof"] for a in ARCHETYPES}
    top_sp = max(sp_values, key=sp_values.get)
    check(
        "social_follower has highest social_proof resonance",
        top_sp == "social_follower",
        f"top is {top_sp} ({sp_values[top_sp]:.2f})",
    )

    # values_buyer should have highest ethics resonance
    eth_values = {a: matrix[a]["ethics"] for a in ARCHETYPES}
    top_eth = max(eth_values, key=eth_values.get)
    check(
        "values_buyer has highest ethics resonance",
        top_eth == "values_buyer",
        f"top is {top_eth} ({eth_values[top_eth]:.2f})",
    )

    # brand_buyer should NOT have high price resonance (premium = quality signal)
    bb_price = matrix["brand_buyer"]["price"]
    check(
        "brand_buyer has low price resonance (< 1.2)",
        bb_price < 1.2,
        f"got {bb_price}",
    )

    # analytical_skeptic should have low social_proof resonance (decides independently)
    as_sp = matrix["analytical_skeptic"]["social_proof"]
    check(
        "analytical_skeptic has low social_proof resonance (< 0.7)",
        as_sp < 0.7,
        f"got {as_sp}",
    )

    # get_resonance returns 1.0 for unknown archetype
    check(
        "get_resonance returns 1.0 for unknown archetype",
        get_resonance("nonexistent_archetype", "price") == 1.0,
    )

    # get_resonance returns 1.0 for 'general' theme
    check(
        "get_resonance returns 1.0 for 'general' theme",
        get_resonance("price_pragmatist", "general") == 1.0,
    )


# ---------------------------------------------------------------------------
# 4. ConcernEvent structure
# ---------------------------------------------------------------------------

def _make_npc(
    npc_id: str, archetype: str, interest: float = 0.3,
    objections: list[str] | None = None,
    connections: list[str] | None = None,
    trust_weights: dict[str, float] | None = None,
) -> Npc:
    npc = Npc(
        id=npc_id, name=npc_id.replace("_", " ").title(),
        age=30, occupation="tester", income_level="middle",
        personality=NpcPersonality(
            social_influence=0.6, conformity=0.5, skepticism=0.5,
            openness=0.5, novelty_seeking=0.5,
        ),
        interests=[], values=[], pain_points=[],
        communication_style="neutral",
        social_connections=connections or [],
        trust_weights=trust_weights or {},
        archetype=archetype,
    )
    npc.state.aware = True
    npc.state.awareness_tick = 1
    npc.state.interest_score = interest
    npc.state.stance = derive_stance(interest, False, True)
    if objections:
        npc.state.objections = objections
        from backend.simulation.resonance import classify_objection_themes
        npc.state.objection_themes = classify_objection_themes(objections)
    return npc


def test_concern_event_structure():
    print("\n" + "=" * 70)
    print("  4. CONCERN EVENT STRUCTURE")
    print("=" * 70)

    # Source: skeptic with price objection, low interest
    source = _make_npc(
        "source", "analytical_skeptic", interest=0.20,
        objections=["This is way too expensive for what it does"],
        connections=["target_pp", "target_bb"],
        trust_weights={"target_pp": 0.7, "target_bb": 0.7},
    )

    # Target 1: price_pragmatist (high price resonance)
    target_pp = _make_npc(
        "target_pp", "price_pragmatist", interest=0.60,
        connections=["source"], trust_weights={"source": 0.7},
    )

    # Target 2: brand_buyer (low price resonance)
    target_bb = _make_npc(
        "target_bb", "brand_buyer", interest=0.60,
        connections=["source"], trust_weights={"source": 0.7},
    )

    idea = InjectedIdea(title="TestProduct", description="A test product")
    config = SimConfig(num_ticks=8, population_size=3, seed_count=1)
    world = WorldState(
        idea=idea, config=config,
        npcs={"source": source, "target_pp": target_pp, "target_bb": target_bb},
    )

    # Run many times to collect events (probabilistic share)
    pp_deltas = []
    bb_deltas = []
    random.seed(42)
    for _ in range(500):
        events = compute_concern_influence(world)
        for evt in events:
            check_first_structure = len(pp_deltas) == 0 and len(bb_deltas) == 0
            if check_first_structure:
                # Verify structure on first event
                check("ConcernEvent is correct type", isinstance(evt, ConcernEvent))
                check("ConcernEvent has source_id", evt.source_id == "source")
                check("ConcernEvent has theme", evt.theme == "price", f"got {evt.theme}")
                check("ConcernEvent has resonance > 0", evt.resonance > 0)
                check("ConcernEvent final_delta is negative", evt.final_delta < 0)
                check("ConcernEvent has objection_content", "expensive" in evt.objection_content.lower())

            if evt.target_id == "target_pp":
                pp_deltas.append(evt.final_delta)
            elif evt.target_id == "target_bb":
                bb_deltas.append(evt.final_delta)

    # Both should fire at least sometimes
    check("Concern fires on price_pragmatist", len(pp_deltas) > 0, f"fired {len(pp_deltas)} times")
    check("Concern fires on brand_buyer", len(bb_deltas) > 0, f"fired {len(bb_deltas)} times")

    if pp_deltas and bb_deltas:
        avg_pp = sum(pp_deltas) / len(pp_deltas)
        avg_bb = sum(bb_deltas) / len(bb_deltas)
        check(
            "Price concern hits price_pragmatist harder than brand_buyer",
            avg_pp < avg_bb,  # more negative = harder hit
            f"avg_pp={avg_pp:.4f}, avg_bb={avg_bb:.4f}",
        )

        ratio = avg_pp / avg_bb if avg_bb != 0 else 0
        check(
            "Resonance difference is meaningful (ratio > 1.2x)",
            ratio > 1.2,
            f"ratio={ratio:.2f}",
        )


# ---------------------------------------------------------------------------
# 5. Memory recording
# ---------------------------------------------------------------------------

def test_memory_recording():
    print("\n" + "=" * 70)
    print("  5. MEMORY RECORDING")
    print("=" * 70)

    state = NpcState()
    state.aware = True
    state.interest_score = 0.5
    state.stance = "curious"

    # PeerWarning recording
    warning = PeerWarning(
        tick=3, source_id="npc_01", source_name="Maya Chen",
        source_archetype="analytical_skeptic",
        theme="price", content="too expensive", delta=-0.05,
    )
    state.record_peer_warning(warning)

    check("PeerWarning stored", len(state.peer_warnings) == 1)
    check("PeerWarning fields correct", state.peer_warnings[0].theme == "price")
    check("most_impactful updated from warning", state.most_impactful is not None)
    check("most_impactful delta correct", state.most_impactful.delta == -0.05)

    # DiscussionMemory recording
    state.record_discussion(
        tick=3, partner_id="npc_02", partner_name="David Park",
        key_point="The AI integration is impressive", my_delta=0.12,
    )

    check("DiscussionMemory stored", len(state.discussion_memories) == 1)
    check("DiscussionMemory key_point correct",
          state.discussion_memories[0].key_point == "The AI integration is impressive")

    # most_impactful should now be the discussion (larger abs delta)
    check("most_impactful updated to discussion (larger delta)",
          state.most_impactful.delta == 0.12)

    # Max peer warnings bounded
    for i in range(10):
        state.record_peer_warning(PeerWarning(
            tick=4 + i, source_id=f"npc_{i:02d}", source_name=f"NPC {i}",
            source_archetype="social_follower",
            theme="social_proof", content=f"warning {i}", delta=-0.02,
        ))
    check(
        "PeerWarnings bounded to MAX_PEER_WARNINGS (5)",
        len(state.peer_warnings) == 5,
        f"got {len(state.peer_warnings)}",
    )

    # Max discussion memories bounded
    for i in range(10):
        state.record_discussion(
            tick=4 + i, partner_id=f"npc_{i:02d}", partner_name=f"NPC {i}",
            key_point=f"point {i}", my_delta=0.01,
        )
    check(
        "DiscussionMemories bounded to MAX_DISCUSSION_MEMORIES (3)",
        len(state.discussion_memories) == 3,
        f"got {len(state.discussion_memories)}",
    )


# ---------------------------------------------------------------------------
# 6. End-to-end: resonance affects outcomes
# ---------------------------------------------------------------------------

def test_end_to_end_resonance():
    print("\n" + "=" * 70)
    print("  6. END-TO-END RESONANCE EFFECT")
    print("=" * 70)

    # Scenario: 3 concerned NPCs with ethics objections influence 2 targets:
    #   - values_buyer (high ethics resonance ~1.8)
    #   - trend_adopter (low ethics resonance ~0.5)
    # Both targets start at same interest, same trust weights.
    # After many concern propagation events, values_buyer should be dampened more.

    idea = InjectedIdea(title="FastFashionApp", description="cheap fashion marketplace")
    config = SimConfig(num_ticks=8, population_size=5, seed_count=3)

    source_ids = ["s1", "s2", "s3"]
    target_ids = ["values_target", "trend_target"]
    all_ids = source_ids + target_ids

    npcs = {}
    for sid in source_ids:
        npc = _make_npc(
            sid, "values_buyer", interest=0.15,
            objections=["This company exploits workers in the supply chain"],
            connections=target_ids,
            trust_weights={tid: 0.7 for tid in target_ids},
        )
        npcs[sid] = npc

    values_target = _make_npc(
        "values_target", "values_buyer", interest=0.55,
        connections=source_ids,
        trust_weights={sid: 0.7 for sid in source_ids},
    )
    trend_target = _make_npc(
        "trend_target", "trend_adopter", interest=0.55,
        connections=source_ids,
        trust_weights={sid: 0.7 for sid in source_ids},
    )
    npcs["values_target"] = values_target
    npcs["trend_target"] = trend_target

    world = WorldState(idea=idea, config=config, npcs=npcs)

    # Accumulate concern deltas over many runs
    values_total = 0.0
    trend_total = 0.0
    values_events = 0
    trend_events = 0

    random.seed(42)
    for _ in range(200):
        events = compute_concern_influence(world)
        for evt in events:
            if evt.target_id == "values_target":
                values_total += evt.final_delta
                values_events += 1
            elif evt.target_id == "trend_target":
                trend_total += evt.final_delta
                trend_events += 1

    check("Ethics concerns hit values_buyer", values_events > 0, f"{values_events} events")
    check("Ethics concerns hit trend_adopter", trend_events > 0, f"{trend_events} events")

    if values_events > 0 and trend_events > 0:
        avg_values = values_total / values_events
        avg_trend = trend_total / trend_events

        check(
            "Ethics concern hits values_buyer harder than trend_adopter",
            avg_values < avg_trend,  # more negative = harder
            f"values avg={avg_values:.4f}, trend avg={avg_trend:.4f}",
        )

        # The resonance ratio should be close to 1.8/0.5 = 3.6x
        # but real ratio will be smaller due to other factors
        ratio = avg_values / avg_trend if avg_trend != 0 else 0
        check(
            "Resonance ratio is meaningful (> 2.0x)",
            ratio > 2.0,
            f"ratio={ratio:.2f}",
        )

    # Print the resonance values for inspection
    print("\n  RESONANCE MATRIX EXCERPT (ethics column):")
    matrix = build_resonance_matrix()
    for arch_id in ARCHETYPES:
        val = matrix[arch_id].get("ethics", 1.0)
        print(f"    {arch_id:25s} {val:.2f}")


# ---------------------------------------------------------------------------
# 7. Objection theme classification on apply_reaction
# ---------------------------------------------------------------------------

def test_objection_theme_on_reaction():
    print("\n" + "=" * 70)
    print("  7. OBJECTION THEME ON REACTION")
    print("=" * 70)

    state = NpcState()
    state.aware = True

    reaction = {
        "interest_score": 0.25,
        "reasoning": "Not convinced",
        "objections": [
            "Way too expensive for what this offers",
            "Nobody uses this, I'll wait and see",
            "Great design though",
        ],
        "would_pay": False,
        "would_recommend": False,
        "emotional_reaction": "skeptical",
    }

    state.apply_reaction(reaction, tick=2)

    check(
        "objection_themes set on apply_reaction",
        len(state.objection_themes) > 0,
        f"got {state.objection_themes}",
    )
    check(
        "First theme is price",
        state.objection_themes[0] == "price",
        f"got {state.objection_themes}",
    )
    check(
        "Second theme is social_proof",
        len(state.objection_themes) >= 2 and state.objection_themes[1] == "social_proof",
        f"got {state.objection_themes}",
    )
    # "Great design though" has no objection keywords — should not appear
    check(
        "Non-objection text not classified as theme",
        "general" not in state.objection_themes,
        f"themes: {state.objection_themes}",
    )


# ---------------------------------------------------------------------------
# Print full matrix for inspection
# ---------------------------------------------------------------------------

def print_resonance_matrix():
    print("\n" + "=" * 70)
    print("  FULL RESONANCE MATRIX (for manual inspection)")
    print("=" * 70)

    matrix = build_resonance_matrix()
    themes = sorted(set().union(*(row.keys() for row in matrix.values())))

    # Header
    header = f"  {'Archetype':25s}"
    for t in themes:
        header += f" {t[:6]:>6s}"
    print(header)
    print("  " + "-" * (25 + 7 * len(themes)))

    for arch_id in ARCHETYPES:
        row = matrix[arch_id]
        line = f"  {arch_id:25s}"
        for t in themes:
            v = row.get(t, 1.0)
            line += f" {v:6.2f}"
        print(line)


# ===========================================================================
# Main
# ===========================================================================

def main():
    print("=" * 70)
    print("  RESONANCE SYSTEM VALIDATION (Phase 1 Hybrid Upgrades)")
    print("=" * 70)

    test_theme_classification()
    test_resonance_matrix()
    test_resonance_sanity()
    test_concern_event_structure()
    test_memory_recording()
    test_end_to_end_resonance()
    test_objection_theme_on_reaction()
    print_resonance_matrix()

    print("\n" + "=" * 70)
    print(f"  RESULTS: {PASS} passed, {FAIL} failed")
    print("=" * 70)

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
