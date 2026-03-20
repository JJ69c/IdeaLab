"""Competition context — classify alternatives and derive structured dimensions.

Converts the raw ``existing_alternatives`` string into a structured
CompetitionContext with typed, confidence-weighted alternatives and five
derived competition dimensions. Follows the asset_signals.py pattern:
frozen dataclass, deterministic derivation, per-NPC adjustment function.

Classification types (ordered by trust level):
- verified_named_competitor: matched in known_products.json (confidence 0.8-1.0)
- inferred_named_competitor: heuristic capitalized-name match (confidence 0.4)
- behavioral_alternative: non-product approach like "pen and paper" (confidence 0.7-0.9)
- generic_category: vague reference like "existing tools" (confidence 0.5)
- unknown: unrecognized text (confidence 0.2)

Only verified_named_competitor entries are referenced by name in LLM prompts.
Inferred names are treated as "unverified competitor mentions" — they contribute
weakly to dimensions but are never named to the LLM.

No LLM calls — all classification is heuristic / lookup-based.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Data loading (module-level cache, same pattern as evaluation.py)
# ---------------------------------------------------------------------------

_KNOWN_PRODUCTS: dict[str, dict] | None = None
_BEHAVIORAL_TERMS: set[str] | None = None
_DATA_PATH = Path(__file__).parent.parent.parent / "data" / "known_products.json"


def _load_known_products() -> tuple[dict[str, dict], set[str]]:
    global _KNOWN_PRODUCTS, _BEHAVIORAL_TERMS
    if _KNOWN_PRODUCTS is not None:
        return _KNOWN_PRODUCTS, _BEHAVIORAL_TERMS  # type: ignore[return-value]
    with open(_DATA_PATH) as f:
        data = json.load(f)
    _KNOWN_PRODUCTS = data.get("products", {})
    _BEHAVIORAL_TERMS = {t.lower().strip() for t in data.get("behavioral_terms", [])}
    return _KNOWN_PRODUCTS, _BEHAVIORAL_TERMS


# ---------------------------------------------------------------------------
# Category mapping: idea categories → product database categories
# ---------------------------------------------------------------------------

# Maps idea category strings to sets of related product-database categories.
# Used to compute category_fit: a competitor in the same functional space
# contributes more to competition intensity than one from a distant category.
_CATEGORY_OVERLAP: dict[str, set[str]] = {
    "saas": {"project_management", "productivity", "crm", "analytics", "support"},
    "productivity_tool": {"project_management", "productivity", "crm"},
    "ecommerce": {"ecommerce", "payments"},
    "marketplace": {"ecommerce", "marketplace"},
    "social_platform": {"social", "communication", "messaging"},
    "content_media": {"media", "social"},
    "mobile_app": {"messaging", "social", "health", "media"},
    "consumer_hardware": {"smart_home"},
    "iot_smart_home": {"smart_home"},
    "health_wellness": {"health"},
    "education": {"education"},
    "payments": {"payments", "finance"},
    "lending": {"finance"},
    "investing": {"finance"},
    "crypto_web3": {"finance"},
    "developer_tools": {"developer_tools"},
}


# ---------------------------------------------------------------------------
# Heuristic keyword sets
# ---------------------------------------------------------------------------

_BEHAVIORAL_KEYWORDS = frozenset({
    "manual", "spreadsheet", "spreadsheets", "email", "paper", "existing",
    "current", "traditional", "phone calls", "nothing", "pen", "notebook",
    "whiteboard", "sticky notes", "face-to-face", "in-person",
})


# ---------------------------------------------------------------------------
# ClassifiedAlternative
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClassifiedAlternative:
    """A single alternative classified by type and confidence.

    Classifications:
    - verified_named_competitor: found in known_products.json (high trust)
    - inferred_named_competitor: heuristic match, NOT verified (low trust)
    - behavioral_alternative: non-product approach (e.g. "pen and paper")
    - generic_category: vague reference (e.g. "existing tools")
    - unknown: unrecognized text
    """
    raw_text: str
    classification: str
    confidence: float       # 0.0-1.0
    known_product: bool     # True only for verified matches in known_products.json
    product_category: str   # category from known_products.json, or "" if unknown
    product_tier: str       # "major", "minor", or "" if unknown


# ---------------------------------------------------------------------------
# CompetitionContext
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CompetitionContext:
    """Structured competition analysis derived from raw alternatives string.

    Five dimensions, each 0.0-1.0, conceptually distinct:

    - direct_competition_intensity: How strong is the direct competitive threat?
      Considers verification confidence, category fit, and market presence.
      A single verified major competitor in the same category scores higher
      than three unverified guesses from distant categories.

    - incumbent_trust_pressure: How much trust have existing players built?
      Measures the credibility moat around incumbents. Users who already trust
      Trello or Notion need convincing that something new is worth the risk.
      Only verified major products contribute — inferred names don't build trust.

    - switching_cost_pressure: How hard is it to move away from current solutions?
      Combines two sources: entrenched behavioral habits (pen and paper,
      spreadsheets) AND incumbent tool lock-in (verified products with
      established workflows). Major verified tools add more switching cost
      than minor ones because deeper integration = harder to leave.

    - familiarity_of_solutions: How well-known is the solution space?
      Measures whether the PROBLEM SPACE already has recognized solutions
      (not whether specific competitors are strong). A space where "everyone
      knows there are apps for this" vs "nobody has heard of a tool for this."
      Driven by the breadth and recognition of alternatives, regardless of
      competitive strength.

    - saturation_pressure: How crowded is the market?
      Pure count of credible alternatives, weighted by confidence.
      More verified names = more crowded. Unknown junk barely counts.
      This is the "how many options are already out there" signal.
    """

    alternatives: tuple[ClassifiedAlternative, ...]

    direct_competition_intensity: float
    incumbent_trust_pressure: float
    switching_cost_pressure: float
    familiarity_of_solutions: float
    saturation_pressure: float

    @property
    def verified_names(self) -> list[str]:
        """Names safe to pass to LLM prompts — verified matches only."""
        return [
            a.raw_text for a in self.alternatives
            if a.classification == "verified_named_competitor"
        ]

    @property
    def behavioral_descriptions(self) -> list[str]:
        """Non-competitor alternatives for LLM context."""
        return [
            a.raw_text for a in self.alternatives
            if a.classification in ("behavioral_alternative", "generic_category")
        ]

    def to_dict(self) -> dict:
        return {
            "alternatives": [
                {
                    "raw_text": a.raw_text,
                    "classification": a.classification,
                    "confidence": round(a.confidence, 2),
                    "known_product": a.known_product,
                    "product_category": a.product_category,
                    "product_tier": a.product_tier,
                }
                for a in self.alternatives
            ],
            "direct_competition_intensity": round(self.direct_competition_intensity, 3),
            "incumbent_trust_pressure": round(self.incumbent_trust_pressure, 3),
            "switching_cost_pressure": round(self.switching_cost_pressure, 3),
            "familiarity_of_solutions": round(self.familiarity_of_solutions, 3),
            "saturation_pressure": round(self.saturation_pressure, 3),
            "verified_names": self.verified_names,
            "behavioral_descriptions": self.behavioral_descriptions,
        }


# ---------------------------------------------------------------------------
# Classification logic
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, round(v, 3)))


def _classify_token(
    token: str,
    products: dict[str, dict],
    behavioral_terms: set[str],
) -> ClassifiedAlternative:
    """Classify a single alternative token."""
    stripped = token.strip()
    if not stripped:
        return ClassifiedAlternative(stripped, "unknown", 0.0, False, "", "")

    normalized = stripped.lower().strip()

    # 1. Known-product lookup (case-insensitive) → verified_named_competitor
    if normalized in products:
        info = products[normalized]
        tier = info.get("tier", "minor")
        cat = info.get("category", "")
        confidence = 1.0 if tier == "major" else 0.8
        return ClassifiedAlternative(
            stripped, "verified_named_competitor", confidence, True, cat, tier,
        )

    # 2. Known behavioral terms from the JSON file
    if normalized in behavioral_terms:
        return ClassifiedAlternative(
            stripped, "behavioral_alternative", 0.9, False, "", "",
        )

    # 3. Heuristic — capitalized name pattern → inferred_named_competitor
    #    1-3 words, at least one capitalized, not ALL CAPS.
    #    Lower confidence (0.4) — this is a GUESS, not verified.
    words = stripped.split()
    if 1 <= len(words) <= 3:
        has_cap = any(w[0].isupper() for w in words if w)
        all_caps = all(w.isupper() for w in words if w)
        if has_cap and not all_caps:
            return ClassifiedAlternative(
                stripped, "inferred_named_competitor", 0.4, False, "", "",
            )

    # 4. Heuristic — behavioral keywords
    if any(kw in normalized for kw in _BEHAVIORAL_KEYWORDS):
        return ClassifiedAlternative(
            stripped, "generic_category", 0.5, False, "", "",
        )

    # 5. Heuristic — lowercase multi-word phrase (behavioral)
    if len(words) >= 2 and all(w.islower() for w in words):
        return ClassifiedAlternative(
            stripped, "behavioral_alternative", 0.4, False, "", "",
        )

    # 6. Default — unknown
    return ClassifiedAlternative(stripped, "unknown", 0.2, False, "", "")


def _category_fit(product_category: str, idea_category: str | None) -> float:
    """How much a competitor's category overlaps with the idea's category.

    Returns 1.0 for same-space, 0.5 for adjacent, 0.2 for unrelated.
    """
    if not idea_category or not product_category:
        return 0.5  # unknown → assume moderate relevance

    idea_cat = idea_category.lower().strip()
    related_cats = _CATEGORY_OVERLAP.get(idea_cat, set())

    if product_category in related_cats:
        return 1.0
    # Check reverse: does any mapping for the product's space include the idea's space?
    for cat_key, cat_set in _CATEGORY_OVERLAP.items():
        if product_category in cat_set and idea_cat == cat_key:
            return 1.0
    return 0.2  # distant category


def classify_alternatives(
    raw_string: str,
    idea_category: str | None = None,
) -> CompetitionContext:
    """Parse and classify alternatives from a raw string into CompetitionContext.

    Args:
        raw_string: Comma/semicolon/ampersand-separated alternatives string.
        idea_category: Optional category for category-fit scoring.

    Returns:
        CompetitionContext with classified alternatives and derived dimensions.
    """
    products, behavioral_terms = _load_known_products()

    # Pre-pass: protect multi-word known phrases that contain "and" before splitting.
    # e.g. "pen and paper" should not be split into "pen" + "paper".
    protected = raw_string
    _placeholder_map: dict[str, str] = {}
    phrases_with_and = [t for t in behavioral_terms if " and " in t]
    for phrase in sorted(phrases_with_and, key=len, reverse=True):
        if phrase in protected.lower():
            placeholder = f"__PROTECTED_{len(_placeholder_map)}__"
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            match = pattern.search(protected)
            if match:
                _placeholder_map[placeholder] = match.group(0)
                protected = pattern.sub(placeholder, protected, count=1)

    # Tokenize using same regex as product_profile.py
    tokens = re.split(r"[,;&/]|\band\b", protected)
    tokens = [t.strip() for t in tokens if t.strip()]

    # Restore protected phrases
    tokens = [_placeholder_map.get(t, t) for t in tokens]

    # Classify each token
    alternatives = tuple(_classify_token(t, products, behavioral_terms) for t in tokens)

    # --- Partition by type ---
    verified = [a for a in alternatives if a.classification == "verified_named_competitor"]
    inferred = [a for a in alternatives if a.classification == "inferred_named_competitor"]
    behavioral = [a for a in alternatives if a.classification in ("behavioral_alternative", "generic_category")]
    all_alts = list(alternatives)

    # -----------------------------------------------------------------------
    # direct_competition_intensity
    # -----------------------------------------------------------------------
    # Not just count-based. Each competitor contributes based on:
    #   confidence × category_fit × tier_weight
    # Then normalized with diminishing returns: 1 - 1/(1 + weighted_sum * k)
    intensity_score = 0.0
    tier_weight = {"major": 1.0, "minor": 0.6}
    for a in verified:
        fit = _category_fit(a.product_category, idea_category)
        tw = tier_weight.get(a.product_tier, 0.5)
        intensity_score += a.confidence * fit * tw
    # Inferred competitors contribute weakly (0.15 per inferred, regardless of name)
    intensity_score += len(inferred) * 0.15
    # Diminishing returns: first few competitors matter most
    direct_competition_intensity = _clamp(1.0 - 1.0 / (1.0 + intensity_score * 0.5))

    # -----------------------------------------------------------------------
    # incumbent_trust_pressure
    # -----------------------------------------------------------------------
    # Only verified products build trust moats. Major verified products
    # that users already trust create pressure: "why would I switch from X?"
    # Inferred names do NOT contribute — you can't trust what isn't verified.
    trust_score = 0.0
    for a in verified:
        if a.product_tier == "major":
            trust_score += 0.30  # major verified products carry serious trust
        else:
            trust_score += 0.10  # minor verified products carry some
    incumbent_trust_pressure = _clamp(trust_score)

    # -----------------------------------------------------------------------
    # switching_cost_pressure
    # -----------------------------------------------------------------------
    # Two sources of switching cost:
    # 1. Entrenched behavioral habits (pen and paper, spreadsheets, email)
    #    — these are hard to change because they're embedded in daily routines
    # 2. Incumbent tool lock-in (verified products with established workflows)
    #    — major tools have deeper integration (data, workflows, team habits)
    #    — minor tools have lighter lock-in
    # Inferred competitors contribute minimally (might not even exist).
    switching_score = 0.0
    for a in behavioral:
        switching_score += 0.15  # each behavioral habit adds friction
    for a in verified:
        if a.product_tier == "major":
            switching_score += 0.20  # deep integration lock-in
        else:
            switching_score += 0.10  # lighter lock-in
    switching_score += len(inferred) * 0.05  # weak signal
    switching_cost_pressure = _clamp(switching_score)

    # -----------------------------------------------------------------------
    # familiarity_of_solutions
    # -----------------------------------------------------------------------
    # How well-known is the SOLUTION SPACE (not specific competitors)?
    # A market where "everyone knows tools exist for this" vs a novel space.
    # Driven by breadth and recognition of alternatives:
    # - Many alternatives of any type → familiar space
    # - High-confidence alternatives → more recognized space
    # - Even behavioral alternatives contribute (people know the problem has solutions)
    if all_alts:
        # Breadth: how many distinct alternatives exist (diminishing returns)
        breadth = 1.0 - 1.0 / (1.0 + len(all_alts) * 0.3)
        # Recognition: average confidence across all alternatives
        recognition = sum(a.confidence for a in all_alts) / len(all_alts)
        familiarity_of_solutions = _clamp(breadth * 0.6 + recognition * 0.4)
    else:
        familiarity_of_solutions = 0.0

    # -----------------------------------------------------------------------
    # saturation_pressure
    # -----------------------------------------------------------------------
    # Pure market crowdedness: how many credible options exist?
    # Confidence-weighted count. Verified names count fully, inferred weakly,
    # unknown barely. Calibrated so 3 verified (conf ~1.0) → 0.75,
    # 6 verified → 1.0, 3 unknown (conf 0.2) → 0.15.
    confidence_sum = sum(a.confidence for a in all_alts)
    saturation_pressure = _clamp(confidence_sum * 0.25)

    return CompetitionContext(
        alternatives=alternatives,
        direct_competition_intensity=direct_competition_intensity,
        incumbent_trust_pressure=incumbent_trust_pressure,
        switching_cost_pressure=switching_cost_pressure,
        familiarity_of_solutions=familiarity_of_solutions,
        saturation_pressure=saturation_pressure,
    )


# ---------------------------------------------------------------------------
# Per-NPC adjustment
# ---------------------------------------------------------------------------

def compute_competition_adjustment(
    context: CompetitionContext,
    personality: dict,
    archetype_id: str | None = None,
) -> float:
    """Per-NPC competition adjustment based on competition context x personality.

    Returns a delta in [-0.08, +0.08]. Smaller range than asset_delta because
    competition context is a product-level signal refined per-persona.
    """
    delta = 0.0

    # Low-openness NPCs resist switching (inertia regardless of archetype)
    openness = personality.get("openness", 0.5)
    if openness < 0.35:
        delta -= context.switching_cost_pressure * 0.06

    # Social Followers: familiar solutions = social proof (positive)
    if archetype_id == "social_follower":
        delta += context.familiarity_of_solutions * 0.05

    # High-skepticism NPCs: incumbent trust pressure raises the bar
    skepticism = personality.get("skepticism", 0.5)
    delta -= context.incumbent_trust_pressure * skepticism * 0.04

    # Open people + low competition = exciting opportunity
    delta += (1.0 - context.direct_competition_intensity) * openness * 0.03

    return max(-0.08, min(0.08, round(delta, 4)))
