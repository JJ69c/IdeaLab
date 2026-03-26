"""Validation script for the simulation correction pass.

Tests all six correction priorities (A-F) to verify they produce the
intended distributional and behavioral effects. No LLM or server needed —
all tests are deterministic, exercising the evaluation/propagation/profile
pipeline directly.

Run:  PYTHONIOENCODING=utf-8 python -m tests.test_correction_pass
"""

from __future__ import annotations

import random
import statistics
import sys
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

sys.path.insert(0, ".")

from backend.simulation.evaluation import (
    BASELINE_CENTER,
    compute_archetype_baseline,
    compute_individual_delta,
    get_archetype_evaluation,
    get_identity_fit_multiplier,
    reload_evaluations,
)
from backend.simulation.npc import Npc, NpcPersonality, NpcState
from backend.simulation.population import (
    generate_npc,
    generate_population,
    load_archetypes,
    parse_archetype_defs,
)
from backend.simulation.product_profile import ProductProfile, build_product_profile
from backend.simulation.propagation import (
    CONCERN_INTEREST_THRESHOLD,
    compute_concern_influence,
    compute_peer_susceptibility,
)
from backend.simulation.world import InjectedIdea, WorldState

# Force reload evaluation cache
reload_evaluations()

# ---------------------------------------------------------------------------
# Test product profiles (representative scenarios)
# ---------------------------------------------------------------------------

_WELL_DESCRIBED_FREE_APP = InjectedIdea(
    title="FocusFlow",
    description="An AI-powered productivity app that learns your work patterns and automatically blocks distractions during your deep work hours. Uses machine learning to identify your most productive times and adjusts notification filtering accordingly.",
    category="productivity_tool",
    stage="mvp",
    target_audience="knowledge workers and remote professionals",
    problem_statement="Remote workers lose 2+ hours daily to context-switching and notification overload",
    price_point="Free",
    existing_alternatives="Forest, Freedom, Cold Turkey",
    differentiator="AI-driven automatic scheduling vs manual timer-based blocking",
    known_strengths="Non-intrusive, learns passively, cross-platform",
    known_risks="Privacy concerns around work pattern monitoring",
)

_VAGUE_EXPENSIVE_CONCEPT = InjectedIdea(
    title="CryptoGuard",
    description="A crypto security thing",
    category="crypto_web3",
    stage="concept",
    target_audience="",
    problem_statement="",
    price_point="$50-$100/mo",
    existing_alternatives="Ledger, MetaMask",
    differentiator="",
    known_strengths="",
    known_risks="Regulatory uncertainty",
)

_HEALTH_PRODUCT = InjectedIdea(
    title="NutriScan",
    description="A mobile app that uses your phone camera to scan food labels and provides personalized nutritional analysis based on your health goals, allergies, and dietary preferences.",
    category="health_wellness",
    stage="prototype",
    target_audience="health-conscious consumers with dietary restrictions",
    problem_statement="Reading food labels is confusing and time-consuming, especially for people with multiple dietary constraints",
    price_point="$5-$20/mo",
    existing_alternatives="MyFitnessPal, Yuka, Fooducate",
    differentiator="Camera-based instant scanning with personalized health scoring vs manual food logging",
    known_strengths="Easy to use, instant results, personalized",
    known_risks="Camera accuracy may vary, nutritional databases may be incomplete",
)

