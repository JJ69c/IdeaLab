"""NPC state management during a simulation run."""

from __future__ import annotations

from dataclasses import dataclass, field


# Ordered states for the UI legend and color mapping
STANCES = [
    "unaware", "aware",
    "opposed", "skeptical", "indifferent",
    "curious", "interested", "willing_to_try", "willing_to_pay",
]


def derive_stance(interest_score: float, would_pay: bool, aware: bool) -> str:
    """Deterministically map interest score → stance label.

    The interest_score is the single source of truth.
    would_pay (from LLM) unlocks the highest tier.
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

    # Stage 3: Exposure tracking for archetype-aware influence
    exposure_count: int = 0  # ticks since becoming aware (incremented each tick)
    discussion_partners: set = field(default_factory=set)  # NPC IDs discussed with

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

        old_stance = self.stance
        self.stance = derive_stance(self.interest_score, self.would_pay, self.aware)
        self.events.append(
            {"tick": tick, "type": "reacted", "stance": self.stance,
             "interest": self.interest_score}
        )
        self._record_history(tick)
        return self.stance if self.stance != old_stance else None

    def apply_discussion_outcome(
        self, delta: float, tick: int, partner_id: str
    ) -> str | None:
        """Apply discussion result. Returns new stance if it changed."""
        old_stance = self.stance
        self.interest_score = max(0.0, min(1.0, self.interest_score + delta))
        self.stance = derive_stance(self.interest_score, self.would_pay, self.aware)

        if partner_id not in self.influence_sources:
            self.influence_sources.append(partner_id)
        self.discussion_partners.add(partner_id)

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

    def update_would_recommend(self):
        """Re-derive would_recommend from current interest_score.

        Removes the LLM gate on spread — NPCs who become more interested
        through discussions/influence can start recommending.
        """
        self.would_recommend = self.interest_score >= 0.65

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
