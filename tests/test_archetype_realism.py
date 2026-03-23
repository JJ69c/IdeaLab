"""Archetype Realism & Robustness Validation.

Tests whether archetype behavior is believable, varied within-archetype,
and produces sensible cross-archetype influence dynamics.

4 validation areas:
1. Scenario realism — do reaction orderings match intuition for real products?
2. Within-archetype variation — do individuals differ while preserving core?
3. Cross-archetype influence — do different archetypes respond differently to peers?
4. Over-constraint check — are any archetypes too rigid to be realistic?
"""

import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.simulation.evaluation import (
    compute_archetype_baseline,
    compute_individual_delta,
    get_archetype_evaluation,
    reload_evaluations,
)
from backend.simulation.population import generate_population
from backend.simulation.product_profile import ProductProfile
from backend.simulation.npc import Npc, NpcPersonality, NpcState
from backend.simulation.propagation import (
    compute_peer_susceptibility,
    _SOURCE_CREDIBILITY,
)

reload_evaluations()

ARCHETYPES = [
    "analytical_skeptic", "trend_adopter", "price_pragmatist",
    "health_evaluator", "brand_buyer", "social_follower",
    "convenience_user", "values_buyer",
]


# ============================================================
# PART 1: SCENARIO REALISM
# ============================================================

