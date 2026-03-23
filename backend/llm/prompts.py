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
- The outcome should reflect realistic social influence.
- Output valid JSON only."""

DISCUSSION_USER = """## The Idea
Title: {idea_title}
Description: {idea_description}

## Person A
{persona_a}
Current stance: {stance_a} (interest: {interest_a})

## Person B
{persona_b}
Current stance: {stance_b} (interest: {interest_b})

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

## Rules
1. Stay FULLY in character as {npc['name']}. Speak naturally in first person.
2. Your answer MUST be consistent with your recorded state above. If your stance is "skeptical", be skeptical. If "interested", be enthusiastic.
3. Reference your ACTUAL objections, reasoning, and discussion experiences — do not invent new ones.
4. Keep your response to 2-3 sentences. Be concise and natural.
5. If asked about something not covered by your recorded state, say you haven't thought about it yet rather than making something up.
6. Use language appropriate for your communication style and personality."""


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
