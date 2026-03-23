"""Post-correction reality check: full multi-tick simulation harness.

Runs 10 diverse products through a deterministic simulation loop that
mirrors the real engine (baseline + individual delta + simulated LLM hint
+ peer influence + concern propagation + spread + adoption) over 8 ticks.

LLM reactions are replaced with a deterministic proxy that produces
bounded hints proportional to the gap between baseline and current score.
Discussions are skipped (LLM-dependent) but their absence is compensated
by the peer influence phase.

Run:  PYTHONIOENCODING=utf-8 python -m tests.test_post_correction_reality
"""

from __future__ import annotations

import random
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from backend.simulation.adoption import compute_npc_adoption
from backend.simulation.competition import classify_alternatives
from backend.simulation.evaluation import (
    BASELINE_CENTER,
    compute_archetype_baseline,
    compute_individual_delta,
    get_archetype_evaluation,
    reload_evaluations,
)
from backend.simulation.npc import Npc, NpcState, derive_stance
from backend.simulation.population import generate_population
from backend.simulation.product_profile import ProductProfile, build_product_profile
from backend.simulation.propagation import (
    calculate_peer_influence,
    compute_concern_influence,
    compute_spreads,
)
from backend.simulation.world import InjectedIdea, SimConfig, WorldState

reload_evaluations()

# ---------------------------------------------------------------------------
# Scenario definitions (10 products spanning different archetypes & strengths)
# ---------------------------------------------------------------------------

