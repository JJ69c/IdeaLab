# Simulation Foundation Spec

This document defines the core simulation logic, NPC archetype system, validation framework, and implementation strategy for IdeaLab. It was produced from a full audit of the current codebase and identifies what works, what's fragile, and what needs to change.

---

## A. Simulation Logic Spec

### A1. System Overview

The simulation is a discrete-tick agent-based model. Each tick has 5 phases. Opinions form through a combination of **deterministic math** (product profile, peer influence, spread probability) and **LLM-generated qualitative behavior** (initial reactions, discussions).

The key design principle: **math controls the mechanics, LLM provides the texture**. The LLM should never be the sole source of truth for numeric outcomes — it provides language, reasoning, and emotional color, while deterministic formulas anchor scores to product and personality reality.

### A2. Product Intrinsic Signals (ProductProfile)

The product profile converts unstructured idea inputs into 8 normalized dimensions (0-1) that modulate all deterministic math. These are the "physics" of the product.

| Dimension | What it captures | Downstream effects |
|-----------|------------------|--------------------|
| **novelty** | How new/unfamiliar | Boosts word-of-mouth spread; attracts novelty-seekers |
| **utility_clarity** | How clear the value prop is | Boosts interest for open-minded NPCs |
| **differentiation** | How distinct from alternatives | Small universal interest boost |
| **price_friction** | Cost resistance | Dampens interest for price-sensitive NPCs; reduces casual recs |
| **trust_barrier** | Trust required before adoption | Dampens interest for skeptics; raises conviction threshold for spread |
| **identity_fit** | Audience-product alignment | Per-NPC adjustment factor |
| **trial_friction** | Effort required to try | Dampens interest for low-tech NPCs |
| **market_saturation** | How crowded the space is | Dampens peer influence (people have strong priors) |

**Current build logic:** Rule-based scoring from idea fields (stage, category, description length, alternatives count, etc.). No LLM involvement.

**Current issues identified:**
- `utility_clarity` uses description length as a proxy for clarity — fragile heuristic
- No interaction terms between dimensions (e.g., high price + low trust should compound)
- `identity_fit` is generic — doesn't vary per NPC despite being labeled "refined per-NPC later"

**Recommended changes:**
1. Keep rule-based profile building (fast, deterministic, reproducible)
2. Add 2-3 interaction terms to `compute_npc_adjustment`:
   - `price_friction * trust_barrier * skepticism * 0.08` — expensive + unproven compounds
   - `utility_clarity * differentiation * openness * 0.06` — clear + differentiated compounds for open minds
3. Make `identity_fit` actually per-NPC: compare `idea.target_audience` keywords against NPC interests/occupation

### A3. NPC Preference Model

Each NPC evaluates a product through two stages:

**Stage A: Individual Evaluation (LLM + deterministic adjustment)**
1. LLM generates an initial reaction given NPC personality + idea description
2. Deterministic adjustment of [-0.20, +0.20] anchors the LLM score to product profile x personality reality

**Current adjustment formula:**
```
delta  = -(price_friction * price_sensitivity * 0.15)
       - (trial_friction * (1 - tech_savviness) * 0.10)
       + (novelty * novelty_seeking * 0.10)
       - (trust_barrier * skepticism * 0.10)
       + (utility_clarity * openness * 0.08)
       + (differentiation * 0.05)
       - (market_saturation * (1 - novelty_seeking) * 0.08)
```

**Current issues identified:**
- `openness` and `skepticism` only affect the adjustment, not peer influence or spread
- `conformity` only affects peer influence, not reactions
- Adjustment range [-0.20, +0.20] means a "mildly interested" (0.50) NPC can swing to "interested" (0.70) or "indifferent" (0.30) on profile alone — this is too large for a correction factor
- LLM reasoning can be narratively contradicted by the adjustment (LLM says "excited" but score gets pulled down)

**Recommended changes:**
1. Reduce adjustment cap to [-0.15, +0.15] — correction, not override
2. Pass the adjustment direction back to the LLM prompt as a constraint ("this NPC should lean skeptical given the price")
3. Use personality traits more broadly (see A4)

**Stance derivation (deterministic, from interest_score):**
```
0.85+ AND would_pay  → willing_to_pay
0.75 - 0.84          → willing_to_try
0.60 - 0.74          → interested
0.45 - 0.59          → curious
0.30 - 0.44          → indifferent
0.15 - 0.29          → skeptical
0.00 - 0.14          → opposed
```

