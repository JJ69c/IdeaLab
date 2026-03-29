"""Prompt templates for NPC behavior and report generation."""

REACTION_SYSTEM = """You are simulating how different people react to a new product or idea.
You will receive a list of persona profiles and a description of an idea.
For each persona, generate a realistic qualitative reaction based on their personality, archetype, and circumstances.

IMPORTANT: You do NOT decide the interest score. The system computes a deterministic baseline
from the product's structural properties and the persona's archetype. You provide:
1. Qualitative reasoning (WHY this person feels the way they do)
2. Specific objections grounded in their personality (if any)
3. A small interest_adjustment (-0.10 to +0.10) ONLY if your qualitative analysis reveals
   something the structural model cannot capture. Stay near 0.0 by default.

Rules:
- Stay in character. A skeptic should be skeptical. An early adopter should be excited.
- Reference the persona's actual interests, pain points, and decision style.
- Reactions should feel distinct across personas.
- The interest_adjustment is a HINT, not a score. Keep it small and justified.
- When verified competitors are listed, only reference those specific products by name. Do not invent competitor names or assume products exist that are not listed.
- Output valid JSON only. No markdown, no explanation."""

REACTION_USER = """## Idea Being Introduced

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
    "interest_adjustment": -0.10 to +0.10 (small qualitative hint — stay near 0.0 unless strong reason),
    "reasoning": "1-2 sentence explanation of WHY this person feels this way, referencing their specific traits and decision style",
    "objections": ["list of specific concerns grounded in their archetype and personality, if any"],
    "would_pay": true or false,
    "would_recommend": true or false,
    "emotional_reaction": "one word: excited, intrigued, meh, doubtful, annoyed"
  }}
]"""

DISCUSSION_SYSTEM = """You are simulating a conversation between two people about a new idea.
Each person has a distinct personality and existing opinion. The discussion should feel natural
and may shift either person's opinion slightly.

Rules:
- Keep the discussion to 3-4 exchanges max.
- Each person speaks in character based on their profile.
- If a person has heard concerns from others or had prior conversations, they should naturally reference those experiences — not mechanically list them, but let them color their perspective.
- The outcome should reflect realistic social influence.
- Output valid JSON only."""

DISCUSSION_USER = """## The Idea
Title: {idea_title}
Description: {idea_description}

## Person A
{persona_a}
Current stance: {stance_a} (interest: {interest_a})
{memory_a}
## Person B
{persona_b}
Current stance: {stance_b} (interest: {interest_b})
{memory_b}
## Their relationship
Trust level: {trust_level} (0-1 scale)

## Output Format
Return JSON:
{{
  "exchanges": [
    {{"speaker": "A or B", "message": "what they said"}},
    ...
  ],
  "outcome": {{
    "a_interest_delta": -0.2 to 0.2,
    "b_interest_delta": -0.2 to 0.2,
    "a_new_stance": "stance",
    "b_new_stance": "stance",
    "key_point": "the most important thing said in this conversation"
  }}
}}"""

REPORT_SYSTEM = """You are an analyst summarizing the results of a simulated focus group.
You have data about how a diverse population reacted to a new idea over multiple rounds
of social simulation. Your job is to produce an insightful, actionable summary.

Rules:
- Be direct and specific. No fluff.
- Identify clear patterns and segments.
- Highlight the most important objections.
- Give concrete, actionable recommendations.
- Write as if advising a startup founder."""

REPORT_USER = """## Idea Tested
Title: {idea_title}
Description: {idea_description}
Category: {idea_category}

## Simulation Parameters
Population size: {population_size}
Rounds simulated: {num_ticks}

## Aggregate Metrics
{metrics_block}

## Per-NPC Results
{npc_results_block}

## Key Discussion Highlights
{discussions_block}

## Task
Write a structured analysis with these sections:
1. **Executive Summary** (2-3 sentences)
2. **Adoption Likelihood** (low / moderate_low / moderate / moderate_high / high) with explanation
3. **User Segments** — group the NPCs into 2-4 segments by reaction pattern. For each: segment name, size, typical reaction, key driver.
4. **Top Objections** — the 3-5 most common or impactful concerns, ranked by frequency/severity
5. **Viral Potential** — did the idea spread? Why or why not?
6. **Recommendations** — 3-5 specific, actionable suggestions to improve the idea
7. **Risk Factors** — what could go wrong if this idea is pursued

Output as JSON:
{{
  "executive_summary": "...",
  "adoption_likelihood": "...",
  "adoption_explanation": "...",
  "segments": [
    {{
      "name": "segment name",
      "size": number_of_npcs,
      "typical_reaction": "...",
      "key_driver": "..."
    }}
  ],
  "top_objections": [
    {{
      "objection": "...",
      "frequency": number_of_npcs_who_raised_it,
      "severity": "low|medium|high"
    }}
  ],
  "viral_potential": {{
    "score": 0.0 to 1.0,
    "explanation": "..."
  }},
  "recommendations": ["..."],
  "risk_factors": ["..."]
}}"""