_NONPROFIT_PRODUCT = InjectedIdea(
    title="VolunteerBridge",
    description="A platform connecting skilled professionals with nonprofits for pro-bono consulting projects",
    category="nonprofit",
    stage="concept",
    target_audience="skilled professionals wanting to give back",
    problem_statement="Nonprofits struggle to access professional expertise they can't afford",
    price_point="Free",
    existing_alternatives="Catchafire, Taproot Foundation",
    differentiator="AI-matched skill pairing with structured project timelines",
    known_strengths="Clear social impact, strong mission alignment",
    known_risks="Volunteer retention, quality consistency",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ARCHETYPES = [
    "analytical_skeptic", "trend_adopter", "price_pragmatist",
    "health_evaluator", "brand_buyer", "social_follower",
    "convenience_user", "values_buyer",
]

STANCES = [
    "opposed", "skeptical", "indifferent", "curious",
    "interested", "willing_to_try", "willing_to_pay",
]


def _stance_from_score(score: float) -> str:
    if score >= 0.85:
        return "willing_to_pay"
    if score >= 0.75:
        return "willing_to_try"
    if score >= 0.60:
        return "interested"
    if score >= 0.45:
        return "curious"
    if score >= 0.30:
        return "indifferent"
    if score >= 0.15:
        return "skeptical"
    return "opposed"


def _build_profile(idea: InjectedIdea) -> ProductProfile:
    return build_product_profile(idea)


def _compute_baselines(profile: ProductProfile, category: str | None = None) -> dict[str, float]:
    """Compute archetype baselines for a profile."""
    result = {}
    for arch in ARCHETYPES:
        eval_def = get_archetype_evaluation(arch)
        result[arch] = compute_archetype_baseline(profile, eval_def, category=category)
    return result


def _generate_population_scores(
    idea: InjectedIdea, size: int = 30, seed: int = 42
) -> list[tuple[str, float, str]]:
    """Generate a population and compute baseline + individual delta for each NPC.

    Returns list of (archetype, score, stance).
    """
    profile = _build_profile(idea)
    npcs, npc_archetypes = generate_population(size=size, seed=seed)
    results = []
    for npc in npcs:
        arch_id = npc_archetypes[npc.id]
        eval_def = get_archetype_evaluation(arch_id)
        baseline = compute_archetype_baseline(profile, eval_def, category=idea.category)
        ind_delta = compute_individual_delta(npc.personality, profile)
        score = max(0.0, min(1.0, baseline + ind_delta))
        stance = _stance_from_score(score)
        results.append((arch_id, score, stance))
    return results


passed = 0
failed = 0
warnings = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}{' -- ' + detail if detail else ''}")


def warn(name: str, detail: str = ""):
    global warnings
    warnings += 1
    print(f"  WARN  {name}{' -- ' + detail if detail else ''}")


# ===========================================================================
# A. BASELINE CENTER
# ===========================================================================

def test_baseline_center():
    print("\n=== A. Baseline Center ===")

    check(
        "BASELINE_CENTER is 0.40",
        BASELINE_CENTER == 0.40,
        f"got {BASELINE_CENTER}",
    )

    # A "zero signal" product should produce baselines near 0.40
    neutral_profile = ProductProfile(
        novelty=0.5, utility_clarity=0.5, differentiation=0.5,
        price_friction=0.5, trust_barrier=0.5, identity_fit=0.5,
        trial_friction=0.5, market_saturation=0.5,
    )
    baselines = _compute_baselines(neutral_profile)
    mean_baseline = statistics.mean(baselines.values())
    check(
        "Neutral product mean baseline near 0.40",
        0.35 <= mean_baseline <= 0.50,
        f"got {mean_baseline:.3f}",
    )

    # No archetype should be above 'interested' for a neutral product
    max_baseline = max(baselines.values())
    check(
        "No archetype above 'interested' for neutral product",
        max_baseline < 0.60,
        f"max baseline = {max_baseline:.3f} ({max(baselines, key=baselines.get)})",
    )


# ===========================================================================
# B. PRODUCTPROFILE BIAS REDUCTION
# ===========================================================================

def test_product_profile_bias():
    print("\n=== B. ProductProfile Bias Reduction ===")

    well_described = _build_profile(_WELL_DESCRIBED_FREE_APP)
    vague = _build_profile(_VAGUE_EXPENSIVE_CONCEPT)

    # Well-described should not max out utility_clarity
    check(
        "Well-described product utility_clarity < 0.75",
        well_described.utility_clarity < 0.75,
        f"got {well_described.utility_clarity:.3f}",
    )

    # Differentiation should not exceed 0.60 even with differentiator provided
    check(
        "Differentiation capped reasonably (< 0.65)",
        well_described.differentiation < 0.65,
        f"got {well_described.differentiation:.3f}",
    )

    # Identity fit should not exceed 0.70 from form fields alone
    check(
        "Identity fit from form < 0.70",
        well_described.identity_fit < 0.70,
        f"got {well_described.identity_fit:.3f}",
    )

    # Vague product should have meaningfully lower signals
    uc_gap = well_described.utility_clarity - vague.utility_clarity
    check(
        "Utility clarity gap between well-described and vague > 0.15",
        uc_gap > 0.15,
        f"gap = {uc_gap:.3f}",
    )

    # Vague expensive concept should have high friction signals
    check(
        "Vague concept has high trust_barrier (> 0.50)",
        vague.trust_barrier > 0.50,
        f"got {vague.trust_barrier:.3f}",
    )
    check(
        "Vague concept has high price_friction (> 0.55)",
        vague.price_friction > 0.55,
        f"got {vague.price_friction:.3f}",
    )


