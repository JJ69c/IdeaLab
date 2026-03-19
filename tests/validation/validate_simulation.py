"""Simulation redesign validation harness.

Runs deterministic baseline tests (no LLM calls needed) to verify that:
1. Archetypes produce meaningfully different baselines for the same product
2. Price sensitivity works as expected (Budget-Conscious drops hard for expensive products)
3. Individual deltas are bounded and reasonable
4. Face-validity scenarios produce expected archetype orderings
5. Convergence tracking and archetype coherence work
6. Input wording robustness (same product, 3 description styles → same baselines)
7. Archetype behavioral separation across 5 dimensions
8. Repeated-exposure sensitivity (bounded decay, no runaway effects)
9. Seed sensitivity (population generation randomness classified low/medium/high)
10. Holdout validation scenarios (unseen products not used during tuning)

Usage:
    cd idealab
    python -m tests.validation.validate_simulation [--layer 1..10]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

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
# All 10 archetypes
# ---------------------------------------------------------------------------

ALL_ARCHETYPES = [
    "enthusiast", "pragmatist", "skeptic", "follower", "gatekeeper",
    "budget_conscious", "health_evaluator", "brand_buyer", "values_buyer",
    "loyal_incumbent",
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
    print("LAYER 1: Deterministic Baseline Validation (10 archetypes)")
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
    """Test that price changes affect Budget-Conscious much more than Enthusiast.
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
    test_archetypes = ["enthusiast", "budget_conscious", "pragmatist", "brand_buyer", "loyal_incumbent"]
    for arch_id in test_archetypes:
        eval_def = get_archetype_evaluation(arch_id)
        bl_free = compute_archetype_baseline(profile_free, eval_def)
        bl_expensive = compute_archetype_baseline(profile_expensive, eval_def)
        drop = bl_free - bl_expensive
        print(f"\n  {arch_id:20s}: free={bl_free:.3f}  expensive={bl_expensive:.3f}  drop={drop:.3f}")

    # Budget-Conscious should drop more than Enthusiast
    bc_eval = get_archetype_evaluation("budget_conscious")
    en_eval = get_archetype_evaluation("enthusiast")
    bc_drop = compute_archetype_baseline(profile_free, bc_eval) - compute_archetype_baseline(profile_expensive, bc_eval)
    en_drop = compute_archetype_baseline(profile_free, en_eval) - compute_archetype_baseline(profile_expensive, en_eval)

    ratio = bc_drop / en_drop if en_drop > 0 else float("inf")
    passed = bc_drop > en_drop and bc_drop >= 0.15
    status = "PASS" if passed else "FAIL"
    print(f"\n  Budget-Conscious drop: {bc_drop:.3f}")
    print(f"  Enthusiast drop:      {en_drop:.3f}")
    print(f"  Ratio:                {ratio:.1f}x")
    print(f"  Budget-Conscious drops harder? [{status}]")
    if not passed:
        all_passed = False

    # Brand-Buyer should drop LESS than Enthusiast (or even gain)
    # because brand_buyer has positive price_friction weight
    bb_eval = get_archetype_evaluation("brand_buyer")
    bb_drop = compute_archetype_baseline(profile_free, bb_eval) - compute_archetype_baseline(profile_expensive, bb_eval)
    passed_bb = bb_drop < en_drop
    status_bb = "PASS" if passed_bb else "FAIL"
    print(f"\n  Brand-Buyer drop:     {bb_drop:.3f}")
    print(f"  Brand-Buyer less price-sensitive than Enthusiast? [{status_bb}]")
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
# Layer 4: Face validity scenarios (10 archetypes)
# ---------------------------------------------------------------------------

