# IdeaLab

> **Educational / Experimental Project** — Built as a learning exercise exploring AI agent simulation, full-stack architecture, and LLM integration. Not intended for production use or commercial decision-making.

A synthetic population idea-testing engine. Inject a product idea into a simulated society of AI-driven NPCs and get structured insight reports on adoption likelihood, objections, viral potential, and segment analysis — in minutes, not weeks.

## What This Project Explores

IdeaLab is a technical sandbox for experimenting with several intersecting concepts:

- **Multi-agent simulation** — Emergent social dynamics from 30+ AI personas across 8 behaviorally distinct archetypes, each with unique evaluation weights, social connections, and belief systems
- **LLM integration patterns** — Batched API calls, vision API for image analysis, structured output parsing, and a deterministic-first scoring pipeline where archetype baselines drive ~70% of outcomes with LLM providing bounded qualitative hints
- **Full-stack architecture** — FastAPI backend, React/TypeScript frontend, SSE streaming for real-time updates, SQLite event persistence with replay
- **Canvas-based visualization** — Force-directed social graphs, network animations, real-time data rendering
- **Simulation design** — Tick-based loops, convergence detection, polarization tracking, and product profile normalization

## How It Works

```
You describe an idea → Engine builds a product profile (8 dimensions)
                     → Deterministic archetype baselines computed per NPC
                     → LLM adds bounded qualitative hints (±0.10)
                     → Archetype-aware social influence with exposure decay
                     → Convergence tracking classifies outcome (convergence / polarization / unstable)
                     → You get a structured report with scores and recommendations
```

### Simulation Pipeline

Each simulation runs a **discrete tick-based loop** with 5 phases per tick:

1. **Awareness** — NPCs become aware of the idea (seed group first, then social spread)
2. **Reaction** — Newly-aware NPCs get a deterministic archetype baseline (from product profile × archetype evaluation weights), an individual trait delta (±0.10), an optional asset delta (±0.08), a competition delta (±0.08), and a bounded LLM qualitative hint (±0.10). The deterministic components drive ~70% of the final interest score.
3. **Discussion** — Interested NPCs discuss with connected peers. Discussion weight factors in archetype source credibility (Analytical Skeptics carry 1.3x weight, Social Followers 0.55x).
4. **Influence** — Archetype-aware peer influence with exposure decay (diminishing returns over ticks, except Social Followers who get increasing social proof). Resistance floors prevent peer enthusiasm from moving NPCs whose baseline says "this product is fundamentally wrong for me."
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
| Market Saturation | How crowded the competitive space is (confidence-weighted) | Dampens peer influence |

### Competition Context

When alternatives are provided, the engine classifies each one before using it in the simulation. This prevents fake names from inflating market saturation and stops the LLM from hallucinating comparisons against non-existent products.

**Classification types (ordered by trust level):**
- **Verified named competitor** (confidence 0.8-1.0) — matched in `known_products.json`, safe to reference by name in prompts
- **Inferred named competitor** (confidence 0.4) — heuristic capitalized-name match, contributes weakly to dimensions, never named to the LLM
- **Behavioral alternative** (confidence 0.4-0.9) — non-product approaches like "pen and paper", "spreadsheets"
- **Generic category** (confidence 0.5) — vague references like "existing tools"
- **Unknown** (confidence 0.2) — unrecognized text, contributes minimally

The classified alternatives produce 5 competition dimensions:

| Dimension | What it captures | How it affects simulation |
|-----------|-----------------|--------------------------|
| Direct Competition Intensity | Strength of competitive threat (confidence × category fit × tier weight, diminishing returns) | Reduces novelty, raises the bar |
| Incumbent Trust Pressure | Trust moat of verified major incumbents only | Raises trust barrier for skeptical NPCs |
| Switching Cost Pressure | Entrenched behavioral habits + incumbent tool lock-in | Penalizes low-openness NPCs via trait-based check |
| Familiarity of Solutions | Breadth and recognition of solution space (all alt types) | Boosts Follower (social proof) |
| Saturation Pressure | Confidence-weighted market crowdedness | Replaces old comma-count formula for market saturation |