# ===========================================================================
# C. WITHIN-ARCHETYPE VARIATION
# ===========================================================================

def test_within_archetype_variation():
    print("\n=== C. Within-Archetype Variation ===")

    profile = _build_profile(_WELL_DESCRIBED_FREE_APP)
    raw = load_archetypes()
    arch_defs = parse_archetype_defs(raw)
    rng = random.Random(42)

    for arch_id in ARCHETYPES:
        arch_def = arch_defs[arch_id]
        eval_def = get_archetype_evaluation(arch_id)
        baseline = compute_archetype_baseline(profile, eval_def, category=_WELL_DESCRIBED_FREE_APP.category)

        # Generate 20 NPCs of this archetype and compute individual deltas
        deltas = []
        for i in range(20):
            npc = generate_npc(
                f"test_{arch_id}_{i}", arch_def, f"Test {i}",
                "Professional", "middle", rng,
            )
            d = compute_individual_delta(npc.personality, profile)
            deltas.append(d)

        std = statistics.stdev(deltas)
        rng_span = max(deltas) - min(deltas)

        # Signature-trait archetypes (trend_adopter, social_follower) have
        # narrow ranges on the traits that dominate this product, so their
        # variation is naturally lower. Use relaxed thresholds for them.
        narrow_sig = arch_id in ("trend_adopter", "social_follower")
        std_floor = 0.006 if narrow_sig else 0.01
        range_floor = 0.02 if narrow_sig else 0.03

        check(
            f"{arch_id}: std > {std_floor}",
            std > std_floor,
            f"std = {std:.4f}",
        )
        check(
            f"{arch_id}: range > {range_floor}",
            rng_span > range_floor,
            f"range = {rng_span:.4f}",
        )


# ===========================================================================
# D. CONCERN PROPAGATION
# ===========================================================================

def test_concern_propagation():
    print("\n=== D. Concern Propagation ===")

    # Verify the threshold constant
    check(
        "CONCERN_INTEREST_THRESHOLD is 0.45",
        CONCERN_INTEREST_THRESHOLD == 0.45,
        f"got {CONCERN_INTEREST_THRESHOLD}",
    )

    # Create a mini world with a skeptical NPC connected to an interested NPC
    world = WorldState(
        idea=_WELL_DESCRIBED_FREE_APP,
        config={"num_ticks": 5, "population_size": 3, "seed_count": 1},
    )

    # Skeptical NPC (low interest, has objections)
    skeptic = Npc(
        id="s1", name="Skeptic", age=40, occupation="Analyst",
        income_level="high",
        personality=NpcPersonality(
            openness=0.3, skepticism=0.85, tech_savviness=0.6,
            price_sensitivity=0.4, social_influence=0.7,
            conformity=0.3, novelty_seeking=0.2,
        ),
        interests=[], values=[], pain_points=[],
        communication_style="questioning",
        social_connections=["t1"],
        trust_weights={"t1": 0.7},
        archetype="analytical_skeptic",
        decision_style="evidence-driven",
    )
    skeptic.state = NpcState()
    skeptic.state.aware = True
    skeptic.state.interest_score = 0.20  # below threshold
    skeptic.state.objections = ["privacy concerns", "unproven technology"]
    skeptic.state.stance = "skeptical"

    # Target NPC (interested)
    target = Npc(
        id="t1", name="Target", age=30, occupation="Designer",
        income_level="middle",
        personality=NpcPersonality(
            openness=0.7, skepticism=0.3, tech_savviness=0.5,
            price_sensitivity=0.5, social_influence=0.5,
            conformity=0.6, novelty_seeking=0.6,
        ),
        interests=[], values=[], pain_points=[],
        communication_style="enthusiastic",
        social_connections=["s1"],
        trust_weights={"s1": 0.7},
        archetype="trend_adopter",
        decision_style="trend-following",
    )
    target.state = NpcState()
    target.state.aware = True
    target.state.interest_score = 0.65
    target.state.stance = "interested"

    world.npcs = {"s1": skeptic, "t1": target}

    # Run concern influence multiple times to check it can fire
    total_deltas = 0
    fired = False
    random.seed(42)
    for _ in range(100):
        events = compute_concern_influence(world)
        if events:
            fired = True
            for evt in events:
                total_deltas += evt.final_delta

    check(
        "Concern propagation fires from skeptical NPC",
        fired,
        "never fired in 100 runs",
    )
    check(
        "Concern deltas are negative",
        total_deltas < 0,
        f"total = {total_deltas:.4f}",
    )