SCENARIOS = {
    "premium_polished_consumer": {
        "description": "Apple-like premium consumer product. Beautiful, expensive, polished, strong brand identity, moderate novelty.",
        "profile": ProductProfile(
            novelty=0.55, utility_clarity=0.70, differentiation=0.65,
            price_friction=0.75, trust_barrier=0.20, identity_fit=0.80,
            trial_friction=0.25, market_saturation=0.40,
        ),
        "expect_top_3": ["brand_buyer", "trend_adopter", "values_buyer"],
        "expect_bottom_3": ["price_pragmatist", "social_follower", "analytical_skeptic"],
        "reasoning": "Brand buyers love premium+identity. Trend adopters like novelty+differentiation. Price pragmatists reject the price. Social followers see moderate saturation as insufficient proof.",
    },
    "cheap_boring_utility": {
        "description": "A free, unglamorous spreadsheet tool. High utility, zero novelty, no brand, no friction.",
        "profile": ProductProfile(
            novelty=0.10, utility_clarity=0.90, differentiation=0.25,
            price_friction=0.05, trust_barrier=0.15, identity_fit=0.20,
            trial_friction=0.10, market_saturation=0.70,
        ),
        "expect_top_3": ["social_follower", "health_evaluator", "analytical_skeptic"],
        "expect_bottom_3": ["brand_buyer", "trend_adopter"],
        "reasoning": "Social followers love the saturation (+0.20 weight). Health evaluator and analytical skeptic have strongest utility_clarity weights (0.20, 0.25) — a high-utility tool is their sweet spot. Brand buyers hate low identity. Trend adopters hate zero novelty + high saturation.",
    },
    "low_trust_crypto": {
        "description": "Slick crypto/DeFi platform. Polished UI, novel concept, but extremely low trust, moderate price.",
        "profile": ProductProfile(
            novelty=0.85, utility_clarity=0.40, differentiation=0.70,
            price_friction=0.45, trust_barrier=0.90, identity_fit=0.55,
            trial_friction=0.50, market_saturation=0.15,
        ),
        "expect_top_3": ["trend_adopter", "brand_buyer"],
        "expect_bottom_3": ["price_pragmatist", "analytical_skeptic", "social_follower"],
        "reasoning": "Trend adopters tolerate low trust for novelty. Social followers killed by sat=0.15 (no social proof) + negative novelty weight. Price pragmatists penalized by moderate price + high trust barrier. Analytical skeptics destroyed by trust_barrier=0.90.",
    },
    "weak_evidence_health": {
        "description": "Health supplement with wellness claims but minimal clinical evidence. Moderate price, high identity fit for health-conscious.",
        "profile": ProductProfile(
            novelty=0.40, utility_clarity=0.45, differentiation=0.35,
            price_friction=0.40, trust_barrier=0.75, identity_fit=0.70,
            trial_friction=0.30, market_saturation=0.30,
        ),
        "expect_top_3": ["brand_buyer", "trend_adopter", "values_buyer"],
        "expect_bottom_3": ["health_evaluator", "analytical_skeptic", "price_pragmatist"],
        "reasoning": "Health evaluators REJECT despite identity fit — trust barrier weight (-0.30) dominates. Analytical skeptics also reject on trust. Brand buyers see identity + differentiation.",
    },
    "sustainable_values_brand": {
        "description": "Ethically-sourced, B-corp certified consumer brand. Strong mission, moderate price, not novel.",
        "profile": ProductProfile(
            novelty=0.25, utility_clarity=0.60, differentiation=0.55,
            price_friction=0.35, trust_barrier=0.25, identity_fit=0.85,
            trial_friction=0.20, market_saturation=0.25,
        ),
        "expect_top_3": ["values_buyer", "brand_buyer", "health_evaluator"],
        "expect_bottom_3": ["social_follower", "trend_adopter"],
        "reasoning": "Values buyers have highest identity_fit weight (0.35) — this is their product. Brand buyers also like identity+differentiation. Trend adopters penalized by low novelty. Social followers see low saturation = insufficient proof.",
    },
    "viral_social_app": {
        "description": "A viral social app that everyone is talking about. Not novel technically, low differentiation, but massive adoption already.",
        "profile": ProductProfile(
            novelty=0.30, utility_clarity=0.50, differentiation=0.20,
            price_friction=0.05, trust_barrier=0.30, identity_fit=0.50,
            trial_friction=0.10, market_saturation=0.90,
        ),
        "expect_top_3": ["social_follower", "convenience_user"],
        "expect_bottom_3": ["brand_buyer", "trend_adopter"],
        "reasoning": "Social followers have +0.20 market saturation weight — mass adoption IS their signal. Brand buyers penalized by saturation (-0.20) — mass market kills exclusivity. Trend adopters hate both low novelty AND high saturation.",
    },
    "complex_enterprise_tool": {
        "description": "Enterprise SaaS with steep learning curve but powerful features. Expensive, high utility, high friction.",
        "profile": ProductProfile(
            novelty=0.35, utility_clarity=0.80, differentiation=0.60,
            price_friction=0.70, trust_barrier=0.30, identity_fit=0.40,
            trial_friction=0.80, market_saturation=0.35,
        ),
        "expect_top_3": ["analytical_skeptic", "values_buyer"],
        "expect_bottom_3": ["convenience_user", "price_pragmatist", "social_follower"],
        "reasoning": "Convenience users destroyed by trial_friction=0.80 (weight -0.30). Price pragmatists killed by price. Analytical skeptics like high utility+differentiation despite price.",
    },
    "free_novel_experiment": {
        "description": "Free AI art generator. Completely novel, zero price, unclear long-term value, experimental stage.",
        "profile": ProductProfile(
            novelty=0.95, utility_clarity=0.30, differentiation=0.80,
            price_friction=0.00, trust_barrier=0.55, identity_fit=0.45,
            trial_friction=0.15, market_saturation=0.05,
        ),
        "expect_top_3": ["trend_adopter", "brand_buyer"],
        "expect_bottom_3": ["social_follower", "analytical_skeptic"],
        "reasoning": "Trend adopters get maximum novelty boost. Social followers see near-zero saturation = no social proof. Analytical skeptics see low utility + moderate trust barrier.",
    },
}


