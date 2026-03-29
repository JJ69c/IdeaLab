# IdeaLab — Technical Design Document

## Architecture Overview

Monolithic Python backend with a React SPA frontend. All simulation logic runs
server-side. PostgreSQL for persistence (SQLite fallback for local dev). Claude API for NPC intelligence. Alembic for schema migrations.

```
Frontend (React/Vite) → REST API (FastAPI) → Simulation Engine → LLM Client (Claude)
                                            → PostgreSQL (persistence)
                                            → SSE (live event streaming)
```

## Backend Architecture

### Layers
1. **API Layer** (`api/`) — FastAPI routes, request/response schemas, JWT auth
2. **Simulation Layer** (`simulation/`) — V1 + V2 engines, NPC logic, propagation, adoption, reporting
3. **LLM Layer** (`llm/`) — Claude API client with retry, prompt templates (V1 + V2), response parsing
4. **Data Layer** (`db/`) — SQLAlchemy 2.0 models, Alembic migrations, dual-driver sessions

### Simulation Engines

Two engine versions coexist. The API dispatches based on the `simulation_version` field ("v1" or "v2", default "v1"). V2 imports from V1 — zero V1 files are modified.

#### V1 Engine (Deterministic — `engine.py`)

Discrete tick-based simulation with 7 phases per tick:

1. **Awareness** — NPCs become aware (stratified seed in tick 1, social spread after)
2. **Reaction** — Each newly-aware NPC evaluates via LLM (batched) + deterministic adjustment
3. **Discussion** — Interested NPC pairs have LLM-driven conversations (capped, with cooldown)
4. **Peer Influence** — Deterministic social influence shifts opinions (archetype-aware, exposure decay)
5. **Concern Propagation** — Low-interest NPCs dampen peers' enthusiasm (content-aware, 9 themes)
6. **Spread** — Interested NPCs probabilistically spread awareness to connections
7. **Adoption** — Deterministic per-NPC barrier model with per-archetype thresholds

#### V2 Engine (LLM-Primary — `engine_v2.py`)

Three-layer architecture: world building → NPC enrichment → tick loop.

**Prep Phase** (before tick loop):
- **Layer 1: World Construction** — Single LLM call builds a shared `WorldContext` (category description, key players, market maturity, typical price range, common complaints, switching barriers, social perception). Injected into every NPC interaction.
- **Layer 2: NPC Enrichment** — Batched LLM calls generate per-NPC `NpcCategoryContext` (current solution, satisfaction level, price anchor, category familiarity, openness to switch, pain points). Represents what each NPC already uses/feels before the product is introduced.

**Tick Loop** (same 7 phases, but Phase 2 differs):
- **Phase 2 (V2 Reaction)** — LLM generates `interest_score` directly (not a hint). Guardrail clamping: score is bounded to `baseline ± 0.30` (`GUARDRAIL_MAX_DEVIATION`). The LLM prompt includes world context + NPC category context for richer reasoning.
- **Phases 1, 3–7** — Identical to V1 (reused via imports)

### Dual-Driver Database

PostgreSQL uses two drivers:
- **asyncpg** — Async driver for FastAPI endpoints (via `AsyncSession`)
- **psycopg2** — Sync driver for background simulation threads (via `SyncSession`)

Both derived from a single `DATABASE_URL` in config. SQLite fallback uses `aiosqlite` / `sqlite`.

### LLM Cost Strategy

**V1:**
- **Batch reactions**: Group 5-8 NPCs into single LLM calls
- **Tiered models**: Haiku for NPC reactions, Sonnet for final report
- **Deterministic math**: Influence, spread, adoption, convergence — no LLM
- **Discussion cap**: Max 5 discussions per tick with per-pair cooldown
- **Discussion uplift cap** (0.40): Interest cannot rise more than 0.40 above NPC baseline via discussions. Prevents hype cascades.
- **Discussion downdraft cap** (0.50): Interest cannot fall more than 0.50 below baseline via discussions. Prevents skeptic death spirals. Asymmetric — skepticism flows slightly more freely than hype.
- **Retry with backoff**: 3 retries, 1-8s exponential delay for transient failures

**V2 (additional costs):**
- **World building**: 1 Sonnet call to construct WorldContext
- **NPC enrichment**: Batched Sonnet calls to generate per-NPC NpcCategoryContext
- **LLM-primary reactions**: Per-tick Haiku batches with world context + NPC context in prompt
- **Guardrail clamping** (±0.30): LLM interest_score bounded to baseline ± GUARDRAIL_MAX_DEVIATION
- **JSON truncation repair**: Detects max_tokens truncation and recovers partial JSON arrays