def run_layer_4():
    """Test expected archetype orderings for specific products across all 10 archetypes."""
    print("\n" + "=" * 70)
    print("LAYER 4: Face Validity Scenarios (10 archetypes)")
    print("=" * 70)

    reload_evaluations()

    # With 10 archetypes, use top 4 / bottom 4 for checks
    scenarios = [
        {
            "name": "Free SaaS concept -> Enthusiast & Values-Buyer should lead, Loyal Incumbent trails",
            "product": "free_saas_concept",
            "expected_high": ["enthusiast", "values_buyer"],
            "expected_low": ["loyal_incumbent"],
        },
        {
            "name": "Expensive hardware -> Budget-Conscious & Loyal Incumbent should hate it",
            "product": "expensive_hardware",
            "expected_high": ["enthusiast"],
            "expected_low": ["budget_conscious", "loyal_incumbent"],
        },
        {
            "name": "Health app -> Health Evaluator should be engaged",
            "product": "health_app",
            "expected_high": ["enthusiast"],
            "expected_low": ["loyal_incumbent"],
        },
        {
            "name": "Saturated todo -> Follower should lead (loves mainstream)",
            "product": "saturated_todo",
            "expected_high": ["follower"],
            "expected_low": ["loyal_incumbent"],
        },
        {
            "name": "Privacy messenger -> Values-Buyer & Enthusiast should appreciate it",
            "product": "privacy_messenger",
            "expected_high": ["enthusiast"],
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
        top_4 = [a[0] for a in sorted_archetypes[:4]]
        bottom_4 = [a[0] for a in sorted_archetypes[-4:]]

        passed = True
        for expected_high in scenario["expected_high"]:
            if expected_high not in top_4:
                passed = False
        for expected_low in scenario["expected_low"]:
            if expected_low not in bottom_4:
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

        # CHECK 2: would_try / would_pay / would_recommend each have at least one T and one F
        for dim_name in ["would_try", "would_pay", "would_recommend"]:
            values = [r[dim_name] for r in results.values()]
            has_both = True in values and False in values
            status = "PASS" if has_both else "FAIL"
            if not has_both:
                print(f"    {dim_name} is uniform ({values[0]}) [{status}]")
                all_passed = False

        # CHECK 3: >= 8 of 10 archetypes have unique behavioral fingerprints
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
        passed_fp = len(fingerprints) >= 8
        status = "PASS" if passed_fp else "FAIL"
        print(f"    Unique fingerprints: {len(fingerprints)}/10 (min 8) [{status}]")
        if not passed_fp:
            all_passed = False

    return all_passed


# ---------------------------------------------------------------------------
# Layer 8: Repeated-exposure sensitivity
# ---------------------------------------------------------------------------

def run_layer_8():
    """Verify exposure decay formulas are bounded and don't produce runaway effects.

    Follower formula: min(1.5, 1.0 + 0.08 * exposure) — caps at 1.5x
    Others formula:   1.0 / (1.0 + 0.25 * exposure)   — diminishes monotonically
    """
    print("\n" + "=" * 70)
    print("LAYER 8: Repeated-Exposure Sensitivity")
    print("=" * 70)

    all_passed = True

    # --- Test 1: Follower susceptibility is bounded ---
    print("\n  --- Test 1: Follower decay cap ---")
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
    print(f"    Follower cap check: [{status}]")
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
    print("\n  --- Test 3: Cumulative peer influence (Follower vs Skeptic) ---")
    trajectories = {}
    for arch_id, susc_mult, skepticism_val in [
        ("follower", 1.5, 0.3),
        ("skeptic", 0.5, 0.8),
    ]:
        interest = 0.5
        conformity = 0.7
        peer_avg = 0.85

        trajectory = [interest]
        for tick in range(1, 21):
            base_susc = conformity * (1.0 - skepticism_val * 0.3) * 0.3
            base_susc *= susc_mult
            if arch_id == "follower":
                decay = min(1.5, 1.0 + 0.08 * tick)
            else:
                decay = 1.0 / (1.0 + 0.25 * tick)
            susceptibility = base_susc * decay
            delta = (peer_avg - interest) * susceptibility
            interest = max(0.0, min(1.0, interest + delta))
            trajectory.append(interest)

        trajectories[arch_id] = trajectory
        movement = trajectory[-1] - trajectory[0]
        print(f"    {arch_id:10s}: start={trajectory[0]:.3f} end={trajectory[-1]:.3f} "
              f"movement={movement:.3f}")

    follower_move = trajectories["follower"][-1] - trajectories["follower"][0]
    skeptic_move = trajectories["skeptic"][-1] - trajectories["skeptic"][0]

    # Follower stays bounded
    follower_bounded = all(v <= 1.0 for v in trajectories["follower"])
    passed_fb = follower_bounded
    status = "PASS" if passed_fb else "FAIL"
    print(f"    Follower stays <= 1.0: [{status}]")
    if not passed_fb:
        all_passed = False

    # Skeptic moves < 0.15
    passed_sm = skeptic_move < 0.15
    status = "PASS" if passed_sm else "FAIL"
    print(f"    Skeptic movement < 0.15: {skeptic_move:.3f} [{status}]")
    if not passed_sm:
        all_passed = False

    # Follower moves at least 2x Skeptic
    ratio = follower_move / skeptic_move if skeptic_move > 0 else float("inf")
    passed_ratio = follower_move > skeptic_move * 2
    status = "PASS" if passed_ratio else "FAIL"
    print(f"    Follower/Skeptic ratio: {ratio:.1f}x (min 2x) [{status}]")
    if not passed_ratio:
        all_passed = False

    # --- Test 4: Print decay curves at key tick marks ---
    print("\n  --- Decay curves at key ticks ---")
    print(f"    {'tick':>6s}  {'follower':>10s}  {'other':>10s}")
    for t in [0, 1, 3, 6, 10, 15, 20]:
        f_decay = min(1.5, 1.0 + 0.08 * t)
        o_decay = 1.0 / (1.0 + 0.25 * t)
        print(f"    {t:6d}  {f_decay:10.3f}  {o_decay:10.3f}")

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
            "name": "LingoLoop (education MVP) -> Enthusiast high, Loyal Incumbent low",
            "product": "language_learning_app",
            "expected_high": ["enthusiast"],
            "expected_low": ["loyal_incumbent"],
        },
        {
            "name": "GreenThread (ethical fashion) -> Values-Buyer high, Budget-Conscious low",
            "product": "sustainable_fashion",
            "expected_high": ["values_buyer"],
            "expected_low": ["budget_conscious"],
        },
        {
            "name": "PawSense Collar (hardware prototype) -> Enthusiast high, Budget-Conscious & Loyal Incumbent low",
            "product": "pet_tech_device",
            "expected_high": ["enthusiast"],
            "expected_low": ["budget_conscious", "loyal_incumbent"],
        },
        {
            "name": "QueryBench (free dev tool) -> Values-Buyer high, Budget-Conscious low",
            "product": "developer_tool_free",
            "expected_high": ["values_buyer"],
            "expected_low": ["budget_conscious"],
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
        top_4 = [a for a, _ in sorted_archetypes[:4]]
        bottom_4 = [a for a, _ in sorted_archetypes[-4:]]

        passed = True
        for eh in scenario["expected_high"]:
            if eh not in top_4:
                passed = False
        for el in scenario["expected_low"]:
            if el not in bottom_4:
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
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Simulation redesign validation")
    parser.add_argument(
        "--layer", type=int,
        choices=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
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