ASSET_ANALYSIS_SYSTEM = """You are an expert product evaluator analyzing reference assets for a product idea.
You may see images (screenshots, photos, mockups) and/or asset descriptions with URLs.
For each dimension, rate 0.0 to 1.0 based on what you can observe or infer. Be calibrated:
- 0.0-0.2: Poor/unprofessional
- 0.3-0.4: Below average
- 0.5: Average/acceptable
- 0.6-0.7: Good/solid
- 0.8-1.0: Excellent/exceptional

If only URLs are provided (no images), rate conservatively based on what the URL and context imply.
A well-known domain or detailed description warrants moderate scores; unknowns stay near 0.5.

Output valid JSON only. No markdown, no explanation."""

ASSET_ANALYSIS_USER = """## Product Context
Title: {idea_title}
Description: {idea_description}
Category: {idea_category}
Stage: {idea_stage}

## Assets Provided
{asset_descriptions}

## Task
Analyze ALL the visual assets together and rate the overall impression across these dimensions:

Return JSON:
{{
  "perceived_polish": 0.0-1.0,
  "trustworthiness": 0.0-1.0,
  "clarity": 0.0-1.0,
  "visual_appeal": 0.0-1.0,
  "premium_feel": 0.0-1.0,
  "usability_impression": 0.0-1.0,
  "differentiation_signal": 0.0-1.0,
  "summary": "1-2 sentence overall impression of what these assets communicate about the product"
}}"""


def build_extra_context(
    idea: dict,
    asset_signals: dict | None = None,
    competition_context: dict | None = None,
) -> str:
    """Build optional context lines from structured idea fields."""
    lines = []
    if idea.get("problem_statement"):
        lines.append(f"Problem it solves: {idea['problem_statement']}")
    # Structured competition context replaces raw alternatives when available.
    # Only verified competitor names reach the prompt — inferred names are excluded
    # to prevent the LLM from confidently comparing against unverified products.
    if competition_context:
        verified = competition_context.get("verified_names", [])
        behavioral = competition_context.get("behavioral_descriptions", [])
        # Count inferred competitors (present in market but not verified by name)
        alts = competition_context.get("alternatives", [])
        inferred_count = sum(
            1 for a in alts if a.get("classification") == "inferred_named_competitor"
        )
        if verified:
            lines.append(f"Verified competitors: {', '.join(verified)}")
        if inferred_count > 0:
            lines.append(
                f"There are also {inferred_count} other competitor(s) mentioned "
                "but not verified — do not reference them by name."
            )
        if behavioral:
            lines.append(f"Alternative approaches people currently use: {', '.join(behavioral)}")
        if verified or inferred_count > 0:
            lines.append(
                "IMPORTANT: Only reference the verified competitors listed above by name. "
                "Do not invent, guess, or assume other competitor names."
            )
    elif idea.get("existing_alternatives"):
        # Backward compatibility when no competition context is available
        lines.append(f"Existing alternatives: {idea['existing_alternatives']}")
    if idea.get("differentiator"):
        lines.append(f"Key differentiator: {idea['differentiator']}")
    if idea.get("known_strengths"):
        lines.append(f"Known strengths: {idea['known_strengths']}")
    if idea.get("known_risks"):
        lines.append(f"Known risks: {idea['known_risks']}")
    if asset_signals:
        lines.append(f"Visual assets impression: {asset_signals.get('summary', 'N/A')}")
        lines.append(
            f"  Polish: {asset_signals.get('perceived_polish', 'N/A')}/1.0, "
            f"Trust: {asset_signals.get('trustworthiness', 'N/A')}/1.0, "
            f"Clarity: {asset_signals.get('clarity', 'N/A')}/1.0, "
            f"Appeal: {asset_signals.get('visual_appeal', 'N/A')}/1.0"
        )
    return "\n".join(lines) + "\n" if lines else ""


