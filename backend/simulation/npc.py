"""NPC state management during a simulation run."""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Social memory dataclasses — typed records of what an NPC has heard/experienced
# ---------------------------------------------------------------------------
# These replace untyped dict fields and enforce schema at write time.
# Each has a bounded max count on NpcState to prevent unbounded growth.

@dataclass(frozen=True, slots=True)
class PeerWarning:
    """A negative concern heard through concern propagation (Phase 4b).

    Source is always an NPC with low interest who shared negativity.
    Distinct from discussion memories — this is passive negative influence.
    """
    tick: int
    source_id: str
    source_name: str
    source_archetype: str  # UX-only: helps prompt injection, not used in math
    theme: str             # from resonance.classify_objection_theme
    content: str           # the objection text that triggered the concern
    delta: float           # the interest change applied to the target


@dataclass(frozen=True, slots=True)
class DiscussionMemory:
    """Record of a two-way discussion this NPC participated in (Phase 3)."""
    tick: int
    partner_id: str
    partner_name: str
    key_point: str     # most important thing said (from LLM)
    my_delta: float    # how this NPC's interest changed


@dataclass(frozen=True, slots=True)
class ImpactfulExchange:
    """The single most impactful social exchange this NPC experienced.

    Tracked as "what moved me most" — dominated by speaker's social power
    and trust, not argument quality. Named to reflect this honestly.
    """
    tick: int
    source_id: str
    source_name: str
    content: str       # the key_point or objection text
    delta: float       # the interest change (positive or negative)
    theme: str         # classified theme of the content


@dataclass(frozen=True, slots=True)
class ConcernEvent:
    """Structured output from compute_concern_influence.

    Preserves source attribution so engine.py can write PeerWarning
    memory on the target without propagation.py mutating NPC state.
    """
    target_id: str
    source_id: str
    source_name: str
    source_archetype: str
    raw_delta: float         # delta before resonance
    resonance: float         # archetype-theme resonance multiplier
    final_delta: float       # raw_delta * resonance (clamped)
    theme: str               # classified theme driving this concern
    objection_content: str   # source's top objection text (for memory)


# Max items stored per memory type on NpcState
MAX_PEER_WARNINGS = 5
MAX_DISCUSSION_MEMORIES = 3


# Ordered states for the UI legend and color mapping
STANCES = [
    "unaware", "aware",
    "opposed", "skeptical", "indifferent",
    "curious", "interested", "willing_to_try", "willing_to_pay",
]

# Interest score threshold for recommending the product to others.
# 0.68 = calibrated so strong products spread through discussions,
# high enough that mediocre products need uplift. (Calibrated 2026-03-23)
RECOMMEND_THRESHOLD = 0.68


def derive_stance(interest_score: float, would_pay: bool, aware: bool) -> str:
    """Deterministically map interest score → stance label.

    The interest_score is the single source of truth.
    would_pay (from LLM) unlocks the highest tier.

    Band widths are chosen so a single discussion delta (typically ±0.05–0.10)
    rarely flips more than one band.  The middle bands (curious, interested)
    are wider (~0.15) to absorb normal discussion variance.
    """
    if not aware:
        return "unaware"
    if interest_score >= 0.85 and would_pay:
        return "willing_to_pay"
    if interest_score >= 0.75:
        return "willing_to_try"
    if interest_score >= 0.60:
        return "interested"
    if interest_score >= 0.45:
        return "curious"
    if interest_score >= 0.30:
        return "indifferent"
    if interest_score >= 0.15:
        return "skeptical"
    return "opposed"