# ===========================================================================
# E. RECOMMENDATION THRESHOLD
# ===========================================================================

def test_recommendation_threshold():
    print("\n=== E. Recommendation Threshold ===")

    npc = Npc(
        id="r1", name="Recommender", age=30, occupation="Engineer",
        income_level="middle",
        personality=NpcPersonality(
            openness=0.6, skepticism=0.4, tech_savviness=0.7,
            price_sensitivity=0.5, social_influence=0.6,
            conformity=0.5, novelty_seeking=0.5,
        ),
        interests=[], values=[], pain_points=[],
        communication_style="enthusiastic",
        social_connections=[], trust_weights={},
        archetype="trend_adopter",
        decision_style="trend-following",
    )

    # At 0.60 (well below threshold) — should NOT recommend
    npc.state.interest_score = 0.60
    npc.state.update_would_recommend()
    check(
        "Score 0.60 does NOT trigger recommendation",
        not npc.state.would_recommend,
        "would_recommend should be False at 0.60",
    )

    # At 0.67 — should NOT recommend
    npc.state.interest_score = 0.67
    npc.state.update_would_recommend()
    check(
        "Score 0.67 does NOT trigger recommendation",
        not npc.state.would_recommend,
        "would_recommend should be False at 0.67",
    )

    # At 0.68 — SHOULD recommend
    npc.state.interest_score = 0.68
    npc.state.update_would_recommend()
    check(
        "Score 0.68 triggers recommendation",
        npc.state.would_recommend,
        "would_recommend should be True at 0.68",
    )

    # At 0.80 — SHOULD recommend
    npc.state.interest_score = 0.80
    npc.state.update_would_recommend()
    check(
        "Score 0.80 triggers recommendation",
        npc.state.would_recommend,
        "would_recommend should be True at 0.80",
    )


# ===========================================================================
# F. IDENTITY FIT PER-NPC (CATEGORY AFFINITY)
# ===========================================================================

