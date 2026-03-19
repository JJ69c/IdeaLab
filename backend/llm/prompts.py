"""Prompt templates for NPC behavior and report generation."""

REACTION_SYSTEM = """You are simulating how different people react to a new product or idea.
You will receive a list of persona profiles and a description of an idea.
For each persona, generate a realistic reaction based on their personality, interests, and circumstances.

Rules:
- Stay in character for each persona. A skeptical person should be skeptical. An early adopter should be excited.
- Be specific. Reference the persona's actual interests and pain points.
- Reactions should feel distinct. Not everyone reacts the same way.
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
    "interest_score": 0.0 to 1.0,
    "stance": "interested" | "curious" | "indifferent" | "skeptical" | "opposed",
    "reasoning": "1-2 sentence explanation of WHY this person feels this way, referencing their specific traits",
    "objections": ["list of specific concerns, if any"],
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


ASSET_ANALYSIS_SYSTEM = """You are an expert product evaluator analyzing visual assets for a product idea.
You will see one or more images (screenshots, photos, mockups) representing a product.
For each dimension, rate 0.0 to 1.0 based on what you see. Be calibrated:
- 0.0-0.2: Poor/unprofessional
- 0.3-0.4: Below average
- 0.5: Average/acceptable
- 0.6-0.7: Good/solid
- 0.8-1.0: Excellent/exceptional

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


def build_extra_context(idea: dict, asset_signals: dict | None = None) -> str:
    """Build optional context lines from structured idea fields."""
    lines = []
    if idea.get("problem_statement"):
        lines.append(f"Problem it solves: {idea['problem_statement']}")
    if idea.get("existing_alternatives"):
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
    return (
        f"ID: {npc['id']}\n"
        f"Name: {npc['name']}, Age: {npc['age']}, Occupation: {npc['occupation']}\n"
        f"Income: {npc.get('income_level', 'middle')}\n"
        f"Personality: openness={personality.get('openness', 0.5)}, "
        f"skepticism={personality.get('skepticism', 0.5)}, "
        f"tech_savviness={personality.get('tech_savviness', 0.5)}, "
        f"price_sensitivity={personality.get('price_sensitivity', 0.5)}, "
        f"novelty_seeking={personality.get('novelty_seeking', 0.5)}\n"
        f"Interests: {', '.join(npc.get('interests', []))}\n"
        f"Values: {', '.join(npc.get('values', []))}\n"
        f"Pain points: {', '.join(npc.get('pain_points', []))}\n"
        f"Style: {npc.get('communication_style', 'neutral')}"
    )