Only **verified** named competitors reach LLM prompts by name. Inferred competitors are noted as a count ("there are also N other competitor(s) mentioned but not verified") without naming them. Behavioral alternatives are presented separately as "alternative approaches people currently use." An explicit instruction prevents the LLM from inventing or guessing competitor names.

### NPC Archetypes

Each NPC belongs to one of **8 behaviorally distinct archetypes**, each with unique evaluation weights, propagation parameters, and adoption thresholds:

| Archetype | Core driver | Key behavior |
|-----------|-------------|--------------|
| Analytical Skeptic | Evidence, risk assessment | Assumes claims are exaggerated, highest source credibility (1.3x), resistance floor 0.40 |
| Trend-Driven Early Adopter | Novelty, being first | Novelty weight 0.30, lowest adoption threshold (0.55), market saturation penalty -0.15 |
| Price-Sensitive Pragmatist | Cost/benefit obsession | Price friction weight -0.35 (strongest gate), highest price_sensitivity trait |
| Health-Conscious Evaluator | Safety, clinical evidence | Trust barrier weight -0.30, resistance floor 0.40, demands credentials |
| Aesthetic / Brand-Sensitive Buyer | Identity, polish | Positive price friction (+0.05 = premium signals quality), market saturation penalty -0.20 |
| Social-Proof Follower | Peer behavior | Positive market saturation (+0.20), susceptibility 1.30 (highest), increasing social proof returns |
| Convenience-First Busy User | Time, friction | Trial friction weight -0.30 (strongest gate), rejects anything with setup friction |
| Values-Driven Buyer | Mission, ethics | Identity fit weight 0.35 (highest), susceptibility 0.30 (lowest), suspicious of greenwashing |

Population presets (balanced, young_consumer, health_conscious, skeptical, premium) control the mix of archetypes in each simulation.

### Convergence Tracking

The engine monitors population dynamics each round:

- **Stabilization** — Is mean interest still changing or settling?
- **Variance stability** — Is the spread of opinions stabilizing?
- **Polarization** — Is the population splitting into opposing camps?
- **Archetype coherence** — Do NPCs within the same archetype agree? (Low within-group std dev confirms deterministic baselines dominate over LLM noise)
- **Result classification** — `stable_convergence`, `stable_polarization`, `unstable`, or `noisy`
- **Objection convergence** — Are concerns concentrating around a few themes or fragmenting?

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

**Section 3: Reference Assets**

Upload product screenshots, UI mockups, packaging photos, or provide website URLs. Up to 5 assets, max 5MB each (JPEG, PNG, WebP, GIF). URL-only assets (no image upload) are also supported — the LLM rates based on what the URL and context imply.

| Field | Required | Example |
|-------|----------|---------|
| Image | No (drag-drop or browse) | Screenshot of your landing page |
| Asset Type | Yes | website, app_ui, product_photo, packaging, prototype, marketing_visual |
| URL | No | "https://myproduct.com" |
| Note | No | "Final product look" or "Early prototype" |

Assets are analyzed via a single LLM vision call (or text-only for URL-only assets) to extract 7 structured perception signals:

| Signal | What it measures |
|--------|-----------------|
| Perceived Polish | Professional craftsmanship rating |
| Trustworthiness | Legitimacy and safety impression |
| Clarity | Value proposition immediately clear? |
| Visual Appeal | Aesthetic quality |
| Premium Feel | Premium vs. budget impression |
| Usability Impression | Ease/intuitiveness from visuals |
| Differentiation Signal | Visual distinctiveness from typical products |

These signals affect the simulation at two levels:
- **Product-level** — Trust barrier reduced by trustworthiness (×0.20), utility clarity boosted by clarity (×0.15), differentiation boosted by differentiation signal (×0.10), trial friction reduced by polish (×0.15)
- **Per-NPC** — Personality-weighted adjustment (±0.10): tech-savvy people are more critical of polish, price-sensitive people discount premium feel, open people amplify visual appeal, skeptics discount usability impressions from screenshots