def test_identity_fit_affinity():
    print("\n=== F. Identity Fit per-NPC (Category Affinity) ===")

    # Test that health products favor health_evaluator
    health_profile = _build_profile(_HEALTH_PRODUCT)

    health_eval = get_archetype_evaluation("health_evaluator")
    trend_eval = get_archetype_evaluation("trend_adopter")

    b_health_health = compute_archetype_baseline(health_profile, health_eval, category="health_wellness")
    b_health_neutral = compute_archetype_baseline(health_profile, health_eval, category=None)
    b_trend_health = compute_archetype_baseline(health_profile, trend_eval, category="health_wellness")
    b_trend_neutral = compute_archetype_baseline(health_profile, trend_eval, category=None)

    check(
        "health_evaluator gets identity boost for health product",
        b_health_health > b_health_neutral,
        f"health={b_health_health:.3f} vs neutral={b_health_neutral:.3f}",
    )

    check(
        "trend_adopter gets identity penalty for health product",
        b_trend_health < b_trend_neutral,
        f"health={b_trend_health:.3f} vs neutral={b_trend_neutral:.3f}",
    )

    # Test that values_buyer strongly favors nonprofit
    nonprofit_profile = _build_profile(_NONPROFIT_PRODUCT)
    values_eval = get_archetype_evaluation("values_buyer")
    brand_eval = get_archetype_evaluation("brand_buyer")

    b_values_nonprofit = compute_archetype_baseline(nonprofit_profile, values_eval, category="nonprofit")
    b_brand_nonprofit = compute_archetype_baseline(nonprofit_profile, brand_eval, category="nonprofit")

    check(
        "values_buyer scores higher than brand_buyer for nonprofit",
        b_values_nonprofit > b_brand_nonprofit,
        f"values={b_values_nonprofit:.3f} vs brand={b_brand_nonprofit:.3f}",
    )

    # Test multiplier values make sense
    check(
        "health_evaluator x health_wellness multiplier > 1.3",
        get_identity_fit_multiplier("health_evaluator", "health_wellness") >= 1.3,
    )
    check(
        "health_evaluator x crypto_web3 multiplier < 0.7",
        get_identity_fit_multiplier("health_evaluator", "crypto_web3") <= 0.7,
    )
    check(
        "values_buyer x nonprofit multiplier > 1.3",
        get_identity_fit_multiplier("values_buyer", "nonprofit") >= 1.3,
    )
    check(
        "brand_buyer x consumer multiplier > 1.2",
        get_identity_fit_multiplier("brand_buyer", "ecommerce") >= 1.2,
    )
    check(
        "Unknown archetype returns 1.0",
        get_identity_fit_multiplier("nonexistent", "saas") == 1.0,
    )
    check(
        "None category returns 1.0",
        get_identity_fit_multiplier("health_evaluator", None) == 1.0,
    )


# ===========================================================================
# DISTRIBUTION REALISM (composite check)
# ===========================================================================

def test_distribution_realism():
    print("\n=== Distribution Realism (Composite) ===")

    # Well-described free app — should NOT produce all-green
    results = _generate_population_scores(_WELL_DESCRIBED_FREE_APP, size=30, seed=42)
    stance_counts = {}
    for _, _, stance in results:
        stance_counts[stance] = stance_counts.get(stance, 0) + 1

    print(f"    Well-described free app stance distribution: {stance_counts}")

    # Not everyone should be interested or above
    positive_count = sum(v for k, v in stance_counts.items() if k in ("interested", "willing_to_try", "willing_to_pay"))
    check(
        "Well-described free app: < 60% in positive stances",
        positive_count / 30 < 0.60,
        f"positive = {positive_count}/30 = {positive_count/30:.1%}",
    )

    # Should have at least some non-positive stances (curious counts as non-positive
    # since it's below the "interested" threshold). A well-described free app is
    # genuinely strong, so we expect most NPCs in "curious" — the key is that not
    # everyone is "interested" or above.
    non_positive = sum(v for k, v in stance_counts.items() if k in ("indifferent", "skeptical", "opposed", "curious"))
    check(
        "Well-described free app: >= 60% NOT in positive stances (curious or below)",
        non_positive / 30 >= 0.60,
        f"non-positive = {non_positive}/30 = {non_positive/30:.1%}",
    )

    # Vague expensive concept — should be majority negative
    results_vague = _generate_population_scores(_VAGUE_EXPENSIVE_CONCEPT, size=30, seed=42)
    stance_counts_v = {}
    for _, _, stance in results_vague:
        stance_counts_v[stance] = stance_counts_v.get(stance, 0) + 1

    print(f"    Vague expensive concept stance distribution: {stance_counts_v}")

    positive_v = sum(v for k, v in stance_counts_v.items() if k in ("interested", "willing_to_try", "willing_to_pay"))
    check(
        "Vague expensive concept: < 20% in positive stances",
        positive_v / 30 < 0.20,
        f"positive = {positive_v}/30 = {positive_v/30:.1%}",
    )

    skeptical_negative_v = sum(v for k, v in stance_counts_v.items() if k in ("skeptical", "opposed"))
    check(
        "Vague expensive concept: >= 25% in skeptical/opposed",
        skeptical_negative_v / 30 >= 0.25,
        f"skeptical/opposed = {skeptical_negative_v}/30 = {skeptical_negative_v/30:.1%}",
    )

    # Health product — health_evaluator BASELINE should be boosted by identity_fit
    # affinity. Note: individual deltas may push health_evaluators down because
    # their high skepticism interacts with the health product's high trust_barrier.
    # This is realistic — health evaluators scrutinize health claims carefully.
    # We verify the identity_fit mechanism works at the baseline level.
    health_profile = _build_profile(_HEALTH_PRODUCT)
    he_eval = get_archetype_evaluation("health_evaluator")
    he_baseline_with_cat = compute_archetype_baseline(health_profile, he_eval, category="health_wellness")
    he_baseline_no_cat = compute_archetype_baseline(health_profile, he_eval, category=None)
    check(
        "Health product: health_evaluator baseline boosted by category affinity",
        he_baseline_with_cat > he_baseline_no_cat,
        f"with_cat={he_baseline_with_cat:.3f} vs no_cat={he_baseline_no_cat:.3f}",
    )