## Database Schema

Managed via Alembic migrations (auto-run on startup).

### users
- id (UUID, PK)
- username (unique, indexed)
- email (unique, indexed)
- hashed_password (bcrypt)
- created_at (timestamp)

### simulations
- id (UUID, PK)
- user_id (FK → users, nullable, indexed)
- idea_title, idea_description, idea_category, idea_metadata (JSON)
- config (JSON — tick count, population size, seed count)
- status (pending | running | completed | failed)
- report (JSON), summary (text), metrics (JSON)
- created_at, completed_at
- parent_simulation_id, root_simulation_id (variant lineage)
- variant_name, changed_fields (JSON)
- simulation_version (String(10), default "v1" — "v1" or "v2")
- error_message (Text, nullable — stores failure details for debugging)

### assets
- id (UUID, PK)
- filename, original_name, asset_type, url, note, file_path
- created_at

### simulation_events
- id (auto, PK)
- simulation_id (indexed), tick, npc_id, event_type, data (JSON)
- created_at

## API Design

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | /api/auth/register | Create account (returns JWT) |
| POST | /api/auth/login | Login (returns JWT) |

### Simulations
| Method | Path | Description |
|--------|------|-------------|
| POST | /api/simulations | Create + run a simulation (`simulation_version`: "v1" or "v2") |
| GET | /api/simulations | List simulations (filtered by user if auth'd) |
| GET | /api/simulations/{id} | Get simulation details |
| GET | /api/simulations/{id}/stream | SSE event stream (live or replay) |
| GET | /api/simulations/{id}/report | Get structured report |
| POST | /api/simulations/{id}/ask-npc | Chat with an NPC |
| GET | /api/simulations/{id}/variants | List variants |
| GET | /api/simulations/{id}/compare/{vid} | Compare parent vs variant (population match + seed lists) |
| POST | /api/simulations/{id}/compare/{vid}/explain | AI explanation of differences |
| DELETE | /api/simulations/{id} | Delete simulation and all its events |
| GET | /api/simulations/{id}/events | List persisted events (supports ?tick=N filter) |

### Assets
| Method | Path | Description |
|--------|------|-------------|
| POST | /api/assets/upload | Upload reference asset |

## Reliability

- **LLM retry** — Exponential backoff (3 retries, 1-8s) for API timeouts, rate limits, server errors
- **JSON parse retry** — Malformed LLM output retried up to 3 times
- **Discussion cooldown on failure** — Failed LLM calls still set pair cooldown
- **Simulation timeout** — Watchdog thread marks simulations as failed after 15 minutes
- **Event store cleanup** — Auto-purge completed events after 2 minutes
- **Input validation** — Cross-field: seed_count <= population_size

## Frontend Pages

1. **Dashboard** — Simulations grouped by parent/variant hierarchy. Variants stacked under their parent with compact metric cards. Each simulation displays a version badge (V1 or V2).
2. **Inject** — Structured form: idea details, market positioning, assets, strengths/risks. 3 quick-start templates (Notion AI, Oura Ring, Duolingo Max). Engine version selector (V1/V2, default V1). For variants: seed population toggle + version selector.
3. **Live Simulation** — Real-time social graph, metrics, event feed via SSE. V2 simulations show a prep phase indicator (world building / NPC enrichment) before the tick loop. Error overlay for failed simulations with specific error details.
4. **Report** — Full results with charts, segment analysis, NPC breakdown. Individual Reactions filterable by seed/all-aware and sortable with seeds-first or others-first. Seed NPCs visually marked.
5. **Compare** — Side-by-side variant comparison with metrics deltas, population verification (confirms same 30 NPCs), initial seed lists for both runs, archetype impact, AI explanation.

### Variant Options

Both Quick Variant (drawer) and Full Variant (Inject page) support:

**Engine version:**
- **V1 Deterministic** (default) — Fast, consistent, math-driven
- **V2 LLM-Primary** — Slower, costlier, more nuanced reactions

**Seed population:**
- **Fresh seeds** (default) — Re-selects the initial 8 exposed NPCs via stratified sampling. Adds realistic market variance but conflates seed selection noise with the product change.
- **Same seeds** — Locks the variant to use the exact same 8 NPCs that were exposed first in the parent. Isolates the product variable for a controlled A/B comparison.

## Deployment

MVP runs locally. Production path:
- Backend: Railway or Fly.io (single container)
- Frontend: Vercel or same container
- Database: PostgreSQL (managed instance for multi-user)