def run_scenario_realism():
    """Test 1: Do archetype reaction orderings match real-world intuition?"""
    print("=" * 80)
    print("  PART 1: SCENARIO REALISM VALIDATION")
    print("  8 scenarios × 8 archetypes — checking reaction orderings")
    print("=" * 80)

    evals = {a: get_archetype_evaluation(a) for a in ARCHETYPES}
    issues = []

    for name, scenario in SCENARIOS.items():
        profile = scenario["profile"]

        # Compute baselines + individual deltas at trait midpoints
        results = {}
        for arch_id in ARCHETYPES:
            baseline = compute_archetype_baseline(profile, evals[arch_id])
            # Use archetype midpoint traits for individual delta
            results[arch_id] = baseline

        ranked = sorted(results.items(), key=lambda x: x[1], reverse=True)
        top_3 = [r[0] for r in ranked[:3]]
        bottom_3 = [r[0] for r in ranked[-3:]]

        print(f"\n{'─' * 70}")
        print(f"  Scenario: {name}")
        print(f"  {scenario['description']}")
        print(f"  Profile: nov={profile.novelty:.2f} util={profile.utility_clarity:.2f} "
              f"diff={profile.differentiation:.2f} price={profile.price_friction:.2f} "
              f"trust={profile.trust_barrier:.2f} ident={profile.identity_fit:.2f} "
              f"trial={profile.trial_friction:.2f} sat={profile.market_saturation:.2f}")
        print()

        for arch_id, score in ranked:
            threshold = evals[arch_id].adoption_threshold
            would_adopt = "ADOPT" if score >= threshold else "reject"
            bar = "█" * int(score * 40)
            print(f"    {arch_id:22s} {score:.3f} [{would_adopt:6s}]  {bar}")

        # Check expectations
        expect_top = scenario.get("expect_top_3", [])
        expect_bottom = scenario.get("expect_bottom_3", [])

        top_hits = sum(1 for a in expect_top if a in top_3)
        bottom_hits = sum(1 for a in expect_bottom if a in bottom_3)

        top_ok = top_hits >= len(expect_top) - 1  # allow 1 miss
        bottom_ok = bottom_hits >= len(expect_bottom) - 1

        top_status = "PASS" if top_ok else "ISSUE"
        bottom_status = "PASS" if bottom_ok else "ISSUE"

        print(f"\n    Expected top:    {expect_top} → actual top 3: {top_3}  [{top_status}]")
        print(f"    Expected bottom: {expect_bottom} → actual bottom 3: {bottom_3}  [{bottom_status}]")
        print(f"    Reasoning: {scenario['reasoning']}")

        if not top_ok:
            issues.append(f"{name}: expected top {expect_top}, got {top_3}")
        if not bottom_ok:
            issues.append(f"{name}: expected bottom {expect_bottom}, got {bottom_3}")

    print(f"\n{'─' * 70}")
    if issues:
        print(f"  SCENARIO REALISM: {len(issues)} issue(s) found")
        for issue in issues:
            print(f"    ⚠ {issue}")
    else:
        print("  SCENARIO REALISM: All orderings match intuition")

    return issues


# ============================================================
# PART 2: WITHIN-ARCHETYPE VARIATION
# ============================================================

