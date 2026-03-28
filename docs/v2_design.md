# IdeaLab V2 Design Document

**Status:** Accepted
**Date:** 2026-03-28
**Authors:** Architecture review from V1 codebase analysis + lessons from first V2 implementation attempt

---

## Table of Contents

1. [Core Philosophy](#1-core-philosophy)
2. [Score Flow Comparison](#2-score-flow-comparison)
3. [Three-Layer Architecture](#3-three-layer-architecture)
4. [Data Models](#4-data-models)
5. [Engine V2 Specification](#5-engine-v2-specification)
6. [LLM Client V2 Methods](#6-llm-client-v2-methods)
7. [Prompt Templates](#7-prompt-templates)
8. [JSON Truncation Repair](#8-json-truncation-repair)
9. [V2 Progress Events and Frontend](#9-v2-progress-events-and-frontend)
10. [Population Reuse for Variants](#10-population-reuse-for-variants)
11. [Database Changes](#11-database-changes)
12. [API Route Changes](#12-api-route-changes)
13. [Frontend Changes](#13-frontend-changes)
14. [Error Handling Strategy](#14-error-handling-strategy)
15. [File Structure](#15-file-structure)
16. [Configuration](#16-configuration)
17. [V1 Isolation Contract](#17-v1-isolation-contract)
18. [Migration Checklist](#18-migration-checklist)

---

## 1. Core Philosophy

V1 uses deterministic scoring where the LLM has minimal influence -- outcomes are approximately 90% predetermined by math:

```
archetype_baseline (0.15-0.85)    from ProductProfile x archetype weights
+ individual_delta  (+-0.20)      from trait deviation x ProductProfile
+ asset_delta       (+-0.08)      from AssetSignals x traits
+ competition_delta (+-0.08)      from CompetitionContext x personality
+ llm_hint          (+-0.10)      LLM qualitative adjustment
= final interest_score (0-1)      clamped
```

The problem: NPCs do not know whether a product is real. They cannot distinguish Coca-Cola from an unknown launched beverage. The math-driven `product_profile.py` heuristics convert form fields (description length, whether a problem statement exists) into product quality signals. This means filling in more form fields mechanically produces higher scores.

**V2 flips this.** The LLM is the PRIMARY scorer. It generates `interest_score` (0.0 to 1.0) directly, using full world context -- what products already exist in this market, what people typically pay, what the common complaints are. Math provides guardrails only: clamping LLM scores that deviate too far from archetype baselines.

### Why This Matters

- NPCs become "people living in the real world" who already know about competing products
- A knife product gets evaluated against the knives people already own
- Price sensitivity is grounded in actual market price ranges, not abstract 0-1 floats
- The LLM can express genuine nuance: "This is a good product but I just bought one last month"
- Archetypes still constrain behavior -- a skeptic cannot suddenly become enthusiastic

### Tradeoffs Accepted

| Gain | Cost |
|------|------|
| Realistic, world-aware NPC reactions | Cost per simulation increases (~$0.50-1.50 vs ~$0.15) |
| Products evaluated against real competition | Reproducibility decreases slightly (mitigated by structured output) |
| No more "form field gaming" | 30-120 second prep phase before ticks start |
| Genuine LLM reasoning, not narration | More complex error handling needed |

---

## 2. Score Flow Comparison

### V1 Score Flow

```
InjectedIdea
    |
    v
build_product_profile()  -->  ProductProfile (8 dimensions, 0-1)
    |
    v
compute_archetype_baseline(profile, eval_def, category)  -->  baseline (0.15-0.85)
    +
compute_individual_delta(personality, profile)            -->  ind_delta (+-0.20)
    +
compute_asset_adjustment(signals, personality)            -->  asset_delta (+-0.08)
    +
compute_competition_adjustment(ctx, personality, arch)    -->  comp_delta (+-0.08)
    +
llm_client.batch_react() --> interest_adjustment          -->  llm_hint (+-0.10)
    =
final_score = clamp(0, 1, baseline + ind + asset + comp + hint)
```

### V2 Score Flow

```
InjectedIdea
    |
    v
Layer 1: llm_client.build_world_context(idea) --> WorldContext (structured)
    |
    v
Layer 2: llm_client.enrich_npcs(npcs, world_ctx, idea) --> NpcCategoryContext per NPC
    |
    v
Layer 3: llm_client.v2_batch_react(npcs, idea, world_ctx, npc_ctx) --> interest_score (0-1) per NPC
    |
    v
Guardrail: archetype_baseline = compute_archetype_baseline(profile, eval_def, category)
           if |llm_score - baseline| > GUARDRAIL_MAX_DEVIATION:
               final_score = clamp(llm_score, baseline - 0.30, baseline + 0.30)
           else:
               final_score = llm_score
    =
final_score (0-1)
```

### Guardrail Constant

```python
GUARDRAIL_MAX_DEVIATION = 0.30
```

This value is wide enough that the LLM has genuine room to express nuanced judgment (a baseline-0.40 archetype can score anywhere from 0.10 to 0.70), while preventing pathological cases where the LLM ignores archetype identity entirely.

---

## 3. Three-Layer Architecture

### Layer 1: World Construction (1 LLM call)

**Purpose:** Generate the shared reality that all NPCs already live in. This represents "what an average person in this market already knows" before the product is introduced.

**Timing:** Before tick 1. Single LLM call.

**Input:** The `InjectedIdea` (title, description, category, stage, price_point, existing_alternatives, etc.)

**Output:** A `WorldContext` dataclass (see Section 4).

**Key insight:** The world context is injected into every subsequent NPC interaction. This means an NPC evaluating a kitchen knife already knows that good knives cost $30-$150, that Victorinox and Wusthof are established players, and that most people replace knives every 5-10 years.

### Layer 2: NPC Enrichment (batched LLM calls)

**Purpose:** For each NPC, generate their pre-existing relationship with the product category. A 25-year-old barista and a 55-year-old executive have different current solutions, different satisfaction levels, and different price anchors -- even before they see the product.

**Timing:** After Layer 1, before tick 1. Batched LLM calls using `reaction_batch_size`.

**Input:** NPC profiles + WorldContext + InjectedIdea (category only, not the product itself)

**Output:** An `NpcCategoryContext` per NPC (see Section 4).

**Batching:** MUST be batched at `settings.reaction_batch_size` NPCs per call to avoid token overflow. Dynamic `max_tokens`: `max(1024, batch_size * 350)`.

**Graceful fallback:** If any enrichment batch fails, fill defaults for all NPCs in that batch.

### Layer 3: Product Injection + Tick Loop

**Purpose:** The product enters the world. NPCs react from their enriched life context. The tick loop runs with V2 reactions replacing V1's deterministic scoring.

**What changes from V1:**
- Phase 2 (Reaction): LLM generates `interest_score` directly; math guardrails clamp
- Phases 1, 3, 4, 4b, 5, 6: Unchanged, imported from V1 modules

**Dynamic `max_tokens` for reactions:** `max(2048, batch_size * 600)`.

---

## 4. Data Models

### 4.1 WorldContext

File: `backend/simulation/world_builder.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class WorldContext:
    """Structured market context generated by the LLM for a product category.

    Represents "what an average person living in this world already knows"
    about this product category. Injected into every NPC interaction.
    """

    category_description: str = ""
    # e.g., "Kitchen knives are everyday tools used for food preparation..."

    key_players: list[str] = field(default_factory=list)
    # e.g., ["Victorinox", "Wusthof", "Henckels", "Shun"]

    market_maturity: str = "mature"
    # "emerging" | "growing" | "mature" | "declining"

    typical_price_range: str = ""
    # e.g., "$20-$200 for consumer knives, $200+ for professional"

    common_purchase_triggers: list[str] = field(default_factory=list)
    # e.g., ["Moving to a new home", "Current knife is dull", "Gift purchase"]

    common_complaints: list[str] = field(default_factory=list)
    # e.g., ["Dulls quickly", "Handle uncomfortable", "Rust issues"]

    switching_barriers: list[str] = field(default_factory=list)
    # e.g., ["Already own a full set", "Emotional attachment to current knife"]

    trend_awareness: list[str] = field(default_factory=list)
    # e.g., ["Japanese-style knives trending", "Sustainability in materials"]

    social_perception: str = ""
    # e.g., "Premium knives are seen as a marker of serious cooking"

    trust_factors: list[str] = field(default_factory=list)
    # e.g., ["Brand reputation", "Professional endorsements", "Steel quality certifications"]

    def to_dict(self) -> dict:
        return {
            "category_description": self.category_description,
            "key_players": self.key_players,
            "market_maturity": self.market_maturity,
            "typical_price_range": self.typical_price_range,
            "common_purchase_triggers": self.common_purchase_triggers,
            "common_complaints": self.common_complaints,
            "switching_barriers": self.switching_barriers,
            "trend_awareness": self.trend_awareness,
            "social_perception": self.social_perception,
            "trust_factors": self.trust_factors,
        }

    @classmethod
    def from_dict(cls, d: dict) -> WorldContext:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def default(cls) -> WorldContext:
        """Minimal fallback when LLM world-building fails."""
        return cls(
            category_description="General consumer product category.",
            key_players=[],
            market_maturity="mature",
            typical_price_range="Varies",
            common_purchase_triggers=[],
            common_complaints=[],
            switching_barriers=[],
            trend_awareness=[],
            social_perception="No specific social perception data available.",
            trust_factors=[],
        )
```

### 4.2 NpcCategoryContext

File: `backend/simulation/world_builder.py` (same file)

```python
@dataclass
class NpcCategoryContext:
    """An individual NPC's pre-existing relationship with the product category.

    Generated by the LLM during Layer 2 enrichment. Represents what this
    specific person already uses, feels, and knows about this category
    BEFORE the product is introduced.
    """

    npc_id: str = ""

    current_solution: str = ""
    # e.g., "Owns a $40 Victorinox chef's knife, bought 3 years ago"

    satisfaction_level: str = "neutral"
    # "very_satisfied" | "satisfied" | "neutral" | "dissatisfied" | "very_dissatisfied"

    price_anchor: str = ""
    # e.g., "Spent $40 on current knife, considers $80+ expensive"

    category_familiarity: str = "moderate"
    # "expert" | "familiar" | "moderate" | "low" | "none"

    openness_to_switch: str = "moderate"
    # "very_open" | "open" | "moderate" | "resistant" | "very_resistant"

    personal_connection: str = ""
    # e.g., "Cooks daily for family, knife is important kitchen tool"
    # 1 short sentence max

    pain_points: list[str] = field(default_factory=list)
    # e.g., ["Current knife dulls quickly"]
    # 1-2 items max

    def to_dict(self) -> dict:
        return {
            "npc_id": self.npc_id,
            "current_solution": self.current_solution,
            "satisfaction_level": self.satisfaction_level,
            "price_anchor": self.price_anchor,
            "category_familiarity": self.category_familiarity,
            "openness_to_switch": self.openness_to_switch,
            "personal_connection": self.personal_connection,
            "pain_points": self.pain_points,
        }

    @classmethod
    def from_dict(cls, d: dict) -> NpcCategoryContext:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def default(cls, npc_id: str) -> NpcCategoryContext:
        """Fallback when LLM enrichment fails for this NPC."""
        return cls(
            npc_id=npc_id,
            current_solution="Uses a generic existing solution",
            satisfaction_level="neutral",
            price_anchor="Average market price",
            category_familiarity="moderate",
            openness_to_switch="moderate",
            personal_connection="No specific connection to this category",
            pain_points=[],
        )
```

### 4.3 WorldContext JSON Schema (LLM Output)

```json
{
  "category_description": "string (2-3 sentences)",
  "key_players": ["string", "..."],
  "market_maturity": "emerging | growing | mature | declining",
  "typical_price_range": "string (e.g., '$20-$200 for consumer, $200+ for pro')",
  "common_purchase_triggers": ["string", "..."],
  "common_complaints": ["string", "..."],
  "switching_barriers": ["string", "..."],
  "trend_awareness": ["string", "..."],
  "social_perception": "string (1-2 sentences)",
  "trust_factors": ["string", "..."]
}
```

### 4.4 NpcCategoryContext JSON Schema (LLM Output, Batched)

```json
[
  {
    "npc_id": "npc_001",
    "current_solution": "string (1 sentence)",
    "satisfaction_level": "very_satisfied | satisfied | neutral | dissatisfied | very_dissatisfied",
    "price_anchor": "string (1 sentence)",
    "category_familiarity": "expert | familiar | moderate | low | none",
    "openness_to_switch": "very_open | open | moderate | resistant | very_resistant",
    "personal_connection": "string (1 short sentence max)",
    "pain_points": ["string (under 15 words each)", "max 2 items"]
  }
]
```

### 4.5 V2 Reaction JSON Schema (LLM Output, Batched)

```json
[
  {
    "npc_id": "npc_001",
    "interest_score": 0.0 to 1.0,
    "reasoning": "string (2 sentences MAX)",
    "objections": ["string (under 15 words each)", "1-2 items max"],
    "would_pay": true or false,
    "would_recommend": true or false,
    "emotional_reaction": "excited | intrigued | meh | doubtful | annoyed"
  }
]
```

---

## 5. Engine V2 Specification

File: `backend/simulation/engine_v2.py`

### 5.1 Function Signatures

```python
"""V2 simulation engine -- world-aware, LLM-primary with math guardrails.

Layers 1-2 run as a prep phase before any ticks.
Layer 3 replaces V1's reaction phase; all other phases reuse V1 logic.
"""

from __future__ import annotations

import logging
from typing import Callable

from backend.config import settings
from backend.llm.client import llm_client
from backend.simulation.convergence import ConvergenceTracker
from backend.simulation.engine import (
    EventCallback,
    _build_edge_list,
    _run_discussion,
    _stratified_seed_selection,
    DISCUSSION_UPLIFT_CAP,
    _noop,
)
from backend.simulation.adoption import compute_world_adoptions
from backend.simulation.evaluation import (
    compute_archetype_baseline,
    get_archetype_evaluation,
)
from backend.simulation.npc import Npc, PeerWarning
from backend.simulation.population import generate_population
from backend.simulation.product_profile import build_product_profile
from backend.simulation.propagation import (
    calculate_peer_influence,
    compute_concern_influence,
    compute_spreads,
    select_discussion_pairs,
)
from backend.simulation.reporter import generate_report
from backend.simulation.world import InjectedIdea, SimConfig, WorldState, load_population
from backend.simulation.world_builder import NpcCategoryContext, WorldContext

logger = logging.getLogger(__name__)

# Guardrail: max deviation of LLM score from archetype baseline
GUARDRAIL_MAX_DEVIATION = 0.30


def run_simulation_v2(
    idea: InjectedIdea,
    config: SimConfig,
    emit: EventCallback | None = None,
    asset_signals: object | None = None,
    population_override: list[Npc] | None = None,
    npc_archetypes_override: dict[str, str] | None = None,
) -> dict:
    """Run a full V2 simulation with world construction, NPC enrichment, and tick loop.

    Args:
        idea: The injected idea to test.
        config: Simulation parameters.
        emit: Optional callback for SSE streaming.
        asset_signals: Optional structured signals from reference assets.
        population_override: Pre-generated NPC list (for variant reuse).
        npc_archetypes_override: Pre-generated archetype map (for variant reuse).

    Returns:
        The final report dict.
    """
    ...


def _run_v2_prep(
    world: WorldState,
    idea: InjectedIdea,
    emit: EventCallback,
) -> tuple[WorldContext, dict[str, NpcCategoryContext]]:
    """Execute Layers 1-2: world construction and NPC enrichment.

    Emits v2_progress events before each layer so the frontend shows progress.

    Returns:
        (world_context, npc_contexts) where npc_contexts maps npc_id -> NpcCategoryContext
    """
    ...


def _v2_batch_react(
    world: WorldState,
    npcs: list[Npc],
    tick: int,
    emit: EventCallback,
    world_context: WorldContext,
    npc_contexts: dict[str, NpcCategoryContext],
):
    """V2 reaction phase: LLM generates interest_score directly, math guardrails clamp.

    Score composition (LLM-primary):
        llm_score (0-1)  generated by LLM with full world + NPC context
        -> clamped to [baseline - 0.30, baseline + 0.30]
        = final interest_score (0-1)
    """
    ...


def _run_v2_tick(
    world: WorldState,
    tick: int,
    emit: EventCallback,
    world_context: WorldContext,
    npc_contexts: dict[str, NpcCategoryContext],
):
    """Execute one V2 simulation tick.

    Phase 1 (Awareness): same as V1
    Phase 2 (Reaction): V2 -- LLM-primary with guardrails
    Phase 3 (Discussion): same as V1 -- reuse _run_discussion from engine.py
    Phase 4 (Influence): same as V1 -- reuse calculate_peer_influence
    Phase 4b (Concern propagation): same as V1 -- reuse compute_concern_influence
    Phase 5 (Spread): same as V1 -- reuse compute_spreads
    Phase 6 (Adoption): same as V1 -- reuse compute_world_adoptions
    """
    ...
```

### 5.2 Detailed Implementation: run_simulation_v2

```python
def run_simulation_v2(
    idea: InjectedIdea,
    config: SimConfig,
    emit: EventCallback | None = None,
    asset_signals: object | None = None,
    population_override: list[Npc] | None = None,
    npc_archetypes_override: dict[str, str] | None = None,
) -> dict:
    emit = emit or _noop

    # --- Create world (reuse V1's create_world with population_override) ---
    from backend.simulation.engine import create_world
    world = create_world(
        idea, config,
        asset_signals=asset_signals,
        population_override=population_override,
        npc_archetypes_override=npc_archetypes_override,
    )
    tracker = ConvergenceTracker()

    # --- Layer 1 + Layer 2: V2 Prep Phase ---
    world_context, npc_contexts = _run_v2_prep(world, idea, emit)

    # --- Emit simulation_start (same as V1) ---
    edges = _build_edge_list(world)
    emit({
        "type": "simulation_start",
        "tick": 0,
        "data": {
            "npcs": [npc.to_init_dict() for npc in world.npcs.values()],
            "edges": edges,
            "idea": idea.to_dict(),
            "config": {"num_ticks": config.num_ticks, "population_size": len(world.npcs)},
            "product_profile": world.product_profile.to_dict() if world.product_profile else None,
            "asset_signals": world.asset_signals.to_dict() if world.asset_signals else None,
            "competition_context": world.competition_context.to_dict() if world.competition_context else None,
            "npc_archetypes": world.npc_archetypes,
            "world_context": world_context.to_dict(),
            "simulation_version": "v2",
        },
    })

    # --- Tick Loop ---
    for tick in range(1, config.num_ticks + 1):
        world.current_tick = tick
        emit({"type": "tick_start", "tick": tick, "data": {}})
        logger.info("=== V2 Tick %d / %d ===", tick, config.num_ticks)

        _run_v2_tick(world, tick, emit, world_context, npc_contexts)

        convergence = tracker.record_tick(
            tick, world.aware_npcs, npc_archetypes=world.npc_archetypes,
        )
        metrics = world.compute_metrics()
        emit({
            "type": "tick_end",
            "tick": tick,
            "data": {"metrics": metrics, "convergence": convergence.to_dict()},
        })

        if convergence.converged and tick >= 4:
            logger.info("V2 Simulation converged at tick %d", tick)

    logger.info("V2 Simulation complete. Generating report...")
    report = generate_report(world, convergence=tracker.to_report_dict())
    emit({"type": "simulation_complete", "tick": config.num_ticks, "data": {"report": report}})
    return report
```

### 5.3 Detailed Implementation: _run_v2_prep

```python
def _run_v2_prep(
    world: WorldState,
    idea: InjectedIdea,
    emit: EventCallback,
) -> tuple[WorldContext, dict[str, NpcCategoryContext]]:
    # --- Layer 1: World Construction ---
    emit({
        "type": "v2_progress",
        "tick": 0,
        "data": {
            "phase": "world_builder",
            "message": "Building world context...",
        },
    })

    try:
        world_context = llm_client.build_world_context(idea.to_dict())
    except Exception:
        logger.exception("V2 world builder failed, using defaults")
        world_context = WorldContext.default()

    emit({
        "type": "v2_progress",
        "tick": 0,
        "data": {
            "phase": "world_builder_complete",
            "message": f"World context ready: {world_context.market_maturity} market with {len(world_context.key_players)} key players",
        },
    })

    # --- Layer 2: NPC Enrichment ---
    emit({
        "type": "v2_progress",
        "tick": 0,
        "data": {
            "phase": "npc_enrichment",
            "message": f"Enriching {len(world.npcs)} NPCs with category context...",
        },
    })

    all_npcs = list(world.npcs.values())
    npc_contexts: dict[str, NpcCategoryContext] = {}
    batch_size = settings.reaction_batch_size

    for i in range(0, len(all_npcs), batch_size):
        batch = all_npcs[i : i + batch_size]
        profiles = [npc.to_profile_dict() for npc in batch]

        try:
            batch_contexts = llm_client.enrich_npcs(
                profiles, world_context.to_dict(), idea.to_dict(),
            )
            # Map results by npc_id
            for ctx_dict in batch_contexts:
                npc_id = ctx_dict.get("npc_id", "")
                npc_contexts[npc_id] = NpcCategoryContext.from_dict(ctx_dict)
        except Exception:
            logger.exception("V2 NPC enrichment failed for batch starting at %d", i)
            for npc in batch:
                npc_contexts[npc.id] = NpcCategoryContext.default(npc.id)

        emit({
            "type": "v2_progress",
            "tick": 0,
            "data": {
                "phase": "npc_enrichment",
                "message": f"Enriched {min(i + batch_size, len(all_npcs))}/{len(all_npcs)} NPCs...",
            },
        })

    # Fill defaults for any NPCs missed
    for npc in all_npcs:
        if npc.id not in npc_contexts:
            npc_contexts[npc.id] = NpcCategoryContext.default(npc.id)

    emit({
        "type": "v2_progress",
        "tick": 0,
        "data": {
            "phase": "npc_enrichment_complete",
            "message": "All NPCs enriched. Starting simulation...",
        },
    })

    return world_context, npc_contexts
```

### 5.4 Detailed Implementation: _v2_batch_react

```python
def _v2_batch_react(
    world: WorldState,
    npcs: list[Npc],
    tick: int,
    emit: EventCallback,
    world_context: WorldContext,
    npc_contexts: dict[str, NpcCategoryContext],
):
    batch_size = settings.reaction_batch_size
    idea_dict = world.idea.to_dict()
    profile = getattr(world, "product_profile", None)

    for i in range(0, len(npcs), batch_size):
        batch = npcs[i : i + batch_size]
        npc_profiles = [npc.to_profile_dict() for npc in batch]

        # Attach category context to each profile for the prompt
        enriched_profiles = []
        for npc_prof in npc_profiles:
            npc_id = npc_prof["id"]
            cat_ctx = npc_contexts.get(npc_id, NpcCategoryContext.default(npc_id))
            npc_prof["category_context"] = cat_ctx.to_dict()
            enriched_profiles.append(npc_prof)

        try:
            reactions = llm_client.v2_batch_react(
                enriched_profiles, idea_dict, world_context.to_dict(),
            )
        except Exception:
            logger.exception("V2 batch_react failed for batch starting at %d", i)
            # Fallback: use archetype baseline scores
            reactions = []
            for npc in batch:
                archetype_id = world.npc_archetypes.get(npc.id)
                eval_def = get_archetype_evaluation(archetype_id)
                idea_category = getattr(world.idea, "category", None)
                baseline = compute_archetype_baseline(profile, eval_def, category=idea_category) if profile else 0.5
                reactions.append({
                    "npc_id": npc.id,
                    "interest_score": baseline,
                    "reasoning": "Used archetype baseline (LLM call failed).",
                    "objections": [],
                    "would_pay": False,
                    "would_recommend": False,
                    "emotional_reaction": "meh",
                })

        reaction_map = {r["npc_id"]: r for r in reactions}

        for npc in batch:
            reaction = reaction_map.get(npc.id, {})

            # --- Get LLM's raw score ---
            llm_score = float(reaction.get("interest_score", 0.5))
            llm_score = max(0.0, min(1.0, llm_score))

            # --- Compute archetype baseline for guardrail ---
            archetype_id = world.npc_archetypes.get(npc.id)
            eval_def = get_archetype_evaluation(archetype_id)
            idea_category = getattr(world.idea, "category", None)
            baseline = compute_archetype_baseline(
                profile, eval_def, category=idea_category
            ) if profile else 0.5

            # --- Apply guardrail clamp ---
            floor = max(0.0, baseline - GUARDRAIL_MAX_DEVIATION)
            ceiling = min(1.0, baseline + GUARDRAIL_MAX_DEVIATION)
            final_score = max(floor, min(ceiling, llm_score))
            was_clamped = abs(final_score - llm_score) > 0.001

            if was_clamped:
                logger.info(
                    "V2 guardrail clamped NPC %s (%s): llm=%.3f baseline=%.3f -> final=%.3f",
                    npc.id, archetype_id or "?", llm_score, baseline, final_score,
                )

            reaction["interest_score"] = final_score

            logger.debug(
                "V2 NPC %s (%s): llm=%.3f baseline=%.3f final=%.3f%s",
                npc.id, archetype_id or "?",
                llm_score, baseline, final_score,
                " [CLAMPED]" if was_clamped else "",
            )

            # Cache baseline (used by discussion uplift cap and influence floor)
            if not hasattr(world, "_npc_baselines"):
                world._npc_baselines = {}
            world._npc_baselines[npc.id] = baseline

            new_stance = npc.state.apply_reaction(reaction, tick)

            emit({
                "type": "npc_reaction",
                "tick": tick,
                "data": {
                    "npc_id": npc.id,
                    "name": npc.name,
                    "stance": npc.state.stance,
                    "interest_score": round(npc.state.interest_score, 3),
                    "reasoning": npc.state.reasoning,
                    "objections": npc.state.objections,
                    "would_pay": npc.state.would_pay,
                    "emotional_reaction": npc.state.emotional_reaction,
                    "llm_raw_score": round(llm_score, 3),
                    "baseline": round(baseline, 3),
                    "was_clamped": was_clamped,
                },
            })

            if new_stance:
                emit({
                    "type": "npc_state_change",
                    "tick": tick,
                    "data": {
                        "npc_id": npc.id, "name": npc.name,
                        "new_stance": new_stance,
                        "interest_score": round(npc.state.interest_score, 3),
                        "reason": "initial_reaction",
                    },
                })

            world.log_event(tick, npc.id, "reacted", {
                "stance": npc.state.stance,
                "interest": npc.state.interest_score,
                "baseline": round(baseline, 3),
                "llm_raw": round(llm_score, 3),
            })
```

### 5.5 Detailed Implementation: _run_v2_tick

```python
def _run_v2_tick(
    world: WorldState,
    tick: int,
    emit: EventCallback,
    world_context: WorldContext,
    npc_contexts: dict[str, NpcCategoryContext],
):
    """Execute one V2 simulation tick. Identical to V1 except Phase 2."""
    # Phase 1 through 6 are identical to V1's _run_tick except:
    # - Phase 2 uses _v2_batch_react instead of _batch_react

    # --- Phase 1: Awareness (same as V1) ---
    if tick == 1:
        all_npcs = list(world.npcs.values())
        seed_count = min(world.config.seed_count, len(all_npcs))
        seeds = _stratified_seed_selection(
            all_npcs, seed_count, npc_archetypes=world.npc_archetypes
        )
        for npc in seeds:
            npc.state.become_aware(tick, source="direct_exposure")
            world.log_event(tick, npc.id, "became_aware", {"source": "direct_exposure"})
            emit({
                "type": "npc_aware",
                "tick": tick,
                "data": {"npc_id": npc.id, "name": npc.name, "source": "direct_exposure"},
            })
    else:
        for spread in world.pending_spreads:
            target = world.npcs.get(spread.target_id)
            if target and not target.state.aware:
                source_npc = world.npcs.get(spread.source_id)
                source_name = source_npc.name if source_npc else spread.source_id
                target.state.become_aware(tick, source=spread.source_id)
                world.log_event(tick, target.id, "became_aware", {"source": spread.source_id})
                emit({
                    "type": "npc_aware",
                    "tick": tick,
                    "data": {
                        "npc_id": target.id, "name": target.name,
                        "source": spread.source_id, "source_name": source_name,
                    },
                })
        world.pending_spreads = []

    # Exposure tracking
    for npc in world.aware_npcs:
        npc.state.increment_exposure()

    # --- Phase 2: V2 Reaction (LLM-primary) ---
    newly_aware = [n for n in world.npcs.values() if n.state.awareness_tick == tick]
    if newly_aware:
        _v2_batch_react(world, newly_aware, tick, emit, world_context, npc_contexts)

    # --- Phase 3-6: Reuse V1 logic unchanged ---
    # Phase 3: Discussion
    from backend.simulation.engine import _run_discussion
    pairs = select_discussion_pairs(world, max_pairs=settings.max_discussions_per_tick)
    for npc_a, npc_b in pairs:
        _run_discussion(world, npc_a, npc_b, tick, emit)

    # Phase 4: Peer Influence (same as V1's _run_tick, lines 299-313)
    for npc in world.aware_npcs:
        delta = calculate_peer_influence(npc, world)
        new_stance = npc.state.apply_influence(delta, tick)
        if new_stance:
            emit({
                "type": "npc_state_change",
                "tick": tick,
                "data": {
                    "npc_id": npc.id, "name": npc.name,
                    "new_stance": new_stance,
                    "interest_score": round(npc.state.interest_score, 3),
                    "reason": "peer_influence",
                },
            })

    # Phase 4b: Concern propagation (same as V1's _run_tick, lines 316-375)
    # [Copy concern propagation logic from engine.py _run_tick lines 316-375 verbatim]
    concern_events = compute_concern_influence(world)
    from collections import defaultdict
    target_concerns: dict[str, list] = defaultdict(list)
    for evt in concern_events:
        target_concerns[evt.target_id].append(evt)

    for target_id, events in target_concerns.items():
        target_npc = world.npcs.get(target_id)
        if not target_npc:
            continue
        total_delta = sum(e.final_delta for e in events)
        old_interest = target_npc.state.interest_score
        new_stance = target_npc.state.apply_influence(total_delta, tick)
        emit({
            "type": "concern_applied",
            "tick": tick,
            "data": {
                "npc_id": target_npc.id, "name": target_npc.name,
                "delta": round(total_delta, 4),
                "old_interest": round(old_interest, 3),
                "new_interest": round(target_npc.state.interest_score, 3),
                "sources": [
                    {
                        "source_name": e.source_name, "theme": e.theme,
                        "content": e.objection_content[:150],
                        "delta": round(e.final_delta, 4),
                    }
                    for e in events if e.objection_content
                ],
            },
        })
        if new_stance:
            emit({
                "type": "npc_state_change",
                "tick": tick,
                "data": {
                    "npc_id": target_npc.id, "name": target_npc.name,
                    "new_stance": new_stance,
                    "interest_score": round(target_npc.state.interest_score, 3),
                    "reason": "concern_influence",
                },
            })

    for evt in (e for evts in target_concerns.values() for e in evts):
        target_npc = world.npcs.get(evt.target_id)
        if target_npc and evt.objection_content:
            target_npc.state.record_peer_warning(PeerWarning(
                tick=tick, source_id=evt.source_id, source_name=evt.source_name,
                source_archetype=evt.source_archetype, theme=evt.theme,
                content=evt.objection_content, delta=evt.final_delta,
            ))

    # Re-derive would_recommend
    for npc in world.aware_npcs:
        npc.state.update_would_recommend()

    # Phase 5: Spread
    world.pending_spreads = compute_spreads(world)
    for spread in world.pending_spreads:
        source_npc = world.npcs.get(spread.source_id)
        target_npc = world.npcs.get(spread.target_id)
        emit({
            "type": "npc_spread",
            "tick": tick,
            "data": {
                "source_id": spread.source_id,
                "source_name": source_npc.name if source_npc else "",
                "target_id": spread.target_id,
                "target_name": target_npc.name if target_npc else "",
            },
        })
        world.log_event(tick, spread.source_id, "will_spread", {"target": spread.target_id})

    # Phase 6: Adoption
    compute_world_adoptions(world)
```

---

## 6. LLM Client V2 Methods

File: `backend/llm/client.py` (add methods to existing `LLMClient` class)

### 6.1 build_world_context

```python
def build_world_context(self, idea: dict) -> WorldContext:
    """Layer 1: Generate structured market context for the product category.

    Single LLM call. Uses the report_model for higher quality.
    """
    from backend.llm.prompts import V2_WORLD_BUILDER_SYSTEM, V2_WORLD_BUILDER_USER
    from backend.simulation.world_builder import WorldContext

    prompt = V2_WORLD_BUILDER_USER.format(
        idea_title=idea.get("title", ""),
        idea_description=idea.get("description", ""),
        idea_category=idea.get("category", "general"),
        idea_stage=idea.get("stage", "concept"),
        target_audience=idea.get("target_audience", "general public"),
        price_point=idea.get("price_point", "not specified"),
        existing_alternatives=idea.get("existing_alternatives", ""),
    )

    result = self._call_json(
        V2_WORLD_BUILDER_SYSTEM, prompt,
        model=settings.report_model,
        max_tokens=2048,
    )

    if not isinstance(result, dict):
        logger.warning("World builder returned non-dict: %s", type(result))
        return WorldContext.default()

    return WorldContext.from_dict(result)
```

### 6.2 enrich_npcs

```python
def enrich_npcs(
    self, npc_profiles: list[dict], world_context: dict, idea: dict,
) -> list[dict]:
    """Layer 2: Generate pre-existing category relationship for each NPC.

    Batched call. Dynamic max_tokens.
    """
    from backend.llm.prompts import (
        V2_NPC_ENRICHMENT_SYSTEM,
        V2_NPC_ENRICHMENT_USER,
        format_v2_persona_for_prompt,
    )

    personas_block = "\n---\n".join(
        format_v2_persona_for_prompt(npc) for npc in npc_profiles
    )

    # Format world context for prompt
    wc = world_context
    world_block = (
        f"Category: {wc.get('category_description', 'N/A')}\n"
        f"Key players: {', '.join(wc.get('key_players', []))}\n"
        f"Market maturity: {wc.get('market_maturity', 'mature')}\n"
        f"Typical prices: {wc.get('typical_price_range', 'N/A')}\n"
        f"Common complaints: {', '.join(wc.get('common_complaints', []))}\n"
        f"Trends: {', '.join(wc.get('trend_awareness', []))}"
    )

    prompt = V2_NPC_ENRICHMENT_USER.format(
        idea_category=idea.get("category", "general"),
        world_context_block=world_block,
        personas_block=personas_block,
    )

    max_tokens = max(1024, len(npc_profiles) * 350)

    result = self._call_json(
        V2_NPC_ENRICHMENT_SYSTEM, prompt,
        max_tokens=max_tokens,
    )

    if not isinstance(result, list):
        logger.warning("NPC enrichment returned non-list: %s", type(result))
        return []

    return result
```

### 6.3 v2_batch_react

```python
def v2_batch_react(
    self, enriched_profiles: list[dict], idea: dict, world_context: dict,
) -> list[dict]:
    """Layer 3: Get V2 reactions -- LLM generates interest_score directly.

    Each enriched_profile has a 'category_context' key from Layer 2.
    """
    from backend.llm.prompts import (
        V2_REACTION_SYSTEM,
        V2_REACTION_USER,
        format_v2_persona_for_prompt,
        build_extra_context,
    )

    personas_block = "\n---\n".join(
        format_v2_persona_for_prompt(npc) for npc in enriched_profiles
    )

    # Format world context summary
    wc = world_context
    world_summary = (
        f"Market: {wc.get('category_description', 'N/A')}\n"
        f"Key players: {', '.join(wc.get('key_players', []))}\n"
        f"Typical prices: {wc.get('typical_price_range', 'N/A')}\n"
        f"Social perception: {wc.get('social_perception', 'N/A')}\n"
        f"Trust factors: {', '.join(wc.get('trust_factors', []))}"
    )

    prompt = V2_REACTION_USER.format(
        idea_title=idea.get("title", ""),
        idea_description=idea.get("description", ""),
        idea_category=idea.get("category", "general"),
        idea_stage=idea.get("stage", "concept"),
        target_audience=idea.get("target_audience", "general public"),
        price_point=idea.get("price_point", "not specified"),
        extra_context=build_extra_context(idea),
        world_context_summary=world_summary,
        personas_block=personas_block,
    )

    max_tokens = max(2048, len(enriched_profiles) * 600)

    result = self._call_json(
        V2_REACTION_SYSTEM, prompt,
        max_tokens=max_tokens,
    )

    if not isinstance(result, list):
        logger.warning("V2 batch_react returned non-list: %s", type(result))
        return []

    return result
```

---

## 7. Prompt Templates

File: `backend/llm/prompts.py` (add V2 templates, do not modify V1 templates)

### 7.1 V2_WORLD_BUILDER_SYSTEM

```python
V2_WORLD_BUILDER_SYSTEM = """You are a market research analyst building a realistic world context for a product simulation.

Given a product idea, generate the shared market knowledge that an average person in this category already possesses. This is NOT about the product itself -- it is about the WORLD the product enters.

Think about what a normal consumer already knows:
- What brands exist in this space?
- What do people typically pay?
- What are the common frustrations?
- What are the barriers to switching from what they already use?

Be realistic and grounded. For well-known categories (e.g., kitchen knives, streaming services), use real brand names and real price ranges. For niche or new categories, describe the landscape honestly.

Rules:
- Lists should have 3-5 items each (not more)
- Keep descriptions concise (1-2 sentences max per field)
- market_maturity must be exactly one of: emerging, growing, mature, declining
- Output valid JSON only. No markdown, no explanation."""
```

### 7.2 V2_WORLD_BUILDER_USER

```python
V2_WORLD_BUILDER_USER = """## Product Entering This World

Title: {idea_title}
Description: {idea_description}
Category: {idea_category}
Stage: {idea_stage}
Target Audience: {target_audience}
Price Point: {price_point}
Existing Alternatives Mentioned: {existing_alternatives}

## Task

Generate the market context for the **{idea_category}** category. What does an average person already know about this space?

Return JSON:
{{
  "category_description": "2-3 sentence description of this product category from a consumer perspective",
  "key_players": ["3-5 well-known brands or products in this space"],
  "market_maturity": "emerging | growing | mature | declining",
  "typical_price_range": "what people typically pay in this category",
  "common_purchase_triggers": ["3-5 reasons people buy in this category"],
  "common_complaints": ["3-5 common frustrations with existing products"],
  "switching_barriers": ["3-5 reasons people stick with what they have"],
  "trend_awareness": ["2-4 current trends consumers might be aware of"],
  "social_perception": "1-2 sentences on how this category is perceived socially",
  "trust_factors": ["3-5 things that make consumers trust a product in this category"]
}}"""
```

### 7.3 V2_NPC_ENRICHMENT_SYSTEM

```python
V2_NPC_ENRICHMENT_SYSTEM = """You are enriching simulated consumer personas with their pre-existing relationship to a product category.

Each persona has a personality profile (traits 0-1) and demographic info. Based on who they are and the market context provided, generate what they ALREADY own/use in this category, how satisfied they are, and how open they are to switching.

A 25-year-old barista and a 55-year-old executive will have very different relationships with kitchen knives or productivity software.

Rules:
- Stay consistent with the persona's personality traits and income level
- personal_connection: 1 short sentence max
- pain_points: 1-2 items max, each under 15 words
- satisfaction_level must be exactly one of: very_satisfied, satisfied, neutral, dissatisfied, very_dissatisfied
- category_familiarity must be exactly one of: expert, familiar, moderate, low, none
- openness_to_switch must be exactly one of: very_open, open, moderate, resistant, very_resistant
- Be concise. This data enriches prompts -- verbosity wastes tokens.
- Output valid JSON array only. No markdown, no explanation."""
```

### 7.4 V2_NPC_ENRICHMENT_USER

```python
V2_NPC_ENRICHMENT_USER = """## Product Category
{idea_category}

## World Context
{world_context_block}

## Personas to Enrich

{personas_block}

## Output Format

Return a JSON array with one object per persona, in the same order:
[
  {{
    "npc_id": "the persona's id",
    "current_solution": "what they currently use in this category (1 sentence)",
    "satisfaction_level": "very_satisfied | satisfied | neutral | dissatisfied | very_dissatisfied",
    "price_anchor": "what they've paid or expect to pay (1 sentence)",
    "category_familiarity": "expert | familiar | moderate | low | none",
    "openness_to_switch": "very_open | open | moderate | resistant | very_resistant",
    "personal_connection": "how this category fits their life (1 short sentence max)",
    "pain_points": ["1-2 items max, each under 15 words"]
  }}
]"""
```

### 7.5 V2_REACTION_SYSTEM

```python
V2_REACTION_SYSTEM = """You are simulating how real people react to a new product.

Each persona has:
- A personality profile (traits 0-1)
- A pre-existing relationship with this product category (what they use now, satisfaction, price anchor)
- World context (what the market looks like)

You generate the interest_score (0.0 to 1.0) directly. This is the PRIMARY score -- not a hint.

## Score Calibration Guide

0.00-0.10: Actively opposed. "This is worse than what I have and I want nothing to do with it."
0.10-0.20: Very skeptical. "I see no reason to consider this."
0.20-0.35: Mildly negative / indifferent. "Meh, I have something that works."
0.35-0.50: Neutral with slight curiosity. "Interesting concept, but I'm not sold."
0.50-0.65: Genuinely interested. "This could actually solve a problem I have."
0.65-0.80: Strongly interested. "I want to try this. It addresses my needs well."
0.80-0.90: Very enthusiastic. "This is exactly what I've been looking for."
0.90-1.00: Extremely enthusiastic and ready to commit. Reserved for exceptional fit.

## Important Scoring Rules

- Most reactions for average products should cluster in 0.25-0.55
- Scores above 0.70 require STRONG justification (clear pain point solved, great price, high trust)
- Scores below 0.15 require STRONG justification (active harm, severe mismatch, ethical concern)
- A concept-stage product with no trust signals should rarely score above 0.60
- Reference the persona's ACTUAL current solution and price anchor
- A person satisfied with their current solution should score LOWER than someone dissatisfied
- High price sensitivity + expensive product = lower score (be specific about why)
- When verified competitors exist, compare the product to them specifically

Rules:
- Stay in character for each persona
- reasoning: 2 sentences MAX
- objections: 1-2 items max, each under 15 words
- Output valid JSON array only. No markdown, no explanation."""
```

### 7.6 V2_REACTION_USER

```python
V2_REACTION_USER = """## World Context
{world_context_summary}

## Product Being Introduced

Title: {idea_title}
Description: {idea_description}
Category: {idea_category}
Stage: {idea_stage}
Target Audience: {target_audience}
Price Point: {price_point}
{extra_context}

## Personas to React

{personas_block}

## Output Format

Return a JSON array with one object per persona, in the same order:
[
  {{
    "npc_id": "the persona's id",
    "interest_score": 0.0 to 1.0 (this is the PRIMARY score -- see calibration guide),
    "reasoning": "2 sentences MAX explaining WHY, referencing their current solution and personality",
    "objections": ["1-2 items max, each under 15 words"],
    "would_pay": true or false,
    "would_recommend": true or false,
    "emotional_reaction": "excited | intrigued | meh | doubtful | annoyed"
  }}
]"""
```

### 7.7 format_v2_persona_for_prompt

```python
def format_v2_persona_for_prompt(npc: dict) -> str:
    """Format a single NPC profile with category context for V2 prompts.

    Includes the category_context block when present (from Layer 2 enrichment).
    """
    personality = npc.get("personality", {})
    archetype = npc.get("archetype", "")
    decision_style = npc.get("decision_style", "")
    cat_ctx = npc.get("category_context", {})

    lines = [
        f"ID: {npc['id']}",
        f"Name: {npc['name']}, Age: {npc['age']}, Occupation: {npc['occupation']}",
        f"Income: {npc.get('income_level', 'middle')}",
    ]
    if archetype:
        lines.append(f"Archetype: {archetype}")
    if decision_style:
        lines.append(f"Decision style: {decision_style}")
    lines.extend([
        f"Personality: openness={personality.get('openness', 0.5)}, "
        f"skepticism={personality.get('skepticism', 0.5)}, "
        f"tech_savviness={personality.get('tech_savviness', 0.5)}, "
        f"price_sensitivity={personality.get('price_sensitivity', 0.5)}, "
        f"novelty_seeking={personality.get('novelty_seeking', 0.5)}",
        f"Interests: {', '.join(npc.get('interests', []))}",
        f"Values: {', '.join(npc.get('values', []))}",
        f"Pain points: {', '.join(npc.get('pain_points', []))}",
        f"Style: {npc.get('communication_style', 'neutral')}",
    ])

    # Category context from Layer 2 enrichment
    if cat_ctx:
        lines.append("--- Category Context ---")
        if cat_ctx.get("current_solution"):
            lines.append(f"Currently uses: {cat_ctx['current_solution']}")
        if cat_ctx.get("satisfaction_level"):
            lines.append(f"Satisfaction: {cat_ctx['satisfaction_level']}")
        if cat_ctx.get("price_anchor"):
            lines.append(f"Price anchor: {cat_ctx['price_anchor']}")
        if cat_ctx.get("category_familiarity"):
            lines.append(f"Familiarity: {cat_ctx['category_familiarity']}")
        if cat_ctx.get("openness_to_switch"):
            lines.append(f"Openness to switch: {cat_ctx['openness_to_switch']}")
        if cat_ctx.get("personal_connection"):
            lines.append(f"Connection: {cat_ctx['personal_connection']}")
        if cat_ctx.get("pain_points"):
            lines.append(f"Category pain points: {', '.join(cat_ctx['pain_points'])}")

    return "\n".join(lines)
```

---

## 8. JSON Truncation Repair

File: `backend/llm/client.py` (add as private method on `LLMClient`)

### Problem

When LLM output exceeds `max_tokens`, the response is truncated mid-JSON. For batched calls returning arrays of objects, this means the last object is incomplete. Without repair, the entire batch fails on `json.loads()`.

### Detection

The Anthropic API returns `stop_reason == "max_tokens"` when truncated. The `_call` method must be updated to return this signal, or `_call_json` must handle it.

### Implementation

```python
def _call_with_metadata(
    self, system: str, user: str, model: str | None = None, max_tokens: int = 4096
) -> tuple[str, str]:
    """Like _call but also returns stop_reason."""
    model = model or settings.reaction_model
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = response.content[0].text
            stop_reason = response.stop_reason  # "end_turn" | "max_tokens" | ...
            return text, stop_reason
        except (
            anthropic.APITimeoutError,
            anthropic.RateLimitError,
            anthropic.InternalServerError,
            anthropic.APIConnectionError,
        ) as exc:
            last_exc = exc
            delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
            logger.warning(
                "LLM call failed (attempt %d/%d, retrying in %.1fs): %s",
                attempt + 1, MAX_RETRIES, delay, exc,
            )
            time.sleep(delay)
    raise last_exc


def _repair_truncated_json(self, raw: str) -> dict | list:
    """Attempt to repair truncated JSON from max_tokens cutoff.

    Strategy 1: Use json.JSONDecoder.raw_decode() to find the longest
    valid JSON prefix. Works when truncation happens after at least one
    complete object in an array.

    Strategy 2: For arrays, extract complete objects one by one using
    raw_decode in a loop.
    """
    import json

    cleaned = _strip_markdown_fences(raw)

    # Strategy 1: raw_decode finds longest valid JSON prefix
    decoder = json.JSONDecoder()
    try:
        result, _ = decoder.raw_decode(cleaned)
        return result
    except json.JSONDecodeError:
        pass

    # Strategy 2: Extract complete array elements one by one
    if cleaned.startswith("["):
        objects = []
        # Remove the opening bracket
        remaining = cleaned[1:].strip()
        while remaining:
            remaining = remaining.lstrip(", \n\r\t")
            if remaining.startswith("]"):
                break
            if not remaining:
                break
            try:
                obj, end_idx = decoder.raw_decode(remaining)
                objects.append(obj)
                remaining = remaining[end_idx:].strip()
            except json.JSONDecodeError:
                break  # Hit the truncated part -- stop here

        if objects:
            logger.warning(
                "Repaired truncated JSON array: recovered %d of unknown total objects",
                len(objects),
            )
            return objects

    raise json.JSONDecodeError("Could not repair truncated JSON", raw, 0)


def _call_json_v2(
    self, system: str, user: str, model: str | None = None, max_tokens: int = 4096
) -> dict | list:
    """V2 JSON call with truncation detection and repair."""
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            raw, stop_reason = self._call_with_metadata(system, user, model, max_tokens)

            if stop_reason == "max_tokens":
                logger.warning(
                    "LLM response truncated (max_tokens=%d). Attempting repair...",
                    max_tokens,
                )
                return self._repair_truncated_json(raw)

            cleaned = _strip_markdown_fences(raw)
            return json.loads(cleaned)

        except json.JSONDecodeError as exc:
            last_exc = exc
            logger.warning(
                "JSON parse failed (attempt %d/%d): %s -- raw[:200]: %s",
                attempt + 1, MAX_RETRIES, exc, raw[:200] if raw else "",
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BASE_DELAY)

    raise last_exc
```

### Usage

All V2 LLM client methods (`build_world_context`, `enrich_npcs`, `v2_batch_react`) should use `_call_json_v2` instead of `_call_json`. V1 methods continue using `_call_json` unchanged.

---

## 9. V2 Progress Events and Frontend

### 9.1 The Problem

V2 has a 30-120 second prep phase (Layers 1+2) before any ticks start. Without progress events, the frontend shows "Waiting for simulation data..." with no feedback, making users think it is broken.

### 9.2 Event Format

```json
{
  "type": "v2_progress",
  "tick": 0,
  "data": {
    "phase": "world_builder | world_builder_complete | npc_enrichment | npc_enrichment_complete",
    "message": "Human-readable progress message"
  }
}
```

### 9.3 Event Sequence (V2 Simulation)

```
v2_progress  (phase: "world_builder", message: "Building world context...")
v2_progress  (phase: "world_builder_complete", message: "World context ready: mature market with 4 key players")
v2_progress  (phase: "npc_enrichment", message: "Enriching 30 NPCs with category context...")
v2_progress  (phase: "npc_enrichment", message: "Enriched 6/30 NPCs...")
v2_progress  (phase: "npc_enrichment", message: "Enriched 12/30 NPCs...")
v2_progress  (phase: "npc_enrichment", message: "Enriched 18/30 NPCs...")
v2_progress  (phase: "npc_enrichment", message: "Enriched 24/30 NPCs...")
v2_progress  (phase: "npc_enrichment", message: "Enriched 30/30 NPCs...")
v2_progress  (phase: "npc_enrichment_complete", message: "All NPCs enriched. Starting simulation...")
simulation_start  (tick: 0, ...)
tick_start        (tick: 1, ...)
npc_aware         (...)
npc_reaction      (...)
...
```

---

## 10. Population Reuse for Variants

### 10.1 The Problem

When creating a variant, V1 generates a completely random new population. This makes comparison meaningless -- different NPCs with different social graphs produce different results regardless of parameter changes.

### 10.2 Solution

Variants MUST reuse the parent simulation's NPC population. The population is loaded from the parent's `simulation_start` event in the database.

### 10.3 Implementation

#### 10.3.1 Modify create_world (V1's engine.py -- minimal change)

```python
def create_world(
    idea: InjectedIdea,
    config: SimConfig,
    preset: str = "balanced",
    asset_signals: AssetSignals | None = None,
    population_override: list[Npc] | None = None,
    npc_archetypes_override: dict[str, str] | None = None,
) -> WorldState:
    """Initialize a world with a population, injected idea, and product profile.

    When population_override is provided (variant reuse), skips generation
    and uses the provided NPCs directly.
    """
    if population_override is not None:
        npcs = population_override
        npc_archetypes = npc_archetypes_override or {}
        for npc in npcs:
            npc.reset_state()
    else:
        try:
            npcs, npc_archetypes = generate_population(
                size=config.population_size, preset=preset,
            )
        except Exception:
            logger.warning("Population generator failed, falling back to legacy JSON", exc_info=True)
            npcs = load_population(limit=config.population_size)
            npc_archetypes = {}
        for npc in npcs:
            npc.reset_state()

    # ... rest unchanged ...
```

#### 10.3.2 Load Parent Population (in simulation route)

```python
def _load_parent_population(
    db_session, parent_simulation_id: str
) -> tuple[list[Npc] | None, dict[str, str] | None]:
    """Load the NPC population from a parent simulation's simulation_start event.

    Returns (npcs, npc_archetypes) or (None, None) if not found.
    """
    from backend.simulation.npc import Npc

    evt = db_session.query(SimulationEvent).filter(
        SimulationEvent.simulation_id == parent_simulation_id,
        SimulationEvent.event_type == "simulation_start",
    ).first()

    if not evt:
        logger.warning("No simulation_start event found for parent %s", parent_simulation_id)
        return None, None

    data = evt.data.get("data", {})
    raw_npcs = data.get("npcs", [])
    npc_archetypes = data.get("npc_archetypes", {})

    npcs = []
    for raw in raw_npcs:
        npc = Npc.from_dict(raw)
        # Restore archetype and decision_style (from_dict does not set these by default)
        npc.archetype = raw.get("archetype")
        npc.decision_style = raw.get("decision_style", "")
        # Restore social connections and trust weights
        npc.social_connections = raw.get("social_connections", [])
        npc.trust_weights = raw.get("trust_weights", {})
        npcs.append(npc)

    logger.info("Loaded %d NPCs from parent simulation %s", len(npcs), parent_simulation_id)
    return npcs, npc_archetypes
```

#### 10.3.3 Fix Npc.from_dict to Restore Archetype

```python
# In backend/simulation/npc.py, update from_dict:
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
        archetype=d.get("archetype"),           # NEW
        decision_style=d.get("decision_style", ""),  # NEW
    )
```

---

## 11. Database Changes

### 11.1 SimulationRecord Changes

Add two columns to the `simulations` table:

```python
# In backend/db/models.py, add to SimulationRecord:

simulation_version: Mapped[str] = mapped_column(
    String(10), default="v1",
)  # "v1" | "v2"

error_message: Mapped[str | None] = mapped_column(
    Text, nullable=True,
)  # Human-readable error for frontend display
```

### 11.2 Alembic Migration

Create a new migration file:

```python
"""add simulation_version and error_message columns

Revision ID: [auto-generated]
Revises: [previous_revision]
Create Date: 2026-03-28
"""

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column(
        "simulations",
        sa.Column("simulation_version", sa.String(10), server_default="v1", nullable=False),
    )
    op.add_column(
        "simulations",
        sa.Column("error_message", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("simulations", "error_message")
    op.drop_column("simulations", "simulation_version")
```

---

## 12. API Route Changes

File: `backend/api/routes/simulation.py`

### 12.1 Request Schema Update

```python
# In backend/api/schemas/requests.py, add to CreateSimulationRequest:

simulation_version: str = Field(
    default="v1",
    description="Engine version to use: v1 (deterministic) or v2 (LLM-primary)",
    pattern="^(v1|v2)$",
)
```

### 12.2 Response Schema Update

```python
# In backend/api/schemas/responses.py:

# Add to SimulationSummary:
simulation_version: str = "v1"

# Add to SimulationDetail:
simulation_version: str = "v1"
error_message: str | None = None
```

### 12.3 Route Dispatch Logic

In `_run_simulation_thread`, dispatch based on `simulation_version`:

```python
def _run_simulation_thread(
    sim_id: str,
    idea: InjectedIdea,
    config: SimConfig,
    simulation_version: str = "v1",
    asset_file_paths: list[str] | None = None,
    asset_metadata: list[dict] | None = None,
    parent_simulation_id: str | None = None,
):
    db_session = SyncSession()

    def emit(event: dict):
        # ... same as current ...

    try:
        # Analyze reference assets (same for both versions)
        asset_signals = None
        if asset_file_paths:
            from backend.simulation.asset_signals import analyze_assets
            asset_signals = analyze_assets(
                asset_file_paths=asset_file_paths,
                asset_metadata=asset_metadata or [],
                idea=idea.to_dict(),
            )

        # Load parent population for variants
        population_override = None
        npc_archetypes_override = None
        if parent_simulation_id:
            population_override, npc_archetypes_override = _load_parent_population(
                db_session, parent_simulation_id,
            )

        # Dispatch to correct engine
        if simulation_version == "v2":
            from backend.simulation.engine_v2 import run_simulation_v2
            report = run_simulation_v2(
                idea, config, emit=emit,
                asset_signals=asset_signals,
                population_override=population_override,
                npc_archetypes_override=npc_archetypes_override,
            )
        else:
            report = run_simulation(
                idea, config, emit=emit,
                asset_signals=asset_signals,
                # V1 also gets population_override once engine.py is updated
            )

        # ... persist report (same as current) ...

    except Exception as exc:
        logger.exception("Simulation %s failed", sim_id)
        error_msg = str(exc)[:500]
        db_session.rollback()
        emit({"type": "error", "tick": 0, "data": {"message": error_msg}})
        db_session.commit()

        try:
            record = db_session.get(SimulationRecord, sim_id)
            if record:
                record.status = "failed"
                record.error_message = error_msg
                db_session.commit()
        except Exception:
            logger.warning("Failed to mark sim %s as failed", sim_id, exc_info=True)
    finally:
        db_session.close()
        event_store.mark_complete(sim_id)
        event_store.purge_stale()
```

---

## 13. Frontend Changes

### 13.1 types.ts

Add new fields to `SimulationState`:

```typescript
export interface SimulationState {
  // ... existing fields ...

  // V2 additions
  v2Phase: string | null           // "world_builder" | "npc_enrichment" | null
  v2PhaseMessage: string | null    // Human-readable progress message
  errorMessage: string | null      // Error message from failed simulation
  simulationVersion: string | null // "v1" | "v2"
}
```

Update `INITIAL_STATE` in `useSimulationStream.ts`:

```typescript
const INITIAL_STATE: SimulationState = {
  // ... existing fields ...
  v2Phase: null,
  v2PhaseMessage: null,
  errorMessage: null,
  simulationVersion: null,
}
```

### 13.2 useSimulationStream.ts -- New Reducer Cases

```typescript
case 'v2_progress': {
  return {
    ...state,
    v2Phase: d.phase as string,
    v2PhaseMessage: d.message as string,
    events: [...state.events, payload],
  }
}

case 'simulation_start': {
  // ... existing logic ...
  return {
    ...newState,
    simulationVersion: (d.simulation_version as string) ?? 'v1',
    v2Phase: null,       // Clear prep phase
    v2PhaseMessage: null,
  }
}

case 'error': {
  return {
    ...state,
    isRunning: false,
    errorMessage: (d.message as string) ?? 'Simulation failed',
    events: [...state.events, payload],
  }
}
```

### 13.3 TickProgress Component

Show V2 prep phase progress when `v2Phase` is set:

```typescript
// In TickProgress.tsx, before the tick progress bar:
if (v2Phase && !isRunning) {
  return (
    <div className="flex items-center gap-2">
      <div className="animate-spin w-4 h-4 border-2 border-primary border-t-transparent rounded-full" />
      <span className="text-sm text-on-surface-variant">{v2PhaseMessage}</span>
    </div>
  )
}
```

### 13.4 LiveSimulation -- Error Overlay

```typescript
// In LiveSimulation.tsx:
{state.errorMessage && (
  <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-50">
    <div className="bg-error-container text-on-error-container rounded-2xl p-6 max-w-md shadow-lg">
      <h3 className="font-semibold text-lg mb-2">Simulation Failed</h3>
      <p className="text-sm">{state.errorMessage}</p>
      <Link
        to="/dashboard"
        className="mt-4 inline-block text-sm text-primary hover:underline"
      >
        Return to Dashboard
      </Link>
    </div>
  </div>
)}
```

### 13.5 Inject Page -- Engine Version Selector

Add a toggle/dropdown on the Inject page between V1 and V2:

```typescript
// State
const [engineVersion, setEngineVersion] = useState<'v1' | 'v2'>('v1')

// UI (add near the simulation config section)
<div className="flex items-center gap-3">
  <label className="text-sm font-medium text-on-surface-variant">Engine</label>
  <div className="flex rounded-xl border border-outline-variant overflow-hidden">
    <button
      onClick={() => setEngineVersion('v1')}
      className={`px-4 py-1.5 text-xs font-medium transition-colors ${
        engineVersion === 'v1'
          ? 'bg-primary text-on-primary'
          : 'bg-surface text-on-surface-variant hover:bg-surface-variant'
      }`}
    >
      V1 Deterministic
    </button>
    <button
      onClick={() => setEngineVersion('v2')}
      className={`px-4 py-1.5 text-xs font-medium transition-colors ${
        engineVersion === 'v2'
          ? 'bg-primary text-on-primary'
          : 'bg-surface text-on-surface-variant hover:bg-surface-variant'
      }`}
    >
      V2 World-Aware
    </button>
  </div>
</div>

// Include in request body:
body: JSON.stringify({
  idea: { ... },
  config: { ... },
  simulation_version: engineVersion,
})
```

### 13.6 Dashboard -- Version Badge

Display a small badge on each simulation card:

```typescript
// In the simulation list card:
<span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
  sim.simulation_version === 'v2'
    ? 'bg-secondary-container text-on-secondary-container'
    : 'bg-surface-variant text-on-surface-variant'
}`}>
  {sim.simulation_version?.toUpperCase() ?? 'V1'}
</span>
```

---

## 14. Error Handling Strategy

Every LLM call in V2 has a try/except with graceful fallback. The simulation must never crash -- it must always produce a result, even if degraded.

### 14.1 Error Hierarchy

| Layer | LLM Call | Fallback | User Impact |
|-------|----------|----------|-------------|
| Layer 1 | `build_world_context` | `WorldContext.default()` | NPCs lack market context -- reactions are more generic |
| Layer 2 | `enrich_npcs` (per batch) | `NpcCategoryContext.default(npc_id)` for all NPCs in batch | NPCs use "neutral" category context -- less personalized |
| Layer 3 | `v2_batch_react` (per batch) | Archetype baseline scores with default reasoning | Scores are deterministic-only for that batch -- same as V1 |
| Layer 3 | JSON truncation | `_repair_truncated_json()` recovers partial results | Some NPCs in batch use fallback, rest have real reactions |

### 14.2 Error Surfacing

Errors are surfaced to the frontend via:

1. **error_message on SimulationRecord** -- persisted for dashboard display
2. **error SSE event** -- real-time for live viewers
3. **v2_progress events** -- include failure info when a layer falls back

### 14.3 Logging Requirements

Every fallback must log at WARNING level with:
- Which layer/batch failed
- The exception message
- How many NPCs were affected
- What fallback was used

---

## 15. File Structure

### New Files

```
backend/simulation/engine_v2.py       -- V2 engine (Layers 1-2 prep + tick loop)
backend/simulation/world_builder.py   -- WorldContext + NpcCategoryContext dataclasses + builder functions
alembic/versions/xxxx_add_v2_columns.py  -- Migration for simulation_version + error_message
```

### Modified Files

```
backend/llm/client.py                 -- Add V2 methods:
                                          build_world_context()
                                          enrich_npcs()
                                          v2_batch_react()
                                          _call_with_metadata()
                                          _repair_truncated_json()
                                          _call_json_v2()

backend/llm/prompts.py                -- Add V2 prompt templates:
                                          V2_WORLD_BUILDER_SYSTEM
                                          V2_WORLD_BUILDER_USER
                                          V2_NPC_ENRICHMENT_SYSTEM
                                          V2_NPC_ENRICHMENT_USER
                                          V2_REACTION_SYSTEM
                                          V2_REACTION_USER
                                          format_v2_persona_for_prompt()

backend/api/routes/simulation.py      -- Dispatch V2 engine, population_override,
                                          _load_parent_population(), pass simulation_version

backend/api/schemas/requests.py       -- simulation_version field on CreateSimulationRequest

backend/api/schemas/responses.py      -- simulation_version + error_message fields

backend/db/models.py                  -- simulation_version + error_message columns

backend/simulation/engine.py          -- Add population_override + npc_archetypes_override
                                          params to create_world() (minimal V1 change)

backend/simulation/npc.py             -- Fix from_dict() to restore archetype + decision_style

backend/config.py                     -- Add v2_world_builder_model setting (optional)

frontend/src/types.ts                 -- v2Phase, v2PhaseMessage, errorMessage,
                                          simulationVersion fields

frontend/src/hooks/useSimulationStream.ts -- v2_progress case in reducer,
                                              error case with errorMessage

frontend/src/components/TickProgress.tsx  -- V2 prep phase display

frontend/src/pages/LiveSimulation.tsx     -- Error overlay for failed simulations

frontend/src/pages/Inject.tsx             -- Engine version selector (v1/v2 toggle)

frontend/src/pages/Dashboard.tsx          -- Version badge display
(or equivalent simulation list component)
```

---

## 16. Configuration

### 16.1 New Settings (backend/config.py)

```python
# Add to Settings class:

# V2 engine
v2_world_builder_model: str = "claude-sonnet-4-6"  # Higher quality for world building
```

The V2 world builder uses `report_model` by default (currently `claude-sonnet-4-6`). NPC enrichment and V2 reactions use `reaction_model` (currently `claude-haiku-4-5-20251001`) for cost efficiency.

### 16.2 Existing Settings Used by V2

| Setting | Default | Used By |
|---------|---------|---------|
| `reaction_model` | `claude-haiku-4-5-20251001` | NPC enrichment, V2 reactions |
| `report_model` | `claude-sonnet-4-6` | World builder, final report |
| `reaction_batch_size` | 6 | NPC enrichment batching, V2 reaction batching |
| `max_discussions_per_tick` | 5 | Phase 3 discussion cap (unchanged) |

### 16.3 Token Budget Estimates

| Call | Batch Size | Estimated Input | max_tokens | Estimated Cost |
|------|-----------|-----------------|------------|----------------|
| World builder | 1 | ~800 tokens | 2048 | ~$0.01 |
| NPC enrichment | 6 | ~1200 tokens | max(1024, 6*350) = 2100 | ~$0.005 per batch |
| V2 reactions | 6 | ~2000 tokens | max(2048, 6*600) = 3600 | ~$0.008 per batch |

For a 30-NPC simulation: ~5 enrichment batches + ~5 reaction batches (tick 1) + spread reactions in later ticks.

**Estimated total V2 cost per simulation: $0.15 - $0.50** (depending on spread dynamics and discussion count).

---

## 17. V1 Isolation Contract

V2 MUST NOT modify any V1 logic. This is the fundamental safety guarantee.

### What V2 DOES NOT Touch

- `engine.py` logic within `_batch_react`, `_run_tick`, `_run_discussion` (these functions stay as-is)
- `evaluation.py` score computation logic (used by V2 as guardrail read-only)
- `propagation.py` influence, spread, and concern logic
- `adoption.py` adoption computation
- `convergence.py` convergence tracking
- `population.py` NPC generation
- `product_profile.py` ProductProfile computation (V2 still builds one for guardrails)
- `reporter.py` report generation
- V1 prompt templates in `prompts.py` (all V2 prompts are V2_ prefixed)
- V1 client methods in `client.py` (`batch_react`, `simulate_discussion`, etc.)

### What V2 DOES Modify (Minimal, Backward-Compatible)

1. **engine.py `create_world()`**: Add `population_override` and `npc_archetypes_override` optional params. When `None` (default), behavior is identical to current V1.

2. **npc.py `Npc.from_dict()`**: Add `archetype` and `decision_style` restoration from dict. These fields already exist on the class but were not being set from `from_dict`. This is a bug fix that benefits V1 too.

3. **engine.py `run_simulation()`**: Optionally accept and pass through `population_override` for V1 variant reuse (same benefit).

### What V2 IMPORTS from V1

```python
from backend.simulation.engine import (
    _build_edge_list,         # Graph edge construction
    _run_discussion,          # Phase 3: discussion (uses LLM, unchanged)
    _stratified_seed_selection,  # Phase 1: seed selection
    DISCUSSION_UPLIFT_CAP,    # Phase 3: discussion cap constant
    _noop,                    # Default emit callback
    EventCallback,            # Type alias
)
from backend.simulation.propagation import (
    calculate_peer_influence,    # Phase 4: deterministic influence
    compute_concern_influence,   # Phase 4b: concern propagation
    compute_spreads,             # Phase 5: spread computation
    select_discussion_pairs,     # Phase 3: pair selection
)
from backend.simulation.adoption import compute_world_adoptions  # Phase 6
from backend.simulation.evaluation import (
    compute_archetype_baseline,  # Guardrail computation
    get_archetype_evaluation,    # Archetype lookup
)
```

---

## 18. Migration Checklist

### Phase 1: Backend Foundation (no frontend changes)

- [ ] Create `backend/simulation/world_builder.py` with `WorldContext` and `NpcCategoryContext` dataclasses
- [ ] Add V2 prompt templates to `backend/llm/prompts.py` (V2_ prefixed)
- [ ] Add `format_v2_persona_for_prompt()` to `backend/llm/prompts.py`
- [ ] Add `_call_with_metadata()` and `_repair_truncated_json()` and `_call_json_v2()` to `backend/llm/client.py`
- [ ] Add `build_world_context()`, `enrich_npcs()`, `v2_batch_react()` to `backend/llm/client.py`
- [ ] Update `Npc.from_dict()` to restore `archetype` and `decision_style`
- [ ] Add `population_override` param to `create_world()` in `engine.py`
- [ ] Create `backend/simulation/engine_v2.py` with full V2 engine

### Phase 2: Database + API

- [ ] Add `simulation_version` and `error_message` columns to `SimulationRecord` in `models.py`
- [ ] Create Alembic migration for new columns
- [ ] Run migration
- [ ] Add `simulation_version` to `CreateSimulationRequest` in `requests.py`
- [ ] Add `simulation_version` and `error_message` to response schemas
- [ ] Update `_run_simulation_thread` to dispatch V2 and handle population reuse
- [ ] Add `_load_parent_population()` to simulation route
- [ ] Update `create_simulation` to pass `simulation_version` through

### Phase 3: Frontend

- [ ] Add V2 fields to `types.ts` (`v2Phase`, `v2PhaseMessage`, `errorMessage`, `simulationVersion`)
- [ ] Add `v2_progress` case to `useSimulationStream.ts` reducer
- [ ] Update `simulation_start` case to extract `simulationVersion`
- [ ] Update `error` case to extract `errorMessage`
- [ ] Add V2 prep phase display to `TickProgress`
- [ ] Add error overlay to `LiveSimulation`
- [ ] Add engine version selector to `Inject` page
- [ ] Add version badge to Dashboard simulation list
- [ ] Update `SimulationGraph` and other components to accept v2Phase props if needed

### Phase 4: Testing + Validation

- [ ] Test V1 simulation still works identically (regression)
- [ ] Test V2 with a well-known product category (kitchen knives, smartphones)
- [ ] Test V2 with a niche/novel category (AI-powered pet translator)
- [ ] Test V2 with all LLM calls failing (verify graceful fallback chain)
- [ ] Test JSON truncation repair with artificially low max_tokens
- [ ] Test variant creation with population reuse (same NPCs, different parameters)
- [ ] Test V2 progress events render correctly on frontend
- [ ] Test error overlay appears on simulation failure
- [ ] Verify V2 guardrail clamping works (check logs for "[CLAMPED]" entries)
- [ ] Compare V1 vs V2 results for the same idea to validate meaningful differences

---

## Appendix A: Data Flow Diagram

```
                                    CREATE SIMULATION
                                          |
                                          v
                                  simulation_version?
                                    /           \
                                  v1              v2
                                  |               |
                                  v               v
                          V1: engine.py     V2: engine_v2.py
                          run_simulation()  run_simulation_v2()
                                  |               |
                                  |         +-----+-----+
                                  |         |           |
                                  |    Layer 1:    Layer 2:
                                  |    World       NPC
                                  |    Builder     Enrichment
                                  |    (1 call)    (N/batch_size calls)
                                  |         |           |
                                  |         +-----+-----+
                                  |               |
                                  v               v
                          create_world()    create_world()
                          (population       (population_override
                           generated)        from parent OR generated)
                                  |               |
                                  v               v
                          +----- Tick Loop ------+
                          |                       |
                    Phase 1: Awareness      Phase 1: Awareness
                    (same)                  (same)
                          |                       |
                    Phase 2: V1 React       Phase 2: V2 React
                    _batch_react()          _v2_batch_react()
                    (deterministic +        (LLM score + guardrail)
                     bounded hint)                |
                          |                       |
                    Phase 3-6: Same logic for both versions
                    (Discussion, Influence, Concern, Spread, Adoption)
                          |                       |
                          v                       v
                      Report Generation (same for both)
```

## Appendix B: Guardrail Examples

### Example 1: Normal Case (No Clamping)

```
Archetype: price_pragmatist
Product: $30/mo productivity SaaS
Archetype baseline: 0.42
LLM score: 0.35
|0.35 - 0.42| = 0.07 < 0.30
Final score: 0.35 (LLM score used directly)
```

### Example 2: Slight Clamping

```
Archetype: trend_adopter
Product: AI pet translator (concept stage)
Archetype baseline: 0.52
LLM score: 0.88 (LLM too enthusiastic)
|0.88 - 0.52| = 0.36 > 0.30
Ceiling: 0.52 + 0.30 = 0.82
Final score: 0.82 (clamped down from 0.88)
```

### Example 3: Strong Clamping

```
Archetype: analytical_skeptic
Product: Crypto dating app (concept stage)
Archetype baseline: 0.22
LLM score: 0.65 (LLM ignoring skepticism)
|0.65 - 0.22| = 0.43 > 0.30
Ceiling: 0.22 + 0.30 = 0.52
Final score: 0.52 (clamped significantly)
```

### Example 4: Negative Clamping

```
Archetype: health_evaluator
Product: Organic supplement subscription
Archetype baseline: 0.68
LLM score: 0.30 (LLM too negative for health-focused archetype)
|0.30 - 0.68| = 0.38 > 0.30
Floor: 0.68 - 0.30 = 0.38
Final score: 0.38 (clamped up from 0.30)
```