@dataclass
class NpcPersonality:
    openness: float = 0.5
    skepticism: float = 0.5
    tech_savviness: float = 0.5
    price_sensitivity: float = 0.5
    social_influence: float = 0.5
    conformity: float = 0.5
    novelty_seeking: float = 0.5

    @classmethod
    def from_dict(cls, d: dict) -> NpcPersonality:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class NpcState:
    """Runtime state of an NPC during a simulation. Separate from the static profile."""

    aware: bool = False
    awareness_tick: int | None = None
    awareness_source: str | None = None
    interest_score: float = 0.0
    stance: str = "unaware"
    reasoning: str = ""
    objections: list[str] = field(default_factory=list)
    would_pay: bool = False
    would_recommend: bool = False
    emotional_reaction: str = ""
    events: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)  # [{tick, stance, interest}]
    influence_sources: list[str] = field(default_factory=list)

    # Adoption (computed deterministically from interest, profile, personality)
    adopted: bool = False
    adoption_score: float = 0.0
    adoption_blockers: list[str] = field(default_factory=list)

    # Stage 3: Exposure tracking for archetype-aware influence
    exposure_count: int = 0  # ticks since becoming aware (incremented each tick)
    discussion_partners: set = field(default_factory=set)  # NPC IDs discussed with

    # Social memory (Phase 1 hybrid upgrades)
    peer_warnings: list[PeerWarning] = field(default_factory=list)
    discussion_memories: list[DiscussionMemory] = field(default_factory=list)
    most_impactful: ImpactfulExchange | None = None
    objection_themes: list[str] = field(default_factory=list)  # classified once during apply_reaction

    def increment_exposure(self):
        """Increment exposure counter for aware NPCs. Called once per tick."""
        if self.aware:
            self.exposure_count += 1

    def become_aware(self, tick: int, source: str):
        self.aware = True
        self.awareness_tick = tick
        self.awareness_source = source
        self.stance = "aware"
        self.events.append(
            {"tick": tick, "type": "became_aware", "source": source}
        )
        self._record_history(tick)

    def apply_reaction(self, reaction: dict, tick: int) -> str | None:
        """Apply LLM reaction. Returns new stance if it changed, else None."""
        self.interest_score = reaction.get("interest_score", 0.5)
        self.reasoning = reaction.get("reasoning", "")
        self.objections = reaction.get("objections", [])
        self.would_pay = reaction.get("would_pay", False)
        self.would_recommend = reaction.get("would_recommend", False)
        self.emotional_reaction = reaction.get("emotional_reaction", "meh")

        # Classify objection themes once (avoids re-classification every tick)
        from backend.simulation.resonance import classify_objection_themes
        self.objection_themes = classify_objection_themes(self.objections)

        old_stance = self.stance
        self.stance = derive_stance(self.interest_score, self.would_pay, self.aware)
        self.events.append(
            {"tick": tick, "type": "reacted", "stance": self.stance,
             "interest": self.interest_score}
        )
        self._record_history(tick)
        return self.stance if self.stance != old_stance else None

    def apply_discussion_outcome(
        self,
        delta: float,
        tick: int,
        partner_id: str,
        partner_name: str = "",
        key_point: str = "",
    ) -> str | None:
        """Apply discussion result. Returns new stance if it changed."""
        old_stance = self.stance
        self.interest_score = max(0.0, min(1.0, self.interest_score + delta))
        self.stance = derive_stance(self.interest_score, self.would_pay, self.aware)

        if partner_id not in self.influence_sources:
            self.influence_sources.append(partner_id)
        self.discussion_partners.add(partner_id)

        # Record discussion memory
        if key_point:
            self.record_discussion(tick, partner_id, partner_name, key_point, delta)

        self.events.append(
            {"tick": tick, "type": "discussed", "with": partner_id,
             "interest_delta": delta, "new_interest": self.interest_score}
        )
        self._record_history(tick)
        return self.stance if self.stance != old_stance else None

    def apply_influence(self, delta: float, tick: int) -> str | None:
        """Apply peer influence. Returns new stance if it changed."""
        if abs(delta) < 0.005:
            return None
        old_stance = self.stance
        self.interest_score = max(0.0, min(1.0, self.interest_score + delta))
        self.stance = derive_stance(self.interest_score, self.would_pay, self.aware)

        self.events.append(
            {"tick": tick, "type": "influenced",
             "delta": round(delta, 3), "new_interest": round(self.interest_score, 3)}
        )
        self._record_history(tick)
        return self.stance if self.stance != old_stance else None

    def record_peer_warning(self, warning: PeerWarning) -> None:
        """Record a concern heard through concern propagation."""
        self.peer_warnings.append(warning)
        if len(self.peer_warnings) > MAX_PEER_WARNINGS:
            self.peer_warnings = self.peer_warnings[-MAX_PEER_WARNINGS:]
        self._update_most_impactful(
            warning.tick, warning.source_id, warning.source_name,
            warning.content, warning.delta, warning.theme,
        )

    def record_discussion(
        self, tick: int, partner_id: str, partner_name: str,
        key_point: str, my_delta: float,
    ) -> None:
        """Record a discussion memory."""
        mem = DiscussionMemory(
            tick=tick, partner_id=partner_id, partner_name=partner_name,
            key_point=key_point, my_delta=my_delta,
        )
        self.discussion_memories.append(mem)
        if len(self.discussion_memories) > MAX_DISCUSSION_MEMORIES:
            self.discussion_memories = self.discussion_memories[-MAX_DISCUSSION_MEMORIES:]
        self._update_most_impactful(
            tick, partner_id, partner_name, key_point, my_delta,
            theme="",  # theme not classified here; discussion resonance is Phase 4
        )

    def _update_most_impactful(
        self, tick: int, source_id: str, source_name: str,
        content: str, delta: float, theme: str,
    ) -> None:
        """Update the most impactful exchange if this one is larger."""
        if self.most_impactful is None or abs(delta) > abs(self.most_impactful.delta):
            self.most_impactful = ImpactfulExchange(
                tick=tick, source_id=source_id, source_name=source_name,
                content=content, delta=delta, theme=theme,
            )

    def update_would_recommend(self):
        """Re-derive would_recommend from current interest_score.

        Removes the LLM gate on spread — NPCs who become more interested
        through discussions/influence can start recommending.
        Uses module-level RECOMMEND_THRESHOLD (default 0.68).
        """
        self.would_recommend = self.interest_score >= RECOMMEND_THRESHOLD

    def _record_history(self, tick: int):
        self.history.append({
            "tick": tick,
            "stance": self.stance,
            "interest": round(self.interest_score, 3),
        })

    def to_result_dict(self) -> dict:
        return {
            "aware": self.aware,
            "awareness_tick": self.awareness_tick,
            "interest_score": round(self.interest_score, 3),
            "stance": self.stance,
            "reasoning": self.reasoning,
            "objections": self.objections,
            "would_pay": self.would_pay,
            "would_recommend": self.would_recommend,
            "adopted": self.adopted,
            "adoption_score": round(self.adoption_score, 3),
            "adoption_blockers": self.adoption_blockers,
            "emotional_reaction": self.emotional_reaction,
            "history": self.history,
            "influence_sources": self.influence_sources,
            "exposure_count": self.exposure_count,
        }