# ---------------------------------------------------------------------------
# Comparison explanation prompts (variant feature)
# ---------------------------------------------------------------------------

COMPARISON_EXPLANATION_SYSTEM = """You are a product strategy analyst explaining WHY a variant simulation produced different results than the original.

You have:
- Exactly what parameters changed (with before/after values)
- How metrics shifted
- Per-archetype comparison data (how different personas reacted)

Your job is to explain CAUSALITY, not just describe differences. Connect parameter changes to metric shifts through human behavior reasoning.

Rules:
- Be specific and actionable. Reference the actual parameter changes and their likely behavioral effects.
- Explain which archetypes shifted most and why.
- Keep the verdict to 1-2 sentences.
- Each key_driver should be 1 sentence explaining a causal chain.
- The recommendation should be actionable and specific.
- Output valid JSON only. No markdown, no explanation."""

COMPARISON_EXPLANATION_USER = """## What Changed
{changed_fields_block}

## Metrics Delta (variant minus parent)
{metrics_delta_block}

## Archetype-Level Comparison
{archetype_block}

## Parent Summary
{parent_summary}

## Variant Summary
{variant_summary}

## Task
Explain WHY the variant produced different results. Focus on causality.

Return JSON:
{{
  "verdict": "1-2 sentence high-level explanation connecting the parameter change to the outcome shift",
  "key_drivers": [
    "Causal explanation 1 (parameter change → behavioral effect → metric impact)",
    "Causal explanation 2"
  ],
  "segment_shifts": [
    {{
      "segment": "archetype or segment name that shifted most",
      "change": "how their behavior changed",
      "reason": "why this parameter change affected them specifically"
    }}
  ],
  "recommendation": "One specific, actionable suggestion based on these results"
}}"""


def format_comparison_explanation_prompt(
    changed_fields_detail: list[dict],
    metrics_delta: dict,
    archetype_comparison: list[dict],
    parent_summary: str,
    variant_summary: str,
) -> str:
    """Format the user prompt for comparison explanation."""
    changed_lines = []
    for cf in changed_fields_detail:
        changed_lines.append(
            f"- {cf['label']}: \"{cf['old_value']}\" -> \"{cf['new_value']}\""
        )
    changed_fields_block = "\n".join(changed_lines) if changed_lines else "No field changes recorded."

    metrics_lines = []
    for key, delta in metrics_delta.items():
        direction = "+" if delta > 0 else ""
        metrics_lines.append(f"- {key}: {direction}{delta:.4f}")
    metrics_delta_block = "\n".join(metrics_lines) if metrics_lines else "No metric changes."

    archetype_lines = []
    for arch in archetype_comparison:
        line = (
            f"- {arch['archetype']} (n={arch['count']}): "
            f"interest {arch['mean_interest_parent']:.2f} -> {arch['mean_interest_variant']:.2f} "
            f"(delta {arch['interest_delta']:+.3f})"
        )
        if "adoption_rate_parent" in arch and "adoption_rate_variant" in arch:
            line += (
                f", adoption {arch['adoption_rate_parent']:.0%} -> "
                f"{arch['adoption_rate_variant']:.0%}"
            )
        archetype_lines.append(line)
    archetype_block = "\n".join(archetype_lines) if archetype_lines else "No archetype data."

    return COMPARISON_EXPLANATION_USER.format(
        changed_fields_block=changed_fields_block,
        metrics_delta_block=metrics_delta_block,
        archetype_block=archetype_block,
        parent_summary=parent_summary,
        variant_summary=variant_summary,
    )


