# IdeaLab

> **Educational / Experimental Project** — Built as a learning exercise exploring AI agent simulation, full-stack architecture, and LLM integration. Not intended for production use or commercial decision-making.

A synthetic population idea-testing engine. Inject a product idea into a simulated society of AI-driven NPCs and get structured insight reports on adoption likelihood, objections, viral potential, and segment analysis — in minutes, not weeks.

## What This Project Explores

IdeaLab is a technical sandbox for experimenting with several intersecting concepts:

- **Multi-agent simulation** — Emergent social dynamics from 30+ AI personas with distinct personalities, social connections, and belief systems
- **LLM integration patterns** — Batched API calls, vision API for image analysis, structured output parsing, and deterministic math layered on top of LLM outputs for reproducibility
- **Full-stack architecture** — FastAPI backend, React/TypeScript frontend, SSE streaming for real-time updates, SQLite event persistence with replay
- **Canvas-based visualization** — Force-directed social graphs, network animations, real-time data rendering
- **Simulation design** — Tick-based loops, convergence detection, polarization tracking, and product profile normalization

## How It Works

```
You describe an idea → Engine builds a product profile (8 dimensions)
                     → 30+ AI personas react individually (LLM + deterministic adjustment)
                     → Social interactions update beliefs over rounds
                     → Convergence tracking detects stabilization or polarization
                     → You get a structured report with scores and recommendations
```

### Simulation Pipeline

Each simulation runs a **discrete tick-based loop** with 5 phases per tick:

1. **Awareness** — NPCs become aware of the idea (seed group first, then social spread)
2. **Reaction** — Newly-aware NPCs generate LLM-driven reactions, then a per-NPC deterministic adjustment anchors the result to the product profile and personality traits (Stage A: individual evaluation)
3. **Discussion** — Interested NPCs discuss with connected peers (Stage B: social influence)
4. **Influence** — Deterministic social influence math shifts opinions, modulated by market saturation
5. **Spread** — Interested NPCs probabilistically spread awareness, boosted by novelty, dampened by price friction and trust barriers

### Product Profile

Before the simulation starts, the engine normalizes your structured inputs into 8 dimensions that shape the deterministic math:

| Dimension | What it captures | How it affects simulation |
|-----------|-----------------|--------------------------|
| Novelty | How new/unfamiliar the concept is | Boosts word-of-mouth spread |
| Utility Clarity | How clearly the value proposition is understood | Boosts interest for open-minded NPCs |
| Differentiation | How distinct from known alternatives | Small universal interest boost |
| Price Friction | Resistance introduced by pricing | Dampens interest for price-sensitive NPCs, reduces casual recommendations |
| Trust Barrier | How much trust is needed before adoption | Dampens interest for skeptical NPCs, raises conviction threshold for spread |
| Identity Fit | Baseline audience-product alignment | Per-NPC adjustment factor |
| Trial Friction | Effort required to try the product | Dampens interest for low-tech NPCs |
| Market Saturation | How crowded the competitive space is | Dampens peer influence |

### Convergence Tracking

The engine monitors population dynamics each round:

- **Stabilization** — Is mean interest still changing or settling?
- **Polarization** — Is the population splitting into opposing camps?
- **Objection convergence** — Are concerns concentrating around a few themes or fragmenting?
- **Overall convergence** — Has the simulation reached a steady state?

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI, SQLAlchemy |
| Frontend | React 18, TypeScript, Vite, TailwindCSS, Recharts |
| Database | SQLite (events persisted for replay) |
| AI | Claude API (Haiku for NPC reactions, Sonnet for reports) |

## Prerequisites