@dataclass
class Npc:
    """Full NPC: static profile + runtime state."""

    id: str
    name: str
    age: int
    occupation: str
    income_level: str
    personality: NpcPersonality
    interests: list[str]
    values: list[str]
    pain_points: list[str]
    communication_style: str
    social_connections: list[str]
    trust_weights: dict[str, float]

    # Archetype tag (set by population generator, None for legacy JSON NPCs)
    archetype: str | None = None
    decision_style: str = ""

    # Runtime state (reset per simulation)
    state: NpcState = field(default_factory=NpcState)

    @classmethod
    def from_dict(cls, d: dict) -> Npc:
        return cls(
            id=d["id"],
            name=d["name"],
            age=d.get("age", 30),
            occupation=d.get("occupation", "unknown"),
            income_level=d.get("income_level", "middle"),
            personality=NpcPersonality.from_dict(d.get("personality", {})),
            interests=d.get("interests", []),
            values=d.get("values", []),
            pain_points=d.get("pain_points", []),
            communication_style=d.get("communication_style", "neutral"),
            social_connections=d.get("social_connections", []),
            trust_weights=d.get("trust_weights", {}),
            archetype=d.get("archetype"),
            decision_style=d.get("decision_style", ""),
        )

    def to_profile_dict(self) -> dict:
        """Return the static profile as a dict (for prompt formatting)."""
        return {
            "id": self.id,
            "name": self.name,
            "age": self.age,
            "occupation": self.occupation,
            "income_level": self.income_level,
            "personality": {
                "openness": self.personality.openness,
                "skepticism": self.personality.skepticism,
                "tech_savviness": self.personality.tech_savviness,
                "price_sensitivity": self.personality.price_sensitivity,
                "social_influence": self.personality.social_influence,
                "conformity": self.personality.conformity,
                "novelty_seeking": self.personality.novelty_seeking,
            },
            "interests": self.interests,
            "values": self.values,
            "pain_points": self.pain_points,
            "communication_style": self.communication_style,
            "archetype": self.archetype,
            "decision_style": self.decision_style,
        }

    def to_init_dict(self) -> dict:
        """Full NPC data for the simulation_start event (sent to frontend)."""
        d = self.to_profile_dict()
        d["social_connections"] = self.social_connections
        d["trust_weights"] = self.trust_weights
        d["stance"] = self.state.stance
        d["interest_score"] = self.state.interest_score
        d["aware"] = self.state.aware
        return d

    def reset_state(self):
        self.state = NpcState()