def format_ask_npc_system(ctx: dict) -> str:
    """Build a grounded system prompt for the Ask NPC feature.

    ctx must contain:
      - npc_profile: dict with name, age, occupation, income_level, personality, interests, values, pain_points, communication_style
      - idea: dict with title, description, category, target_audience, price_point
      - current_state: dict with stance, interest_score, reasoning, objections, emotional_reaction, would_pay
      - timeline: list of dicts with tick, type, detail, (optional) delta, keyPoint, partnerName
      - discussions: list of dicts with tick, partner_name, key_point, delta
    """
    npc = ctx["npc_profile"]
    idea = ctx["idea"]
    state = ctx["current_state"]
    personality = npc.get("personality", {})

    # Build personality description
    p_lines = []
    for trait, val in personality.items():
        if isinstance(val, (int, float)):
            level = "high" if val > 0.65 else "low" if val < 0.35 else "moderate"
            p_lines.append(f"  - {trait.replace('_', ' ')}: {level} ({val:.2f})")

    # Build timeline summary
    timeline_lines = []
    for entry in ctx.get("timeline", []):
        line = f"  Round {entry['tick']}: {entry['detail']}"
        if entry.get("delta") and entry["delta"] != 0:
            line += f" (interest shift: {entry['delta']:+.0%})"
        if entry.get("keyPoint"):
            line += f' — key point: "{entry["keyPoint"]}"'
        timeline_lines.append(line)

    # Build discussion summary
    discussion_lines = []
    for d in ctx.get("discussions", []):
        discussion_lines.append(
            f'  Round {d["tick"]}: Talked with {d["partner_name"]} — '
            f'"{d["key_point"]}" (your interest shifted {d["delta"]:+.0%})'
        )

    # Build peer warnings summary
    warning_lines = []
    for w in ctx.get("peer_warnings", []):
        theme = w.get("theme", "")
        source = w.get("source_name", "someone")
        content = w.get("content", "")
        short = (content[:120] + "...") if len(content) > 120 else content
        delta = w.get("delta", 0)
        warning_lines.append(
            f'  Round {w.get("tick", "?")}: {source} shared a {theme} concern: '
            f'"{short}" (your interest dropped {abs(delta):.0%})'
        )

    # Build objections list
    objection_lines = ""
    if state.get("objections"):
        objection_lines = "\n".join(f"  - {o}" for o in state["objections"])

    return f"""You are {npc['name']}, a {npc['age']}-year-old {npc['occupation']}.
You are participating in a focus group discussion about a new product idea.

## Your Identity
- Income level: {npc.get('income_level', 'middle')}
- Communication style: {npc.get('communication_style', 'neutral')}
- Interests: {', '.join(npc.get('interests', []))}
- Values: {', '.join(npc.get('values', []))}
- Pain points: {', '.join(npc.get('pain_points', []))}

## Your Personality Traits
{chr(10).join(p_lines)}

## The Idea Being Discussed
- Name: {idea.get('title', 'Unknown')}
- Description: {idea.get('description', '')}
- Category: {idea.get('category', '')}
- Target audience: {idea.get('target_audience', '')}
- Price: {idea.get('price_point', 'not specified')}

## YOUR RECORDED STATE (this is ground truth — do NOT contradict any of this)
- Current stance: {state.get('stance', 'unaware')}
- Interest level: {state.get('interest_score', 0):.0%}
- Your reasoning: "{state.get('reasoning', 'No reasoning recorded')}"
- Emotional reaction: {state.get('emotional_reaction', 'neutral')}
- Would pay: {'yes' if state.get('would_pay') else 'no'}
{f'- Your objections:{chr(10)}{objection_lines}' if objection_lines else '- No objections recorded'}

## YOUR BELIEF TIMELINE (what actually happened to you in the simulation)
{chr(10).join(timeline_lines) if timeline_lines else '  No events recorded yet.'}

## YOUR DISCUSSIONS
{chr(10).join(discussion_lines) if discussion_lines else '  No discussions recorded.'}

## WHAT YOU'VE HEARD FROM OTHERS
{chr(10).join(warning_lines) if warning_lines else '  No one has shared concerns with you.'}

## Rules
1. Stay FULLY in character as {npc['name']}. Speak naturally in first person.
2. Your answer MUST be consistent with your recorded state above. If your stance is "skeptical", be skeptical. If "interested", be enthusiastic.
3. Reference your ACTUAL objections, reasoning, discussion experiences, and concerns you've heard from others — do not invent new ones.
4. Keep your response to 2-3 sentences. Be concise and natural.
5. If asked about something not covered by your recorded state, say you haven't thought about it yet rather than making something up.
6. Use language appropriate for your communication style and personality."""