SCENARIOS: dict[str, dict] = {
    # --- STRONG PRODUCTS ---
    "strong_free_saas": {
        "label": "Strong: Free AI Writing Assistant (SaaS)",
        "idea": InjectedIdea(
            title="ProseAI",
            description="An AI writing assistant that learns your style and helps you write faster. Integrates with Google Docs, Notion, and email. Uses fine-tuned language models to match your tone and vocabulary.",
            category="ai_ml_product",
            stage="mvp",
            target_audience="content creators, marketers, and professional writers",
            problem_statement="Writing high-quality content is time-consuming and writer's block is universal",
            price_point="Free",
            existing_alternatives="Grammarly, Jasper, Copy.ai, ChatGPT",
            differentiator="Learns your personal writing style rather than generic outputs",
            known_strengths="Easy integration, privacy-focused, adapts to user",
            known_risks="AI writing fatigue in the market",
        ),
        "expect": "positive_lean",
    },
    "strong_health_app": {
        "label": "Strong: Personalized Nutrition Scanner (Health)",
        "idea": InjectedIdea(
            title="NutriLens",
            description="Point your phone camera at any food to get instant nutritional analysis personalized to your health goals. AI identifies dishes, reads labels, and scores meals against your dietary profile.",
            category="health_wellness",
            stage="prototype",
            target_audience="health-conscious consumers with dietary goals or restrictions",
            problem_statement="People struggle to make informed food choices quickly, especially with complex dietary needs",
            price_point="$5-$20/mo",
            existing_alternatives="MyFitnessPal, Yuka, Fooducate",
            differentiator="Camera-based instant recognition vs manual logging, personalized health scoring",
            known_strengths="Instant results, personalized, no manual entry required",
            known_risks="Camera accuracy limitations, food database completeness",
        ),
        "expect": "mixed_leaning_positive",
    },

    # --- WEAK PRODUCTS ---
    "weak_vague_crypto": {
        "label": "Weak: Vague Crypto Security Concept",
        "idea": InjectedIdea(
            title="CryptoShield",
            description="A blockchain security solution",
            category="crypto_web3",
            stage="concept",
            target_audience="",
            problem_statement="",
            price_point="$50-$100/mo",
            existing_alternatives="Ledger, MetaMask, Fireblocks",
            differentiator="",
            known_strengths="",
            known_risks="Regulatory uncertainty",
        ),
        "expect": "negative_dominant",
    },
    "weak_crowded_todo": {
        "label": "Weak: Another Todo App in Saturated Market",
        "idea": InjectedIdea(
            title="TaskFlow",
            description="A simple task management app with lists, due dates, and reminders",
            category="productivity_tool",
            stage="concept",
            target_audience="anyone who needs to manage tasks",
            problem_statement="People forget tasks",
            price_point="$5-$20/mo",
            existing_alternatives="Todoist, TickTick, Any.do, Google Tasks, Apple Reminders, Microsoft To Do",
            differentiator="Cleaner interface",
            known_strengths="Simple",
            known_risks="Extremely crowded market",
        ),
        "expect": "negative_lean",
    },

    # --- PREMIUM / HIGH-BARRIER ---
    "premium_hardware": {
        "label": "Premium: Smart Home Hub ($100+/mo)",
        "idea": InjectedIdea(
            title="HomeNexus",
            description="A premium AI-powered smart home hub that unifies all IoT devices with predictive automation. Learns household patterns and optimizes energy usage, security, and comfort.",
            category="iot_smart_home",
            stage="prototype",
            target_audience="affluent smart home enthusiasts and tech-forward homeowners",
            problem_statement="Smart home devices from different brands don't communicate, leading to fragmented experiences",
            price_point="$100+/mo",
            existing_alternatives="Amazon Echo, Google Nest, Apple HomeKit, Samsung SmartThings",
            differentiator="Unified cross-brand AI orchestration with predictive automation",
            known_strengths="Comprehensive integration, energy savings, premium build quality",
            known_risks="High price point, privacy concerns, vendor lock-in",
        ),
        "expect": "mixed_leaning_negative",
    },

    # --- LOW-TRUST ---
    "low_trust_fintech": {
        "label": "Low-Trust: P2P Lending Platform (Fintech)",
        "idea": InjectedIdea(
            title="LendCircle",
            description="A peer-to-peer lending platform that connects borrowers with individual lenders for personal loans at competitive rates. Uses AI credit scoring.",
            category="lending",
            stage="mvp",
            target_audience="borrowers seeking lower rates and individual investors seeking higher returns",
            problem_statement="Banks offer low returns to savers and charge high rates to borrowers",
            price_point="usage-based",
            existing_alternatives="LendingClub, Prosper, SoFi",
            differentiator="AI-powered credit risk assessment with transparent risk tiers",
            known_strengths="Lower rates for qualified borrowers, higher returns for lenders",
            known_risks="Default risk, regulatory compliance complexity",
        ),
        "expect": "negative_lean",
    },

    # --- NICHE / VALUES-DRIVEN ---
    "niche_nonprofit": {
        "label": "Niche: Pro-Bono Consulting Matcher (Nonprofit)",
        "idea": InjectedIdea(
            title="SkillBridge",
            description="A platform matching skilled professionals with nonprofits for pro-bono consulting projects. AI matches expertise to nonprofit needs and structures 4-8 week engagements.",
            category="nonprofit",
            stage="concept",
            target_audience="professionals in consulting, law, marketing, and tech wanting to volunteer their expertise",
            problem_statement="Nonprofits can't afford professional consulting but desperately need strategic help",
            price_point="Free",
            existing_alternatives="Catchafire, Taproot Foundation",
            differentiator="AI-matched skill pairing with structured project timelines and milestone tracking",
            known_strengths="Clear social impact, strong mission, scalable matching",
            known_risks="Volunteer retention, project completion rates",
        ),
        "expect": "mixed_polarized",
    },

    # --- HIGH-UTILITY / PRACTICAL ---
    "high_utility_tool": {
        "label": "High-Utility: API Cost Monitor (Developer Tool)",
        "idea": InjectedIdea(
            title="APIWatch",
            description="Real-time monitoring dashboard for API costs across cloud providers. Alerts on spending anomalies, predicts monthly bills, and suggests optimization opportunities.",
            category="developer_tool",
            stage="mvp",
            target_audience="engineering teams and DevOps managing multi-cloud API spending",
            problem_statement="Unexpected API bills are the #1 cloud cost surprise for startups",
            price_point="$5-$20/mo",
            existing_alternatives="AWS Cost Explorer, Datadog, custom dashboards",
            differentiator="Cross-provider unified view with predictive anomaly detection",
            known_strengths="Immediate ROI, easy integration, actionable alerts",
            known_risks="API provider rate-limiting, accuracy of predictions",
        ),
        "expect": "mixed_leaning_positive",
    },

    # --- HOLDOUT: Not part of tuning (for overfitting check) ---
    "holdout_fashion_subscription": {
        "label": "Holdout: AI Fashion Subscription Box (E-commerce)",
        "idea": InjectedIdea(
            title="StyleGenius",
            description="Monthly clothing subscription box curated by AI that learns your style from social media, saved Pinterest boards, and purchase history. Includes virtual try-on.",
            category="subscription_box",
            stage="launched",
            target_audience="fashion-forward millennials who want personalized style without shopping effort",
            problem_statement="People want to look good but hate browsing endless product pages",
            price_point="$20-$50/mo",
            existing_alternatives="Stitch Fix, Trunk Club, Wantable, Amazon Personal Shopper",
            differentiator="AI learns style from social media rather than quizzes",
            known_strengths="Personalized, convenient, social media integration",
            known_risks="Return logistics, fit accuracy, fashion taste is subjective",
        ),
        "expect": "mixed_leaning_negative",
    },
    "holdout_meditation_wearable": {
        "label": "Holdout: Meditation Wearable (Health + Hardware)",
        "idea": InjectedIdea(
            title="ZenBand",
            description="A lightweight headband that measures brainwaves during meditation and provides real-time audio feedback to deepen practice. Pairs with a guided meditation app.",
            category="wearable",
            stage="prototype",
            target_audience="meditation practitioners and mindfulness enthusiasts",
            problem_statement="People struggle to know if they're meditating correctly and can't measure progress",
            price_point="$50-$100/mo",
            existing_alternatives="Muse, Calm, Headspace",
            differentiator="Real-time EEG biofeedback during meditation vs guided audio only",
            known_strengths="Science-backed, measurable progress, unique technology",
            known_risks="EEG accuracy in consumer hardware, high price for meditation audience",
        ),
        "expect": "negative_dominant",
    },
}

