"""LLM client wrapper for Claude API calls with batching and structured output."""

from __future__ import annotations

import json
import logging

import anthropic

from backend.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def _call(
        self, system: str, user: str, model: str | None = None, max_tokens: int = 4096
    ) -> str:
        """Make a single LLM call and return the text response."""
        model = model or settings.reaction_model
        response = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text

    def _call_json(
        self, system: str, user: str, model: str | None = None, max_tokens: int = 4096
    ) -> dict | list:
        """Make an LLM call and parse the response as JSON."""
        raw = self._call(system, user, model, max_tokens)
        # Strip markdown fences if the model wraps output
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            if cleaned.endswith("```"):
                cleaned = cleaned[: cleaned.rfind("```")]
            cleaned = cleaned.strip()
        return json.loads(cleaned)

    def batch_react(
        self, npc_profiles: list[dict], idea: dict,
        asset_signals_dict: dict | None = None,
        competition_context_dict: dict | None = None,
    ) -> list[dict]:
        """Get reactions for a batch of NPCs to an idea. Returns list of reaction dicts."""
        from backend.llm.prompts import (
            REACTION_SYSTEM,
            REACTION_USER,
            build_extra_context,
            format_persona_for_prompt,
        )

        personas_block = "\n---\n".join(
            format_persona_for_prompt(npc) for npc in npc_profiles
        )

        prompt = REACTION_USER.format(
            idea_title=idea.get("title", ""),
            idea_description=idea.get("description", ""),
            idea_category=idea.get("category", "general"),
            idea_stage=idea.get("stage", "concept"),
            target_audience=idea.get("target_audience", "general public"),
            price_point=idea.get("price_point", "not specified"),
            extra_context=build_extra_context(
                idea,
                asset_signals=asset_signals_dict,
                competition_context=competition_context_dict,
            ),
            personas_block=personas_block,
        )

        result = self._call_json(REACTION_SYSTEM, prompt)
        if not isinstance(result, list):
            logger.warning("Expected list from batch_react, got %s", type(result))
            return []
        return result

    def simulate_discussion(
        self,
        npc_a: dict,
        npc_b: dict,
        idea: dict,
        stance_a: str,
        interest_a: float,
        stance_b: str,
        interest_b: float,
        trust_level: float,
    ) -> dict:
        """Simulate a discussion between two NPCs about an idea."""
        from backend.llm.prompts import (
            DISCUSSION_SYSTEM,
            DISCUSSION_USER,
            format_persona_for_prompt,
        )

        prompt = DISCUSSION_USER.format(
            idea_title=idea.get("title", ""),
            idea_description=idea.get("description", ""),
            persona_a=format_persona_for_prompt(npc_a),
            persona_b=format_persona_for_prompt(npc_b),
            stance_a=stance_a,
            interest_a=interest_a,
            stance_b=stance_b,
            interest_b=interest_b,
            trust_level=trust_level,
        )

        result = self._call_json(DISCUSSION_SYSTEM, prompt)
        if not isinstance(result, dict):
            logger.warning("Expected dict from discussion, got %s", type(result))
            return {"outcome": {"a_interest_delta": 0, "b_interest_delta": 0}}
        return result

    def ask_npc(self, system_prompt: str, question: str) -> str:
        """Ask an NPC a question using a grounded system prompt. Returns plain text."""
        return self._call(system_prompt, question, max_tokens=300)

    def analyze_assets(
        self,
        image_blocks: list[dict],
        idea: dict,
        asset_descriptions: str,
    ) -> dict | None:
        """Analyze reference asset images via a single vision call.

        Args:
            image_blocks: List of Anthropic image content blocks (base64-encoded).
            idea: The idea dict for context.
            asset_descriptions: Text listing each asset's type, URL, and note.

        Returns:
            Parsed JSON dict with signal dimensions, or None on failure.
        """
        from backend.llm.prompts import ASSET_ANALYSIS_SYSTEM, ASSET_ANALYSIS_USER

        prompt_text = ASSET_ANALYSIS_USER.format(
            idea_title=idea.get("title", ""),
            idea_description=idea.get("description", ""),
            idea_category=idea.get("category", "general"),
            idea_stage=idea.get("stage", "concept"),
            asset_descriptions=asset_descriptions,
        )

        # Build content array: images first (if any), then the text prompt.
        # When no images are provided (URL-only assets), this becomes a
        # text-only call — the LLM rates based on asset descriptions alone.
        content: list[dict] = []
        for block in image_blocks:
            content.append(block)
        content.append({"type": "text", "text": prompt_text})

        try:
            response = self.client.messages.create(
                model=settings.asset_analysis_model,
                max_tokens=1024,
                system=ASSET_ANALYSIS_SYSTEM,
                messages=[{"role": "user", "content": content}],
            )
            raw = response.content[0].text
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
                if cleaned.endswith("```"):
                    cleaned = cleaned[: cleaned.rfind("```")]
                cleaned = cleaned.strip()
            result = json.loads(cleaned)
            if not isinstance(result, dict):
                logger.warning("Asset analysis returned non-dict: %s", type(result))
                return None
            logger.info("Asset analysis complete: %s", result.get("summary", "")[:80])
            return result
        except Exception:
            logger.exception("Asset analysis LLM call failed")
            return None

    def generate_comparison_explanation(
        self,
        changed_fields_detail: list[dict],
        metrics_delta: dict,
        archetype_comparison: list[dict],
        parent_summary: str,
        variant_summary: str,
    ) -> dict:
        """Generate an LLM explanation of WHY a variant produced different results."""
        from backend.llm.prompts import (
            COMPARISON_EXPLANATION_SYSTEM,
            format_comparison_explanation_prompt,
        )

        prompt = format_comparison_explanation_prompt(
            changed_fields_detail=changed_fields_detail,
            metrics_delta=metrics_delta,
            archetype_comparison=archetype_comparison,
            parent_summary=parent_summary,
            variant_summary=variant_summary,
        )

        result = self._call_json(
            COMPARISON_EXPLANATION_SYSTEM, prompt, max_tokens=1024,
        )
        if not isinstance(result, dict):
            logger.warning("Expected dict from comparison explanation, got %s", type(result))
            return {"verdict": "Explanation generation failed.", "key_drivers": [], "segment_shifts": [], "recommendation": ""}
        return result

    def generate_report(
        self,
        idea: dict,
        metrics: dict,
        npc_results: list[dict],
        discussions: list[dict],
        num_ticks: int,
        population_size: int,
    ) -> dict:
        """Generate the final structured analysis report using the stronger model."""
        from backend.llm.prompts import REPORT_SYSTEM, REPORT_USER

        metrics_block = "\n".join(f"- {k}: {v}" for k, v in metrics.items())
        npc_results_block = json.dumps(npc_results, indent=2)
        discussions_block = json.dumps(discussions[:15], indent=2)  # cap for token budget

        prompt = REPORT_USER.format(
            idea_title=idea.get("title", ""),
            idea_description=idea.get("description", ""),
            idea_category=idea.get("category", "general"),
            population_size=population_size,
            num_ticks=num_ticks,
            metrics_block=metrics_block,
            npc_results_block=npc_results_block,
            discussions_block=discussions_block,
        )

        return self._call_json(
            REPORT_SYSTEM, prompt, model=settings.report_model, max_tokens=4096
        )


# Singleton
llm_client = LLMClient()