def format_social_memory(
    peer_warnings: list,
    discussion_memories: list,
    objection_themes: list[str] | None = None,
) -> str:
    """Format an NPC's social memory for injection into discussion/ask_npc prompts.

    Accepts PeerWarning/DiscussionMemory dataclasses or plain dicts.
    Returns an empty string if no memories exist.
    """
    sections: list[str] = []

    if peer_warnings:
        lines = []
        for w in peer_warnings:
            tick = w.tick if hasattr(w, "tick") else w.get("tick", "?")
            source = w.source_name if hasattr(w, "source_name") else w.get("source_name", "someone")
            theme = w.theme if hasattr(w, "theme") else w.get("theme", "")
            content = w.content if hasattr(w, "content") else w.get("content", "")
            delta = w.delta if hasattr(w, "delta") else w.get("delta", 0)
            short = (content[:120] + "...") if len(content) > 120 else content
            lines.append(
                f'  Round {tick}: {source} raised a {theme} concern: '
                f'"{short}" (lowered your interest by {abs(delta):.0%})'
            )
        sections.append("What you've heard from others:\n" + "\n".join(lines))

    if discussion_memories:
        lines = []
        for d in discussion_memories:
            tick = d.tick if hasattr(d, "tick") else d.get("tick", "?")
            partner = d.partner_name if hasattr(d, "partner_name") else d.get("partner_name", "someone")
            key_point = d.key_point if hasattr(d, "key_point") else d.get("key_point", "")
            delta = d.my_delta if hasattr(d, "my_delta") else d.get("my_delta", 0)
            direction = "raised" if delta > 0 else "lowered"
            lines.append(
                f'  Round {tick}: Talked with {partner} — '
                f'"{key_point}" ({direction} your interest by {abs(delta):.0%})'
            )
        sections.append("Your past discussions:\n" + "\n".join(lines))

    if objection_themes:
        sections.append(f"Your main concerns: {', '.join(objection_themes)}")

    return "\n".join(sections) + "\n" if sections else ""


def format_persona_for_prompt(npc: dict) -> str:
    """Format a single NPC profile into a readable text block for prompts."""
    personality = npc.get("personality", {})
    archetype = npc.get("archetype", "")
    decision_style = npc.get("decision_style", "")

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
    return "\n".join(lines)


# ===========================================================================
# V2 Prompt Templates — LLM-primary scoring architecture
# ===========================================================================

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

V2_WORLD_BUILDER_USER = """## Product Idea

Title: {idea_title}
Description: {idea_description}
Category: {idea_category}
Stage: {idea_stage}
Target Audience: {target_audience}
Price Point: {price_point}
Existing Alternatives: {existing_alternatives}

## Task

Generate the shared world context for the category above. What does an average consumer already know about this market?

Return JSON:
{{
  "category_description": "1-2 sentence description of this product category from a consumer perspective",
  "key_players": ["brand or product name that consumers would recognize"],
  "market_maturity": "emerging | growing | mature | declining",
  "typical_price_range": "what consumers expect to pay (e.g. $10-$30/month)",
  "common_purchase_triggers": ["what makes someone buy in this category"],
  "common_complaints": ["what consumers commonly dislike about current options"],
  "switching_barriers": ["what stops people from trying something new"],
  "trend_awareness": "1-2 sentence summary of what consumers have heard lately about this category",
  "social_perception": "how is using/buying products in this category perceived socially",
  "trust_factors": ["what makes consumers trust a product in this category"]
}}"""

V2_NPC_ENRICHMENT_SYSTEM = """You are enriching simulated personas with pre-existing relationships to a product category.

Each persona already has a personality, archetype, income level, and interests. Your job is to give each persona a REALISTIC pre-existing relationship with the category BEFORE they encounter the new product.

Think about:
- What solution do they currently use (if any)?
- How satisfied are they with it?
- What price do they consider "normal" for this category?
- How familiar are they with the category?
- How open are they to trying something new?

Rules:
- Stay consistent with the persona's personality traits. A price-sensitive person should have a lower price anchor. A tech-savvy early adopter should have higher category familiarity.
- personal_connection must be 1 short sentence max (or null if none).
- pain_points must have 1-2 items, each under 15 words.
- satisfaction_level must be exactly one of: very_dissatisfied, dissatisfied, neutral, satisfied, very_satisfied
- category_familiarity must be exactly one of: unaware, heard_of_it, casual_user, regular_user, power_user
- openness_to_switch must be exactly one of: locked_in, reluctant, open_if_better, actively_looking
- Output valid JSON only. No markdown, no explanation."""