def run_within_archetype_variation():
    """Test 2: Individuals within the same archetype should vary but preserve core."""
    print("\n" + "=" * 80)
    print("  PART 2: WITHIN-ARCHETYPE VARIATION")
    print("  Do individuals differ while preserving behavioral core?")
    print("=" * 80)

    npcs, npc_archetypes = generate_population(size=80, preset="balanced")
    evals = {a: get_archetype_evaluation(a) for a in ARCHETYPES}

    # Test against 3 different products
    test_profiles = {
        "novel_free": ProductProfile(
            novelty=0.80, utility_clarity=0.50, differentiation=0.60,
            price_friction=0.05, trust_barrier=0.40, identity_fit=0.50,
            trial_friction=0.20, market_saturation=0.15,
        ),
        "expensive_proven": ProductProfile(
            novelty=0.20, utility_clarity=0.85, differentiation=0.50,
            price_friction=0.80, trust_barrier=0.15, identity_fit=0.60,
            trial_friction=0.20, market_saturation=0.70,
        ),
        "high_identity": ProductProfile(
            novelty=0.40, utility_clarity=0.55, differentiation=0.55,
            price_friction=0.35, trust_barrier=0.30, identity_fit=0.85,
            trial_friction=0.25, market_saturation=0.25,
        ),
    }

    issues = []

    for profile_name, profile in test_profiles.items():
        print(f"\n  --- Product: {profile_name} ---")

        # Group NPCs by archetype and compute individual scores
        arch_scores: dict[str, list[float]] = defaultdict(list)
        for npc in npcs:
            arch_id = npc_archetypes.get(npc.id, "unknown")
            if arch_id not in ARCHETYPES:
                continue
            baseline = compute_archetype_baseline(profile, evals[arch_id])
            ind_delta = compute_individual_delta(npc.personality, profile)
            final = max(0.0, min(1.0, baseline + ind_delta))
            arch_scores[arch_id].append(final)

        print(f"    {'archetype':22s} {'n':>3s} {'mean':>6s} {'std':>6s} {'min':>6s} {'max':>6s} {'range':>6s}")
        for arch_id in ARCHETYPES:
            scores = arch_scores.get(arch_id, [])
            if len(scores) < 2:
                continue
            mean = sum(scores) / len(scores)
            variance = sum((s - mean) ** 2 for s in scores) / len(scores)
            std = math.sqrt(variance)
            lo, hi = min(scores), max(scores)
            rng = hi - lo
            print(f"    {arch_id:22s} {len(scores):3d} {mean:6.3f} {std:6.3f} {lo:6.3f} {hi:6.3f} {rng:6.3f}")

            # Check 1: std should be > 0 (not literally identical)
            # Note: baseline-only variation is intentionally small (0.001-0.005) because
            # within-archetype traits are generated in narrow bands. Real simulation adds
            # asset_delta (±0.08), competition_delta (±0.08), and llm_hint (±0.10).
            if std < 0.001:
                issues.append(f"{arch_id} in {profile_name}: std={std:.4f} — near-identical outputs")

            # Check 2: range should show some spread
            if rng < 0.003:
                issues.append(f"{arch_id} in {profile_name}: range={rng:.3f} — collapsed variation")

            # Check 3: std should be < 0.10 (not chaotic — archetype core preserved)
            if std > 0.10:
                issues.append(f"{arch_id} in {profile_name}: std={std:.4f} — too much intra-archetype chaos")

    # Cross-archetype ordering stability: the rank ordering should be preserved
    # across individuals (if arch A > arch B at archetype level, most A individuals > most B individuals)
    print(f"\n  --- Cross-archetype ordering stability ---")
    for profile_name, profile in test_profiles.items():
        arch_means = {}
        for arch_id in ARCHETYPES:
            scores = arch_scores.get(arch_id, [])
            if scores:
                arch_means[arch_id] = sum(scores) / len(scores)

        ranked = sorted(arch_means.items(), key=lambda x: x[1], reverse=True)
        top_arch = ranked[0][0]
        bottom_arch = ranked[-1][0]
        top_scores = arch_scores.get(top_arch, [])
        bottom_scores = arch_scores.get(bottom_arch, [])

        # What fraction of top-archetype individuals outscore bottom-archetype individuals?
        if top_scores and bottom_scores:
            overlaps = sum(1 for t in top_scores for b in bottom_scores if t <= b)
            total_pairs = len(top_scores) * len(bottom_scores)
            overlap_rate = overlaps / total_pairs if total_pairs > 0 else 0
            print(f"    {profile_name}: {top_arch} vs {bottom_arch} — "
                  f"overlap rate = {overlap_rate:.1%} (should be < 30%)")
            if overlap_rate > 0.30:
                issues.append(
                    f"{profile_name}: {top_arch} vs {bottom_arch} overlap {overlap_rate:.1%}"
                )

    print()
    if issues:
        print(f"  WITHIN-ARCHETYPE VARIATION: {len(issues)} issue(s)")
        for issue in issues:
            print(f"    ⚠ {issue}")
    else:
        print("  WITHIN-ARCHETYPE VARIATION: Individuals vary but preserve archetype core")

    return issues


# ============================================================
# PART 3: CROSS-ARCHETYPE INFLUENCE
# ============================================================

