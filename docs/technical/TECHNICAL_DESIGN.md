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

### Competitor Enrichment

Before engine dispatch (both V1 and V2), if `existing_alternatives` is non-empty, the LLM verifies each alternative against real products and enriches with:
- Pricing, positioning, strengths, weaknesses
- Relative price, market presence, category match
- Verification status (real product vs. hallucination)

Enriched profiles are persisted on `idea_metadata.competitor_profiles` and included in the simulation report. Progress is streamed via SSE (`v2_progress` event with `competitor_research` phase).

### LLM Cost Strategy

**V1:**
- **Competitor enrichment**: 1 Sonnet call to verify/enrich listed alternatives (optional)
- **Batch reactions**: Group 5-8 NPCs into single LLM calls
- **Tiered models**: Haiku for NPC reactions, Sonnet for final report
- **Deterministic math**: Influence, spread, adoption, convergence — no LLM
- **Discussion cap**: Max 5 discussions per tick with per-pair cooldown
- **Discussion uplift cap** (0.40): Interest cannot rise more than 0.40 above NPC baseline via discussions. Prevents hype cascades.
- **Discussion downdraft cap** (0.50): Interest cannot fall more than 0.50 below baseline via discussions. Prevents skeptic death spirals. Asymmetric — skepticism flows slightly more freely than hype.
- **Retry with backoff**: 3 retries, 1-8s exponential delay for transient failures

**V2 (additional costs):**
- **Competitor enrichment**: Same as V1 (shared pre-processing step)
- **World building**: 1 Sonnet call to construct WorldContext
- **NPC enrichment**: Batched Sonnet calls to generate per-NPC NpcCategoryContext
- **LLM-primary reactions**: Per-tick Haiku batches with world context + NPC context in prompt
- **Guardrail clamping** (±0.30): LLM interest_score bounded to baseline ± GUARDRAIL_MAX_DEVIATION
- **JSON truncation repair**: Detects max_tokens truncation and recovers partial JSON arrays

**Business Plan (on-demand, both versions):**
- **1 Sonnet call** (report model, 6000 max tokens) to generate a 9-section plan from stored simulation data
- Uses `_call_json_v2` with truncation repair for robust JSON recovery
- Only aware NPCs are sent in the prompt to save tokens (unaware NPCs filtered out)
- `monetization_approach` from idea metadata flows into the business plan prompt
- **Persisted to database** — stored as a `business_plan` JSON column on `SimulationRecord` (Alembic migration 0005). Once generated, subsequent requests return the cached plan instantly without an LLM call.
- Not part of the simulation pipeline — generated only when the user requests it, avoiding unnecessary cost
- Prompt templates: `BUSINESS_PLAN_SYSTEM` / `BUSINESS_PLAN_USER` in `prompts.py`
- Data sources: simulation report (metrics, npc_results, analysis, adoption_breakdown, archetype_breakdown, convergence, competitor_profiles) plus idea metadata

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
- idea_title, idea_description, idea_category, idea_metadata (JSON — includes `monetization_approach`, V2-only)
- config (JSON — tick count, population size, seed count)
- status (pending | running | completed | failed)
- report (JSON), summary (text), metrics (JSON), business_plan (JSON, nullable — cached plan)
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
| GET | /api/simulations/{id}/business-plan | Return cached business plan (404 if not yet generated) |
| POST | /api/simulations/{id}/business-plan | Generate + persist a business plan; returns cached if already exists (on-demand, uses Sonnet) |
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

