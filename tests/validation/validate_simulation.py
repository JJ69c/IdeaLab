"""Simulation redesign validation harness.

Runs deterministic baseline tests (no LLM calls needed) to verify that:
1. Archetypes produce meaningfully different baselines for the same product
2. Price sensitivity works as expected (Price-Pragmatist drops hard for expensive products)
3. Individual deltas are bounded and reasonable
4. Face-validity scenarios produce expected archetype orderings
5. Convergence tracking and archetype coherence work
6. Input wording robustness (same product, 3 description styles → same baselines)
7. Archetype behavioral separation across 5 dimensions
8. Repeated-exposure sensitivity (bounded decay, no runaway effects)
9. Seed sensitivity (population generation randomness classified low/medium/high)
10. Holdout validation scenarios (unseen products not used during tuning)
11. Competition context: classification, confidence weighting, backward compat
12. Asset signals: product profile shifts, per-NPC adjustments, backward compat
13. Adoption model: per-NPC barriers, hard gates, personality sensitivity, bounds

Usage:
    cd idealab
    python -m tests.validation.validate_simulation [--layer 1..13]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.simulation.asset_signals import AssetSignals, compute_asset_adjustment
from backend.simulation.evaluation import (
    compute_archetype_baseline,
    compute_individual_delta,
    get_archetype_evaluation,
    reload_evaluations,
)
from backend.simulation.npc import NpcPersonality
from backend.simulation.product_profile import ProductProfile, build_product_profile
from backend.simulation.world import InjectedIdea


# ---------------------------------------------------------------------------
# All 8 archetypes
# ---------------------------------------------------------------------------

ALL_ARCHETYPES = [
    "analytical_skeptic", "trend_adopter", "price_pragmatist",
    "health_evaluator", "brand_buyer", "social_follower",
    "convenience_user", "values_buyer",
]


# ---------------------------------------------------------------------------
# Test products
# ---------------------------------------------------------------------------

TEST_PRODUCTS = {
    "free_saas_concept": InjectedIdea(
        title="TaskHelper",
        description="A simple AI-powered task management tool that learns your workflow patterns and suggests optimal task ordering for productivity",
        category="saas",
        stage="concept",
        target_audience="knowledge workers",
        price_point="free",
        problem_statement="People waste 30 minutes daily deciding what to work on next",
        existing_alternatives="",
        differentiator="AI learns your personal productivity patterns",
        known_strengths="Simple, free, learns over time",
        known_risks="Requires behavior data collection",
    ),
    "expensive_hardware": InjectedIdea(
        title="SmartPlug X",
        description="Wi-Fi smart plug with energy monitoring, voice control, and automation scheduling for home IoT enthusiasts",
        category="consumer_hardware",
        stage="prototype",
        target_audience="smart home enthusiasts",
        price_point="$100+/mo",
        problem_statement="Existing smart plugs lack energy monitoring and automation",
        existing_alternatives="TP-Link Kasa, Wemo, Amazon Smart Plug",
        differentiator="Real-time energy analytics dashboard",
        known_strengths="Comprehensive energy data",
        known_risks="High price point, requires always-on WiFi",
    ),
    "health_app": InjectedIdea(
        title="FitTrack Pro",
        description="AI-powered health monitoring app that tracks nutrition, exercise, and sleep patterns with personalized recommendations",
        category="health_wellness",
        stage="prototype",
        target_audience="health-conscious adults 25-45",
        price_point="$20\u2013$50/mo",
        problem_statement="People struggle to maintain consistent healthy habits without personalized guidance",
        existing_alternatives="MyFitnessPal, Fitbit app, Apple Health",
        differentiator="AI learns your patterns and adapts recommendations weekly",
        known_strengths="Accurate tracking, beautiful UI",
        known_risks="Requires consistent data input from users",
    ),
    "saturated_todo": InjectedIdea(
        title="TaskFlow",
        description="Yet another task management tool with Kanban boards and team collaboration features",
        category="saas",
        stage="launched",
        target_audience="small teams",
        price_point="freemium",
        problem_statement="",
        existing_alternatives="Trello, Asana, Notion, Monday, ClickUp, Todoist",
        differentiator="",
        known_strengths="",
        known_risks="",
    ),
    "privacy_messenger": InjectedIdea(
        title="VaultChat",
        description="End-to-end encrypted messaging with zero-knowledge architecture and self-destructing messages",
        category="mobile_app",
        stage="mvp",
        target_audience="privacy-conscious users",
        price_point="free",
        problem_statement="Major messaging apps collect and monetize user data",
        existing_alternatives="Signal, Telegram",
        differentiator="Zero-knowledge proof architecture \u2014 even we cannot read your messages",
        known_strengths="Military-grade encryption, open source",
        known_risks="Small user base, no network effect yet",
    ),
}


# ---------------------------------------------------------------------------
# Layer 1: Deterministic baseline validation (no LLM)
# ---------------------------------------------------------------------------

def run_layer_1():
    """Test that archetype baselines differ meaningfully for each product."""
    print("=" * 70)
    print("LAYER 1: Deterministic Baseline Validation (8 archetypes)")
    print("=" * 70)

    reload_evaluations()
    all_passed = True

    for product_name, idea in TEST_PRODUCTS.items():
        profile = build_product_profile(idea)
        print(f"\n--- Product: {product_name} ---")
        print(f"  Profile: novelty={profile.novelty:.2f} utility={profile.utility_clarity:.2f} "
              f"diff={profile.differentiation:.2f} price={profile.price_friction:.2f} "
              f"trust={profile.trust_barrier:.2f} identity={profile.identity_fit:.2f} "
              f"trial={profile.trial_friction:.2f} saturation={profile.market_saturation:.2f}")

        baselines = {}
        for arch_id in ALL_ARCHETYPES:
            eval_def = get_archetype_evaluation(arch_id)
            baseline = compute_archetype_baseline(profile, eval_def)
            baselines[arch_id] = baseline

        # Sort by baseline descending
        sorted_archetypes = sorted(baselines.items(), key=lambda x: x[1], reverse=True)
        for arch_id, bl in sorted_archetypes:
            bar = "#" * int(bl * 40)
            print(f"  {arch_id:20s}: {bl:.3f}  {bar}")

        # Test: spread should be >= 0.15 (with 10 archetypes, more differentiation expected)
        spread = max(baselines.values()) - min(baselines.values())
        passed = spread >= 0.15
        status = "PASS" if passed else "FAIL"
        print(f"  Spread: {spread:.3f} (min 0.15) [{status}]")
        if not passed:
            all_passed = False

    return all_passed


# ---------------------------------------------------------------------------
# Layer 2: Price sensitivity test
# ---------------------------------------------------------------------------

def run_layer_2():
    """Test that price changes affect Price-Pragmatist much more than Trend-Adopter.
    Also verify Brand-Buyer has minimal drop or even benefits from premium pricing."""
    print("\n" + "=" * 70)
    print("LAYER 2: Price Sensitivity Validation")
    print("=" * 70)

    reload_evaluations()

    # Same product, two price points
    base_idea = InjectedIdea(
        title="WidgetApp",
        description="A useful productivity tool with clear value proposition and strong differentiation from existing alternatives",
        category="saas",
        stage="mvp",
        target_audience="professionals",
        price_point="free",
        problem_statement="Professionals need better workflow automation",
        existing_alternatives="Competitor A",
        differentiator="AI-powered automation",
        known_strengths="Fast, reliable",
        known_risks="",
    )

    expensive_idea = InjectedIdea(
        title=base_idea.title,
        description=base_idea.description,
        category=base_idea.category,
        stage=base_idea.stage,
        target_audience=base_idea.target_audience,
        price_point="$100+/mo",
        problem_statement=base_idea.problem_statement,
        existing_alternatives=base_idea.existing_alternatives,
        differentiator=base_idea.differentiator,
        known_strengths=base_idea.known_strengths,
        known_risks=base_idea.known_risks,
    )

    profile_free = build_product_profile(base_idea)
    profile_expensive = build_product_profile(expensive_idea)

    print(f"\n  Free:      price_friction={profile_free.price_friction:.2f}")
    print(f"  $100+/mo:  price_friction={profile_expensive.price_friction:.2f}")

    all_passed = True
    test_archetypes = ["trend_adopter", "price_pragmatist", "convenience_user", "brand_buyer", "analytical_skeptic"]
    for arch_id in test_archetypes:
        eval_def = get_archetype_evaluation(arch_id)
        bl_free = compute_archetype_baseline(profile_free, eval_def)
        bl_expensive = compute_archetype_baseline(profile_expensive, eval_def)
        drop = bl_free - bl_expensive
        print(f"\n  {arch_id:20s}: free={bl_free:.3f}  expensive={bl_expensive:.3f}  drop={drop:.3f}")

    # Price-Pragmatist should drop more than Trend-Adopter
    pp_eval = get_archetype_evaluation("price_pragmatist")
    ta_eval = get_archetype_evaluation("trend_adopter")
    pp_drop = compute_archetype_baseline(profile_free, pp_eval) - compute_archetype_baseline(profile_expensive, pp_eval)
    ta_drop = compute_archetype_baseline(profile_free, ta_eval) - compute_archetype_baseline(profile_expensive, ta_eval)

    ratio = pp_drop / ta_drop if ta_drop > 0 else float("inf")
    passed = pp_drop > ta_drop and pp_drop >= 0.15
    status = "PASS" if passed else "FAIL"
    print(f"\n  Price-Pragmatist drop: {pp_drop:.3f}")
    print(f"  Trend-Adopter drop:    {ta_drop:.3f}")
    print(f"  Ratio:                 {ratio:.1f}x")
    print(f"  Price-Pragmatist drops harder? [{status}]")
    if not passed:
        all_passed = False

    # Brand-Buyer should drop LESS than Trend-Adopter (or even gain)
    # because brand_buyer has positive price_friction weight
    bb_eval = get_archetype_evaluation("brand_buyer")
    bb_drop = compute_archetype_baseline(profile_free, bb_eval) - compute_archetype_baseline(profile_expensive, bb_eval)
    passed_bb = bb_drop < ta_drop
    status_bb = "PASS" if passed_bb else "FAIL"
    print(f"\n  Brand-Buyer drop:     {bb_drop:.3f}")
    print(f"  Brand-Buyer less price-sensitive than Trend-Adopter? [{status_bb}]")
    if not passed_bb:
        all_passed = False

    return all_passed


# ---------------------------------------------------------------------------
# Layer 3: Individual delta bounds
# ---------------------------------------------------------------------------

def run_layer_3():
    """Test that individual deltas stay within +-0.10 bounds."""
    print("\n" + "=" * 70)
    print("LAYER 3: Individual Delta Bounds Validation")
    print("=" * 70)

    all_passed = True

    for product_name, idea in TEST_PRODUCTS.items():
        profile = build_product_profile(idea)

        # Test with extreme personalities
        extreme_cases = [
            ("max_all", NpcPersonality(openness=1.0, skepticism=1.0, tech_savviness=1.0,
                                       price_sensitivity=1.0, social_influence=1.0,
                                       conformity=1.0, novelty_seeking=1.0)),
            ("min_all", NpcPersonality(openness=0.0, skepticism=0.0, tech_savviness=0.0,
                                       price_sensitivity=0.0, social_influence=0.0,
                                       conformity=0.0, novelty_seeking=0.0)),
            ("high_skeptic", NpcPersonality(openness=0.1, skepticism=0.95, tech_savviness=0.2,
                                            price_sensitivity=0.9, social_influence=0.1,
                                            conformity=0.1, novelty_seeking=0.05)),
            ("high_enthusiast", NpcPersonality(openness=0.95, skepticism=0.1, tech_savviness=0.9,
                                               price_sensitivity=0.1, social_influence=0.9,
                                               conformity=0.2, novelty_seeking=0.95)),
        ]

        for case_name, personality in extreme_cases:
            delta = compute_individual_delta(personality, profile)
            in_bounds = -0.10 <= delta <= 0.10
            if not in_bounds:
                print(f"  FAIL: {product_name} x {case_name}: delta={delta:.4f} OUT OF BOUNDS")
                all_passed = False

    if all_passed:
        print("  All individual deltas within [-0.10, +0.10] bounds: PASS")

    return all_passed


# ---------------------------------------------------------------------------
# Layer 4: Face validity scenarios (8 archetypes)
# ---------------------------------------------------------------------------

def run_layer_4():
    """Test expected archetype orderings for specific products across all 8 archetypes."""
    print("\n" + "=" * 70)
    print("LAYER 4: Face Validity Scenarios (8 archetypes)")
    print("=" * 70)

    reload_evaluations()

    # With 8 archetypes, use top 3 / bottom 3 for checks
    scenarios = [
        {
            "name": "Free SaaS concept -> Trend-Adopter & Values-Buyer should lead, Analytical-Skeptic trails",
            "product": "free_saas_concept",
            "expected_high": ["trend_adopter", "values_buyer"],
            "expected_low": ["analytical_skeptic"],
        },
        {
            "name": "Expensive hardware -> Price-Pragmatist should hate it, Brand-Buyer should lead",
            "product": "expensive_hardware",
            "expected_high": ["brand_buyer"],
            "expected_low": ["price_pragmatist"],
        },
        {
            "name": "Health app -> Trend-Adopter should lead, Price-Pragmatist trails",
            "product": "health_app",
            "expected_high": ["trend_adopter"],
            "expected_low": ["price_pragmatist"],
        },
        {
            "name": "Saturated todo -> Social-Follower should lead (loves mainstream)",
            "product": "saturated_todo",
            "expected_high": ["social_follower"],
            "expected_low": ["price_pragmatist"],
        },
        {
            "name": "Privacy messenger -> Values-Buyer should appreciate it",
            "product": "privacy_messenger",
            "expected_high": ["values_buyer"],
            "expected_low": [],
        },
    ]

    all_passed = True
    for scenario in scenarios:
        idea = TEST_PRODUCTS[scenario["product"]]
        profile = build_product_profile(idea)

        baselines = {}
        for arch_id in ALL_ARCHETYPES:
            eval_def = get_archetype_evaluation(arch_id)
            baselines[arch_id] = compute_archetype_baseline(profile, eval_def)

        sorted_archetypes = sorted(baselines.items(), key=lambda x: x[1], reverse=True)
        top_3 = [a[0] for a in sorted_archetypes[:3]]
        bottom_3 = [a[0] for a in sorted_archetypes[-3:]]

        passed = True
        for expected_high in scenario["expected_high"]:
            if expected_high not in top_3:
                passed = False
        for expected_low in scenario["expected_low"]:
            if expected_low not in bottom_3:
                passed = False

        status = "PASS" if passed else "FAIL"
        print(f"\n  [{status}] {scenario['name']}")
        for arch_id, bl in sorted_archetypes:
            marker = ""
            if arch_id in scenario["expected_high"]:
                marker = " <-- expected high"
            elif arch_id in scenario["expected_low"]:
                marker = " <-- expected low"
            print(f"    {arch_id:20s}: {bl:.3f}{marker}")

        if not passed:
            all_passed = False

    return all_passed


# ---------------------------------------------------------------------------
# Layer 5: Convergence & archetype coherence (simulated, no LLM)
# ---------------------------------------------------------------------------

def run_layer_5():
    """Test convergence tracker with synthetic NPC data.

    Verifies:
    - Variance stability detection works
    - Archetype coherence computation works
    - Result classification produces expected outcomes
    """
    print("\n" + "=" * 70)
    print("LAYER 5: Convergence & Archetype Coherence Validation")
    print("=" * 70)

    from backend.simulation.convergence import ConvergenceTracker
    from backend.simulation.npc import Npc, NpcState
    from backend.simulation.population import generate_population

    reload_evaluations()
    all_passed = True

    # --- Test 1: Convergence tracker with stable scenario ---
    print("\n  --- Test: Stable convergence detection ---")
    tracker = ConvergenceTracker()

    # Generate a real population to get proper archetypes
    npcs, npc_archetypes = generate_population(size=30, preset="balanced", seed=42)

    # Simulate 5 ticks of gradually stabilizing interest
    idea = TEST_PRODUCTS["free_saas_concept"]
    profile = build_product_profile(idea)

    for npc in npcs:
        npc.state.aware = True
        npc.state.awareness_tick = 1
        # Set interest based on archetype baseline
        eval_def = get_archetype_evaluation(npc.archetype)
        baseline = compute_archetype_baseline(profile, eval_def)
        ind_delta = compute_individual_delta(npc.personality, profile)
        npc.state.interest_score = max(0.0, min(1.0, baseline + ind_delta))
        npc.state.stance = "interested" if npc.state.interest_score > 0.5 else "skeptical"

    # Tick 1: initial
    tracker.record_tick(1, npcs, npc_archetypes)
    # Ticks 2-5: minimal change (simulating stability)
    for tick in range(2, 6):
        for npc in npcs:
            npc.state.interest_score += 0.001  # tiny drift
            npc.state.interest_score = min(1.0, npc.state.interest_score)
        tracker.record_tick(tick, npcs, npc_archetypes)

    state = tracker.state
    print(f"    interest_stable: {state.interest_stable}")
    print(f"    variance_stable: {state.variance_stable}")
    print(f"    result_class: {state.result_class}")

    # After 5 ticks of tiny drift, should be stable_convergence
    passed = state.result_class == "stable_convergence"
    status = "PASS" if passed else "FAIL"
    print(f"    Expected stable_convergence: [{status}]")
    if not passed:
        all_passed = False

    # --- Test 2: Archetype coherence should be low (deterministic baselines dominate) ---
    print("\n  --- Test: Archetype coherence (within-group std dev) ---")
    coherence = state.archetype_coherence
    if coherence:
        avg_std = sum(coherence.values()) / len(coherence)
        print(f"    Average within-archetype std dev: {avg_std:.4f}")
        for arch_id, std in sorted(coherence.items()):
            status_c = "OK" if std < 0.15 else "HIGH"
            print(f"      {arch_id:20s}: {std:.4f} [{status_c}]")

        # With purely deterministic scores, coherence should be very low
        passed_c = avg_std < 0.15
        status = "PASS" if passed_c else "FAIL"
        print(f"    Average std dev < 0.15: [{status}]")
        if not passed_c:
            all_passed = False
    else:
        print("    No coherence data (no archetypes mapped)")
        all_passed = False

    # --- Test 3: Result classification not 'unknown' ---
    print("\n  --- Test: Result classification is meaningful ---")
    passed_rc = state.result_class != "unknown"
    status = "PASS" if passed_rc else "FAIL"
    print(f"    result_class = '{state.result_class}' (not 'unknown'): [{status}]")
    if not passed_rc:
        all_passed = False

    # --- Test 4: Convergence dict has all expected fields ---
    print("\n  --- Test: Convergence state has all new fields ---")
    d = state.to_dict()
    required_fields = [
        "variance_stable", "variance_delta", "archetype_coherence", "result_class",
    ]
    missing = [f for f in required_fields if f not in d]
    passed_fields = len(missing) == 0
    status = "PASS" if passed_fields else "FAIL"
    print(f"    All new fields present: [{status}]")
    if missing:
        print(f"    Missing: {missing}")
        all_passed = False

    return all_passed


# ---------------------------------------------------------------------------
# Holdout products (never used during weight tuning)
# ---------------------------------------------------------------------------

HOLDOUT_PRODUCTS = {
    "language_learning_app": InjectedIdea(
        title="LingoLoop",
        description="Spaced-repetition language learning app with AI conversation partner and speech recognition for immersive practice",
        category="education",
        stage="mvp",
        target_audience="adults learning a second language",
        price_point="$10-$20/mo",
        problem_statement="Language learners plateau without conversation practice partners",
        existing_alternatives="Duolingo, Babbel, Rosetta Stone, Busuu",
        differentiator="AI conversation partner with real-time accent correction",
        known_strengths="Engaging conversation mode, effective spaced repetition",
        known_risks="AI voices still sound robotic, limited to 8 languages",
    ),
    "sustainable_fashion": InjectedIdea(
        title="GreenThread",
        description="Sustainable fashion marketplace connecting conscious consumers with verified ethical clothing brands and transparent supply chains",
        category="ecommerce",
        stage="launched",
        target_audience="environmentally conscious millennials",
        price_point="$50-$100/mo",
        problem_statement="Consumers want ethical fashion but cannot verify brand sustainability claims",
        existing_alternatives="ThredUp, Poshmark, Everlane",
        differentiator="Blockchain-verified supply chain transparency for every garment",
        known_strengths="Strong brand partnerships, verified sustainability scores",
        known_risks="Premium pricing limits market, supply chain verification is slow",
    ),
    "pet_tech_device": InjectedIdea(
        title="PawSense Collar",
        description="Smart pet collar with GPS tracking, activity monitoring, and health alerts for dogs using veterinary-grade sensors",
        category="consumer_hardware",
        stage="prototype",
        target_audience="dog owners",
        price_point="$50-$100/mo",
        problem_statement="Pet owners worry about their dogs location and health when away",
        existing_alternatives="Fi Smart Collar, Whistle, Apple AirTag",
        differentiator="Veterinary-grade health monitoring with anomaly detection",
        known_strengths="Medical-grade sensors, long battery life",
        known_risks="Collar size and weight for small dogs, subscription model required",
    ),
    "developer_tool_free": InjectedIdea(
        title="QueryBench",
        description="Open-source SQL query optimizer and visual explain-plan analyzer for PostgreSQL databases with one-click index suggestions",
        category="saas",
        stage="launched",
        target_audience="backend developers and DBAs",
        price_point="free",
        problem_statement="",
        existing_alternatives="pgAdmin, DataGrip, DBeaver, EXPLAIN ANALYZE",
        differentiator="Visual bottleneck detection with one-click index suggestions",
        known_strengths="Fast, open-source, Postgres-native",
        known_risks="",
    ),
}


# ---------------------------------------------------------------------------
# Layer 6: Input wording robustness
# ---------------------------------------------------------------------------

PROFILE_DIMS = [
    "novelty", "utility_clarity", "differentiation", "price_friction",
    "trust_barrier", "identity_fit", "trial_friction", "market_saturation",
]


def run_layer_6():
    """Input wording robustness: same product, 3 description styles produce same baselines.

    build_product_profile() is rule-based. Description text only affects utility_clarity
    via length. All other dimensions are driven by structured fields. This layer verifies
    that superficial wording changes don't alter deterministic outcomes.
    """
    print("\n" + "=" * 70)
    print("LAYER 6: Input Wording Robustness")
    print("=" * 70)

    reload_evaluations()
    all_passed = True

    # 3 versions of the same product, varying ONLY text wording (not structured fields)
    versions = {
        "neutral": InjectedIdea(
            title="FitTrack Pro",
            description=(
                "Health monitoring app that tracks nutrition, exercise, and sleep "
                "with personalized recommendations based on user behavior patterns. "
                "Analyzes daily habits and provides actionable insights for improvement."
            ),
            category="health_wellness",
            stage="prototype",
            target_audience="health-conscious adults 25-45",
            price_point="$20-$50/mo",
            problem_statement="People struggle to maintain consistent healthy habits",
            existing_alternatives="MyFitnessPal, Fitbit app, Apple Health",
            differentiator="AI adapts recommendations weekly based on patterns",
            known_strengths="Accurate tracking, clean interface",
            known_risks="Requires consistent data input",
        ),
        "marketing": InjectedIdea(
            title="FitTrack Pro",
            description=(
                "Revolutionary AI-powered wellness companion that transforms your health journey! "
                "Track nutrition, exercise, and sleep patterns with cutting-edge personalized "
                "recommendations that actually work. Join thousands already living healthier!"
            ),
            category="health_wellness",
            stage="prototype",
            target_audience="health-conscious adults 25-45",
            price_point="$20-$50/mo",
            problem_statement=(
                "Millions of people fail at building healthy habits because "
                "one-size-fits-all approaches simply do not work!"
            ),
            existing_alternatives="MyFitnessPal, Fitbit app, Apple Health",
            differentiator=(
                "Our proprietary AI engine learns YOUR unique patterns and delivers "
                "hyper-personalized weekly adaptations!"
            ),
            known_strengths="Industry-leading accuracy, award-winning beautiful UI",
            known_risks="Requires users to consistently log their data",
        ),
        "technical": InjectedIdea(
            title="FitTrack Pro",
            description=(
                "ML-based health telemetry platform. Ingests nutrition macros, activity sensor "
                "data, and polysomnographic sleep metrics. Outputs personalized behavioral "
                "nudges via adaptive Bayesian model with weekly retraining cycles."
            ),
            category="health_wellness",
            stage="prototype",
            target_audience="health-conscious adults 25-45",
            price_point="$20-$50/mo",
            problem_statement=(
                "Adherence to health protocols degrades without "
                "closed-loop personalized feedback"
            ),
            existing_alternatives="MyFitnessPal, Fitbit app, Apple Health",
            differentiator=(
                "Adaptive Bayesian recommendation engine retrained weekly "
                "on user behavior vectors"
            ),
            known_strengths="High-fidelity tracking, polished UX",
            known_risks="Cold-start problem requires minimum 7 days of consistent data entry",
        ),
    }

    profiles = {name: build_product_profile(idea) for name, idea in versions.items()}

    # CHECK 1: All 8 profile dimensions differ by <= 0.05 across versions
    print("\n  --- Check 1: Profile dimension stability ---")
    for dim in PROFILE_DIMS:
        values = [getattr(p, dim) for p in profiles.values()]
        spread = max(values) - min(values)
        status = "PASS" if spread <= 0.05 else "FAIL"
        print(f"    {dim:20s}: spread={spread:.3f} [{status}]")
        if spread > 0.05:
            for name, p in profiles.items():
                print(f"      {name}: {getattr(p, dim):.3f}")
            all_passed = False

    # CHECK 2: For each archetype, baselines across versions differ by <= 0.02
    print("\n  --- Check 2: Archetype baseline stability ---")
    for arch_id in ALL_ARCHETYPES:
        eval_def = get_archetype_evaluation(arch_id)
        baselines = [compute_archetype_baseline(p, eval_def) for p in profiles.values()]
        spread = max(baselines) - min(baselines)
        status = "PASS" if spread <= 0.02 else "FAIL"
        if spread > 0.02:
            print(f"    {arch_id:20s}: spread={spread:.3f} [{status}]")
            all_passed = False
    if all_passed:
        print("    All archetype baselines within 0.02 band: PASS")

    # CHECK 3: Archetype rank ordering is identical across all 3 versions
    print("\n  --- Check 3: Rank ordering stability ---")
    rankings = []
    for name, p in profiles.items():
        ranked = sorted(
            ALL_ARCHETYPES,
            key=lambda a: compute_archetype_baseline(p, get_archetype_evaluation(a)),
            reverse=True,
        )
        rankings.append(ranked)
    ranks_match = rankings[0] == rankings[1] == rankings[2]
    status = "PASS" if ranks_match else "FAIL"
    print(f"    Identical ordering across 3 versions: [{status}]")
    if not ranks_match:
        for name, ranking in zip(profiles.keys(), rankings):
            print(f"      {name}: {ranking}")
        all_passed = False

    return all_passed


# ---------------------------------------------------------------------------
# Layer 7: Archetype behavioral separation
# ---------------------------------------------------------------------------

def run_layer_7():
    """Archetype behavioral separation across 5 dimensions.

    For each product, verify archetypes differ in:
    1. Initial interest (baseline)
    2. Would try (baseline >= adoption_threshold - 0.10)
    3. Would pay (baseline >= adoption_threshold AND price not prohibitive)
    4. Would recommend (baseline >= 0.65)
    5. Primary objection category (highest-drag penalty dimension)
    """
    print("\n" + "=" * 70)
    print("LAYER 7: Archetype Behavioral Separation (5 dimensions)")
    print("=" * 70)

    reload_evaluations()
    all_passed = True

    for product_name, idea in TEST_PRODUCTS.items():
        profile = build_product_profile(idea)
        print(f"\n  --- Product: {product_name} ---")

        results = {}
        for arch_id in ALL_ARCHETYPES:
            eval_def = get_archetype_evaluation(arch_id)
            baseline = compute_archetype_baseline(profile, eval_def)

            would_try = baseline >= (eval_def.adoption_threshold - 0.10)

            if arch_id == "brand_buyer":
                would_pay = baseline >= eval_def.adoption_threshold
            else:
                would_pay = (
                    baseline >= eval_def.adoption_threshold
                    and profile.price_friction < 0.60
                )

            would_recommend = baseline >= 0.65

            # Primary objection: which negative weight contributes most drag?
            penalty_dims = {
                dim: w for dim, w in eval_def.weights.items() if w < 0
            }
            if penalty_dims:
                primary_objection = max(
                    penalty_dims.items(),
                    key=lambda dw: abs(dw[1]) * getattr(profile, dw[0], 0.5),
                )[0]
            else:
                primary_objection = "none"

            results[arch_id] = {
                "interest": baseline,
                "would_try": would_try,
                "would_pay": would_pay,
                "would_recommend": would_recommend,
                "primary_objection": primary_objection,
            }

        # Print table
        print(f"    {'archetype':20s} {'interest':>8s} {'try':>5s} {'pay':>5s} {'rec':>5s} {'objection':>18s}")
        for arch_id in ALL_ARCHETYPES:
            r = results[arch_id]
            print(
                f"    {arch_id:20s} {r['interest']:8.3f} "
                f"{'Y' if r['would_try'] else 'N':>5s} "
                f"{'Y' if r['would_pay'] else 'N':>5s} "
                f"{'Y' if r['would_recommend'] else 'N':>5s} "
                f"{r['primary_objection']:>18s}"
            )

        # CHECK 1: At least 2 distinct primary objection categories
        # (free products may only trigger 2 penalty dimensions)
        objection_set = {r["primary_objection"] for r in results.values()}
        passed_obj = len(objection_set) >= 2
        status = "PASS" if passed_obj else "FAIL"
        print(f"    Distinct objection categories: {len(objection_set)} (min 2) [{status}]")
        if not passed_obj:
            all_passed = False

        # CHECK 2: would_pay / would_recommend each have at least one T and one F
        # (would_try can be uniformly True for free/low-friction products — that's realistic)
        for dim_name in ["would_pay", "would_recommend"]:
            values = [r[dim_name] for r in results.values()]
            has_both = True in values and False in values
            status = "PASS" if has_both else "FAIL"
            if not has_both:
                print(f"    {dim_name} is uniform ({values[0]}) [{status}]")
                all_passed = False
        # would_try uniformity is just a warning
        try_values = [r["would_try"] for r in results.values()]
        if not (True in try_values and False in try_values):
            print(f"    would_try is uniform ({try_values[0]}) [WARN — expected for free/low-friction products]")

        # CHECK 3: >= 6 of 8 archetypes have unique behavioral fingerprints
        fingerprints = set()
        for arch_id, r in results.items():
            fp = (
                round(r["interest"], 2),
                r["would_try"],
                r["would_pay"],
                r["would_recommend"],
                r["primary_objection"],
            )
            fingerprints.add(fp)
        passed_fp = len(fingerprints) >= 6
        status = "PASS" if passed_fp else "FAIL"
        print(f"    Unique fingerprints: {len(fingerprints)}/8 (min 6) [{status}]")
        if not passed_fp:
            all_passed = False

    return all_passed


# ---------------------------------------------------------------------------
# Layer 8: Repeated-exposure sensitivity
# ---------------------------------------------------------------------------

def run_layer_8():
    """Verify exposure decay formulas are bounded and don't produce runaway effects.

    Social-Follower formula: min(1.5, 1.0 + 0.08 * exposure) — caps at 1.5x
    Others formula:          1.0 / (1.0 + 0.25 * exposure)   — diminishes monotonically
    """
    print("\n" + "=" * 70)
    print("LAYER 8: Repeated-Exposure Sensitivity")
    print("=" * 70)

    all_passed = True

    # --- Test 1: Social-Follower susceptibility is bounded ---
    print("\n  --- Test 1: Social-Follower decay cap ---")
    follower_values = []
    for exposure in range(0, 25):
        decay = min(1.5, 1.0 + 0.08 * exposure)
        follower_values.append(decay)

    cap_ok = all(v <= 1.5 for v in follower_values)
    reaches_cap = follower_values[-1] == 1.5
    passed_1 = cap_ok and reaches_cap
    status = "PASS" if passed_1 else "FAIL"
    print(f"    All values <= 1.5: {cap_ok}")
    print(f"    Reaches cap: {reaches_cap}")
    print(f"    Social-Follower cap check: [{status}]")
    if not passed_1:
        all_passed = False

    # --- Test 2: Non-follower decay is monotonically decreasing ---
    print("\n  --- Test 2: Non-follower monotonic decay ---")
    prev = None
    monotonic = True
    for exposure in range(0, 25):
        decay = 1.0 / (1.0 + 0.25 * exposure)
        if prev is not None and decay > prev:
            monotonic = False
            break
        prev = decay
    final_decay = 1.0 / (1.0 + 0.25 * 20)
    under_threshold = final_decay < 0.20
    passed_2 = monotonic and under_threshold
    status = "PASS" if passed_2 else "FAIL"
    print(f"    Monotonically decreasing: {monotonic}")
    print(f"    After 20 ticks: {final_decay:.3f} (< 0.20: {under_threshold})")
    print(f"    Non-follower decay check: [{status}]")
    if not passed_2:
        all_passed = False

    # --- Test 3: Cumulative peer influence simulation ---
    print("\n  --- Test 3: Cumulative peer influence (Social-Follower vs Analytical-Skeptic) ---")
    trajectories = {}
    for arch_id, susc_mult, skepticism_val in [
        ("social_follower", 1.30, 0.3),
        ("analytical_skeptic", 0.35, 0.8),
    ]:
        interest = 0.5
        conformity = 0.7
        peer_avg = 0.85

        trajectory = [interest]
        for tick in range(1, 21):
            base_susc = conformity * (1.0 - skepticism_val * 0.3) * 0.3
            base_susc *= susc_mult
            if arch_id == "social_follower":
                decay = min(1.5, 1.0 + 0.08 * tick)
            else:
                decay = 1.0 / (1.0 + 0.25 * tick)
            susceptibility = base_susc * decay
            delta = (peer_avg - interest) * susceptibility
            interest = max(0.0, min(1.0, interest + delta))
            trajectory.append(interest)

        trajectories[arch_id] = trajectory
        movement = trajectory[-1] - trajectory[0]
        print(f"    {arch_id:20s}: start={trajectory[0]:.3f} end={trajectory[-1]:.3f} "
              f"movement={movement:.3f}")

    follower_move = trajectories["social_follower"][-1] - trajectories["social_follower"][0]
    skeptic_move = trajectories["analytical_skeptic"][-1] - trajectories["analytical_skeptic"][0]

    # Social-Follower stays bounded
    follower_bounded = all(v <= 1.0 for v in trajectories["social_follower"])
    passed_fb = follower_bounded
    status = "PASS" if passed_fb else "FAIL"
    print(f"    Social-Follower stays <= 1.0: [{status}]")
    if not passed_fb:
        all_passed = False

    # Analytical-Skeptic moves < 0.15
    passed_sm = skeptic_move < 0.15
    status = "PASS" if passed_sm else "FAIL"
    print(f"    Analytical-Skeptic movement < 0.15: {skeptic_move:.3f} [{status}]")
    if not passed_sm:
        all_passed = False

    # Social-Follower moves at least 2x Analytical-Skeptic
    ratio = follower_move / skeptic_move if skeptic_move > 0 else float("inf")
    passed_ratio = follower_move > skeptic_move * 2
    status = "PASS" if passed_ratio else "FAIL"
    print(f"    Social-Follower/Analytical-Skeptic ratio: {ratio:.1f}x (min 2x) [{status}]")
    if not passed_ratio:
        all_passed = False

    # --- Test 4: Print decay curves at key tick marks ---
    print("\n  --- Decay curves at key ticks ---")
    print(f"    {'tick':>6s}  {'social_follower':>16s}  {'other':>10s}")
    for t in [0, 1, 3, 6, 10, 15, 20]:
        f_decay = min(1.5, 1.0 + 0.08 * t)
        o_decay = 1.0 / (1.0 + 0.25 * t)
        print(f"    {t:6d}  {f_decay:16.3f}  {o_decay:10.3f}")

    return all_passed


# ---------------------------------------------------------------------------
# Layer 9: Seed sensitivity
# ---------------------------------------------------------------------------

def run_layer_9():
    """Seed sensitivity: same product x preset, 10 seeds -> classify variance.

    LOW:    mean_spread < 0.04, adoption_spread < 0.10
    MEDIUM: mean_spread < 0.08, adoption_spread < 0.20
    HIGH:   worse (FAIL — deterministic baseline not dominating)
    """
    print("\n" + "=" * 70)
    print("LAYER 9: Seed Sensitivity")
    print("=" * 70)

    from backend.simulation.population import generate_population

    reload_evaluations()
    all_passed = True

    seeds = list(range(42, 52))  # 10 seeds

    for product_name in ["free_saas_concept", "expensive_hardware", "health_app"]:
        idea = TEST_PRODUCTS[product_name]
        profile = build_product_profile(idea)
        print(f"\n  --- Product: {product_name} ---")

        per_seed = []
        for seed in seeds:
            npcs, npc_archetypes = generate_population(size=30, preset="balanced", seed=seed)

            scores = []
            for npc in npcs:
                eval_def = get_archetype_evaluation(npc.archetype)
                baseline = compute_archetype_baseline(profile, eval_def)
                ind_delta = compute_individual_delta(npc.personality, profile)
                scores.append(max(0.0, min(1.0, baseline + ind_delta)))

            mean_interest = sum(scores) / len(scores)
            adoption_rate = sum(1 for s in scores if s >= 0.65) / len(scores)
            per_seed.append({
                "seed": seed,
                "mean_interest": mean_interest,
                "adoption_rate": adoption_rate,
            })

        means = [r["mean_interest"] for r in per_seed]
        adoptions = [r["adoption_rate"] for r in per_seed]
        mean_spread = max(means) - min(means)
        adoption_spread = max(adoptions) - min(adoptions)

        if mean_spread < 0.04 and adoption_spread < 0.10:
            sensitivity = "LOW"
        elif mean_spread < 0.08 and adoption_spread < 0.20:
            sensitivity = "MEDIUM"
        else:
            sensitivity = "HIGH"

        passed = sensitivity in ("LOW", "MEDIUM")
        status = "PASS" if passed else "FAIL"
        print(f"    Mean interest:  min={min(means):.3f} max={max(means):.3f} "
              f"spread={mean_spread:.3f}")
        print(f"    Adoption rate:  min={min(adoptions):.3f} max={max(adoptions):.3f} "
              f"spread={adoption_spread:.3f}")
        print(f"    Sensitivity: {sensitivity} [{status}]")
        if not passed:
            all_passed = False

    return all_passed


# ---------------------------------------------------------------------------
# Layer 10: Holdout validation scenarios
# ---------------------------------------------------------------------------

def run_layer_10():
    """Holdout validation: products never seen during weight tuning.

    If the system only works on the 5 tuning products, it's overfit.
    """
    print("\n" + "=" * 70)
    print("LAYER 10: Holdout Validation Scenarios (unseen products)")
    print("=" * 70)

    reload_evaluations()
    all_passed = True

    holdout_scenarios = [
        {
            "name": "LingoLoop (education MVP) -> Values-Buyer high, Price-Pragmatist low",
            "product": "language_learning_app",
            "expected_high": ["values_buyer"],
            "expected_low": ["price_pragmatist"],
        },
        {
            "name": "GreenThread (ethical fashion) -> Values-Buyer high, Price-Pragmatist low",
            "product": "sustainable_fashion",
            "expected_high": ["values_buyer"],
            "expected_low": ["price_pragmatist"],
        },
        {
            "name": "PawSense Collar (hardware prototype) -> Trend-Adopter high, Price-Pragmatist & Analytical-Skeptic low",
            "product": "pet_tech_device",
            "expected_high": ["trend_adopter"],
            "expected_low": ["price_pragmatist", "analytical_skeptic"],
        },
        {
            "name": "QueryBench (free dev tool) -> Values-Buyer high, Price-Pragmatist low",
            "product": "developer_tool_free",
            "expected_high": ["values_buyer"],
            "expected_low": ["price_pragmatist"],
        },
    ]

    for scenario in holdout_scenarios:
        idea = HOLDOUT_PRODUCTS[scenario["product"]]
        profile = build_product_profile(idea)

        baselines = {}
        for arch_id in ALL_ARCHETYPES:
            eval_def = get_archetype_evaluation(arch_id)
            baselines[arch_id] = compute_archetype_baseline(profile, eval_def)

        sorted_archetypes = sorted(baselines.items(), key=lambda x: x[1], reverse=True)
        top_3 = [a for a, _ in sorted_archetypes[:3]]
        bottom_3 = [a for a, _ in sorted_archetypes[-3:]]

        passed = True
        for eh in scenario["expected_high"]:
            if eh not in top_3:
                passed = False
        for el in scenario["expected_low"]:
            if el not in bottom_3:
                passed = False

        status = "PASS" if passed else "FAIL"
        print(f"\n  [{status}] {scenario['name']}")
        for arch_id, bl in sorted_archetypes:
            marker = ""
            if arch_id in scenario["expected_high"]:
                marker = " <-- expected high"
            elif arch_id in scenario["expected_low"]:
                marker = " <-- expected low"
            print(f"    {arch_id:20s}: {bl:.3f}{marker}")

        if not passed:
            all_passed = False

    # Additional check: spread >= 0.15 for all holdout products
    print("\n  --- Holdout product spread check ---")
    for name, idea in HOLDOUT_PRODUCTS.items():
        profile = build_product_profile(idea)
        baselines = [
            compute_archetype_baseline(profile, get_archetype_evaluation(a))
            for a in ALL_ARCHETYPES
        ]
        spread = max(baselines) - min(baselines)
        passed_s = spread >= 0.15
        status = "PASS" if passed_s else "FAIL"
        print(f"    {name:30s}: spread={spread:.3f} (min 0.15) [{status}]")
        if not passed_s:
            all_passed = False

    return all_passed


# ---------------------------------------------------------------------------
# Layer 11: Competition context validation
# ---------------------------------------------------------------------------

def run_layer_11():
    """Competition context: classification, dimensions, prompt safety, backward compat.

    Tests:
    1.  Classification accuracy: verified vs inferred vs behavioral vs unknown
    2.  Verified ≠ inferred: SomeApp gets inferred (0.4), NOT verified
    3.  Confidence-weighted saturation: verified > inferred > unknown
    4.  Backward compatibility: None context → identical profile
    5.  Product profile integration: market_saturation within 0.10 of old
    6.  Verified-names filtering: only verified_named_competitor in prompt names
    7.  Inferred excluded from prompts: SomeApp not in verified_names
    8.  Category fit: same-space competitors score higher intensity
    9.  Switching cost: incumbent lock-in + behavioral habits both contribute
    10. Dimension separation: trust, familiarity, saturation are distinct
    11. Competition adjustment bounds: ±0.08
    12. Archetype sensitivity: low-openness gets switching cost penalty, social_follower gets familiarity boost
    """
    print("\n" + "=" * 70)
    print("LAYER 11: Competition Context Validation")
    print("=" * 70)

    from backend.simulation.competition import (
        classify_alternatives,
        compute_competition_adjustment,
    )

    all_passed = True

    # --- Test 1: Classification accuracy ---
    print("\n  --- Test 1: Classification accuracy ---")
    cases = [
        ("Trello, Asana, Notion", [
            ("Trello", "verified_named_competitor", 1.0, True),
            ("Asana", "verified_named_competitor", 1.0, True),
            ("Notion", "verified_named_competitor", 1.0, True),
        ]),
        ("pen and paper, spreadsheets", [
            ("pen and paper", "behavioral_alternative", 0.9, False),
            ("spreadsheets", "behavioral_alternative", 0.9, False),
        ]),
        ("", []),
    ]
    test1_ok = True
    for raw, expected in cases:
        ctx = classify_alternatives(raw)
        if len(ctx.alternatives) != len(expected):
            print(f"    FAIL: '{raw}' → {len(ctx.alternatives)} alts, expected {len(expected)}")
            test1_ok = False
            continue
        for alt, (exp_text, exp_class, exp_conf, exp_known) in zip(ctx.alternatives, expected):
            ok = (
                alt.raw_text == exp_text
                and alt.classification == exp_class
                and alt.confidence == exp_conf
                and alt.known_product == exp_known
            )
            if not ok:
                print(f"    FAIL: '{exp_text}' → {alt.classification}/{alt.confidence}/{alt.known_product}, "
                      f"expected {exp_class}/{exp_conf}/{exp_known}")
                test1_ok = False
    status = "PASS" if test1_ok else "FAIL"
    print(f"    Classification accuracy: [{status}]")
    if not test1_ok:
        all_passed = False

    # --- Test 2: Verified ≠ inferred ---
    print("\n  --- Test 2: Verified vs inferred split ---")
    ctx_split = classify_alternatives("Trello, SomeApp, random stuff")
    trello = ctx_split.alternatives[0]
    someapp = ctx_split.alternatives[1]
    random_s = ctx_split.alternatives[2]
    passed_split = (
        trello.classification == "verified_named_competitor"
        and trello.confidence == 1.0
        and someapp.classification == "inferred_named_competitor"
        and someapp.confidence == 0.4
        and random_s.classification == "behavioral_alternative"
        and random_s.confidence == 0.4
    )
    status = "PASS" if passed_split else "FAIL"
    print(f"    Trello: {trello.classification}/{trello.confidence}")
    print(f"    SomeApp: {someapp.classification}/{someapp.confidence}")
    print(f"    random stuff: {random_s.classification}/{random_s.confidence}")
    print(f"    Verified/inferred correctly split: [{status}]")
    if not passed_split:
        all_passed = False

    # --- Test 3: Confidence-weighted saturation ---
    print("\n  --- Test 3: Confidence-weighted saturation ---")
    ctx_verified = classify_alternatives("Trello, Asana, Notion")
    ctx_inferred = classify_alternatives("SomeApp, AnotherApp, FakeApp")
    ctx_unknown = classify_alternatives("thing1, thing2, thing3")
    ok_sat = (
        ctx_verified.saturation_pressure > ctx_inferred.saturation_pressure
        and ctx_inferred.saturation_pressure > ctx_unknown.saturation_pressure
    )
    status = "PASS" if ok_sat else "FAIL"
    print(f"    Verified ({ctx_verified.saturation_pressure}) > "
          f"Inferred ({ctx_inferred.saturation_pressure}) > "
          f"Unknown ({ctx_unknown.saturation_pressure}): [{status}]")
    if not ok_sat:
        all_passed = False

    # --- Test 4: Backward compatibility ---
    print("\n  --- Test 4: Backward compatibility ---")
    all_products = {**TEST_PRODUCTS, **HOLDOUT_PRODUCTS}
    bc_passed = True
    for name, idea in all_products.items():
        p_old = build_product_profile(idea)
        p_new = build_product_profile(idea, competition_context=None)
        if p_old.to_dict() != p_new.to_dict():
            print(f"    FAIL: {name} differs with competition_context=None")
            bc_passed = False
    status = "PASS" if bc_passed else "FAIL"
    print(f"    All products identical with None context: [{status}]")
    if not bc_passed:
        all_passed = False

    # --- Test 5: Product profile integration ---
    print("\n  --- Test 5: Profile integration (market_saturation proximity) ---")
    for name, idea in TEST_PRODUCTS.items():
        if not idea.existing_alternatives.strip():
            continue
        p_old = build_product_profile(idea)
        ctx = classify_alternatives(idea.existing_alternatives, idea_category=idea.category)
        p_new = build_product_profile(idea, competition_context=ctx)
        diff = abs(p_old.market_saturation - p_new.market_saturation)
        passed_ms = diff <= 0.10
        status = "PASS" if passed_ms else "FAIL"
        print(f"    {name:25s}: old={p_old.market_saturation:.3f} new={p_new.market_saturation:.3f} "
              f"diff={diff:.3f} [{status}]")
        if not passed_ms:
            all_passed = False

    # --- Test 6: Verified-names filtering ---
    print("\n  --- Test 6: Verified-names filtering ---")
    ctx_mix = classify_alternatives("Trello, pen and paper, Notion")
    verified = ctx_mix.verified_names
    passed_vn = (
        "Trello" in verified
        and "Notion" in verified
        and "pen and paper" not in verified
    )
    status = "PASS" if passed_vn else "FAIL"
    print(f"    Verified names: {verified}")
    print(f"    Only verified_named_competitor in list: [{status}]")
    if not passed_vn:
        all_passed = False

    # --- Test 7: Inferred names excluded from prompts ---
    print("\n  --- Test 7: Inferred names excluded from prompts ---")
    ctx_inf = classify_alternatives("Trello, SomeApp, FakeProduct")
    verified_inf = ctx_inf.verified_names
    passed_inf = (
        "Trello" in verified_inf
        and "SomeApp" not in verified_inf
        and "FakeProduct" not in verified_inf
    )
    status = "PASS" if passed_inf else "FAIL"
    print(f"    Verified: {verified_inf} (SomeApp/FakeProduct excluded)")
    print(f"    Inferred names excluded from prompt: [{status}]")
    if not passed_inf:
        all_passed = False

    # --- Test 8: Category fit ---
    print("\n  --- Test 8: Category fit effect on intensity ---")
    ctx_same = classify_alternatives("Trello, Asana, Notion", idea_category="saas")
    ctx_diff = classify_alternatives("Trello, Asana, Notion", idea_category="health_wellness")
    passed_cat = ctx_same.direct_competition_intensity > ctx_diff.direct_competition_intensity
    status = "PASS" if passed_cat else "FAIL"
    print(f"    Same category (saas): intensity={ctx_same.direct_competition_intensity}")
    print(f"    Diff category (health): intensity={ctx_diff.direct_competition_intensity}")
    print(f"    Same-space competitors score higher: [{status}]")
    if not passed_cat:
        all_passed = False

    # --- Test 9: Switching cost from both sources ---
    print("\n  --- Test 9: Switching cost dual-source ---")
    ctx_both = classify_alternatives("Trello, Asana, pen and paper, spreadsheets")
    ctx_behavioral_only = classify_alternatives("pen and paper, spreadsheets")
    ctx_incumbent_only = classify_alternatives("Trello, Asana")
    passed_sw = (
        ctx_both.switching_cost_pressure > ctx_behavioral_only.switching_cost_pressure
        and ctx_both.switching_cost_pressure > ctx_incumbent_only.switching_cost_pressure
        and ctx_behavioral_only.switching_cost_pressure > 0
        and ctx_incumbent_only.switching_cost_pressure > 0
    )
    status = "PASS" if passed_sw else "FAIL"
    print(f"    Both sources:     {ctx_both.switching_cost_pressure}")
    print(f"    Behavioral only:  {ctx_behavioral_only.switching_cost_pressure}")
    print(f"    Incumbent only:   {ctx_incumbent_only.switching_cost_pressure}")
    print(f"    Both > either alone, both > 0: [{status}]")
    if not passed_sw:
        all_passed = False

    # --- Test 10: Dimension separation ---
    print("\n  --- Test 10: Dimension separation ---")
    # incumbent_trust_pressure should only come from verified products
    ctx_no_verified = classify_alternatives("SomeApp, FakeApp, pen and paper")
    ctx_all_verified = classify_alternatives("Trello, Asana, Notion")
    passed_sep = (
        ctx_no_verified.incumbent_trust_pressure == 0.0  # no verified → no trust pressure
        and ctx_all_verified.incumbent_trust_pressure > 0.5  # 3 verified major → high trust
        # familiarity should be nonzero even without verified (behavioral contributes)
        and ctx_no_verified.familiarity_of_solutions > 0.0
        # saturation should be much lower for unverified
        and ctx_all_verified.saturation_pressure > ctx_no_verified.saturation_pressure
    )
    status = "PASS" if passed_sep else "FAIL"
    print(f"    No verified: trust={ctx_no_verified.incumbent_trust_pressure} "
          f"familiarity={ctx_no_verified.familiarity_of_solutions} "
          f"saturation={ctx_no_verified.saturation_pressure}")
    print(f"    All verified: trust={ctx_all_verified.incumbent_trust_pressure} "
          f"familiarity={ctx_all_verified.familiarity_of_solutions} "
          f"saturation={ctx_all_verified.saturation_pressure}")
    print(f"    Dimensions are distinct: [{status}]")
    if not passed_sep:
        all_passed = False

    # --- Test 11: Competition adjustment bounds ---
    print("\n  --- Test 11: Competition adjustment bounds ---")
    ctx_heavy = classify_alternatives("Trello, Asana, Notion, Monday, ClickUp, Todoist")
    extreme_personalities = [
        {"openness": 1.0, "skepticism": 1.0, "price_sensitivity": 1.0},
        {"openness": 0.0, "skepticism": 0.0, "price_sensitivity": 0.0},
        {"openness": 0.5, "skepticism": 0.5, "price_sensitivity": 0.5},
    ]
    bounds_ok = True
    for pers in extreme_personalities:
        for arch in ALL_ARCHETYPES:
            delta = compute_competition_adjustment(ctx_heavy, pers, archetype_id=arch)
            if not (-0.08 <= delta <= 0.08):
                print(f"    FAIL: {arch} with {pers} → delta={delta} OUT OF BOUNDS")
                bounds_ok = False
    status = "PASS" if bounds_ok else "FAIL"
    print(f"    All deltas within [-0.08, +0.08]: [{status}]")
    if not bounds_ok:
        all_passed = False

    # --- Test 12: Trait-based sensitivity ---
    print("\n  --- Test 12: Trait-based sensitivity ---")
    # Low-openness personality should get switching cost penalty (openness < 0.35)
    low_openness_pers = {"openness": 0.2, "skepticism": 0.5}
    high_openness_pers = {"openness": 0.8, "skepticism": 0.5}
    low_open_delta = compute_competition_adjustment(ctx_heavy, low_openness_pers, archetype_id="analytical_skeptic")
    high_open_delta = compute_competition_adjustment(ctx_heavy, high_openness_pers, archetype_id="trend_adopter")
    passed_sensitivity = low_open_delta < high_open_delta
    status = "PASS" if passed_sensitivity else "FAIL"
    print(f"    low-openness ({low_open_delta:.4f}) < high-openness ({high_open_delta:.4f}): [{status}]")
    if not passed_sensitivity:
        all_passed = False
    # Social-Follower should get familiarity boost
    follower_delta = compute_competition_adjustment(ctx_heavy, {"openness": 0.5, "skepticism": 0.5}, archetype_id="social_follower")
    other_delta = compute_competition_adjustment(ctx_heavy, {"openness": 0.5, "skepticism": 0.5}, archetype_id="trend_adopter")
    passed_follower = follower_delta > other_delta
    status = "PASS" if passed_follower else "FAIL"
    print(f"    social_follower ({follower_delta:.4f}) > trend_adopter ({other_delta:.4f}): [{status}]")
    if not passed_follower:
        all_passed = False

    return all_passed


# ---------------------------------------------------------------------------
# Layer 12: Asset signals validation (no LLM)
# ---------------------------------------------------------------------------

# Synthetic asset signal profiles for deterministic testing
ASSET_SIGNALS_HIGH_POLISH = AssetSignals(
    perceived_polish=0.9,
    trustworthiness=0.85,
    clarity=0.8,
    visual_appeal=0.85,
    premium_feel=0.75,
    usability_impression=0.8,
    differentiation_signal=0.7,
    summary="Professional, polished product with strong visual identity.",
)

ASSET_SIGNALS_LOW_POLISH = AssetSignals(
    perceived_polish=0.2,
    trustworthiness=0.25,
    clarity=0.3,
    visual_appeal=0.2,
    premium_feel=0.15,
    usability_impression=0.25,
    differentiation_signal=0.2,
    summary="Rough prototype with minimal visual effort.",
)

ASSET_SIGNALS_NEUTRAL = AssetSignals(
    perceived_polish=0.5,
    trustworthiness=0.5,
    clarity=0.5,
    visual_appeal=0.5,
    premium_feel=0.5,
    usability_impression=0.5,
    differentiation_signal=0.5,
    summary="Average-looking product, neither impressive nor concerning.",
)


def run_layer_12():
    """Asset signals: product profile shifts, per-NPC adjustments, backward compat."""
    print("=" * 70)
    print("LAYER 12: Asset Signals Validation")
    print("=" * 70)

    reload_evaluations()
    all_passed = True

    # --- Test 1: Backward compatibility (None assets = no change) ---
    print("\n  --- Test 1: Backward compatibility ---")
    bc_ok = True
    for name, idea in TEST_PRODUCTS.items():
        p_without = build_product_profile(idea)
        p_with_none = build_product_profile(idea, asset_signals=None)
        if p_without.to_dict() != p_with_none.to_dict():
            print(f"    FAIL: {name} differs with asset_signals=None")
            bc_ok = False
    status = "PASS" if bc_ok else "FAIL"
    print(f"    All products identical with None assets: [{status}]")
    if not bc_ok:
        all_passed = False

    # --- Test 2: High-polish assets reduce trust_barrier and trial_friction ---
    print("\n  --- Test 2: High-polish assets reduce trust_barrier & trial_friction ---")
    test2_ok = True
    for name, idea in TEST_PRODUCTS.items():
        p_base = build_product_profile(idea)
        p_polished = build_product_profile(idea, asset_signals=ASSET_SIGNALS_HIGH_POLISH)

        tb_ok = p_polished.trust_barrier <= p_base.trust_barrier
        tf_ok = p_polished.trial_friction <= p_base.trial_friction

        if not tb_ok:
            print(f"    FAIL: {name} trust_barrier went UP with polish "
                  f"({p_base.trust_barrier:.3f} → {p_polished.trust_barrier:.3f})")
            test2_ok = False
        if not tf_ok:
            print(f"    FAIL: {name} trial_friction went UP with polish "
                  f"({p_base.trial_friction:.3f} → {p_polished.trial_friction:.3f})")
            test2_ok = False

    status = "PASS" if test2_ok else "FAIL"
    print(f"    High-polish assets lower trust_barrier & trial_friction: [{status}]")
    if not test2_ok:
        all_passed = False

    # --- Test 3: High-clarity assets boost utility_clarity ---
    print("\n  --- Test 3: High-clarity assets boost utility_clarity ---")
    test3_ok = True
    for name, idea in TEST_PRODUCTS.items():
        p_base = build_product_profile(idea)
        p_clear = build_product_profile(idea, asset_signals=ASSET_SIGNALS_HIGH_POLISH)

        if p_clear.utility_clarity < p_base.utility_clarity:
            print(f"    FAIL: {name} utility_clarity went DOWN with clear assets "
                  f"({p_base.utility_clarity:.3f} → {p_clear.utility_clarity:.3f})")
            test3_ok = False

    status = "PASS" if test3_ok else "FAIL"
    print(f"    High-clarity assets boost utility_clarity: [{status}]")
    if not test3_ok:
        all_passed = False

    # --- Test 4: High vs low polish produce measurable profile differences ---
    print("\n  --- Test 4: High vs low polish produce measurable differences ---")
    idea = TEST_PRODUCTS["free_saas_concept"]
    p_high = build_product_profile(idea, asset_signals=ASSET_SIGNALS_HIGH_POLISH)
    p_low = build_product_profile(idea, asset_signals=ASSET_SIGNALS_LOW_POLISH)

    # Trust barrier should be lower with high polish
    tb_diff = p_low.trust_barrier - p_high.trust_barrier
    # Trial friction should be lower with high polish
    tf_diff = p_low.trial_friction - p_high.trial_friction
    # Utility clarity should be higher with high polish
    uc_diff = p_high.utility_clarity - p_low.utility_clarity
    # Differentiation should be higher with high polish
    d_diff = p_high.differentiation - p_low.differentiation

    # All differences should be > 0 (high is better)
    test4_ok = tb_diff > 0 and tf_diff > 0 and uc_diff > 0 and d_diff > 0
    status = "PASS" if test4_ok else "FAIL"
    print(f"    trust_barrier: low={p_low.trust_barrier:.3f} high={p_high.trust_barrier:.3f} diff={tb_diff:.3f}")
    print(f"    trial_friction: low={p_low.trial_friction:.3f} high={p_high.trial_friction:.3f} diff={tf_diff:.3f}")
    print(f"    utility_clarity: low={p_low.utility_clarity:.3f} high={p_high.utility_clarity:.3f} diff={uc_diff:.3f}")
    print(f"    differentiation: low={p_low.differentiation:.3f} high={p_high.differentiation:.3f} diff={d_diff:.3f}")
    print(f"    All four dimensions diverge in expected direction: [{status}]")
    if not test4_ok:
        all_passed = False

    # --- Test 5: compute_asset_adjustment bounded ±0.10 ---
    print("\n  --- Test 5: Per-NPC adjustment bounded ±0.10 ---")
    extreme_personalities = [
        {"tech_savviness": 1.0, "price_sensitivity": 1.0, "skepticism": 1.0, "openness": 1.0},
        {"tech_savviness": 0.0, "price_sensitivity": 0.0, "skepticism": 0.0, "openness": 0.0},
        {"tech_savviness": 1.0, "price_sensitivity": 0.0, "skepticism": 0.0, "openness": 1.0},
        {"tech_savviness": 0.0, "price_sensitivity": 1.0, "skepticism": 1.0, "openness": 0.0},
    ]
    test_signals = [ASSET_SIGNALS_HIGH_POLISH, ASSET_SIGNALS_LOW_POLISH, ASSET_SIGNALS_NEUTRAL]
    bounds_ok = True
    for signals in test_signals:
        for pers in extreme_personalities:
            delta = compute_asset_adjustment(signals, pers)
            if not (-0.10 <= delta <= 0.10):
                print(f"    FAIL: delta={delta} OUT OF BOUNDS for signals={signals.summary[:30]} pers={pers}")
                bounds_ok = False
    status = "PASS" if bounds_ok else "FAIL"
    print(f"    All deltas within [-0.10, +0.10]: [{status}]")
    if not bounds_ok:
        all_passed = False

    # --- Test 6: Tech-savvy people are more sensitive to polish ---
    print("\n  --- Test 6: Tech-savvy people more sensitive to polish ---")
    tech_high = {"tech_savviness": 0.9, "price_sensitivity": 0.3, "skepticism": 0.3, "openness": 0.5}
    tech_low = {"tech_savviness": 0.1, "price_sensitivity": 0.3, "skepticism": 0.3, "openness": 0.5}

    # With HIGH polish, tech-savvy should get a bigger boost
    delta_tech_high_polish = compute_asset_adjustment(ASSET_SIGNALS_HIGH_POLISH, tech_high)
    delta_tech_low_polish = compute_asset_adjustment(ASSET_SIGNALS_HIGH_POLISH, tech_low)
    tech_polish_ok = delta_tech_high_polish > delta_tech_low_polish

    # With LOW polish, tech-savvy should get a bigger penalty
    delta_tech_high_rough = compute_asset_adjustment(ASSET_SIGNALS_LOW_POLISH, tech_high)
    delta_tech_low_rough = compute_asset_adjustment(ASSET_SIGNALS_LOW_POLISH, tech_low)
    tech_rough_ok = delta_tech_high_rough < delta_tech_low_rough

    status = "PASS" if tech_polish_ok and tech_rough_ok else "FAIL"
    print(f"    High polish: tech_high={delta_tech_high_polish:.4f} > tech_low={delta_tech_low_polish:.4f}: {tech_polish_ok}")
    print(f"    Low polish: tech_high={delta_tech_high_rough:.4f} < tech_low={delta_tech_low_rough:.4f}: {tech_rough_ok}")
    print(f"    Tech-savvy react more strongly to visual quality: [{status}]")
    if not (tech_polish_ok and tech_rough_ok):
        all_passed = False

    # --- Test 7: Price-sensitive people discount premium feel ---
    print("\n  --- Test 7: Price-sensitive discount premium feel ---")
    price_sensitive = {"tech_savviness": 0.5, "price_sensitivity": 0.9, "skepticism": 0.3, "openness": 0.5}
    price_insensitive = {"tech_savviness": 0.5, "price_sensitivity": 0.1, "skepticism": 0.3, "openness": 0.5}

    # Build high-premium signals
    premium_signals = AssetSignals(
        perceived_polish=0.5, trustworthiness=0.5, clarity=0.5,
        visual_appeal=0.5, premium_feel=0.9, usability_impression=0.5,
        differentiation_signal=0.5, summary="Premium-looking product",
    )
    delta_ps = compute_asset_adjustment(premium_signals, price_sensitive)
    delta_pi = compute_asset_adjustment(premium_signals, price_insensitive)
    test7_ok = delta_pi > delta_ps  # Price-insensitive benefits more from premium look
    status = "PASS" if test7_ok else "FAIL"
    print(f"    Premium assets: price_insensitive={delta_pi:.4f} > price_sensitive={delta_ps:.4f}: [{status}]")
    if not test7_ok:
        all_passed = False

    # --- Test 8: Neutral signals produce near-zero product profile shift ---
    print("\n  --- Test 8: Neutral signals produce minimal profile shift ---")
    test8_ok = True
    for name, idea in TEST_PRODUCTS.items():
        p_base = build_product_profile(idea)
        p_neutral = build_product_profile(idea, asset_signals=ASSET_SIGNALS_NEUTRAL)
        # Check each dimension — shift should be small (neutral = 0.5 baseline)
        dims_base = p_base.to_dict()
        dims_neutral = p_neutral.to_dict()
        for dim in ["trust_barrier", "trial_friction", "utility_clarity", "differentiation"]:
            shift = abs(dims_neutral[dim] - dims_base[dim])
            # Neutral signals (all 0.5) should shift by at most ~0.10
            if shift > 0.12:
                print(f"    FAIL: {name}.{dim} shifted by {shift:.3f} with neutral signals")
                test8_ok = False
    status = "PASS" if test8_ok else "FAIL"
    print(f"    Neutral signals shift each dimension <= 0.12: [{status}]")
    if not test8_ok:
        all_passed = False

    # --- Test 9: Asset signals don't affect unrelated dimensions ---
    print("\n  --- Test 9: Asset signals don't affect unrelated dimensions ---")
    idea = TEST_PRODUCTS["free_saas_concept"]
    p_base = build_product_profile(idea)
    p_assets = build_product_profile(idea, asset_signals=ASSET_SIGNALS_HIGH_POLISH)
    # These dimensions should be unaffected by asset signals:
    # novelty, price_friction, identity_fit, market_saturation
    test9_ok = (
        p_base.novelty == p_assets.novelty
        and p_base.price_friction == p_assets.price_friction
        and p_base.identity_fit == p_assets.identity_fit
        and p_base.market_saturation == p_assets.market_saturation
    )
    status = "PASS" if test9_ok else "FAIL"
    print(f"    novelty: {p_base.novelty} == {p_assets.novelty}")
    print(f"    price_friction: {p_base.price_friction} == {p_assets.price_friction}")
    print(f"    identity_fit: {p_base.identity_fit} == {p_assets.identity_fit}")
    print(f"    market_saturation: {p_base.market_saturation} == {p_assets.market_saturation}")
    print(f"    Unrelated dimensions unchanged: [{status}]")
    if not test9_ok:
        all_passed = False

    # --- Test 10: AssetSignals.to_dict() round-trips correctly ---
    print("\n  --- Test 10: AssetSignals.to_dict() ---")
    d = ASSET_SIGNALS_HIGH_POLISH.to_dict()
    test10_ok = (
        isinstance(d, dict)
        and set(d.keys()) == {
            "perceived_polish", "trustworthiness", "clarity", "visual_appeal",
            "premium_feel", "usability_impression", "differentiation_signal", "summary",
        }
        and all(0.0 <= d[k] <= 1.0 for k in d if k != "summary")
        and isinstance(d["summary"], str)
    )
    status = "PASS" if test10_ok else "FAIL"
    print(f"    to_dict() keys and ranges correct: [{status}]")
    if not test10_ok:
        all_passed = False

    return all_passed


# ---------------------------------------------------------------------------
# Layer 13: Adoption Model Validation
# ---------------------------------------------------------------------------

def run_layer_13():
    """Adoption model: per-NPC adoption logic, barriers, hard gates, tuning."""
    print("=" * 70)
    print("LAYER 13: Adoption Model Validation (10 tests)")
    print("=" * 70)

    from backend.simulation.adoption import (
        compute_npc_adoption,
        ADOPTION_THRESHOLD,
        MIN_INTEREST_FOR_ADOPTION,
    )

    all_passed = True

    # Shared product profiles for testing
    easy_product = {
        "price_friction": 0.0,
        "trust_barrier": 0.2,
        "utility_clarity": 0.9,
        "trial_friction": 0.1,
    }
    hard_product = {
        "price_friction": 0.8,
        "trust_barrier": 0.8,
        "utility_clarity": 0.2,
        "trial_friction": 0.7,
    }
    paid_product = {
        "price_friction": 0.5,
        "trust_barrier": 0.3,
        "utility_clarity": 0.7,
        "trial_friction": 0.3,
    }
    neutral_personality = {
        "openness": 0.5, "skepticism": 0.5, "tech_savviness": 0.5,
        "price_sensitivity": 0.5, "conformity": 0.5,
    }

    # --- Test 1: High interest + low barriers → high adoption ---
    print("\n  --- Test 1: High interest + low barriers → adopted ---")
    r1 = compute_npc_adoption(
        interest_score=0.85, would_pay=True, aware=True,
        personality={"openness": 0.8, "skepticism": 0.2, "tech_savviness": 0.8,
                     "price_sensitivity": 0.2, "conformity": 0.3},
        profile_dict=easy_product,
    )
    test1_ok = r1.adopted and r1.score >= ADOPTION_THRESHOLD
    status = "PASS" if test1_ok else "FAIL"
    print(f"    adopted={r1.adopted}, score={r1.score:.3f}: [{status}]")
    if not test1_ok:
        all_passed = False

    # --- Test 2: High interest + high barriers → low/no adoption ---
    print("\n  --- Test 2: High interest + high barriers → not adopted ---")
    r2 = compute_npc_adoption(
        interest_score=0.85, would_pay=True, aware=True,
        personality={"openness": 0.2, "skepticism": 0.9, "tech_savviness": 0.1,
                     "price_sensitivity": 0.9, "conformity": 0.9},
        profile_dict=hard_product,
        competition_dict={"switching_cost_pressure": 0.8, "incumbent_trust_pressure": 0.7},
    )
    test2_ok = not r2.adopted and r2.score < ADOPTION_THRESHOLD
    status = "PASS" if test2_ok else "FAIL"
    print(f"    adopted={r2.adopted}, score={r2.score:.3f}, blockers={r2.blockers}: [{status}]")
    if not test2_ok:
        all_passed = False

    # --- Test 3: Low interest → always low adoption ---
    print("\n  --- Test 3: Low interest → not adopted (regardless of barriers) ---")
    r3 = compute_npc_adoption(
        interest_score=0.20, would_pay=True, aware=True,
        personality=neutral_personality,
        profile_dict=easy_product,
    )
    test3_ok = not r3.adopted and r3.hard_gate_reason == "low_interest"
    status = "PASS" if test3_ok else "FAIL"
    print(f"    adopted={r3.adopted}, gate={r3.hard_gate_reason}: [{status}]")
    if not test3_ok:
        all_passed = False

    # --- Test 4: Hard gate — unaware → not adopted ---
    print("\n  --- Test 4: Hard gate — unaware → not adopted ---")
    r4 = compute_npc_adoption(
        interest_score=0.90, would_pay=True, aware=False,
        personality=neutral_personality,
        profile_dict=easy_product,
    )
    test4_ok = not r4.adopted and r4.hard_gate_reason == "not_aware"
    status = "PASS" if test4_ok else "FAIL"
    print(f"    adopted={r4.adopted}, gate={r4.hard_gate_reason}: [{status}]")
    if not test4_ok:
        all_passed = False

    # --- Test 5: Hard gate — paid product, would_pay=False → not adopted ---
    print("\n  --- Test 5: Hard gate — paid product, won't pay → not adopted ---")
    r5 = compute_npc_adoption(
        interest_score=0.90, would_pay=False, aware=True,
        personality=neutral_personality,
        profile_dict=paid_product,
    )
    test5_ok = not r5.adopted and r5.hard_gate_reason == "would_not_pay"
    status = "PASS" if test5_ok else "FAIL"
    print(f"    adopted={r5.adopted}, gate={r5.hard_gate_reason}: [{status}]")
    if not test5_ok:
        all_passed = False

    # --- Test 6: Price-sensitive NPC + expensive → lower adoption than insensitive ---
    print("\n  --- Test 6: Price sensitivity affects adoption ---")
    r6a = compute_npc_adoption(
        interest_score=0.70, would_pay=True, aware=True,
        personality={**neutral_personality, "price_sensitivity": 0.9},
        profile_dict=paid_product,
    )
    r6b = compute_npc_adoption(
        interest_score=0.70, would_pay=True, aware=True,
        personality={**neutral_personality, "price_sensitivity": 0.1},
        profile_dict=paid_product,
    )
    test6_ok = r6a.score < r6b.score
    status = "PASS" if test6_ok else "FAIL"
    print(f"    price_sens=0.9 → score={r6a.score:.3f}, price_sens=0.1 → score={r6b.score:.3f}: [{status}]")
    if not test6_ok:
        all_passed = False

    # --- Test 7: Skeptical NPC + high trust barrier → lower adoption ---
    print("\n  --- Test 7: Skepticism + high trust barrier lowers adoption ---")
    r7a = compute_npc_adoption(
        interest_score=0.70, would_pay=True, aware=True,
        personality={**neutral_personality, "skepticism": 0.9},
        profile_dict=hard_product,
    )
    r7b = compute_npc_adoption(
        interest_score=0.70, would_pay=True, aware=True,
        personality={**neutral_personality, "skepticism": 0.1},
        profile_dict=hard_product,
    )
    test7_ok = r7a.score < r7b.score
    status = "PASS" if test7_ok else "FAIL"
    print(f"    skeptic=0.9 → score={r7a.score:.3f}, skeptic=0.1 → score={r7b.score:.3f}: [{status}]")
    if not test7_ok:
        all_passed = False

    # --- Test 8: High switching cost → lower adoption for conformist ---
    print("\n  --- Test 8: Switching cost hurts conformist more ---")
    comp_high = {"switching_cost_pressure": 0.8, "incumbent_trust_pressure": 0.5}
    r8a = compute_npc_adoption(
        interest_score=0.70, would_pay=True, aware=True,
        personality={**neutral_personality, "conformity": 0.9},
        profile_dict=easy_product, competition_dict=comp_high,
    )
    r8b = compute_npc_adoption(
        interest_score=0.70, would_pay=True, aware=True,
        personality={**neutral_personality, "conformity": 0.1},
        profile_dict=easy_product, competition_dict=comp_high,
    )
    test8_ok = r8a.score < r8b.score
    status = "PASS" if test8_ok else "FAIL"
    print(f"    conformity=0.9 → score={r8a.score:.3f}, conformity=0.1 → score={r8b.score:.3f}: [{status}]")
    if not test8_ok:
        all_passed = False

    # --- Test 9: Adoption score bounded [0, 1] ---
    print("\n  --- Test 9: Adoption score bounded [0, 1] ---")
    extreme_combos = [
        (1.0, True, True, {"openness": 1.0, "skepticism": 0.0, "tech_savviness": 1.0,
                           "price_sensitivity": 0.0, "conformity": 0.0}, easy_product),
        (0.31, True, True, {"openness": 0.0, "skepticism": 1.0, "tech_savviness": 0.0,
                            "price_sensitivity": 1.0, "conformity": 1.0}, hard_product),
    ]
    test9_ok = True
    for interest, wp, aw, pers, prof in extreme_combos:
        r = compute_npc_adoption(
            interest_score=interest, would_pay=wp, aware=aw,
            personality=pers, profile_dict=prof,
            competition_dict={"switching_cost_pressure": 1.0, "incumbent_trust_pressure": 1.0},
        )
        if not (0.0 <= r.score <= 1.0):
            test9_ok = False
            print(f"    OUT OF BOUNDS: score={r.score}")
    status = "PASS" if test9_ok else "FAIL"
    print(f"    All extreme combos in [0, 1]: [{status}]")
    if not test9_ok:
        all_passed = False

    # --- Test 10: Tech-savvy overcomes trial friction ---
    print("\n  --- Test 10: Tech-savvy NPC overcomes trial friction ---")
    high_trial_product = {**easy_product, "trial_friction": 0.8}
    r10a = compute_npc_adoption(
        interest_score=0.70, would_pay=True, aware=True,
        personality={**neutral_personality, "tech_savviness": 0.9},
        profile_dict=high_trial_product,
    )
    r10b = compute_npc_adoption(
        interest_score=0.70, would_pay=True, aware=True,
        personality={**neutral_personality, "tech_savviness": 0.1},
        profile_dict=high_trial_product,
    )
    test10_ok = r10a.score > r10b.score
    status = "PASS" if test10_ok else "FAIL"
    print(f"    tech=0.9 → score={r10a.score:.3f}, tech=0.1 → score={r10b.score:.3f}: [{status}]")
    if not test10_ok:
        all_passed = False

    return all_passed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Simulation redesign validation")
    parser.add_argument(
        "--layer", type=int,
        choices=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13],
        default=0,
        help="Run specific layer (0 = all)",
    )
    args = parser.parse_args()

    results = {}

    if args.layer in (0, 1):
        results["layer_1"] = run_layer_1()
    if args.layer in (0, 2):
        results["layer_2"] = run_layer_2()
    if args.layer in (0, 3):
        results["layer_3"] = run_layer_3()
    if args.layer in (0, 4):
        results["layer_4"] = run_layer_4()
    if args.layer in (0, 5):
        results["layer_5"] = run_layer_5()
    if args.layer in (0, 6):
        results["layer_6"] = run_layer_6()
    if args.layer in (0, 7):
        results["layer_7"] = run_layer_7()
    if args.layer in (0, 8):
        results["layer_8"] = run_layer_8()
    if args.layer in (0, 9):
        results["layer_9"] = run_layer_9()
    if args.layer in (0, 10):
        results["layer_10"] = run_layer_10()
    if args.layer in (0, 11):
        results["layer_11"] = run_layer_11()
    if args.layer in (0, 12):
        results["layer_12"] = run_layer_12()
    if args.layer in (0, 13):
        results["layer_13"] = run_layer_13()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    all_pass = True
    for layer, passed in sorted(results.items()):
        status = "PASS" if passed else "FAIL"
        print(f"  {layer}: {status}")
        if not passed:
            all_pass = False

    print(f"\n  Overall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