V2_NPC_ENRICHMENT_USER = """## Category
{idea_category}

## World Context
{world_context_block}

## Personas to Enrich

{personas_block}

## Task

For each persona, generate their pre-existing relationship with the category above.

Return a JSON array:
[
  {{
    "npc_id": "the persona's id",
    "current_solution": "what they currently use (e.g. brand name, generic description, or 'nothing')",
    "satisfaction_level": "very_dissatisfied | dissatisfied | neutral | satisfied | very_satisfied",
    "price_anchor": "what they consider a normal price (e.g. '$15/month', '$200')",
    "category_familiarity": "unaware | heard_of_it | casual_user | regular_user | power_user",
    "openness_to_switch": "locked_in | reluctant | open_if_better | actively_looking",
    "personal_connection": "1 short sentence about a personal experience with this category, or null",
    "pain_points": ["1-2 specific frustrations with their current solution, under 15 words each"]
  }}
]"""

V2_REACTION_SYSTEM = """You are simulating how different people react to a new product or idea.
You will receive persona profiles with their pre-existing category relationships, and a description of an idea.
For each persona, generate a realistic reaction INCLUDING a direct interest score.

## Interest Score Calibration Guide

- 0.00-0.10: Actively opposed. This product conflicts with their values or needs.
- 0.10-0.20: Very skeptical. See no reason this is better than what they have.
- 0.20-0.35: Mildly negative or indifferent. Might glance at it but would not engage.
- 0.35-0.50: Neutral with slight curiosity. Would read more but not commit.
- 0.50-0.65: Genuinely interested. Would try it, visit the website, consider a purchase.
- 0.65-0.80: Strongly interested. Would likely buy/sign up if convenient.
- 0.80-0.90: Very enthusiastic. Would actively seek it out and tell friends.
- 0.90-1.00: Extremely enthusiastic. Would pre-order, evangelize, and feel personally excited.

## Important Scoring Rules

- MOST reactions should cluster between 0.25 and 0.55. The average simulated population is mildly interested at best.
- Scores above 0.70 require STRONG justification: the persona must have a clear unmet need, high openness to switch, AND the product must directly address their pain points.
- Concept-stage ideas should rarely score above 0.60 — unproven products get skepticism by default.
- Always reference the persona's current_solution and price_anchor when scoring. A satisfied user of a competitor scores lower. A person whose price anchor is well below the asking price scores lower.
- Satisfied people with locked-in switching barriers should almost never score above 0.40.

Rules:
- Stay in character. A skeptic should be skeptical. An early adopter should be excited.
- Reference the persona's category context: their current solution, satisfaction, and pain points.
- Reactions should feel distinct across personas.
- reasoning must be 2 sentences MAX.
- objections must have 1-2 items, each under 15 words.
- emotional_reaction must be exactly one of: excited, intrigued, meh, doubtful, annoyed
- Output valid JSON only. No markdown, no explanation."""

V2_REACTION_USER = """## World Context
{world_context_summary}

## Idea Being Introduced

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
    "interest_score": 0.0 to 1.0 (use the calibration guide above),
    "reasoning": "2 sentences MAX explaining WHY this person feels this way, referencing their category context",
    "objections": ["1-2 specific concerns under 15 words each"],
    "would_pay": true or false,
    "would_recommend": true or false,
    "emotional_reaction": "excited | intrigued | meh | doubtful | annoyed"
  }}
]"""


def format_v2_persona_for_prompt(npc: dict) -> str:
    """Format a single NPC profile for V2 prompts, including category context.

    Like format_persona_for_prompt but adds a '--- Category Context ---' section
    when the npc dict contains a 'category_context' key with enrichment data
    from the Layer 2 NPC enrichment step.
    """
    personality = npc.get("personality", {})
    archetype = npc.get("archetype", "")
    decision_style = npc.get("decision_style", "")

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

    # Append category context from Layer 2 enrichment if available
    cat_ctx = npc.get("category_context")
    if cat_ctx and isinstance(cat_ctx, dict):
        lines.append("--- Category Context ---")
        lines.append(f"Current solution: {cat_ctx.get('current_solution', 'unknown')}")
        lines.append(f"Satisfaction: {cat_ctx.get('satisfaction_level', 'neutral')}")
        lines.append(f"Price anchor: {cat_ctx.get('price_anchor', 'unknown')}")
        lines.append(f"Familiarity: {cat_ctx.get('category_familiarity', 'unknown')}")
        lines.append(f"Openness to switch: {cat_ctx.get('openness_to_switch', 'unknown')}")
        if cat_ctx.get("personal_connection"):
            lines.append(f"Personal connection: {cat_ctx['personal_connection']}")
        pain_points = cat_ctx.get("pain_points", [])
        if pain_points:
            lines.append(f"Category pain points: {'; '.join(pain_points)}")

    return "\n".join(lines)
