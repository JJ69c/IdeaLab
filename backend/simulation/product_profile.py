"""Idea normalization layer.

Converts raw InjectedIdea fields into a structured ProductProfile with
simulation-relevant dimensions (all 0-1 floats). These dimensions feed
the deterministic math in propagation.py and the post-LLM reaction
adjustments in engine.py — they do NOT replace the LLM's qualitative
reasoning, they shape the mechanical backbone of the simulation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.simulation.world import InjectedIdea

# ---------------------------------------------------------------------------
# Price string → friction mapping
# ---------------------------------------------------------------------------

_PRICE_FRICTION: dict[str, float] = {
    "free": 0.0,
    "freemium": 0.10,
    "< $5/mo": 0.20,
    "$5–$20/mo": 0.35,
    "$5-$20/mo": 0.35,
    "$20–$50/mo": 0.50,
    "$20-$50/mo": 0.50,
    "$50–$100/mo": 0.65,
    "$50-$100/mo": 0.65,
    "$100+/mo": 0.80,
    "one-time purchase": 0.40,
    "usage-based": 0.45,
    "not specified": 0.30,
    "not decided yet": 0.30,
    "": 0.30,
}

# Categories where trust requirements are inherently higher
_HIGH_TRUST_CATEGORIES = frozenset({
    "payments", "lending", "insurance", "investing", "crypto_web3",
    "health_wellness", "biotech", "mental_health",
    "consumer_hardware", "wearable",
})

# Categories the general population is deeply familiar with
_MATURE_CATEGORIES = frozenset({
    "saas", "ecommerce", "marketplace", "social_platform",
    "content_media", "mobile_app", "subscription_box",
})


# ---------------------------------------------------------------------------
# ProductProfile
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProductProfile:
    """Derived simulation dimensions for an injected idea.  All 0-1 floats."""

    novelty: float              # How unfamiliar/new the concept is
    utility_clarity: float      # How clearly the value proposition is understood
    differentiation: float      # How distinct from known alternatives
    price_friction: float       # Resistance introduced by pricing
    trust_barrier: float        # How much trust is needed before adoption
    identity_fit: float         # Baseline audience-product alignment (refined per-NPC)
    trial_friction: float       # Effort required to try (stage + category proxy)
    market_saturation: float    # How crowded the competitive space feels

    def to_dict(self) -> dict:
        return {
            "novelty": round(self.novelty, 3),
            "utility_clarity": round(self.utility_clarity, 3),
            "differentiation": round(self.differentiation, 3),
            "price_friction": round(self.price_friction, 3),
            "trust_barrier": round(self.trust_barrier, 3),
            "identity_fit": round(self.identity_fit, 3),
            "trial_friction": round(self.trial_friction, 3),
            "market_saturation": round(self.market_saturation, 3),
        }


def build_product_profile(
    idea: InjectedIdea,
    asset_signals: object | None = None,
    competition_context: object | None = None,
) -> ProductProfile:
    """Derive a ProductProfile from raw InjectedIdea fields.

    If asset_signals is provided (an AssetSignals instance), its dimensions
    nudge the base profile: polished visuals reduce trust barrier and trial
    friction, clear screenshots boost utility clarity, etc.

    If competition_context is provided (a CompetitionContext instance), it
    replaces the raw comma-count formula for market_saturation and refines
    novelty and trust_barrier based on structured competition dimensions.
    """

    cat = idea.category.lower().strip()
    stage = idea.stage.lower().strip()
    has_alternatives = bool(idea.existing_alternatives.strip())
    has_differentiator = bool(idea.differentiator.strip())
    has_problem = bool(idea.problem_statement.strip())
    has_strengths = bool(idea.known_strengths.strip())
    has_risks = bool(idea.known_risks.strip())
    desc_len = len(idea.description.strip())

    # --- novelty ---
    # Concept-stage ideas in less-known categories feel more novel
    stage_novelty = {"concept": 0.85, "prototype": 0.65, "mvp": 0.45, "launched": 0.25}
    n = stage_novelty.get(stage, 0.65)
    if competition_context is not None:
        n -= competition_context.direct_competition_intensity * 0.25
    elif has_alternatives:
        n -= 0.20  # market already exists → less novel
    if cat in _MATURE_CATEGORIES:
        n -= 0.15
    novelty = _clamp(n)

    # --- utility_clarity ---
    # Reduced bonuses: filling in form fields demonstrates description
    # clarity, not product strength. A well-worded mediocre idea should
    # not score as high as a genuinely clear value proposition.
    uc = 0.25  # baseline: vague
    if has_problem:
        uc += 0.18
    if desc_len > 150:
        uc += 0.10
    elif desc_len > 80:
        uc += 0.05
    if has_differentiator:
        uc += 0.10
    if has_strengths:
        uc += 0.07
    utility_clarity = _clamp(uc)

    # --- differentiation ---
    # Reduced: having a differentiator field doesn't prove real
    # differentiation — it only means the founder articulated one.
    if not has_alternatives:
        diff = 0.45 + (0.10 if has_differentiator else 0)
    elif has_differentiator:
        diff = 0.55
    else:
        diff = 0.25  # alternatives exist but no clear differentiator
    differentiation = _clamp(diff)

    # --- price_friction ---
    price_key = idea.price_point.lower().strip()
    pf = _PRICE_FRICTION.get(price_key, _guess_price_friction(price_key))
    price_friction = _clamp(pf)

    # --- trust_barrier ---
    tb = 0.30  # baseline
    if stage == "concept":
        tb += 0.25
    elif stage == "prototype":
        tb += 0.15
    elif stage == "launched":
        tb -= 0.10
    if cat in _HIGH_TRUST_CATEGORIES:
        tb += 0.20
    if has_risks:
        tb += 0.05  # founder acknowledges risks → slightly more scrutiny
    if competition_context is not None:
        tb += competition_context.incumbent_trust_pressure * 0.10
    trust_barrier = _clamp(tb)

    # --- identity_fit (baseline, refined per-NPC later) ---
    # Reduced bonuses: specifying a target audience doesn't guarantee
    # the product actually fits that audience. Real identity fit is
    # further adjusted per-NPC via category-archetype affinity.
    idf = 0.35
    if idea.target_audience.strip() and idea.target_audience != "general public":
        idf += 0.15
    if has_problem:
        idf += 0.10
    if has_strengths:
        idf += 0.05
    identity_fit = _clamp(idf)

    # --- trial_friction ---
    # How hard is it to try this thing?
    tf = 0.30
    if stage == "concept":
        tf += 0.30  # nothing to try yet
    elif stage == "prototype":
        tf += 0.15
    if cat in {"consumer_hardware", "wearable", "iot_smart_home"}:
        tf += 0.20  # physical products are harder to trial
    if price_friction > 0.5:
        tf += 0.10  # expensive → higher commitment to try
    trial_friction = _clamp(tf)

    # --- market_saturation ---
    ms = 0.25
    if competition_context is not None:
        ms += competition_context.saturation_pressure * 0.40
    elif has_alternatives:
        # Backward compatibility fallback (comma-count when no CompetitionContext)
        alt_count = len(re.split(r"[,;&/]|\band\b", idea.existing_alternatives))
        ms += min(alt_count * 0.10, 0.40)
    if cat in _MATURE_CATEGORIES:
        ms += 0.15
    market_saturation = _clamp(ms)

    # --- Asset signal adjustments (product-level) ---
    if asset_signals is not None:
        trust_barrier = _clamp(trust_barrier - getattr(asset_signals, "trustworthiness", 0) * 0.20)
        utility_clarity = _clamp(utility_clarity + getattr(asset_signals, "clarity", 0) * 0.15)
        differentiation = _clamp(differentiation + getattr(asset_signals, "differentiation_signal", 0) * 0.10)
        trial_friction = _clamp(trial_friction - getattr(asset_signals, "perceived_polish", 0) * 0.15)

    return ProductProfile(
        novelty=novelty,
        utility_clarity=utility_clarity,
        differentiation=differentiation,
        price_friction=price_friction,
        trust_barrier=trust_barrier,
        identity_fit=identity_fit,
        trial_friction=trial_friction,
        market_saturation=market_saturation,
    )


# ---------------------------------------------------------------------------
# Per-NPC adjustment: refine the profile's effect for a specific persona
# ---------------------------------------------------------------------------

def compute_npc_adjustment(profile: ProductProfile, personality: dict) -> float:
    """Compute a per-NPC interest adjustment based on product profile × personality.

    Returns a delta in [-0.15, +0.15] that is applied AFTER the LLM reaction
    to anchor the qualitative response to the quantitative product dimensions.
    This is the "individual evaluation" layer (Stage A). The cap is intentionally
    smaller than the stance band width so the adjustment corrects, not overrides.
    """
    delta = 0.0

    openness = personality.get("openness", 0.5)
    skepticism = personality.get("skepticism", 0.5)
    price_sens = personality.get("price_sensitivity", 0.5)
    tech = personality.get("tech_savviness", 0.5)
    novelty_seek = personality.get("novelty_seeking", 0.5)

    # --- Linear terms (existing) ---

    # Price-sensitive NPC + expensive product → dampen
    delta -= profile.price_friction * price_sens * 0.15

    # Low tech-savviness + high trial friction → dampen
    delta -= profile.trial_friction * (1 - tech) * 0.10

    # High novelty seeking + novel product → boost
    delta += profile.novelty * novelty_seek * 0.10

    # High skepticism + high trust barrier → dampen
    delta -= profile.trust_barrier * skepticism * 0.10

    # Clear utility + high openness → boost
    delta += profile.utility_clarity * openness * 0.08

    # Strong differentiation → modest universal boost
    delta += profile.differentiation * 0.05

    # Market saturation → dampen for less adventurous NPCs
    delta -= profile.market_saturation * (1 - novelty_seek) * 0.08

    # --- Interaction terms (non-linear compounds) ---
    # These create effects that the linear terms above cannot: when multiple
    # negative (or positive) factors coincide, the penalty (or boost) is
    # steeper than the sum of parts.

    # Expensive + unproven + skeptical → compound penalty
    # A skeptic facing a pricey product with a high trust barrier gets hit
    # harder than each factor individually would suggest.
    delta -= profile.price_friction * profile.trust_barrier * skepticism * 0.08

    # Clear value + differentiated + open-minded → compound boost
    # An open NPC seeing a clearly useful AND unique product gets an extra
    # nudge beyond the individual boosts.
    delta += profile.utility_clarity * profile.differentiation * openness * 0.06

    return max(-0.15, min(0.15, round(delta, 4)))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return round(max(lo, min(hi, v)), 3)


def _guess_price_friction(s: str) -> float:
    """Best-effort friction for custom price strings."""
    if not s:
        return 0.30
    s = s.lower()
    if "free" in s:
        return 0.05
    # Try to extract a dollar amount
    m = re.search(r"\$(\d+)", s)
    if m:
        amount = int(m.group(1))
        if amount == 0:
            return 0.0
        if amount < 5:
            return 0.20
        if amount < 20:
            return 0.35
        if amount < 50:
            return 0.50
        if amount < 100:
            return 0.65
        return 0.80
    return 0.35  # unknown → moderate friction