This is clean and correct. The `would_pay` gate on the highest tier is intentional — it prevents pure math from declaring someone a paying customer without LLM confirmation.

### A4. Social Influence Model

**Phase 4: Peer Influence (deterministic)**

Each aware NPC's opinion is pulled toward the weighted average of their aware connections:

```
peer_avg = sum(connected.interest * trust * connected.social_influence) / total_weight
delta = (peer_avg - current) * conformity * 0.3
delta *= (1.0 - market_saturation * 0.30)  // crowded markets resist peer pressure
```

**Current issues:**
- The 0.3 conformity multiplier is hardcoded — high-conformity NPCs (0.9) only get 27% pull, low-conformity (0.1) get 3%
- No time decay — old connections influence as strongly as recent discussions
- No asymmetry — an opposed NPC and an interested NPC pull each other equally (modulo conformity)
- `social_influence` of the *source* NPC weights their opinion, but doesn't affect how persuasive their arguments are in discussions

**Phase 3: Discussion (LLM-driven)**

Selected pairs (up to 5/tick) have a simulated conversation. LLM generates interest deltas capped at [-0.2, +0.2].

**Discussion pair selection heuristic:**
```
score = opinion_gap * 0.4 + passion * 0.4 + trust * 0.2
```

**Current issues:**
- Prioritizing opinion gaps creates a conflict-seeking bias — simulations may over-polarize
- No per-pair frequency cap — same pair can discuss multiple times across ticks
- LLM's `a_new_stance` and `b_new_stance` fields are ignored — only deltas are used
- Trust level is passed to LLM but we can't verify it actually influences the output

**Recommended changes:**
1. Add per-pair discussion cooldown (skip if they discussed within last 2 ticks)
2. Balance the scoring: `opinion_gap * 0.3 + passion * 0.3 + trust * 0.2 + agreement * 0.2` — some discussions should reinforce, not just conflict
3. Validate LLM deltas: if delta > 0.1 and trust < 0.3, cap delta at 0.05 (low trust = hard to persuade)

**Phase 5: Spread (probabilistic)**

Interested NPCs (interest >= 0.60 AND would_recommend) probabilistically spread awareness:

```
prob = interest * social_influence * trust * target.novelty_seeking * 0.5
     * (1 + novelty * 0.30)         // novel ideas spread faster
     * (1 - price_friction * 0.20)  // expensive → less casual recommending
```

**Current issues:**
- `would_recommend` is set by LLM in the initial reaction and never updated — even if an NPC becomes more interested through discussion, they can't start recommending
- No concept of "recommendation fatigue" — an NPC tries to spread every tick until all connections are aware
- `novelty_seeking` of the *target* gates their receptiveness, but `openness` doesn't factor in

**Recommended changes:**
1. Re-derive `would_recommend` from interest_score: `interest >= 0.65 → would_recommend = true` (removes LLM gate on spread)
2. Add spread cooldown: each NPC can attempt spread to a given target once every 2 ticks
3. Include `openness` as a secondary factor in target receptiveness

### A5. Market/World Context

Currently minimal. The world is:
- A static social graph (connections + trust weights, frozen from JSON)
- A product profile (computed once from idea fields)
- No external events, no competing products entering mid-simulation, no information asymmetry

**This is fine for v1.** The product profile captures market context (saturation, alternatives, price). Adding dynamic market events would be Phase 3+ work.

### A6. Convergence Logic

**Stability:** Mean interest change < 1.5% for 2 consecutive ticks.
**Polarization:** Bimodality score = (extreme_ratio) * (balance_of_extremes). Extreme = interest < 0.35 or > 0.65. Polarized if score > 0.35.
**Objection concentration:** HHI index of objection frequencies.
**Overall convergence:** Stability achieved AND at least 3 ticks elapsed.

**Current issues:**
- Convergence doesn't check polarization — a highly polarized but mean-stable population is declared "converged"
- Objection normalization is just lowercase + strip punctuation — "too expensive", "price is too high", "can't afford it" count as 3 separate objections
- No detection of "lock-in" (when all NPCs have settled but the simulation hasn't technically stabilized because it's only tick 3)