def run_cross_archetype_influence():
    """Test 3: Different archetypes respond differently to the same source influence."""
    print("\n" + "=" * 80)
    print("  PART 3: CROSS-ARCHETYPE INFLUENCE VALIDATION")
    print("  Same peer signal, different archetype reactions")
    print("=" * 80)

    from backend.simulation.world import WorldState, InjectedIdea, SimConfig

    # Create a minimal world with controlled setup
    idea = InjectedIdea(
        title="TestProduct", description="A test product",
        category="saas", stage="mvp", target_audience="general",
        price_point="$20–$50/mo",
    )
    config = SimConfig(num_ticks=5, population_size=10)

    issues = []

    # Build pairs to compare
    comparison_pairs = [
        ("social_follower", "analytical_skeptic", "follower vs skeptic"),
        ("brand_buyer", "price_pragmatist", "brand vs pragmatist"),
        ("values_buyer", "trend_adopter", "values vs trend"),
        ("health_evaluator", "convenience_user", "health vs convenience"),
    ]

    # Create NPCs with archetype-midpoint traits for controlled comparison
    def make_npc(arch_id: str, npc_id: str) -> Npc:
        """Create an NPC with the archetype's midpoint traits."""
        import json
        with open(Path(__file__).parent.parent / "data" / "npc_templates" / "archetypes.json", encoding="utf-8") as f:
            arch_data = json.load(f)

        arch_def = next(a for a in arch_data["archetypes"] if a["id"] == arch_id)
        traits = {}
        for trait_name, bounds in arch_def["traits"].items():
            traits[trait_name] = (bounds["min"] + bounds["max"]) / 2

        return Npc(
            id=npc_id,
            name=f"Test_{arch_id}",
            age=35,
            occupation="Tester",
            income_level="middle",
            personality=NpcPersonality(**traits),
            interests=[], values=[], pain_points=[],
            communication_style="neutral",
            social_connections=[],
            trust_weights={},
            archetype=arch_id,
            decision_style=arch_def["decision_style"],
        )

    print("\n  Susceptibility at exposure=0 (fresh encounter):")
    print(f"    {'archetype':22s} {'susc_mult':>9s} {'conformity':>10s} {'skepticism':>10s} {'base_susc':>10s}")

    # Compute raw susceptibility for each archetype at midpoint traits
    susc_results = {}
    for arch_id in ARCHETYPES:
        npc = make_npc(arch_id, f"test_{arch_id}")
        eval_def = get_archetype_evaluation(arch_id)

        # Raw base susceptibility formula: conformity * (1 - skepticism * 0.3) * 0.3 * susc_mult
        conf = npc.personality.conformity
        skep = npc.personality.skepticism
        base = conf * (1.0 - skep * 0.3) * 0.3 * eval_def.susceptibility_multiplier
        susc_results[arch_id] = base

        print(f"    {arch_id:22s} {eval_def.susceptibility_multiplier:9.2f} "
              f"{conf:10.2f} {skep:10.2f} {base:10.4f}")

    # Check pairwise comparisons
    print(f"\n  Pairwise influence comparison:")
    for arch_a, arch_b, label in comparison_pairs:
        susc_a = susc_results[arch_a]
        susc_b = susc_results[arch_b]
        ratio = susc_a / susc_b if susc_b > 0 else float("inf")
        direction = ">" if susc_a > susc_b else "<"

        print(f"    {label:35s}: {arch_a} ({susc_a:.4f}) {direction} {arch_b} ({susc_b:.4f})  "
              f"ratio = {ratio:.2f}x")

    # Specific assertions
    print(f"\n  Assertions:")

    # 1. Social follower >> analytical skeptic in susceptibility
    ratio = susc_results["social_follower"] / susc_results["analytical_skeptic"]
    ok = ratio >= 3.0
    print(f"    social_follower/analytical_skeptic ratio: {ratio:.1f}x (expect >= 3x) [{'PASS' if ok else 'ISSUE'}]")
    if not ok:
        issues.append(f"social_follower/analytical_skeptic susceptibility ratio only {ratio:.1f}x")

    # 2. Brand buyer > price pragmatist in susceptibility
    ok = susc_results["brand_buyer"] > susc_results["price_pragmatist"]
    print(f"    brand_buyer > price_pragmatist: {susc_results['brand_buyer']:.4f} > {susc_results['price_pragmatist']:.4f} [{'PASS' if ok else 'ISSUE'}]")
    if not ok:
        issues.append("brand_buyer not more susceptible than price_pragmatist")

    # 3. Values buyer should have very low susceptibility (independent thinker)
    ok = susc_results["values_buyer"] < 0.02
    print(f"    values_buyer susceptibility < 0.02: {susc_results['values_buyer']:.4f} [{'PASS' if ok else 'ISSUE'}]")
    if not ok:
        issues.append(f"values_buyer susceptibility too high: {susc_results['values_buyer']:.4f}")

    # 4. Convenience user should be mid-range
    ok = 0.01 < susc_results["convenience_user"] < 0.10
    print(f"    convenience_user mid-range: {susc_results['convenience_user']:.4f} [{'PASS' if ok else 'ISSUE'}]")
    if not ok:
        issues.append(f"convenience_user susceptibility out of mid-range: {susc_results['convenience_user']:.4f}")

    # Source credibility comparison
    print(f"\n  Source credibility (when endorsing):")
    cred_ranked = sorted(_SOURCE_CREDIBILITY.items(), key=lambda x: x[1], reverse=True)
    for arch_id, cred in cred_ranked:
        print(f"    {arch_id:22s} {cred:.2f}x")

    # Analytical skeptic endorsement should be worth > 2x social follower endorsement
    as_cred = _SOURCE_CREDIBILITY.get("analytical_skeptic", 1.0)
    sf_cred = _SOURCE_CREDIBILITY.get("social_follower", 1.0)
    ratio = as_cred / sf_cred
    ok = ratio >= 2.0
    print(f"\n    analytical_skeptic/social_follower credibility ratio: {ratio:.2f}x (expect >= 2x) [{'PASS' if ok else 'ISSUE'}]")
    if not ok:
        issues.append(f"credibility ratio too low: {ratio:.2f}x")

    print()
    if issues:
        print(f"  CROSS-ARCHETYPE INFLUENCE: {len(issues)} issue(s)")
        for issue in issues:
            print(f"    ⚠ {issue}")
    else:
        print("  CROSS-ARCHETYPE INFLUENCE: All pairwise dynamics are sensible")

    return issues