# ---------------------------------------------------------------------------
# Deterministic simulation harness (mirrors engine.py without LLM)
# ---------------------------------------------------------------------------

STANCES = ["opposed", "skeptical", "indifferent", "curious", "interested", "willing_to_try", "willing_to_pay"]
POSITIVE_STANCES = {"interested", "willing_to_try", "willing_to_pay"}
NEGATIVE_STANCES = {"opposed", "skeptical"}
NEUTRAL_STANCES = {"indifferent", "curious"}


def _simulated_llm_hint(baseline: float, rng: random.Random) -> float:
    """Simulate LLM hint as small random perturbation bounded to +/-0.10.

    Slightly biased toward 0 (most LLM reactions are close to the
    deterministic baseline). Uses triangular distribution centered at 0.
    """
    return round(rng.triangular(-0.10, 0.10, 0.0), 4)


def _simulated_would_pay(interest_score: float, price_friction: float, rng: random.Random) -> bool:
    """Simulate would_pay decision based on interest and price."""
    if price_friction < 0.05:
        return True  # free product
    prob = max(0, interest_score - price_friction * 0.5) * 0.8
    return rng.random() < prob


def _simulated_objections(
    interest_score: float, profile: ProductProfile, archetype: str, rng: random.Random,
) -> list[str]:
    """Generate plausible objections based on profile signals and interest."""
    objections = []
    if interest_score < 0.50:
        if profile.trust_barrier > 0.50:
            objections.append("trust and credibility concerns")
        if profile.price_friction > 0.40:
            objections.append("pricing is too high")
        if profile.utility_clarity < 0.45:
            objections.append("unclear value proposition")
        if profile.market_saturation > 0.50:
            objections.append("too many similar options already exist")
        if profile.trial_friction > 0.50:
            objections.append("too hard to try")
        if profile.novelty < 0.30:
            objections.append("nothing new here")
    return objections


