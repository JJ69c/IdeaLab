"""Objection theme taxonomy, classification, and archetype resonance matrix.

This module makes concern propagation content-aware. Instead of applying
identical deltas regardless of what the objection is about, the resonance
system amplifies or dampens concern impact based on whether the objection
theme matches what the target archetype actually cares about.

Design principles:
- Deterministic: no LLM calls, no randomness. Same input -> same output.
- Inspectable: the theme taxonomy and resonance values are plain data.
- Partially derived: ~half the resonance matrix is computed from the
  archetype evaluation weights in archetypes.json, reducing hand-written
  surface area and ensuring consistency with baseline scoring.
- Fallback-safe: unknown themes get resonance 1.0 (no amplification).

Theme taxonomy (9 themes):
    price           Cost, expense, value-for-money concerns
    complexity      Difficulty, learning curve, setup friction
    differentiation "Nothing new", "clone of X", lack of uniqueness
    evidence        Clinical proof, studies, data, peer review
    legitimacy      Scam risk, company trustworthiness, track record
    privacy         Data collection, surveillance, personal info
    social_proof    Adoption uncertainty, "nobody uses this"
    ethics          Environmental, labor, greenwashing, moral concerns
    relevance       "Not for me", poor fit, not solving my problem
"""

from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# All known archetype IDs (must match archetypes.json)
# ---------------------------------------------------------------------------

ARCHETYPES: tuple[str, ...] = (
    "analytical_skeptic",
    "trend_adopter",
    "price_pragmatist",
    "health_evaluator",
    "brand_buyer",
    "social_follower",
    "convenience_user",
    "values_buyer",
)

# ---------------------------------------------------------------------------
# Theme taxonomy: keywords that map LLM-generated objections to themes
# ---------------------------------------------------------------------------
# Rules:
# - Multi-word phrases are preferred over single words to avoid false matches.
# - Each keyword list is checked via substring match (case-insensitive).
# - Winner-take-all by keyword hit count; ties broken by list order below.
# - "general" is the fallback (no keywords needed).