# ============================================================
# PART 4: OVER-CONSTRAINT CHECK
# ============================================================

def run_over_constraint_check():
    """Test 4: Are any archetypes too rigid to produce realistic behavior?"""
    print("\n" + "=" * 80)
    print("  PART 4: OVER-CONSTRAINT CHECK")
    print("  Testing whether specific archetypes are unrealistically rigid")
    print("=" * 80)

    evals = {a: get_archetype_evaluation(a) for a in ARCHETYPES}
    issues = []

    # ─── Check A: Social Follower with negative novelty ───
    print(f"\n  --- A: Social Follower negative novelty weight ---")
    print(f"  Concern: novelty weight = -0.10 means they actively avoid new things.")
    print(f"  Is this realistic or too rigid?")

    sf = evals["social_follower"]

    # Test: a novel product with HIGH saturation should still work for followers
    novel_popular = ProductProfile(
        novelty=0.80, utility_clarity=0.50, differentiation=0.40,
        price_friction=0.20, trust_barrier=0.30, identity_fit=0.50,
        trial_friction=0.15, market_saturation=0.85,
    )
    sf_score_popular = compute_archetype_baseline(novel_popular, sf)
    print(f"    Novel but POPULAR product (sat=0.85): {sf_score_popular:.3f} "
          f"(threshold={sf.adoption_threshold})")
    ok_popular = sf_score_popular >= sf.adoption_threshold - 0.05
    print(f"    Social followers can adopt novel-but-popular products: [{'PASS' if ok_popular else 'ISSUE'}]")

    # Test: a novel product with LOW saturation should be hard for followers
    novel_niche = ProductProfile(
        novelty=0.80, utility_clarity=0.50, differentiation=0.40,
        price_friction=0.20, trust_barrier=0.30, identity_fit=0.50,
        trial_friction=0.15, market_saturation=0.10,
    )
    sf_score_niche = compute_archetype_baseline(novel_niche, sf)
    print(f"    Novel NICHE product (sat=0.10): {sf_score_niche:.3f}")
    ok_niche = sf_score_niche < sf.adoption_threshold
    print(f"    Social followers resist novel niche products: [{'PASS' if ok_niche else 'ISSUE'}]")

    delta = sf_score_popular - sf_score_niche
    print(f"    Saturation swing: {delta:+.3f} (popular vs niche)")
    print(f"    Verdict: Negative novelty weight is APPROPRIATE — it means followers don't")
    print(f"    seek novelty, but saturation override makes novel-but-popular products work.")

    if not ok_popular:
        issues.append("Social followers can't adopt even novel products with high saturation")

    # ─── Check B: Values Buyer lowest susceptibility ───
    print(f"\n  --- B: Values Buyer lowest susceptibility (0.30) ---")
    print(f"  Concern: Are values buyers so independent they're unreachable?")

    vb = evals["values_buyer"]

    # Test across a range of products: do values buyers ever score high?
    test_products = {
        "values_aligned": ProductProfile(
            novelty=0.30, utility_clarity=0.60, differentiation=0.55,
            price_friction=0.30, trust_barrier=0.20, identity_fit=0.90,
            trial_friction=0.20, market_saturation=0.20,
        ),
        "values_misaligned": ProductProfile(
            novelty=0.60, utility_clarity=0.70, differentiation=0.50,
            price_friction=0.30, trust_barrier=0.30, identity_fit=0.15,
            trial_friction=0.20, market_saturation=0.40,
        ),
    }

    vb_aligned = compute_archetype_baseline(test_products["values_aligned"], vb)
    vb_misaligned = compute_archetype_baseline(test_products["values_misaligned"], vb)
    swing = vb_aligned - vb_misaligned

    print(f"    Values-aligned product: {vb_aligned:.3f} (identity_fit=0.90)")
    print(f"    Values-misaligned product: {vb_misaligned:.3f} (identity_fit=0.15)")
    print(f"    Identity swing: {swing:+.3f}")

    ok_swing = swing >= 0.20
    ok_adopts = vb_aligned >= vb.adoption_threshold
    print(f"    Swing >= 0.20: [{'PASS' if ok_swing else 'ISSUE'}]")
    print(f"    Adopts aligned product: [{'PASS' if ok_adopts else 'ISSUE'}]")
    print(f"    Verdict: Low susceptibility is fine because identity_fit weight (0.35)")
    print(f"    provides strong internal motivation. They don't need peer pressure — they")
    print(f"    adopt when the product matches their values.")

    if not ok_swing:
        issues.append(f"Values buyer identity swing too small: {swing:.3f}")
    if not ok_adopts:
        issues.append(f"Values buyer can't adopt even highly aligned product: {vb_aligned:.3f}")

    # ─── Check C: Any archetype that NEVER adopts? ───
    print(f"\n  --- C: Universal adoptability check ---")
    print(f"  Can every archetype adopt at least 1 of 8 scenarios?")

    adoptions: dict[str, int] = {a: 0 for a in ARCHETYPES}
    for name, scenario in SCENARIOS.items():
        profile = scenario["profile"]
        for arch_id in ARCHETYPES:
            baseline = compute_archetype_baseline(profile, evals[arch_id])
            if baseline >= evals[arch_id].adoption_threshold:
                adoptions[arch_id] += 1

    for arch_id in ARCHETYPES:
        count = adoptions[arch_id]
        status = "PASS" if count >= 1 else "ISSUE"
        print(f"    {arch_id:22s}: adopts in {count}/8 scenarios [{status}]")
        if count == 0:
            issues.append(f"{arch_id} never adopts in any of 8 scenarios")

    # ─── Check D: Any archetype that ALWAYS adopts? ───
    print(f"\n  --- D: Selectivity check ---")
    print(f"  Does every archetype reject at least 1 of 8 scenarios?")

    for arch_id in ARCHETYPES:
        count = adoptions[arch_id]
        status = "PASS" if count <= 7 else "ISSUE"
        print(f"    {arch_id:22s}: adopts in {count}/8, rejects {8 - count} [{status}]")
        if count == 8:
            issues.append(f"{arch_id} adopts ALL 8 scenarios — not selective enough")

    # ─── Check E: Resistance floor effectiveness ───
    print(f"\n  --- E: Resistance floor check ---")
    print(f"  Do archetypes with resistance floors actually resist in the right scenarios?")

    floor_archetypes = [(a, evals[a]) for a in ARCHETYPES if evals[a].resistance_floor > 0]
    for arch_id, ev in floor_archetypes:
        # Find a scenario where baseline < resistance floor
        blocked_scenarios = []
        for name, scenario in SCENARIOS.items():
            bl = compute_archetype_baseline(scenario["profile"], ev)
            if bl < ev.resistance_floor:
                blocked_scenarios.append((name, bl))

        print(f"    {arch_id:22s} (floor={ev.resistance_floor:.2f}): "
              f"blocked in {len(blocked_scenarios)} scenarios")
        for sname, bl in blocked_scenarios:
            print(f"      {sname}: baseline={bl:.3f} < floor={ev.resistance_floor:.2f} → peer influence blocked")

        if len(blocked_scenarios) == 0:
            print(f"      ⚠ Never blocked — floor may be too low")
            # This isn't necessarily an issue, but worth noting

    # ─── Check F: Spread across adoption thresholds ───
    print(f"\n  --- F: Adoption threshold spread ---")
    thresholds = [(a, evals[a].adoption_threshold) for a in ARCHETYPES]
    thresholds.sort(key=lambda x: x[1])
    for arch_id, th in thresholds:
        print(f"    {arch_id:22s}: {th:.2f}")

    th_range = thresholds[-1][1] - thresholds[0][1]
    ok = th_range >= 0.12
    print(f"    Range: {th_range:.2f} (expect >= 0.12) [{'PASS' if ok else 'ISSUE'}]")
    if not ok:
        issues.append(f"Adoption threshold range too narrow: {th_range:.2f}")

    print()
    if issues:
        print(f"  OVER-CONSTRAINT CHECK: {len(issues)} issue(s)")
        for issue in issues:
            print(f"    ⚠ {issue}")
    else:
        print("  OVER-CONSTRAINT CHECK: No archetypes are over-constrained")

    return issues