def run_deterministic_simulation(
    scenario_name: str,
    idea: InjectedIdea,
    num_ticks: int = 8,
    population_size: int = 30,
    seed_count: int = 5,
    seed: int = 42,
) -> dict:
    """Run a full deterministic simulation mimicking the engine tick loop."""

    rng = random.Random(seed)
    random.seed(seed)  # for propagation functions that use module-level random

    config = SimConfig(num_ticks=num_ticks, population_size=population_size, seed_count=seed_count)
    npcs, npc_archetypes = generate_population(size=population_size, seed=seed)
    for npc in npcs:
        npc.reset_state()

    world = WorldState(idea=idea, config=config, npcs={npc.id: npc for npc in npcs})
    world.npc_archetypes = npc_archetypes

    competition_context = None
    if idea.existing_alternatives.strip():
        competition_context = classify_alternatives(
            idea.existing_alternatives, idea_category=idea.category,
        )
    world.competition_context = competition_context
    profile = build_product_profile(idea, competition_context=competition_context)
    world.product_profile = profile

    profile_dict = profile.to_dict()
    competition_dict = competition_context.to_dict() if competition_context else None

    # Tracking
    tick_snapshots = []
    concern_events = 0
    spread_events = 0

    for tick in range(1, num_ticks + 1):
        world.current_tick = tick

        # --- Phase 1: Awareness ---
        if tick == 1:
            all_npcs = list(world.npcs.values())
            seeds = rng.sample(all_npcs, min(seed_count, len(all_npcs)))
            for npc in seeds:
                npc.state.become_aware(tick, source="direct_exposure")
        else:
            for spread in world.pending_spreads:
                target = world.npcs.get(spread.target_id)
                if target and not target.state.aware:
                    target.state.become_aware(tick, source=spread.source_id)
            world.pending_spreads = []

        # Exposure tracking
        for npc in world.aware_npcs:
            npc.state.increment_exposure()

        # --- Phase 2: Reaction (deterministic proxy for LLM) ---
        newly_aware = [n for n in world.npcs.values() if n.state.awareness_tick == tick]
        for npc in newly_aware:
            archetype_id = npc_archetypes.get(npc.id)
            eval_def = get_archetype_evaluation(archetype_id)
            baseline = compute_archetype_baseline(profile, eval_def, category=idea.category)
            ind_delta = compute_individual_delta(npc.personality, profile)
            llm_hint = _simulated_llm_hint(baseline, rng)

            interest = max(0.0, min(1.0, baseline + ind_delta + llm_hint))
            npc.state.interest_score = interest
            npc.state.stance = derive_stance(npc.state.interest_score, npc.state.would_pay, npc.state.aware)
            npc.state.would_pay = _simulated_would_pay(interest, profile.price_friction, rng)
            npc.state.would_recommend = interest >= 0.72
            npc.state.objections = _simulated_objections(interest, profile, archetype_id, rng)
            npc.state._record_history(tick)

        # --- Phase 3: Discussions (skipped — LLM dependent) ---
        # Peer influence in Phase 4 compensates partially

        # --- Phase 4: Peer influence (deterministic) ---
        for npc in world.aware_npcs:
            delta = calculate_peer_influence(npc, world)
            npc.state.apply_influence(delta, tick)

        # --- Phase 4b: Concern propagation ---
        concern_deltas = compute_concern_influence(world)
        for target_id, delta in concern_deltas:
            target_npc = world.npcs.get(target_id)
            if target_npc:
                target_npc.state.apply_influence(delta, tick)
                concern_events += 1

        # --- Re-derive would_recommend ---
        for npc in world.aware_npcs:
            npc.state.update_would_recommend()

        # --- Phase 5: Spread ---
        world.pending_spreads = compute_spreads(world)
        spread_events += len(world.pending_spreads)

        # --- Phase 6: Adoption ---
        for npc in world.npcs.values():
            if not npc.state.aware:
                continue
            personality = npc.to_profile_dict().get("personality", {})
            result = compute_npc_adoption(
                interest_score=npc.state.interest_score,
                would_pay=npc.state.would_pay,
                aware=npc.state.aware,
                personality=personality,
                profile_dict=profile_dict,
                competition_dict=competition_dict,
            )
            npc.state.adopted = result.adopted
            npc.state.adoption_score = result.score
            npc.state.adoption_blockers = list(result.blockers)

        # --- Snapshot ---
        stance_dist = defaultdict(int)
        scores = []
        for npc in world.aware_npcs:
            stance_dist[npc.state.stance] += 1
            scores.append(npc.state.interest_score)

        tick_snapshots.append({
            "tick": tick,
            "aware": len(world.aware_npcs),
            "stances": dict(stance_dist),
            "mean_interest": round(statistics.mean(scores), 3) if scores else 0,
            "std_interest": round(statistics.stdev(scores), 3) if len(scores) > 1 else 0,
        })

    # --- Final stats ---
    final_stances = defaultdict(int)
    final_scores_by_arch = defaultdict(list)
    would_recommend_count = 0
    would_pay_count = 0
    would_try_count = 0
    adopted_count = 0
    concern_npcs = 0
    all_objections = defaultdict(int)

    for npc in world.npcs.values():
        if not npc.state.aware:
            continue
        final_stances[npc.state.stance] += 1
        arch = npc_archetypes.get(npc.id, "unknown")
        final_scores_by_arch[arch].append(npc.state.interest_score)

        if npc.state.would_recommend:
            would_recommend_count += 1
        if npc.state.would_pay:
            would_pay_count += 1
        if npc.state.interest_score >= 0.75:
            would_try_count += 1
        if npc.state.adopted:
            adopted_count += 1
        if npc.state.interest_score < 0.35 and npc.state.objections:
            concern_npcs += 1
        for obj in npc.state.objections:
            all_objections[obj] += 1

    aware_count = len(world.aware_npcs)
    total = population_size

    return {
        "scenario": scenario_name,
        "profile": profile.to_dict(),
        "tick_snapshots": tick_snapshots,
        "final": {
            "aware_count": aware_count,
            "aware_pct": round(aware_count / total, 2),
            "stances": dict(final_stances),
            "positive_pct": round(sum(v for k, v in final_stances.items() if k in POSITIVE_STANCES) / max(1, aware_count), 2),
            "negative_pct": round(sum(v for k, v in final_stances.items() if k in NEGATIVE_STANCES) / max(1, aware_count), 2),
            "neutral_pct": round(sum(v for k, v in final_stances.items() if k in NEUTRAL_STANCES) / max(1, aware_count), 2),
            "would_recommend_pct": round(would_recommend_count / max(1, aware_count), 2),
            "would_pay_pct": round(would_pay_count / max(1, aware_count), 2),
            "would_try_pct": round(would_try_count / max(1, aware_count), 2),
            "adoption_rate": round(adopted_count / max(1, aware_count), 2),
            "adopted_count": adopted_count,
        },
        "dynamics": {
            "concern_events": concern_events,
            "concern_npcs": concern_npcs,
            "spread_events": spread_events,
            "final_aware_from_spread": aware_count - min(5, total),
        },
        "archetype_breakdown": {
            arch: {
                "count": len(scores),
                "mean": round(statistics.mean(scores), 3),
                "std": round(statistics.stdev(scores), 3) if len(scores) > 1 else 0,
                "min": round(min(scores), 3),
                "max": round(max(scores), 3),
            }
            for arch, scores in sorted(final_scores_by_arch.items())
        },
        "top_objections": sorted(all_objections.items(), key=lambda x: -x[1])[:5],
    }