NPCs never see raw images directly — all visual impressions are first distilled into these structured signals.

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

- **Adoption breakdown** — per-NPC adoption rate with top barrier explanations
- **Product profile** — The 8 derived dimensions and how they shaped the simulation
- **Key metrics** — awareness rate, interest rate, rejection rate, viral coefficient, net sentiment
- **Convergence analysis** — Whether the outcome stabilized, polarized, or remained volatile
- **Segment breakdown** — How different persona groups reacted
- **Top objections** — Most common concerns raised by NPCs
- **Discussion highlights** — Notable conversations between NPCs
- **Recommendations** — AI-generated suggestions to improve the idea
- **Narrative summary** — A written analysis of the simulation results

### Step 5 — Create variants

From any completed simulation report, you can create variants in two ways:

**Quick Variant** (recommended for what-if testing):
- Click **Quick Variant** on the Report page
- A drawer slides in showing only the 6 key parameters that matter for hypothesis testing: pricing, target audience, differentiator, alternatives, simulation rounds, and population size
- Everything else stays the same as the original
- Label the variant and launch — the system tracks which fields changed and maintains full lineage (parent → root chain)

**Full Variant**:
- Click **Full Variant** to open the complete Inject form pre-filled with all original values
- Modify any field (idea name, description, assets, strengths/risks, etc.)
- Useful when testing a fundamentally different positioning

After the variant completes, the **Compare** page shows:

- **What Changed** — Detailed before/after for each changed field with labels
- **Metrics Comparison** — All metrics with directional delta arrows (awareness, interest, rejection, adoption, etc.)
- **Adoption Breakdown** — Side-by-side adoption rates, adopted counts, and top adoption blockers with bar charts
- **Archetype Impact** — Per-archetype interest and adoption delta, sorted by impact magnitude, showing which persona types shifted most
- **Convergence** — Side-by-side result classification (stable convergence, polarization, unstable, noisy), polarization score, stability streak
- **Objections Comparison** — Top objections side-by-side with severity badges
- **Segments Comparison** — LLM-identified user segments side-by-side
- **AI Explanation** — On-demand LLM analysis explaining WHY the variant produced different results (verdict, key causal drivers, segment-level shifts, actionable recommendation)
- **Verdict** — Auto-generated summary of overall metric impact

