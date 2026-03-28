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
2. **Simulation Layer** (`simulation/`) — Engine, NPC logic, propagation, adoption, reporting
3. **LLM Layer** (`llm/`) — Claude API client with retry, prompt templates, response parsing
4. **Data Layer** (`db/`) — SQLAlchemy 2.0 models, Alembic migrations, dual-driver sessions

### Simulation Engine

The engine runs a discrete tick-based simulation with 7 phases per tick:

1. **Awareness** — NPCs become aware (stratified seed in tick 1, social spread after)
2. **Reaction** — Each newly-aware NPC evaluates via LLM (batched) + deterministic adjustment
3. **Discussion** — Interested NPC pairs have LLM-driven conversations (capped, with cooldown)
4. **Peer Influence** — Deterministic social influence shifts opinions (archetype-aware, exposure decay)
5. **Concern Propagation** — Low-interest NPCs dampen peers' enthusiasm (content-aware, 9 themes)
6. **Spread** — Interested NPCs probabilistically spread awareness to connections
7. **Adoption** — Deterministic per-NPC barrier model with per-archetype thresholds

### Dual-Driver Database

PostgreSQL uses two drivers:
- **asyncpg** — Async driver for FastAPI endpoints (via `AsyncSession`)
- **psycopg2** — Sync driver for background simulation threads (via `SyncSession`)

Both derived from a single `DATABASE_URL` in config. SQLite fallback uses `aiosqlite` / `sqlite`.

### LLM Cost Strategy

- **Batch reactions**: Group 5-8 NPCs into single LLM calls
- **Tiered models**: Haiku for NPC reactions, Sonnet for final report
- **Deterministic math**: Influence, spread, adoption, convergence — no LLM
- **Discussion cap**: Max 5 discussions per tick with per-pair cooldown
- **Discussion uplift cap** (0.40): Interest cannot rise more than 0.40 above NPC baseline via discussions. Prevents hype cascades.
- **Discussion downdraft cap** (0.50): Interest cannot fall more than 0.50 below baseline via discussions. Prevents skeptic death spirals. Asymmetric — skepticism flows slightly more freely than hype.
- **Retry with backoff**: 3 retries, 1-8s exponential delay for transient failures

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
| POST | /api/simulations | Create + run a simulation |
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

1. **Dashboard** — Simulations grouped by parent/variant hierarchy. Variants stacked under their parent with compact metric cards.
2. **Inject** — Structured form: idea details, market positioning, assets, strengths/risks. 3 quick-start templates (Notion AI, Oura Ring, Duolingo Max).
3. **Live Simulation** — Real-time social graph, metrics, event feed via SSE
4. **Report** — Full results with charts, segment analysis, NPC breakdown. Individual Reactions filterable by seed/all-aware and sortable with seeds-first or others-first. Seed NPCs visually marked.
5. **Compare** — Side-by-side variant comparison with metrics deltas, population verification (confirms same 30 NPCs), initial seed lists for both runs, archetype impact, AI explanation.

### Variant Seed Mode

When creating a variant, users choose between two seed strategies:
- **Fresh seeds** (default) — Re-selects the initial 8 exposed NPCs via stratified sampling. Adds realistic market variance but conflates seed selection noise with the product change.
- **Same seeds** — Locks the variant to use the exact same 8 NPCs that were exposed first in the parent. Isolates the product variable for a controlled A/B comparison.

## Deployment

MVP runs locally. Production path:
- Backend: Railway or Fly.io (single container)
- Frontend: Vercel or same container
- Database: PostgreSQL (managed instance for multi-user)