OBJECTION_THEMES: dict[str, list[str]] = {
    "price": [
        # Direct price language
        "expensive", "costly", "overpriced", "price", "pricing",
        "afford", "pay more", "subscription fee",
        "free alternative", "cheaper", "waste of money", "hidden cost",
        "premium pricing", "too much money",
        # Natural monetary phrasing
        "dollar", "a month", "per month", "per year", "adds up",
        "fraction of the price", "for the cost", "for that price",
        "not worth", "value for money", "bang for the buck",
        "free version", "free app", "free tool",
        # LLM output patterns (v3: from real Haiku objections)
        "subscription", "/month", "/year",
        "justify", "hard to justify", "unsustainable",
        "recurring", "roi", "expense", "investment",
        "money-back", "free trial", "steep",
        # Removed: "budget" (matches product names), "upsell" (moved to legitimacy)
    ],
    "complexity": [
        # Direct complexity language
        "complicated", "complex", "confusing", "steep learning",
        "learning curve", "hard to use", "difficult to set up",
        "onboarding", "time to learn",
        "not intuitive", "too many steps",
        # Natural effort/friction phrasing
        "too much hassle", "hassle", "too much effort", "too many",
        "figure out", "figure this out", "hard to understand",
        "require an electrician", "requires an electrician",
        "way too much", "overwhelming", "cumbersome",
        "configuration", "configuring", "not user-friendly",
        # LLM output patterns (v3)
        "friction", "demanding", "time-consuming",
        "commitment", "active engagement",
        "plug-and-play", "plug and play",
        "manual input", "under 2 minutes", "in under",
        "how much time", "time constraints", "setup",
    ],
    "differentiation": [
        # Direct differentiation language
        "nothing new", "already exists", "clone", "copycat",
        "same as", "no different", "me too",
        "undifferentiated", "commodity", "crowded market",
        "what makes this different", "why not just use",
        # Natural sameness phrasing
        "does the same", "do the same", "same thing",
        "already have", "already does", "seen this before",
        "just another", "yet another", "one of many",
        "what sets this apart", "how is this different",
        "saturated market", "too many of these",
        # LLM output patterns (v3)
        "why switch", "why pay for both",
        "already covers", "compete with",
        "advantage over", "what does this offer", "unique value",
        "differentiation", "beats", "exclusive features",
    ],
    "evidence": [
        # Direct evidence language (all keywords lowercase for matching)
        "evidence", "study", "studies", "research", "clinical",
        "proven", "peer-reviewed", "credential", "certified", "fda",
        "scientific", "tested", "verified claims", "back up",
        "show me the data", "where are the results",
        # Natural proof-seeking phrasing
        "prove it", "proof", "back it up", "cite",
        "trials", "trial data", "published",
        "where is the data", "what data", "any data",
        # LLM output patterns (v3)
        "methodology", "algorithm", "claims",
        "verify", "transparent", "how does the",
        "trust the", "endorsed", "qualified",
        "regulatory", "certification", "endorsement",
        "validated", "pseudoscience", "biomarker",
        "success rate", "nutritional guideline",
        "unreliable", "actually better", "my doctor",
        "low-quality", "questions whether",
        "marketing hype", "actually works", "reliable than",
    ],
    "legitimacy": [
        "scam", "legitimate", "shady", "sketchy",
        "track record", "reputation", "real company", "verified",
        "trustworthy", "too good to be true", "fly-by-night",
        "who is behind", "credible", "accountability",
        # Natural trust phrasing
        "sounds fishy", "red flag", "disappear tomorrow",
        "will this company", "who runs this", "who are they",
        "can i trust", "vaporware", "snake oil",
        "upsell",
        # Removed: "reliable" (too broad — catches "unreliable" in evidence contexts)
    ],
    "privacy": [
        # All keywords lowercase for matching
        "privacy", "data collection", "surveillance", "tracking",
        "personal data", "personal information",
        "sell my data", "data sharing", "data breach", "gdpr",
        "consent", "opt out",
        # Longer phrases to avoid false positives (removed bare "monitor", "spy")
        "monitor me", "monitors me", "monitoring me", "being monitored",
        "spying on", "spy on", "spies on",
        "how much data", "what data do", "my data",
        "too many permissions", "requires access to",
        "portfolio data", "health data", "location data",
        # LLM output patterns (v3)
        "how data is", "data is stored", "data harvesting",
        "how my data", "hipaa", "data governance",
    ],
    "social_proof": [
        "nobody uses", "no one uses", "unproven", "untested",
        "who uses this", "wait and see", "not enough users",
        "no reviews", "no testimonials", "first one",
        "anyone tried", "mainstream",
        # Verb tense variants and natural phrasing
        "catching on", "catches on", "caught on",
        "wait until", "wait for it to", "wait for more",
        "none of my friends", "nobody i know",
        "no one i know", "haven't heard of anyone",
        "early adopter", "not proven", "not established",
        # LLM output patterns (v3)
        "peers", "critical mass", "widely used", "popular",
        "my circle", "his circle", "her circle",
        "network effect", "adoption",
        "established player", "established platform",
        "already established", "trusted by many", "see peers",
    ],
    "ethics": [
        "ethical", "environmental", "sustainability",
        "greenwashing", "fair trade",
        "carbon footprint", "supply chain", "exploitation",
        "social responsibility", "moral",
        # Longer phrases to avoid false positives
        "exploitative labor", "labor practices", "labor conditions",
        "worker rights", "workers rights", "working conditions",
        "environmental impact", "environmental damage",
        "environmental harm", "harms the environment",
        "social impact", "societal impact",
        "profiting off", "taking advantage of",
        # LLM output patterns (v3)
        "bias", "fairness", "dark pattern",
        "algorithmic fairness", "incentivize",
        "packaging waste", "vulnerable population",
        "digital divide", "privileged",
        "co-op", "democratize",
        "excess packaging", "shipping waste",
    ],
    "relevance": [
        "not for me", "don't need", "no use case", "irrelevant",
        "doesn't solve", "does not solve", "wrong audience",
        "doesn't apply", "does not apply",
        "my situation", "not my problem", "overkill",
        "too specific", "too broad",
        # Natural fit/mismatch phrasing
        "already have a", "already use", "don't have this problem",
        "do not have this problem",
        "doesn't fit", "does not fit", "poor fit", "not relevant",
        "don't see the point", "do not see the point",
        "why would i", "no reason to",
        "solves a problem i don't have", "problem i don't have",
        "problem i still have", "not applicable", "not my use case",
        # LLM output patterns (v3)
        "relevance", "does not align", "doesn't align",
        "no direct value", "not designed for",
        "not the target", "target audience",
        "no professional reason", "professional role",
        "no urgent", "unnecessary", "adequate",
        "current routine", "my routine", "lifestyle",
        "necessary",
    ],
}