**Recommended changes:**
1. Add polarization to convergence criteria: `converged = interest_stable AND NOT polarized AND ticks >= 3`
2. Add simple synonym matching for objections (or LLM-based clustering in the report phase)
3. Add a "locked" state for individual NPCs (if stance hasn't changed in 3+ ticks, stop including them in discussion pairs)

---

## B. NPC Archetype Spec

### B1. Design Principles

Archetypes must differ in **how they evaluate**, not just **who they are**. Two NPCs can both be 30-year-old engineers but evaluate products completely differently based on their decision style, risk tolerance, and adoption path.

Each archetype should have:
1. **Decision style** — How they process information and form opinions
2. **Adoption path** — What sequence of events leads them to adopt
3. **Susceptibility profile** — What influences them and what doesn't
4. **Typical objections** — What they tend to push back on
5. **Trait signature** — The personality trait ranges that define this archetype

### B2. Archetype Definitions

#### 1. The Enthusiast
**Decision style:** Emotion-first, explores before evaluating. Gets excited by vision and novelty. Decides fast, may regret later.
**Adoption path:** Awareness → immediate interest → tries it → tells everyone → may cool off if novelty fades
**Susceptibility:** Very high to novelty, moderate to social proof. Low to price concerns.
**Typical objections:** "What happens after the hype?" / "Is this actually different from X?"
**Trait signature:**
| Trait | Range |
|-------|-------|
| openness | 0.75-0.95 |
| skepticism | 0.10-0.30 |
| tech_savviness | 0.60-0.90 |
| price_sensitivity | 0.15-0.35 |
| social_influence | 0.65-0.90 |
| conformity | 0.20-0.40 |
| novelty_seeking | 0.80-0.95 |

**Count in population:** 4-5 of 30

#### 2. The Pragmatist
**Decision style:** Utility-first. Evaluates cost/benefit ratio. Needs clear problem → solution mapping. Won't adopt without understanding ROI.
**Adoption path:** Awareness → "what problem does this solve?" → evaluates alternatives → cautious trial → adopts if measurable benefit
**Susceptibility:** High to utility evidence and peer case studies. Low to novelty and hype.
**Typical objections:** "How is this better than what I use now?" / "What's the switching cost?" / "Show me the numbers"
**Trait signature:**
| Trait | Range |
|-------|-------|
| openness | 0.40-0.60 |
| skepticism | 0.50-0.70 |
| tech_savviness | 0.50-0.80 |
| price_sensitivity | 0.50-0.70 |
| social_influence | 0.30-0.60 |
| conformity | 0.40-0.60 |
| novelty_seeking | 0.20-0.45 |

**Count in population:** 8-10 of 30 (largest group — this is the mainstream)

#### 3. The Skeptic
**Decision style:** Risk-first. Assumes new things are worse until proven otherwise. Looks for flaws. Hard to convince, but once convinced becomes a credible advocate.
**Adoption path:** Awareness → "what could go wrong?" → resists → needs trusted peer endorsement or overwhelming evidence → slow adoption → strong retention
**Susceptibility:** Very low to marketing and hype. High to trusted peer endorsement. Moderate to evidence.
**Typical objections:** "This sounds too good to be true" / "What happens to my data?" / "Who's behind this?" / "I've seen this fail before"
**Trait signature:**
| Trait | Range |
|-------|-------|
| openness | 0.15-0.40 |
| skepticism | 0.70-0.90 |
| tech_savviness | 0.20-0.60 |
| price_sensitivity | 0.40-0.70 |
| social_influence | 0.20-0.50 |
| conformity | 0.15-0.40 |
| novelty_seeking | 0.05-0.25 |

**Count in population:** 5-6 of 30

#### 4. The Follower
**Decision style:** Social-proof-first. Watches what others do before committing. Comfortable adopting mainstream things. Risk-averse alone, comfortable in groups.
**Adoption path:** Awareness → watches peers → "if everyone else is using it..." → adopts after critical mass → recommends because "everyone uses it"
**Susceptibility:** Very high to peer influence and conformity. Low to novelty. Moderate to price.
**Typical objections:** "I'll wait and see" / "Has anyone I know tried this?" / "Is this actually catching on?"
**Trait signature:**
| Trait | Range |
|-------|-------|
| openness | 0.35-0.55 |
| skepticism | 0.30-0.50 |
| tech_savviness | 0.30-0.60 |
| price_sensitivity | 0.40-0.65 |
| social_influence | 0.15-0.35 |
| conformity | 0.70-0.90 |
| novelty_seeking | 0.15-0.40 |

**Count in population:** 6-8 of 30

#### 5. The Gatekeeper
**Decision style:** Authority/expertise-first. Evaluates from a position of domain knowledge. Their opinion carries weight. Hard to impress but their endorsement is high-value.
**Adoption path:** Awareness → deep evaluation → "does this meet professional standards?" → conditional endorsement → becomes reference for others
**Susceptibility:** Low to hype and social pressure. High to technical merit and evidence. Their own adoption depends on professional relevance.
**Typical objections:** "The implementation details worry me" / "This doesn't scale" / "The security model is unclear" / "I've built something similar and it didn't work because..."
**Trait signature:**
| Trait | Range |
|-------|-------|
| openness | 0.40-0.65 |
| skepticism | 0.55-0.75 |
| tech_savviness | 0.70-0.95 |
| price_sensitivity | 0.25-0.50 |
| social_influence | 0.60-0.85 |
| conformity | 0.10-0.30 |
| novelty_seeking | 0.30-0.55 |

**Count in population:** 3-4 of 30

#### 6. The Budget-Conscious
**Decision style:** Price-first. Will use anything free, resists anything paid. Evaluates value-per-dollar obsessively. Sensitive to hidden costs.
**Adoption path:** Awareness → "how much?" → rejects if too expensive → tries if free/cheap → may upgrade if deeply integrated → very sensitive to price increases
**Susceptibility:** Very high to price signals. Moderate to utility. Low to novelty and brand.
**Typical objections:** "Too expensive" / "Why would I pay when X is free?" / "What do I actually get for that?" / "Hidden costs?"
**Trait signature:**
| Trait | Range |
|-------|-------|
| openness | 0.30-0.60 |
| skepticism | 0.40-0.65 |
| tech_savviness | 0.30-0.70 |
| price_sensitivity | 0.80-0.95 |
| social_influence | 0.20-0.45 |
| conformity | 0.40-0.65 |
| novelty_seeking | 0.20-0.50 |

**Count in population:** 4-5 of 30

### B3. How Archetypes Should Affect Simulation

The current system uses personality traits as continuous floats, which is good — archetypes are clustering conventions, not hard categories. But traits need to *actually drive behavior differently*:

| Behavior | Current driver | Should also consider |
|----------|---------------|---------------------|
| Initial reaction score | LLM + product adjustment | Archetype-specific prompt framing |
| Peer influence susceptibility | conformity * 0.3 | skepticism (high = resistant), openness (high = receptive) |
| Discussion persuasiveness | social_influence (as weight) | tech_savviness (for technical products), communication_style |
| Spread probability | interest * social_influence * trust | conformity (followers spread after everyone, not before) |
| Objection generation | LLM only | Should be guided by archetype's typical concerns |
| would_pay determination | LLM only | Should be strongly influenced by price_sensitivity |
| would_recommend determination | LLM only (set once, never updated) | Should re-derive from interest + social_influence |

### B4. Population Composition

A 30-person population should approximate a realistic market cross-section:

| Archetype | Count | % | Rationale |
|-----------|-------|---|-----------|
| Enthusiast | 4-5 | 15% | Innovators + early adopters (Rogers curve: ~16%) |
| Pragmatist | 8-10 | 30% | Early majority (Rogers: ~34%) |
| Follower | 6-8 | 23% | Late majority (Rogers: ~34%, split with Pragmatist) |
| Skeptic | 5-6 | 18% | Laggards + resistant (Rogers: ~16%) |
| Gatekeeper | 3-4 | 12% | Opinion leaders (not in Rogers, but critical for B2B) |
| Budget-Conscious | 4-5 | 15% | Price-sensitive segment (cross-cuts all Rogers categories) |

Note: Total > 100% because Budget-Conscious overlaps with other archetypes. Some NPCs should combine traits (e.g., a Budget-Conscious Follower or a Skeptical Gatekeeper).

### B5. Social Graph Design

Connections should reflect archetype clustering:
- **Enthusiasts** connect to other Enthusiasts and some Gatekeepers (early adopters know tech experts)
- **Pragmatists** connect broadly (largest group, bridges communities)
- **Followers** connect to Pragmatists and other Followers (wait for mainstream signals)
- **Skeptics** connect to Gatekeepers and some Pragmatists (trust expertise, resist hype)
- **Gatekeepers** connect to Enthusiasts and Skeptics (respected by both extremes)
- **Budget-Conscious** connect to Followers and Pragmatists (share practical concerns)

Trust weights should be higher within-archetype (people trust people who think like them) and between Skeptics-Gatekeepers (mutual respect for rigor).

---

## C. Validation Framework

### C1. Reasonableness Tests

These verify the simulation produces outputs that align with basic product intuition.

**Test 1: Free product should get higher adoption than expensive product**
- Same idea, same population, only change price_point
- Free: adoption_likelihood should be >= 0.15 higher than $100+/mo
- If not, price sensitivity is broken

**Test 2: Launched product should get higher trust than concept**
- Same idea, only change stage
- Launched: mean interest should be >= 0.10 higher than concept
- If not, trust_barrier logic is broken

**Test 3: Enthusiasts should react before Followers**
- In tick 1 seed group, Enthusiasts who are seeded should have higher interest than Followers
- By tick 4, Followers should start moving toward the mean
- If Followers move first, conformity logic is broken

**Test 4: Well-described idea should score higher than vague idea**
- Same core concept. Version A: full problem_statement, differentiator, alternatives. Version B: just title + description
- Version A should produce higher utility_clarity and higher mean interest
- If not, product profile logic is broken

**Test 5: Polarizing idea should actually polarize**
- Inject an idea with clear pros/cons (e.g., crypto product — some love it, some hate it)
- By tick 6, polarization_score should be > 0.25
- If polarization stays at 0, the system is averaging too aggressively

### C2. Stability Tests

These verify the simulation converges to reasonable outcomes and doesn't oscillate or diverge.

**Test 6: Repeated runs should produce similar distributions**
- Same idea + same population, run 5 times
- Mean interest should stay within a 0.15 band across runs
- Stance distribution should be recognizably similar (no run where everyone loves it and another where everyone hates it)
- If variance is too high, LLM is too dominant and deterministic math is too weak

**Test 7: Adding more ticks shouldn't change the outcome**
- Run with 8 ticks vs 15 ticks
- Mean interest at tick 8 should be within 0.05 of mean interest at tick 15
- If it keeps drifting, convergence detection is broken

**Test 8: Population size shouldn't change direction**
- 15 NPCs vs 30 NPCs (stratified sampling preserving archetype ratios)
- Direction should be the same (both positive or both negative net sentiment)
- Magnitude can differ
- If direction flips, population diversity is driving the outcome more than the product

### C3. Anti-Bias Tests

These verify the simulation isn't just goal-seeking or prompt-biased.

**Test 9: Bad idea should fail**
- Inject a clearly bad idea: expensive, vague, crowded market, no differentiator, concept stage
- Adoption likelihood should be < 0.30
- If the simulation is optimistic about everything, there's a positivity bias

**Test 10: LLM removal should not reverse outcomes**
- Replace LLM reactions with deterministic defaults (interest = 0.5 + profile_adjustment for everyone)
- Replace LLM discussions with zero deltas
- The direction of the outcome should be the same (product profile should drive the result)
- If removing LLM flips the outcome, LLM is overriding the structured signals

**Test 11: Seed group shouldn't determine the outcome**
- Run 5 times with different random seeds (different initial seed NPCs)
- Final mean interest should stay within 0.12 band
- If seeding 5 Enthusiasts vs 5 Skeptics completely reverses the outcome, the seed selection needs to be stratified

**Test 12: Personality trait sensitivity**
- Increase all NPCs' skepticism by 0.20 (capped at 1.0)
- Mean interest should decrease by at least 0.05
- If it doesn't change, skepticism isn't actually being used

### C4. Convergence Tests

**Test 13: Monotonic idea should converge fast**
- Inject a universally appealing free product (high utility, low price, launched stage)
- Should converge by tick 5-6
- If it takes 8+ ticks, convergence thresholds may be too strict

**Test 14: Polarizing idea should not converge to consensus**
- Inject a polarizing idea
- Should NOT converge to a single mean interest
- Polarization score should be > 0.25 at simulation end
- If it converges to consensus, peer influence is too strong

**Test 15: Dead idea should stabilize at low interest**
- Inject a bad idea (as in Test 9)
- Mean interest should stabilize below 0.35 by tick 5
- Should not bounce around
- If it oscillates, discussion pair selection may be creating artificial conflict

---

## D. Practical Implementation Order

### D1. What Should Be Hardcoded Rules

These are the simulation's "physics" — deterministic, testable, reproducible:

- **Product profile building** — rule-based dimension scoring
- **NPC adjustment** — profile x personality math
- **Stance derivation** — interest_score thresholds
- **Peer influence** — weighted average with conformity and saturation damping
- **Spread probability** — interest x social_influence x trust with profile modulation
- **Convergence detection** — stability, polarization, objection concentration thresholds
- **Discussion pair selection** — heuristic scoring

### D2. What Should Be LLM-Generated

These provide qualitative texture that math can't produce:

- **Initial reaction reasoning** — *why* an NPC feels a certain way (language, specifics)
- **Discussion exchanges** — natural conversation between two personas
- **Discussion deltas** — how much each NPC shifts (within constrained range)
- **Objection content** — specific concerns in natural language
- **Report narrative** — executive summary, segment analysis, recommendations
- **Ask NPC responses** — in-character answers grounded in simulation state

### D3. What Should Be Derived Heuristics (not LLM, not hardcoded)

These are derived from archetype definitions and should be configurable:

- **would_recommend** — should be re-derived from interest_score (>= 0.65) each tick, not locked by LLM
- **Objection clustering** — group similar objections by keyword overlap
- **NPC lock-in detection** — if stance unchanged for 3 ticks, reduce discussion priority
- **Seed selection** — stratified by archetype (at least 1 Enthusiast, 1 Pragmatist, 1 other)

### D4. Implementation Priority

**Phase 1: Fix the math foundation (no UI changes)**

1. **Re-derive `would_recommend` each tick** — Remove LLM gate on spread. `would_recommend = interest_score >= 0.65`. This is the highest-impact single fix. Currently, spread is bottlenecked by LLM setting this flag in the initial reaction and never updating it.

2. **Add per-pair discussion cooldown** — Skip pairs that discussed within last 2 ticks. Prevents same-pair domination and artificial polarization.

3. **Fix convergence to include polarization** — `converged = interest_stable AND NOT polarized AND ticks >= 3`. Currently, a polarized population can be declared converged.

4. **Reduce NPC adjustment cap** — From [-0.20, +0.20] to [-0.15, +0.15]. The adjustment should anchor, not override.

5. **Stratify seed selection** — When selecting initial seed NPCs, ensure at least 1 from the top quartile of novelty_seeking and at least 1 from the bottom quartile. Prevents all-Enthusiast or all-Skeptic seeds.

**Phase 2: Strengthen personality effects**

6. **Use skepticism in peer influence** — Replace `conformity * 0.3` with `conformity * (1 - skepticism * 0.3) * 0.3`. Skeptics resist social pressure even if they have moderate conformity.

7. **Use openness in spread target receptiveness** — Add `target.openness * 0.3` as a factor alongside `target.novelty_seeking` in spread probability.

8. **Add discussion persuasiveness** — Weight the LLM's discussion delta by `source.social_influence / target.skepticism` (capped). A persuasive person talking to a skeptic should produce smaller deltas than talking to a follower.

9. **Add interaction terms to NPC adjustment** — `price_friction * trust_barrier * skepticism` compound penalty; `utility_clarity * differentiation * openness` compound boost.

**Phase 3: Rebuild the NPC population**

10. **Define archetypes in the population JSON** — Add an `archetype` field to each NPC. Not used in math (traits are), but used for:
    - Stratified sampling when population_size < total
    - Seed selection
    - Report segmentation

11. **Redesign the 30-NPC population** — Using the archetype distributions in B4, with realistic social graph structure from B5. Ensure trait signatures match archetype definitions.

12. **Add archetype-guided prompt framing** — When generating LLM reactions, include a one-line archetype hint: "This person is a pragmatic evaluator who needs clear utility proof before engaging." This steers LLM output toward archetype-consistent reasoning without constraining the specific language.

**Phase 4: Validation harness**

13. **Build a test runner** — Script that runs the 15 validation tests from section C, outputs pass/fail with metrics. No UI needed — this is a CLI/pytest harness.

14. **Run sensitivity analysis** — Vary each hardcoded constant (conformity multiplier, spread base, stability threshold) by +/- 50% and measure impact on mean interest, polarization, and convergence tick. Report which constants matter most.

15. **Establish reproducibility baseline** — Run the same idea 10 times, report the variance in key metrics. Set a target: variance of mean interest should be < 0.10.