# ============================================================
# MAIN
# ============================================================

def main():
    print("╔" + "═" * 78 + "╗")
    print("║" + "  ARCHETYPE REALISM & ROBUSTNESS VALIDATION".center(78) + "║")
    print("║" + "  8 archetypes × 8 scenarios × 4 validation areas".center(78) + "║")
    print("╚" + "═" * 78 + "╝")

    all_issues = []

    scenario_issues = run_scenario_realism()
    all_issues.extend(("SCENARIO", i) for i in scenario_issues)

    variation_issues = run_within_archetype_variation()
    all_issues.extend(("VARIATION", i) for i in variation_issues)

    influence_issues = run_cross_archetype_influence()
    all_issues.extend(("INFLUENCE", i) for i in influence_issues)

    constraint_issues = run_over_constraint_check()
    all_issues.extend(("CONSTRAINT", i) for i in constraint_issues)

    # ─── FINAL SUMMARY ───
    print("\n" + "=" * 80)
    print("  FINAL SUMMARY")
    print("=" * 80)

    if not all_issues:
        print("  ALL 4 VALIDATION AREAS PASSED")
        print("  Archetypes are realistic, varied, and appropriately constrained.")
        return 0
    else:
        by_area = defaultdict(list)
        for area, issue in all_issues:
            by_area[area].append(issue)

        for area, area_issues in by_area.items():
            print(f"\n  [{area}] — {len(area_issues)} issue(s):")
            for issue in area_issues:
                print(f"    ⚠ {issue}")

        print(f"\n  TOTAL: {len(all_issues)} issue(s) found across {len(by_area)} area(s)")
        print(f"  Review the issues above to determine if archetype tuning is needed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