- **Python** 3.9+
- **Node.js** 18+
- **Anthropic API key** — get one at [console.anthropic.com](https://console.anthropic.com)

## Getting Started

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd idealab
```

### 2. Set up environment variables

```bash
cp .env.example .env
```

Edit `.env` and add your Anthropic API key:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 3. Install and run the backend

```bash
# Install Python dependencies
pip install fastapi uvicorn sqlalchemy aiosqlite pydantic pydantic-settings anthropic

# Start the API server (run from the idealab/ root, not backend/)
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be running at `http://localhost:8000`. Verify with:

```bash
curl http://localhost:8000/api/health
```

### 4. Install and run the frontend

Open a new terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend will be running at `http://localhost:5173` and automatically proxies API requests to the backend.

### 5. Open the app

Navigate to **http://localhost:5173** in your browser.

## Usage

### Step 1 — Define your idea

On the **Set Up Simulation** page, fill in four sections:

**Section 1: The Idea**

| Field | Required | Example |
|-------|----------|---------|
| Idea Name | Yes | "FocusFlow" |
| What is it? | Yes | "An AI-powered focus timer that blocks distracting apps..." |
| Category | Yes | Grouped dropdown (Software, Consumer, Fintech, Health, Hardware, Other) + custom option |
| Idea Stage | No | Just an idea / Prototype / Working MVP / Already launched |

**Section 2: Market Positioning**

| Field | Required | Example |
|-------|----------|---------|
| Target Audience | Yes | "remote workers aged 25-40" |
| Problem it Solves | No | "Remote workers lose 2+ hours daily to app switching" |
| Pricing | No | Presets (Free, Freemium, $5-20/mo, etc.) + custom option |
| Existing Alternatives | No | "Forest, Freedom, Cold Turkey" |
| Key Differentiator | No | "AI-powered adaptive blocking that learns your patterns" |

**Section 3: Reference Assets** (collapsible)

Upload product screenshots, UI mockups, packaging photos, or landing page screenshots. Up to 5 assets, max 5MB each (JPEG, PNG, WebP, GIF).

| Field | Required | Example |
|-------|----------|---------|
| Image | Yes (per asset) | Screenshot of your landing page |
| Asset Type | Yes | website, app_ui, product_photo, packaging, prototype, marketing_visual |
| URL | No | "https://myproduct.com" |
| Note | No | "Final product look" or "Early prototype" |

Assets are analyzed via a single LLM vision call to extract structured signals (polish, trustworthiness, clarity, visual appeal, premium feel, usability, differentiation). These signals modify the product profile and add per-NPC adjustments — NPCs never see raw images directly.

**Section 4: Strengths & Risks** (collapsible)

| Field | Required | Example |
|-------|----------|---------|
| Known Strengths | No | "Strong viral loop through team invites" |
| Known Risks | No | "Crowded market, unclear monetization path" |

These optional fields seed the simulation with your existing knowledge rather than letting the LLM invent everything.

### Step 2 — Configure the simulation

**Section 5: Simulation Controls** (collapsible, with range sliders)

| Parameter | Range | Default | Labels |
|-----------|-------|---------|--------|
| Rounds | 3-20 | 8 | Quick check ... Exhaustive |
| Population | 10-50 | 30 | Small focus group ... Full population |
| Initial Exposure | 1-15 | 5 | Organic ... Broad launch |

Includes a live cost/duration estimate.

### Step 3 — Launch the simulation

Click **Launch Simulation**. The live simulation page shows:

- **Social graph** — Interactive force-directed graph. Nodes are NPCs (colored by stance), edges are social connections (weighted by trust and discussion influence).
- **Metrics bar** — Real-time awareness rate, interest rate, and viral coefficient.
- **Convergence signals** — Stability streak, polarization score, objection concentration.
- **Event feed** — NPC reactions, discussions, and spread events as they happen.
- **Tick progress** — Current round and phase.

#### Graph Navigation

The social graph supports zoom, pan, focus mode, and smart label placement:

| Action | How |
|--------|-----|
| **Zoom** | Mouse wheel or trackpad pinch (cursor-centered), or +/− buttons |
| **Pan** | Click and drag on empty space |
| **Select NPC** | Single-click any node — opens inspector panel, dims non-neighbors |
| **Focus on NPC** | Double-click a node — viewport centers and zooms to 1.6x on that NPC |
| **Deselect** | Single-click empty space |
| **Reset view** | Double-click empty space, press Escape, or click the reset button |

**Smart labels** — Labels are placed with collision avoidance (tries below, above, right, left of each node). At default zoom, only the ~8 highest-priority labels are shown (selected, connected, recently-active). Zoom past 1x for more labels, past 1.8x for full names. Hover any node to reveal its label at any zoom level. Overlapping labels from low-priority nodes are automatically hidden.

**2-hop neighborhood dimming** — When an NPC is selected, the graph uses tiered visibility to show network context:
- **Selected node** — fully highlighted with selection ring
- **1-hop neighbors** — strongly visible (full opacity), connected edges emphasized
- **2-hop neighbors** — softly visible (35% opacity), labels faded, edges lightly tinted
- **Everything else** — aggressively dimmed (6% opacity) to remove visual noise

This makes it easy to trace influence paths and understand the selected NPC's extended neighborhood without losing the overall graph structure.

**Stance cluster indicators** — Faint stance-colored background circles appear behind groups of 2+ NPCs sharing the same stance. These update dynamically as opinions evolve during the simulation, making it easy to spot emerging opinion clusters (e.g., a group of skeptical NPCs forming, or interest spreading through a connected cluster).

**Layout** — The force-directed layout uses tuned repulsion (scaled by population size), longer spring rest lengths, and weaker center gravity to produce well-separated clusters with readable spacing.

#### Chat with NPC

When an NPC is selected, the inspector panel includes a **mini chat interface** at the bottom. This lets you have a grounded conversation with any aware NPC about their reaction to the idea.

- **Chat-style layout** — User messages on the right, NPC responses on the left in styled chat bubbles with a scrollable message history.
- **NPC presence** — A status line shows the NPC's current stance and updates during requests: "Dorothy is thinking...", "Dorothy is recalling discussions...", "Dorothy is choosing their words..."
- **Typing indicator** — An animated three-dot bounce appears in an NPC bubble while waiting for a response.
- **Quick prompt chips** — 4 lightweight chips ("Why this stance?", "Change your mind?", "Recommend it?", "Biggest concern") auto-send on click. Chips appear for the first couple of messages, then fade to keep the chat clean.
- **Free-text input** — Textarea with Enter to send, Shift+Enter for newline, send arrow button with loading spinner, auto-resize, and NPC-specific placeholder text.
- **Grounding transparency** — Each NPC reply has a collapsible "based on simulation state" toggle showing the NPC's stance, interest level, top objection, and most recent influence event.
- **Grounded responses** — The NPC answers in character, constrained by their actual simulation state (stance, interest, objections, discussion history). They cannot hallucinate or contradict what happened in the simulation.
- **Unaware NPCs** — NPCs who haven't heard about the idea yet return a canned response without an LLM call.

### Step 4 — Review the report

After the simulation completes, the **Report** page shows:

- **Overall adoption score** (0-1) and adoption likelihood rating
- **Product profile** — The 8 derived dimensions and how they shaped the simulation
- **Key metrics** — awareness rate, interest rate, rejection rate, viral coefficient, net sentiment
- **Convergence analysis** — Whether the outcome stabilized, polarized, or remained volatile
- **Segment breakdown** — How different persona groups reacted
- **Top objections** — Most common concerns raised by NPCs
- **Discussion highlights** — Notable conversations between NPCs
- **Recommendations** — AI-generated suggestions to improve the idea
- **Narrative summary** — A written analysis of the simulation results

### Step 5 — Iterate

Adjust your idea description, pricing, or target audience and run again. Compare results across simulations on the **Dashboard**.

### Replay past simulations

All simulation events are persisted to the database. Restarting the server does not lose history. Navigating to a completed simulation replays the full event stream from the database so you can re-watch how opinions evolved.

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/assets/upload` | Upload a reference asset image |
| `POST` | `/api/simulations` | Create and run a new simulation |
| `GET` | `/api/simulations` | List past simulations |
| `GET` | `/api/simulations/{id}` | Get simulation details and status |
| `GET` | `/api/simulations/{id}/stream` | SSE event stream (live or replay) |
| `GET` | `/api/simulations/{id}/report` | Get the structured report |
| `GET` | `/api/simulations/{id}/events` | Get persisted event log |
| `POST` | `/api/simulations/{id}/ask-npc` | Ask an NPC a question (grounded in sim state) |
| `GET` | `/api/npcs` | List available NPC templates |
| `GET` | `/api/health` | Health check |

### Example: Create a simulation via API

```bash
curl -X POST http://localhost:8000/api/simulations \
  -H "Content-Type: application/json" \
  -d '{
    "idea": {
      "title": "FocusFlow",
      "description": "An AI-powered focus timer that blocks distracting apps and uses gentle nudges to keep remote workers in deep focus mode",
      "category": "productivity_tool",
      "stage": "concept",
      "target_audience": "remote workers aged 25-40",
      "problem_statement": "Remote workers lose 2+ hours daily to app switching and notifications",
      "price_point": "$5-$20/mo",
      "existing_alternatives": "Forest, Freedom, Cold Turkey",
      "differentiator": "AI-powered adaptive blocking that learns your focus patterns"
    },
    "config": {
      "num_ticks": 8,
      "population_size": 30,
      "seed_count": 5
    }
  }'