# Ordered list for tie-breaking (first match wins on equal counts)
_THEME_PRIORITY: list[str] = list(OBJECTION_THEMES.keys())


def classify_objection_theme(text: str) -> str:
    """Classify an objection/concern text into a theme via keyword matching.

    Returns the theme with the most keyword hits. On ties, earlier themes
    in _THEME_PRIORITY win. Returns "general" if no keywords match.

    >>> classify_objection_theme("This is way too expensive for what it does")
    'price'
    >>> classify_objection_theme("I love this product")
    'general'
    """
    if not text:
        return "general"

    lower = text.lower()
    best_theme = "general"
    best_count = 0

    for theme in _THEME_PRIORITY:
        count = sum(1 for kw in OBJECTION_THEMES[theme] if kw in lower)
        if count > best_count:
            best_count = count
            best_theme = theme

    return best_theme


def classify_objection_themes(objections: list[str]) -> list[str]:
    """Classify a list of objections and return unique themes in priority order.

    Used to set NpcState.objection_themes during apply_reaction.
    Deduplicates while preserving the order of first occurrence.
    """
    seen: set[str] = set()
    themes: list[str] = []
    for text in objections:
        theme = classify_objection_theme(text)
        if theme != "general" and theme not in seen:
            seen.add(theme)
            themes.append(theme)
    return themes


# ---------------------------------------------------------------------------
# Resonance matrix: archetype x theme -> multiplier
# ---------------------------------------------------------------------------
# Values represent how much a given archetype is affected by a concern of
# that theme, relative to the base delta.
#
# 1.0 = neutral (no amplification or dampening)
# >1.0 = this archetype is MORE sensitive to this theme (amplifies concern)
# <1.0 = this archetype is LESS sensitive to this theme (dampens concern)
#
# All 72 cells are hand-written based on archetype behavioral definitions.
# Previous approach derived price/complexity/differentiation/evidence from
# evaluation weights, but the formula (1.0 + abs(weight) * SCALE) always
# produced values >= 1.0 with near-zero variance across archetypes.
# Hand-written values allow sub-1.0 resonance and deliberate spread.
#
# Clamped to [0.4, 2.0] to prevent extreme swings.

_RESONANCE_MIN: float = 0.4
_RESONANCE_MAX: float = 2.0