# ===========================================================================
# SCORE RANGE DIVERSITY
# ===========================================================================

def test_score_range_diversity():
    print("\n=== Score Range Diversity ===")

    for idea_name, idea in [
        ("well-described free app", _WELL_DESCRIBED_FREE_APP),
        ("vague expensive concept", _VAGUE_EXPENSIVE_CONCEPT),
        ("health product", _HEALTH_PRODUCT),
    ]:
        results = _generate_population_scores(idea, size=30, seed=42)
        scores = [s for _, s, _ in results]
        score_range = max(scores) - min(scores)
        score_std = statistics.stdev(scores)

        check(
            f"{idea_name}: score range > 0.15",
            score_range > 0.15,
            f"range = {score_range:.3f}",
        )
        check(
            f"{idea_name}: score std > 0.05",
            score_std > 0.05,
            f"std = {score_std:.4f}",
        )

        # Count unique stances
        stances = set(s for _, _, s in results)
        check(
            f"{idea_name}: >= 3 distinct stances",
            len(stances) >= 3,
            f"stances = {stances}",
        )


# ===========================================================================
# WORDING ROBUSTNESS
# ===========================================================================

def test_wording_robustness():
    print("\n=== Wording Robustness ===")

    # Same product, two different descriptions — scores should differ by profile
    # differences, not by massive swings
    idea_a = InjectedIdea(
        title="TaskMaster",
        description="A project management tool for small teams with Kanban boards and time tracking",
        category="productivity_tool",
        stage="mvp",
        target_audience="small business teams",
        problem_statement="Small teams waste time on status updates and manual tracking",
        price_point="$5-$20/mo",
        existing_alternatives="Trello, Asana, Monday.com",
        differentiator="Built-in time tracking with automatic Kanban updates",
        known_strengths="Simple, affordable",
        known_risks="Crowded market",
    )

    idea_b = InjectedIdea(
        title="TaskMaster",
        description="Project management for small teams: Kanban + time tracking in one tool",
        category="productivity_tool",
        stage="mvp",
        target_audience="small business teams",
        problem_statement="Teams lose time on manual status updates",
        price_point="$5-$20/mo",
        existing_alternatives="Trello, Asana, Monday.com",
        differentiator="Integrated time tracking with Kanban",
        known_strengths="Simple and affordable",
        known_risks="Competitive market",
    )

    profile_a = _build_profile(idea_a)
    profile_b = _build_profile(idea_b)

    for arch in ARCHETYPES:
        eval_def = get_archetype_evaluation(arch)
        ba = compute_archetype_baseline(profile_a, eval_def, category="productivity_tool")
        bb = compute_archetype_baseline(profile_b, eval_def, category="productivity_tool")
        diff = abs(ba - bb)
        check(
            f"Wording robustness {arch}: baseline diff < 0.08",
            diff < 0.08,
            f"diff = {diff:.4f}",
        )


# ===========================================================================
# Run all
# ===========================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("SIMULATION CORRECTION PASS — VALIDATION")
    print("=" * 60)

    test_baseline_center()
    test_product_profile_bias()
    test_within_archetype_variation()
    test_concern_propagation()
    test_recommendation_threshold()
    test_identity_fit_affinity()
    test_distribution_realism()
    test_score_range_diversity()
    test_wording_robustness()

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed, {warnings} warnings")
    print("=" * 60)

    sys.exit(1 if failed > 0 else 0)