# ---------------------------------------------------------------------------
# Realism assessment helpers
# ---------------------------------------------------------------------------

def assess_realism(results: dict) -> list[str]:
    """Return list of realism observations about a simulation result."""
    obs = []
    f = results["final"]
    d = results["dynamics"]

    # Stance distribution
    if f["positive_pct"] > 0.60:
        obs.append("WARNING: >60% positive — may still be too optimistic")
    elif f["positive_pct"] > 0.40:
        obs.append("OK: 40-60% positive — moderately optimistic")
    elif f["positive_pct"] > 0.15:
        obs.append("GOOD: 15-40% positive — realistic mixed reception")
    else:
        obs.append("OK: <15% positive — skeptical/negative reception")

    if f["negative_pct"] < 0.05 and results["scenario"] not in ("strong_free_saas",):
        obs.append("WARNING: <5% negative — opposition too absent")
    if f["negative_pct"] > 0.70:
        obs.append("CONCERN: >70% negative — might be too harsh")

    # Adoption
    if f["adoption_rate"] > 0.40:
        obs.append("WARNING: >40% adoption — unusually high")
    elif f["adoption_rate"] == 0:
        obs.append("NOTE: 0% adoption — common without LLM boost")

    # Concern propagation
    if d["concern_events"] > 0:
        obs.append(f"GOOD: concern propagation active ({d['concern_events']} events, {d['concern_npcs']} concerned NPCs)")
    else:
        obs.append("NOTE: no concern propagation fired")

    # Spread
    if d["spread_events"] == 0 and f["aware_pct"] <= 0.20:
        obs.append("NOTE: no word-of-mouth spread — recommendation threshold may be filtering all")
    elif d["spread_events"] > 0:
        obs.append(f"GOOD: word-of-mouth active ({d['spread_events']} spread events)")

    # Archetype differentiation
    arch = results["archetype_breakdown"]
    if len(arch) > 1:
        means = [v["mean"] for v in arch.values()]
        arch_spread = max(means) - min(means)
        if arch_spread < 0.05:
            obs.append(f"WARNING: archetype spread only {arch_spread:.3f} — insufficient differentiation")
        elif arch_spread < 0.10:
            obs.append(f"OK: archetype spread {arch_spread:.3f} — moderate differentiation")
        else:
            obs.append(f"GOOD: archetype spread {arch_spread:.3f} — strong differentiation")

    return obs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 76)
    print("POST-CORRECTION REALITY CHECK — FULL SIMULATION HARNESS")
    print(f"BASELINE_CENTER={BASELINE_CENTER}  recommend_threshold=0.72  concern_mult=0.30")
    print("=" * 76)

    all_results = {}

    for name, scenario in SCENARIOS.items():
        idea = scenario["idea"]
        label = scenario["label"]
        expected = scenario["expect"]

        result = run_deterministic_simulation(name, idea, num_ticks=8, population_size=30, seed=42)
        all_results[name] = result
        f = result["final"]
        d = result["dynamics"]

        print(f"\n{'─' * 76}")
        print(f"  {label}")
        print(f"  Expected: {expected}")
        print(f"{'─' * 76}")

        # Profile summary
        p = result["profile"]
        print(f"  Profile: nov={p['novelty']:.2f} util={p['utility_clarity']:.2f} "
              f"diff={p['differentiation']:.2f} price={p['price_friction']:.2f} "
              f"trust={p['trust_barrier']:.2f} fit={p['identity_fit']:.2f} "
              f"trial={p['trial_friction']:.2f} sat={p['market_saturation']:.2f}")

        # Awareness
        print(f"\n  Awareness: {f['aware_count']}/{30} ({f['aware_pct']:.0%})")

        # Stances
        print(f"  Stances: {f['stances']}")
        print(f"    Positive: {f['positive_pct']:.0%}  |  Neutral: {f['neutral_pct']:.0%}  |  Negative: {f['negative_pct']:.0%}")

        # Rates
        print(f"  Rates:  recommend={f['would_recommend_pct']:.0%}  "
              f"would_pay={f['would_pay_pct']:.0%}  "
              f"would_try={f['would_try_pct']:.0%}  "
              f"adopted={f['adoption_rate']:.0%} ({f['adopted_count']})")

        # Dynamics
        print(f"  Dynamics: concern_events={d['concern_events']}  "
              f"concern_npcs={d['concern_npcs']}  "
              f"spread_events={d['spread_events']}  "
              f"spread_aware={d['final_aware_from_spread']}")

        # Archetype breakdown
        print(f"  Archetype breakdown:")
        for arch, info in sorted(result["archetype_breakdown"].items(), key=lambda x: -x[1]["mean"]):
            bar = "+" * int(info["mean"] * 40)
            print(f"    {arch:25s}: mean={info['mean']:.3f} std={info['std']:.3f} "
                  f"[{info['min']:.3f}-{info['max']:.3f}] {bar}")

        # Top objections
        if result["top_objections"]:
            print(f"  Top objections: {', '.join(f'{o}({c})' for o, c in result['top_objections'][:3])}")

        # Realism assessment
        observations = assess_realism(result)
        print(f"  Realism assessment:")
        for obs in observations:
            print(f"    {obs}")

    # ===================================================================
    # SUMMARY TABLES
    # ===================================================================

    print(f"\n\n{'=' * 76}")
    print("SUMMARY: STANCE DISTRIBUTIONS")
    print(f"{'=' * 76}")
    print(f"  {'Scenario':<30s} {'Pos%':>5s} {'Neu%':>5s} {'Neg%':>5s} {'Aware':>5s} {'Adopt':>5s} {'Recmd':>5s} {'Conc':>5s} {'Sprd':>5s}")
    print(f"  {'─'*30} {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*5}")

    for name, r in all_results.items():
        f = r["final"]
        d = r["dynamics"]
        print(f"  {name:<30s} {f['positive_pct']:>4.0%} {f['neutral_pct']:>4.0%} "
              f"{f['negative_pct']:>4.0%} {f['aware_pct']:>4.0%} {f['adoption_rate']:>4.0%} "
              f"{f['would_recommend_pct']:>4.0%} {d['concern_events']:>5d} {d['spread_events']:>5d}")

    # ===================================================================
    # REALISM VERDICT
    # ===================================================================

    print(f"\n\n{'=' * 76}")
    print("REALISM VERDICT")
    print(f"{'=' * 76}")

    # Check 1: Strong products should be more positive than weak ones
    strong_pos = statistics.mean([all_results[k]["final"]["positive_pct"]
                                  for k in ("strong_free_saas", "strong_health_app")])
    weak_pos = statistics.mean([all_results[k]["final"]["positive_pct"]
                                for k in ("weak_vague_crypto", "weak_crowded_todo")])
    ordering_ok = strong_pos > weak_pos
    print(f"\n  Strong vs Weak ordering: strong_mean_pos={strong_pos:.2f} > weak_mean_pos={weak_pos:.2f} → {'PASS' if ordering_ok else 'FAIL'}")

    # Check 2: Premium/low-trust should have lower adoption than strong free
    strong_adopt = all_results["strong_free_saas"]["final"]["adoption_rate"]
    premium_adopt = all_results["premium_hardware"]["final"]["adoption_rate"]
    lowtrust_adopt = all_results["low_trust_fintech"]["final"]["adoption_rate"]
    barrier_ok = strong_adopt >= premium_adopt and strong_adopt >= lowtrust_adopt
    print(f"  Barrier impact: free_adopt={strong_adopt:.2f} >= premium={premium_adopt:.2f}, lowtrust={lowtrust_adopt:.2f} → {'PASS' if barrier_ok else 'FAIL'}")

    # Check 3: No scenario should have >70% positive (even strong ones)
    max_positive = max(r["final"]["positive_pct"] for r in all_results.values())
    max_pos_name = max(all_results, key=lambda k: all_results[k]["final"]["positive_pct"])
    no_runaway = max_positive <= 0.70
    print(f"  No runaway positivity: max_positive={max_positive:.0%} ({max_pos_name}) → {'PASS' if no_runaway else 'FAIL'}")

    # Check 4: Weak products should have >20% negative
    weak_neg = min(all_results[k]["final"]["negative_pct"]
                   for k in ("weak_vague_crypto", "weak_crowded_todo"))
    weak_neg_ok = weak_neg >= 0.20
    print(f"  Weak products show negativity: min_neg={weak_neg:.0%} (>= 20%) → {'PASS' if weak_neg_ok else 'FAIL'}")

    # Check 5: Concern propagation fires in at least 3 scenarios
    concern_active = sum(1 for r in all_results.values() if r["dynamics"]["concern_events"] > 0)
    concern_ok = concern_active >= 3
    print(f"  Concern propagation active: {concern_active}/10 scenarios → {'PASS' if concern_ok else 'FAIL'}")

    # Check 6: Holdout scenarios produce reasonable distributions (not over-fitted)
    holdout_names = [k for k in all_results if k.startswith("holdout_")]
    holdout_issues = []
    for h in holdout_names:
        hf = all_results[h]["final"]
        if hf["positive_pct"] > 0.60:
            holdout_issues.append(f"{h}: positive too high ({hf['positive_pct']:.0%})")
        if hf["negative_pct"] == 0 and hf["positive_pct"] < 0.60:
            holdout_issues.append(f"{h}: zero negative for a non-dominant product")
    holdout_ok = len(holdout_issues) == 0
    print(f"  Holdout realism: {len(holdout_issues)} issues → {'PASS' if holdout_ok else 'WARN'}")
    for issue in holdout_issues:
        print(f"    {issue}")

    # Check 7: Archetype spread > 0.05 for all scenarios
    low_spread_scenarios = []
    for name, r in all_results.items():
        arch = r["archetype_breakdown"]
        if len(arch) > 1:
            means = [v["mean"] for v in arch.values()]
            spread = max(means) - min(means)
            if spread < 0.05:
                low_spread_scenarios.append(f"{name}: spread={spread:.3f}")
    arch_diff_ok = len(low_spread_scenarios) == 0
    print(f"  Archetype differentiation: {len(low_spread_scenarios)} low-spread scenarios → {'PASS' if arch_diff_ok else 'WARN'}")
    for ls in low_spread_scenarios:
        print(f"    {ls}")

    # Overall
    checks = [ordering_ok, barrier_ok, no_runaway, weak_neg_ok, concern_ok]
    passed = sum(checks)
    print(f"\n  OVERALL: {passed}/{len(checks)} core checks pass")

    return all_results


if __name__ == "__main__":
    main()
