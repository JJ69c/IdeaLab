# IdeaLab

> **Educational / Experimental Project** — Built as a learning exercise exploring AI agent simulation, full-stack architecture, and LLM integration. Not intended for production use or commercial decision-making.

A synthetic population idea-testing engine. Inject a product idea into a simulated society of 30 AI-driven NPCs across 8 behaviorally distinct archetypes. The engine runs a tick-based simulation where NPCs evaluate the product, discuss it with peers, spread awareness through social connections, and ultimately adopt or reject it. The output is a structured insight report covering adoption likelihood, objections, viral potential, and segment analysis.

## How It Works

```
You describe an idea
  -> Engine builds a product profile (8 normalized dimensions)
  -> Optional: LLM vision analyzes uploaded reference assets (7 perception signals)
  -> Optional: Engine classifies listed alternatives into competition context (5 dimensions)
  -> Tick loop runs (default 8 rounds):
      Phase 1: Awareness (stratified seed selection, then social spread)
      Phase 2: Reaction (deterministic baseline + bounded LLM hint per NPC)
      Phase 3: Discussion (LLM-driven pair conversations, capped)
      Phase 4: Peer Influence (deterministic, archetype-aware, with exposure decay)
      Phase 4b: Concern Propagation (negative social spread from skeptical NPCs)
      Phase 5: Spread (probabilistic word-of-mouth)
      Phase 6: Adoption (deterministic per-NPC barrier model)
  -> Convergence tracking classifies outcome
  -> LLM generates narrative report
  -> Results streamed via SSE, persisted to PostgreSQL
```

### Evaluation Pipeline

Every NPC's interest score is a sum of deterministic components plus a small LLM hint:

```
final_score = archetype_baseline (0.15-0.85)   deterministic: product profile x archetype weights
            + individual_delta   (+-0.20)       deterministic: trait deviation x product signals
            + asset_delta        (+-0.08)       deterministic: asset signals x personality
            + competition_delta  (+-0.08)       deterministic: competition context x personality
            + llm_hint           (+-0.10)       LLM qualitative reasoning (bounded)
```

The deterministic components drive ~90% of outcomes. The LLM provides bounded qualitative color — it cannot override product quality signals.

### 8 NPC Archetypes

| Archetype | Core Driver | Key Behavior |
|-----------|-------------|--------------|
| Analytical Skeptic | Evidence, risk assessment | Highest source credibility (1.3x), resistance floor, demands proof |
| Trend-Driven Early Adopter | Novelty, being first | Novelty weight 0.30, lowest adoption threshold |
| Price-Sensitive Pragmatist | Cost/benefit | Price friction weight -0.35 (strongest gate) |
| Health-Conscious Evaluator | Safety, clinical evidence | Trust barrier weight -0.30, resistance floor |
| Brand-Sensitive Buyer | Identity, aesthetics | Premium pricing = quality signal, not cost |
| Social-Proof Follower | Peer behavior | Highest susceptibility (1.30), increasing social proof returns |
| Convenience-First User | Time, friction | Trial friction weight -0.30 (strongest gate) |
| Values-Driven Buyer | Mission, ethics | Identity fit weight 0.35 (highest) |

### Social Dynamics

- **Stratified seed selection** — Guarantees archetype coverage in the initial seed group
- **Discussion uplift cap** (0.40) — Prevents hype cascades from overriding weak product fundamentals. A product with baseline 0.25 cannot exceed 0.55 via discussions alone.
- **Discussion downdraft cap** (0.50) — Symmetric floor for negative deltas. Prevents skeptic death spirals from tanking good products. Asymmetric by design — skepticism can fall further than hype can rise.
- **Concern propagation** — Low-interest NPCs dampen enthusiasm of peers. Source credibility matters. No objections required (low interest alone triggers sharing). Content-aware: objection themes are classified (9 themes) and amplified/dampened by archetype-specific resonance multipliers.
- **Prompt memory injection** — NPCs carry social memory (peer warnings, discussion history, objection themes) into LLM discussion prompts. An NPC who heard price concerns from a skeptic will naturally reference those concerns when discussing with others. Memory also surfaces in Ask NPC responses.
- **Resistance floors** — Some archetypes are nearly immune to peer influence when the product is fundamentally wrong for them
- **Exposure decay** — Diminishing returns on peer influence over time (except Social Followers, who get increasing social proof)

### Adoption Model

Deterministic per-NPC computation with per-archetype thresholds:
```
adoption_score = interest_score x (1.0 - effective_barrier)
effective_barrier = weighted sum of: trust_gap, clarity_gap, price_gap,
                    trial_gap, switching_gap, inertia_gap
adopted = adoption_score >= archetype_threshold AND interest >= 0.30 AND aware
          AND (free product OR would_pay)
```
Archetype thresholds range from 0.55 (Trend Adopter) to 0.70 (Health Evaluator, Values Buyer), reflecting different risk tolerances.

### Reliability