1. **Dashboard** — Simulations grouped by parent/variant hierarchy. Variants stacked under their parent with compact metric cards. Each simulation displays a version badge (V1 or V2). Time-based sorting (newest/oldest) with variant groups moving together.
2. **Inject** — Structured form: idea details, market positioning, monetization approach, assets, strengths/risks. 3 quick-start templates (Notion AI, Oura Ring, Duolingo Max). Engine version selector (V1/V2, default V1). `monetization_approach` is V2-only (ignored by V1's deterministic engine); describes how the product makes money (e.g. "30% commission on creator sales", "freemium with pro tier"). Defaults to "not specified". Flows into `InjectedIdea.to_dict()` and is consumed by V2's world-builder and reaction prompts. Included in variant change tracking (`_compute_changed_fields` / `_FIELD_LABELS`). For variants: seed population toggle + version selector + initial exposure (locked when same seeds). Launch validation blocks if population < initial exposure. Variant-of-variant shows "variant" badge on parent.
3. **Live Simulation** — Real-time social graph, metrics, event feed via SSE. V2 simulations show a prep phase with step indicators (competitor research → world building → NPC enrichment) and rotating flavor text before the tick loop. Error overlay for failed simulations with specific error details.
4. **Report** — Full results with charts, segment analysis, NPC breakdown. Individual Reactions filterable by seed/all-aware and sortable with seeds-first or others-first. Seed NPCs visually marked. Custom Variant button alongside Quick Variant and Full Variant.
5. **Business Plan** (`/business-plan/:id`) — On-demand consultant-grade business plan generated from simulation results. Pre-generation screen shows product context; user clicks to generate. Once generated, the plan is persisted to the database and loaded instantly on return visits (GET returns cached plan, POST generates only if not already cached). Dynamic loading animation displays 8 progress phases (reading data, analyzing signals, sizing market, mapping competition, modeling economics, crafting GTM, assessing risks, writing plan) with a progress bar, elapsed timer, and checklist. Displays 9 sections (Executive Summary, Market Opportunity with TAM/SAM/SOM, Customer Validation, Competitive Positioning, Business Model & Unit Economics, Go-to-Market Strategy, Risk Assessment, Financial Projections, Strategic Recommendations) with gradient cards and table of contents navigation. Accessible via "Business Plan" button on the Report page header.
6. **Compare** — Side-by-side variant comparison: config diffs (rounds, population, initial exposure with change highlighting), metrics deltas, population verification with aligned NPC rows (shared NPCs highlighted, unique NPCs sorted A-Z), archetype impact, AI explanation. Variant marked in header. Supports comparison against root or direct parent. Custom variants display a purple "Hand-picked seeds" badge.

### Variant Options

Quick Variant (drawer), Full Variant (Inject page), and Custom Variant (drawer) are available. Quick and Full support:

**Engine version:**
- **V1 Deterministic** (default) — Fast, consistent, math-driven
- **V2 LLM-Primary** — Slower, costlier, more nuanced reactions

**Seed population:**
- **Fresh seeds** (default) — Re-selects the initial exposed NPCs via stratified sampling. Adds realistic market variance but conflates seed selection noise with the product change. Initial exposure slider adjustable.
- **Same seeds** — Locks the variant to use the exact same NPCs that were exposed first in the parent. Initial exposure slider locked. Isolates the product variable for a controlled A/B comparison.

**Launch validation:** Population must be ≥ initial exposure. If violated, launch is blocked with a user-facing error (no silent auto-adjustment).

**Custom Variant:**
- User hand-picks population members and initial seeds via a two-tier NPC picker (`CustomVariantDrawer.tsx`)
- `CreateSimulationRequest` accepts `custom_seed_ids: list[str] | None` and `custom_population_ids: list[str] | None`
- Backend auto-adjusts `population_size` and `seed_count` in config to match the custom selections
- `changed_fields` includes `"custom_population"` and `"custom_seeds"` when used; `_build_changed_fields_detail` labels them "hand-picked" vs "auto-selected"
- Validation: population ≥ 10, seeds ≥ 1 and ≤ 15
- Compare page shows a purple "Hand-picked seeds" badge when variant used custom selection
- Engine version (V1/V2) and rounds are configurable

## Deployment

MVP runs locally. Production path:
- Backend: Railway or Fly.io (single container)
- Frontend: Vercel or same container
- Database: PostgreSQL (managed instance for multi-user)