# Full resonance matrix — all values hand-written for behavioral accuracy.
#
# Per-archetype rationale:
#
#   analytical_skeptic: Evidence is king (1.8). Demands proof, tolerates
#       complexity (0.7, enjoys figuring things out), wants unique value
#       proposition (differentiation 1.5). Privacy-conscious (1.5). Decides
#       independently — low social_proof (0.5). Moderate price sensitivity.
#
#   trend_adopter: Novelty-driven optimist. Low sensitivity to price (0.6,
#       pays premium for status), complexity (0.6, tech-savvy), and evidence
#       (0.5, acts on excitement). Social_proof inverted (0.5, being early
#       is the point). Differentiation matters (1.3, novelty).
#
#   price_pragmatist: Price is the dominant concern (1.8). Practical —
#       moderate complexity (1.2) and evidence (1.1) sensitivity. Low
#       differentiation sensitivity (1.1, doesn't care about uniqueness
#       if it works). Ethics is not a purchase driver (0.6).
#
#   health_evaluator: Evidence-focused (1.7, demands clinical proof).
#       Legitimacy high (1.4, health scams are dangerous). Privacy moderate
#       (1.2, health data is sensitive). Neutral on price (1.0, health
#       spending is justified). Complexity and differentiation secondary.
#
#   brand_buyer: Premium pricing is a quality signal, not a concern (0.5).
#       Differentiation matters (1.4, brand identity). Relevance is key
#       (1.3, brand fit). Low evidence sensitivity (0.7, judges by prestige).
#       Tolerates complexity for premium experience (0.8).
#
#   social_follower: Social_proof dominates (1.8). Wants easy (complexity 1.3)
#       and affordable (price 1.2). Low independent judgment — evidence (0.6),
#       differentiation (0.5), legitimacy (0.7). Defers to group.
#
#   convenience_user: Complexity/friction is the gate (1.8). Relevance
#       matters (1.3, does this solve my problem?). Low sensitivity to
#       abstract concerns — ethics (0.5), legitimacy (0.7). Moderate
#       evidence (0.8). Low differentiation concern (0.7).
#
#   values_buyer: Ethics dominates (1.8). Legitimacy matters (1.3,
#       greenwashing detection). Evidence of impact (1.3). Privacy
#       moderate (1.2). Tolerates price (0.7) and complexity (0.8) for
#       mission-aligned products. Low differentiation concern (0.8).
#
_RESONANCE_MATRIX: dict[str, dict[str, float]] = {
    "analytical_skeptic": {
        "price": 1.3, "complexity": 0.7, "differentiation": 1.5, "evidence": 1.8,
        "legitimacy": 1.3, "privacy": 1.5, "social_proof": 0.5,
        "ethics": 0.9, "relevance": 1.0,
    },
    "trend_adopter": {
        "price": 0.6, "complexity": 0.6, "differentiation": 1.3, "evidence": 0.5,
        "legitimacy": 0.6, "privacy": 0.6, "social_proof": 0.5,
        "ethics": 0.5, "relevance": 0.8,
    },
    "price_pragmatist": {
        "price": 1.8, "complexity": 1.2, "differentiation": 1.1, "evidence": 1.1,
        "legitimacy": 1.2, "privacy": 0.8, "social_proof": 1.0,
        "ethics": 0.6, "relevance": 1.1,
    },
    "health_evaluator": {
        "price": 1.0, "complexity": 0.9, "differentiation": 0.9, "evidence": 1.7,
        "legitimacy": 1.4, "privacy": 1.2, "social_proof": 0.7,
        "ethics": 1.1, "relevance": 1.0,
    },
    "brand_buyer": {
        "price": 0.5, "complexity": 0.8, "differentiation": 1.4, "evidence": 0.7,
        "legitimacy": 0.7, "privacy": 0.7, "social_proof": 1.1,
        "ethics": 0.6, "relevance": 1.3,
    },
    "social_follower": {
        "price": 1.2, "complexity": 1.3, "differentiation": 0.5, "evidence": 0.6,
        "legitimacy": 0.7, "privacy": 0.6, "social_proof": 1.8,
        "ethics": 0.5, "relevance": 0.9,
    },
    "convenience_user": {
        "price": 1.1, "complexity": 1.8, "differentiation": 0.7, "evidence": 0.8,
        "legitimacy": 0.7, "privacy": 0.9, "social_proof": 0.9,
        "ethics": 0.5, "relevance": 1.3,
    },
    "values_buyer": {
        "price": 0.7, "complexity": 0.8, "differentiation": 0.8, "evidence": 1.3,
        "legitimacy": 1.3, "privacy": 1.2, "social_proof": 0.5,
        "ethics": 1.8, "relevance": 0.9,
    },
}


@lru_cache(maxsize=1)
def build_resonance_matrix() -> dict[str, dict[str, float]]:
    """Build the full resonance matrix from hand-written values.

    Returns {archetype_id: {theme: resonance_multiplier}}.
    All values are clamped to [_RESONANCE_MIN, _RESONANCE_MAX].
    """
    matrix: dict[str, dict[str, float]] = {}

    for arch_id in ARCHETYPES:
        source = _RESONANCE_MATRIX.get(arch_id, {})
        row: dict[str, float] = {}
        for theme, value in source.items():
            row[theme] = round(
                max(_RESONANCE_MIN, min(_RESONANCE_MAX, value)), 2
            )
        matrix[arch_id] = row

    return matrix


def get_resonance(archetype_id: str | None, theme: str) -> float:
    """Get the resonance multiplier for an archetype-theme pair.

    Returns 1.0 (neutral) for unknown archetypes, unknown themes, or
    the "general" fallback theme.
    """
    if not archetype_id or theme == "general":
        return 1.0

    matrix = build_resonance_matrix()
    row = matrix.get(archetype_id)
    if not row:
        return 1.0

    return row.get(theme, 1.0)


def reload_resonance() -> None:
    """Clear the cached resonance matrix. Call after modifying archetypes.json
    or _MANUAL_RESONANCE values at runtime (e.g., during human calibration)."""
    build_resonance_matrix.cache_clear()


def get_primary_concern_theme(npc_objection_themes: list[str]) -> str:
    """Get the most prominent objection theme from an NPC's classified themes.

    Returns the first theme (highest priority from classification order),
    or "general" if the list is empty.
    """
    return npc_objection_themes[0] if npc_objection_themes else "general"