```

## Project Structure

```
idealab/
├── backend/
│   ├── api/
│   │   ├── routes/              # FastAPI route handlers
│   │   └── schemas/             # Pydantic request/response models
│   ├── db/                      # SQLAlchemy models & database setup
│   ├── llm/                     # Claude API client & prompt templates
│   ├── simulation/
│   │   ├── engine.py            # Tick loop orchestration
│   │   ├── npc.py               # NPC state management
│   │   ├── world.py             # World state & population loading
│   │   ├── product_profile.py   # Idea normalization → 8 dimensions
│   │   ├── propagation.py       # Deterministic influence & spread math
│   │   ├── convergence.py       # Stability, polarization, objection tracking
│   │   ├── asset_signals.py      # Reference asset analysis & per-NPC adjustment
│   │   ├── reporter.py          # Report generation
│   │   └── streamer.py          # In-memory event store for live SSE
│   ├── config.py                # App settings (from .env)
│   └── main.py                  # FastAPI app entry point
├── frontend/
│   └── src/
│       ├── pages/               # Dashboard, Inject, LiveSimulation, Report
│       ├── components/          # Charts, metrics, NPC cards
│       ├── hooks/               # SSE streaming hook
│       └── types.ts             # TypeScript interfaces
├── data/
│   ├── npc_templates/           # Pre-built NPC population (30+ personas)
│   └── scenarios/               # Example idea injections
├── docs/
│   ├── PRD.md                   # Product requirements
│   └── TECHNICAL_DESIGN.md      # Architecture & API design
├── .env.example                 # Environment variable template
└── .gitignore
```

## Architecture

### Evaluation Pipeline

```
InjectedIdea (user input) + Reference Assets (optional images)
  → analyze_assets() → AssetSignals (7 dimensions from LLM vision)
  → build_product_profile(idea, asset_signals) → ProductProfile (8 dimensions, nudged by assets)
  → Per tick:
      Stage A (individual): LLM reaction + compute_npc_adjustment(profile × personality)
                            + compute_asset_adjustment(asset_signals × personality)
      Stage B (social):     Discussion (LLM) → Peer influence (math) → Spread (math)
                            All modulated by product profile dimensions
  → ConvergenceTracker records per-tick snapshots
  → generate_report() includes profile, asset signals, convergence, metrics, and LLM analysis
```

### Event Persistence

Simulation events are dual-written:
- **In-memory store** — for live SSE streaming during active simulations
- **SQLite database** — for persistent replay after server restarts

The `/stream` endpoint automatically detects which mode to use:
- Running simulation with in-memory data → live stream
- Completed simulation → replay from database
- Unknown simulation → 404

## Cost

Each simulation targets **under $0.15** in API costs through:

- Batched LLM calls (5-8 NPCs per request)
- Haiku for NPC reactions (fast and cheap), Sonnet for the final report (higher quality)
- Deterministic math for influence and spread phases (no LLM needed)
- Capped discussions (max 5 per tick)

## Disclaimer

This is an educational/experimental project. Simulation results are generated by AI personas and **should not replace real user research, market validation, or professional advice**. The outputs are synthetic directional signals useful for learning and experimentation, not for making business decisions.

## License

This project is licensed under the [GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE).