**Lineage tracking**: Variants maintain `parent_simulation_id` and `root_simulation_id` for full family tree tracking. The Dashboard marks variant simulations with a badge, and the original simulation's report lists all its variants.

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
| `GET` | `/api/simulations/{id}/variants` | List variant simulations |
| `GET` | `/api/simulations/{id}/compare/{variant_id}` | Compare parent vs variant (enhanced with archetype, adoption, convergence data) |
| `POST` | `/api/simulations/{id}/compare/{variant_id}/explain` | Generate AI explanation of variant differences |
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
│   ├── alembic/                 # Database migrations
│   ├── db/                      # SQLAlchemy models & database setup
│   ├── llm/                     # Claude API client & prompt templates
│   ├── simulation/
│   │   ├── engine.py            # Tick loop orchestration
│   │   ├── evaluation.py        # Deterministic archetype baseline & individual delta computation
│   │   ├── npc.py               # NPC state management (with exposure tracking)
│   │   ├── population.py        # Archetype-based NPC generation & social graph
│   │   ├── world.py             # World state & population loading
│   │   ├── product_profile.py   # Idea normalization → 8 dimensions
│   │   ├── propagation.py       # Archetype-aware influence, resistance floors, exposure decay
│   │   ├── convergence.py       # Stability, polarization, archetype coherence, result classification
│   │   ├── asset_signals.py     # Reference asset analysis & per-NPC adjustment
│   │   ├── competition.py       # Alternative classification & competition context
│   │   ├── reporter.py          # Report generation
│   │   └── streamer.py          # In-memory event store for live SSE
│   ├── config.py                # App settings (from .env)
│   └── main.py                  # FastAPI app entry point
├── frontend/
│   └── src/
│       ├── pages/               # Dashboard, Inject, LiveSimulation, Report, Compare
│       ├── components/          # Charts, metrics, NPC cards, QuickVariantDrawer
│       ├── hooks/               # SSE streaming hook
│       └── types.ts             # TypeScript interfaces
├── data/
│   ├── npc_templates/           # Archetype definitions (8 archetypes, evaluation weights, presets)
│   ├── known_products.json      # ~130 known products for competition classification
│   └── scenarios/               # Example idea injections
├── tests/
│   └── validation/              # Deterministic validation harness (13 layers, no LLM needed)
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
  → classify_alternatives() → CompetitionContext (5 dimensions, confidence-weighted)
  → build_product_profile(idea, asset_signals, competition_context) → ProductProfile (8 dimensions)
  → Per NPC:
      archetype_baseline      (0.15–0.85)  deterministic: ProductProfile × archetype weights
    + individual_delta        (±0.10)      deterministic: trait deviation × ProductProfile
    + asset_delta             (±0.08)      deterministic: AssetSignals × personality
    + competition_delta       (±0.08)      deterministic: CompetitionContext × personality/archetype
    + llm_hint                (±0.10)      LLM qualitative reasoning + bounded adjustment
    = final interest_score    (0–1)        clamped
  → Per tick:
      Discussions (LLM) → Archetype-aware peer influence (math, with exposure decay)
                        → Spread (math, modulated by product profile)
                        → Adoption (deterministic, per-NPC):
                            adoption_score = interest × (1 - effective_barrier)
                            effective_barrier = weighted sum of:
                              trust_gap     (0.20) × skepticism adjustment
                              clarity_gap   (0.15) = 1 - utility_clarity
                              price_gap     (0.20) × price_sensitivity (paid only)
                              trial_gap     (0.15) × (1 - tech_savviness)
                              switching_gap (0.15) × conformity (if competition)
                              inertia_gap   (0.15) × (1 - openness) (if competition)
                            Hard gates: not aware → 0, interest < 0.30 → 0,
                                        paid product + won't pay → 0
                            Threshold: adopted = score >= 0.50
  → ConvergenceTracker records per-tick snapshots, archetype coherence, result classification
  → generate_report() includes profile, asset signals, competition context, adoption breakdown, convergence, and LLM analysis
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

## Validation

A 13-layer deterministic validation harness (`tests/validation/validate_simulation.py`) verifies the simulation foundation without LLM calls:

```bash
cd idealab
python -m tests.validation.validate_simulation            # all layers
python -m tests.validation.validate_simulation --layer 13  # specific layer
```

| Layer | What it validates |
|-------|-------------------|
| 1 | Archetype baselines differ meaningfully (spread >= 0.15) |
| 2 | Price sensitivity: Budget-Conscious drops 2.8x harder than Enthusiast |
| 3 | Individual deltas stay within ±0.10 bounds |
| 4 | Face validity: expected archetypes rank top/bottom for each product |
| 5 | Convergence tracker detects stability, computes archetype coherence |
| 6 | Input wording robustness: 3 description styles produce identical baselines |
| 7 | Archetype behavioral separation across 5 dimensions (interest, try, pay, recommend, objection) |
| 8 | Exposure decay: Follower capped at 1.5x, Skeptic moves < 0.15 over 20 ticks |
| 9 | Seed sensitivity: population randomness classified LOW for all test products |
| 10 | Holdout scenarios: 4 unseen products pass face-validity without weight tuning |
| 11 | Competition context: classification accuracy, confidence weighting, backward compat, adjustment bounds |
| 12 | Asset signals: product profile shifts, per-NPC adjustments bounded ±0.10, personality sensitivity, backward compat |
| 13 | Adoption model: per-NPC barriers, hard gates (unaware, low interest, won't pay), personality sensitivity, bounds |

## Disclaimer

This is an educational/experimental project. Simulation results are generated by AI personas and **should not replace real user research, market validation, or professional advice**. The outputs are synthetic directional signals useful for learning and experimentation, not for making business decisions.

## License

This project is licensed under the [GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE).
