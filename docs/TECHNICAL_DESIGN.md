# IdeaLab — Technical Design Document

## Architecture Overview

Monolithic Python backend with a React SPA frontend. All simulation logic runs
server-side. SQLite for persistence. Claude API for NPC intelligence.

```
Frontend (React/Vite) → REST API (FastAPI) → Simulation Engine → LLM Client (Claude)
                                            → SQLite (persistence)
```

## Backend Architecture

### Layers
1. **API Layer** (`api/`) — FastAPI routes, request/response schemas
2. **Simulation Layer** (`simulation/`) — Engine, NPC logic, propagation, reporting
3. **LLM Layer** (`llm/`) — Claude API client, prompt templates, response parsing
4. **Data Layer** (`db/`) — SQLAlchemy models, SQLite database

### Simulation Engine

The engine runs a discrete tick-based simulation with 5 phases per tick:

1. **Awareness** — NPCs become aware of the injected idea (seed in tick 1, social spread after)
2. **Reaction** — Each newly-aware NPC generates a reaction via LLM (batched, 5-8 per call)
3. **Discussion** — Interested NPCs discuss with connected NPCs (LLM, capped at 5/tick)
4. **Influence** — Deterministic social influence math shifts opinions
5. **Spread** — Interested NPCs probabilistically spread awareness to connections

### LLM Cost Strategy

- **Batch reactions**: Group 5-8 NPCs into single LLM calls
- **Tiered models**: Haiku for NPC reactions, Sonnet for final report
- **Deterministic math**: Influence and spread phases use formulas, not LLM
- **Discussion cap**: Max 5 discussions per tick
- **Structured output**: JSON responses minimize tokens

### Data Flow

```
User submits idea
  → Create Simulation record
  → Load NPC population + social graph
  → For each tick:
      → Run 5 phases
      → Log events
      → Update NPC memory states
  → Generate summary report (Sonnet)
  → Persist results
  → Return report to frontend
```

## Database Schema

### simulations
- id (UUID)
- idea_title (text)
- idea_description (text)
- idea_category (text)
- config (JSON — tick count, population size, seed count)
- status (pending | running | completed | failed)
- created_at (timestamp)
- completed_at (timestamp)

### simulation_results
- simulation_id (FK)
- report (JSON — full structured report)
- summary (text — LLM-generated narrative)
- metrics (JSON — aggregate scores)

### simulation_events
- id (auto)
- simulation_id (FK)
- tick (int)
- npc_id (text)
- event_type (text)
- data (JSON)
- created_at (timestamp)

## API Design

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/simulations | Create + run a simulation |
| GET | /api/simulations | List past simulations |
| GET | /api/simulations/{id} | Get simulation details |
| GET | /api/simulations/{id}/report | Get structured report |
| GET | /api/simulations/{id}/events | Get event log |
| GET | /api/npcs | List available NPC templates |
| GET | /api/health | Health check |

### Request: Create Simulation
```json
{
  "idea": {
    "title": "FocusFlow",
    "description": "An AI-powered focus timer that blocks distracting apps...",
    "category": "productivity_app",
    "target_audience": "remote workers",
    "price_point": "$4.99/month"
  },
  "config": {
    "num_ticks": 8,
    "population_size": 30,
    "seed_count": 5
  }
}
```

### Response: Simulation Report
```json
{
  "simulation_id": "...",
  "overall_score": 0.68,
  "adoption_likelihood": "moderate_high",
  "metrics": {
    "awareness_rate": 0.83,
    "interest_rate": 0.54,
    "rejection_rate": 0.18,
    "viral_coefficient": 0.42,
    "net_sentiment": 0.36
  },
  "segments": [...],
  "top_objections": [...],
  "recommendations": [...],
  "narrative_summary": "..."
}
```

## Simulation Tick Pseudocode

```python
def run_tick(world: WorldState, tick: int):
    # Phase 1: Awareness
    if tick == 1:
        seed_npcs = random.sample(world.npcs, world.config.seed_count)
        for npc in seed_npcs:
            npc.become_aware(tick, source="direct_exposure")
    else:
        # NPCs who spread last tick make their targets aware
        for event in world.pending_spreads:
            event.target_npc.become_aware(tick, source=event.source_npc)

    # Phase 2: Reaction (batched LLM)
    newly_aware = [n for n in world.npcs if n.awareness_tick == tick]
    reactions = llm.batch_react(newly_aware, world.idea)
    for npc, reaction in zip(newly_aware, reactions):
        npc.apply_reaction(reaction)
        world.log_event(tick, npc, "reacted", reaction)

    # Phase 3: Discussion (LLM, capped)
    discussion_pairs = select_discussion_pairs(world, max_pairs=5)
    for npc_a, npc_b in discussion_pairs:
        outcome = llm.simulate_discussion(npc_a, npc_b, world.idea)
        npc_a.update_from_discussion(outcome)
        npc_b.update_from_discussion(outcome)
        world.log_event(tick, npc_a, "discussed", outcome)

    # Phase 4: Influence (deterministic math)
    for npc in world.aware_npcs:
        peer_influence = calculate_peer_influence(npc, world.social_graph)
        npc.interest_score = clamp(npc.interest_score + peer_influence, 0, 1)

    # Phase 5: Spread
    world.pending_spreads = []
    for npc in world.interested_npcs:
        for target in npc.unaware_connections(world):
            prob = npc.interest_score * npc.social_influence * trust(npc, target)
            if random.random() < prob * 0.5:
                world.pending_spreads.append(SpreadEvent(npc, target))
```

## Frontend Pages

1. **Dashboard** — List past simulations, quick stats
2. **Inject** — Form to describe idea and configure simulation
3. **Report** — Full results view with charts and NPC breakdown

## Deployment

MVP runs locally. When ready to deploy:
- Backend: Railway or Fly.io (single container)
- Frontend: Vercel or same container
- Database: SQLite file (migrate to managed Postgres for multi-user)