- **LLM retry with exponential backoff** — API timeouts, rate limits, and malformed JSON trigger up to 3 retries with 1-8s delays before falling back
- **Discussion cooldown on failure** — Failed LLM discussions still set pair cooldown to prevent retry-every-tick loops
- **Simulation timeout** — Watchdog thread marks simulations as failed after 15 minutes, notifies SSE clients
- **Event store cleanup** — Completed simulation events auto-purged from memory after 2 minutes (or immediately when SSE client disconnects). Prevents OOM on long-running servers.
- **Calibrated constants** — Key propagation parameters (concern share base, delta multiplier, exposure decay, saturation damper) documented with sensitivity analysis ranges and rationale
- **Input validation** — Cross-field constraint: seed_count cannot exceed population_size
- **Stance band stability** — Band widths (0.12–0.20) sized so a typical discussion delta rarely flips more than one stance

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.10+, FastAPI, SQLAlchemy 2.0, Alembic |
| Frontend | React 18, TypeScript, Vite, TailwindCSS, Recharts |
| Database | PostgreSQL 14+ (production), SQLite (dev fallback) |
| AI | Claude API (Haiku for NPC reactions, Sonnet for reports) |

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL 14+ (or use SQLite for local dev)
- Anthropic API key ([console.anthropic.com](https://console.anthropic.com))

### Setup

```bash
git clone <your-repo-url>
cd idealab

# Environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Create PostgreSQL database
createdb idealab
# Or use SQLite: set DATABASE_URL=sqlite+aiosqlite:///./idealab.db in .env

# Backend
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
# Alembic migrations run automatically on startup

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**.

## Usage

1. **Define your idea** — Fill in the structured form: idea details, market positioning, optional reference assets, strengths/risks
2. **Configure** — Set rounds (3-20), population (10-50), and initial exposure (1-15)
3. **Launch** — Watch the live simulation: interactive social graph, real-time metrics, event feed
4. **Review report** — Adoption breakdown, segment analysis, objections, recommendations
5. **Create variants** — Quick Variant (change 6 key params) or Full Variant. Choose **Fresh seeds** (realistic variance) or **Same seeds** (controlled A/B, isolates the product change). Compare side-by-side with metrics deltas, population verification, and AI explanation.
6. **Chat with NPCs** — Click any NPC in the graph to ask questions. Responses are grounded in their simulation state.

## Project Structure

```
idealab/
├── backend/
│   ├── api/                       # FastAPI routes, schemas, JWT auth
│   ├── alembic/                   # Database migrations (auto-run on startup)
│   ├── db/                        # SQLAlchemy models (User, Simulation, Asset, Event)
│   ├── llm/                       # Claude API client with retry, prompts
│   ├── simulation/
│   │   ├── engine.py              # Tick loop, seeding, discussion cap
│   │   ├── evaluation.py          # Archetype baselines, individual deltas
│   │   ├── npc.py                 # NPC state, stance derivation
│   │   ├── population.py          # Archetype-based generation, social graph
│   │   ├── propagation.py         # Peer influence, concern propagation, spread
│   │   ├── adoption.py            # Per-NPC adoption barriers
│   │   ├── product_profile.py     # 8-dimension normalization
│   │   ├── convergence.py         # Stability and polarization tracking
│   │   ├── asset_signals.py       # Vision-based asset analysis
│   │   ├── competition.py         # Alternative classification
│   │   └── world.py               # World state, config
│   └── config.py                  # Settings
├── frontend/src/
│   ├── pages/                     # Dashboard, Inject, LiveSimulation, Report, Compare
│   └── components/                # Graph, metrics, NPC chat, event feed
├── docs/
│   ├── product/                   # PRD
│   ├── technical/                 # Technical design, simulation foundation spec
│   └── business/                  # Business plan, budget (gitignored)
├── data/
│   ├── npc_templates/             # 8 archetypes, evaluation weights, presets
│   └── known_products.json        # ~130 products for competition classification
└── tests/
    └── validation/                # 13-layer deterministic validation harness
```

## Validation

A 13-layer deterministic validation harness verifies the simulation without LLM calls:

```bash
cd idealab
python -m tests.validation.validate_simulation            # all layers
python -m tests.validation.validate_simulation --layer 13  # specific layer
```

Covers: archetype baseline separation, price sensitivity, individual delta bounds, face validity, convergence detection, input robustness, behavioral separation, exposure decay, seed sensitivity, holdout scenarios, competition context, asset signals, and adoption model.

## Cost

Each simulation targets **under $0.15** in API costs:
- Haiku for all per-tick operations (batched, fast, cheap)
- Sonnet only for the final report (1 call)
- Deterministic math for influence, spread, and adoption (no LLM)

## Authentication

JWT-based auth with bcrypt password hashing. Users only see their own simulations.

```bash
# Register
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "email": "alice@example.com", "password": "secret123"}'
# Returns: { "token": "eyJ...", "user_id": "...", "username": "alice" }

# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secret123"}'

# Use token in subsequent requests
curl -H "Authorization: Bearer eyJ..." http://localhost:8000/api/simulations
```

Auth is currently optional — unauthenticated requests still work but simulations won't be scoped to a user.

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/auth/register` | Create account (returns JWT) |
| `POST` | `/api/auth/login` | Login (returns JWT) |
| `POST` | `/api/simulations` | Create and run a simulation |
| `GET` | `/api/simulations` | List past simulations (filtered by user if auth'd) |
| `GET` | `/api/simulations/{id}` | Get simulation details |
| `GET` | `/api/simulations/{id}/stream` | SSE event stream (live or replay) |
| `GET` | `/api/simulations/{id}/report` | Get structured report |
| `POST` | `/api/simulations/{id}/ask-npc` | Chat with an NPC |
| `GET` | `/api/simulations/{id}/variants` | List variants |
| `GET` | `/api/simulations/{id}/compare/{vid}` | Compare parent vs variant (includes population + seed verification) |
| `POST` | `/api/simulations/{id}/compare/{vid}/explain` | AI explanation of differences |
| `DELETE` | `/api/simulations/{id}` | Delete simulation and all its events |
| `GET` | `/api/simulations/{id}/events` | List persisted events (supports `?tick=N` filter) |
| `POST` | `/api/assets/upload` | Upload reference asset |

## Disclaimer

This is an educational/experimental project. Simulation results are generated by AI personas and **should not replace real user research, market validation, or professional advice**.

## License

[GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE)
