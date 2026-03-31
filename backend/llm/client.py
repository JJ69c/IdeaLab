"""LLM client wrapper for Claude API calls with batching and structured output."""

from __future__ import annotations

import json
import logging
import time

import anthropic

from backend.config import settings

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0   # seconds; doubles each retry → 1s, 2s, 4s
RETRY_MAX_DELAY = 8.0


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences that LLMs sometimes wrap around JSON."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (and optional language tag like ```json)
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[: cleaned.rfind("```")]
        cleaned = cleaned.strip()
    return cleaned


class LLMClient:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def _call(
        self, system: str, user: str, model: str | None = None, max_tokens: int = 4096
    ) -> str:
        """Make a single LLM call with retry on transient failures."""
        model = model or settings.reaction_model
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return response.content[0].text
            except (
                anthropic.APITimeoutError,
                anthropic.RateLimitError,
                anthropic.InternalServerError,
                anthropic.APIConnectionError,
            ) as exc:
                last_exc = exc
                delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
                logger.warning(
                    "LLM call failed (attempt %d/%d, retrying in %.1fs): %s",
                    attempt + 1, MAX_RETRIES, delay, exc,
                )
                time.sleep(delay)
        raise last_exc  # type: ignore[misc]

    def _call_json(
        self, system: str, user: str, model: str | None = None, max_tokens: int = 4096
    ) -> dict | list:
        """Make an LLM call and parse the response as JSON with retry on parse failure."""
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                raw = self._call(system, user, model, max_tokens)
                cleaned = _strip_markdown_fences(raw)
                return json.loads(cleaned)
            except json.JSONDecodeError as exc:
                last_exc = exc
                logger.warning(
                    "JSON parse failed (attempt %d/%d): %s — raw[:200]: %s",
                    attempt + 1, MAX_RETRIES, exc, raw[:200] if raw else "",
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY)
        raise last_exc  # type: ignore[misc]

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
        memory_a: str = "",
        memory_b: str = "",
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
            memory_a=memory_a,
            memory_b=memory_b,
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
        archetype_breakdown: list[dict] | None = None,
        convergence: dict | None = None,
        competitor_profiles: list[dict] | None = None,
    ) -> dict:
        """Generate the final structured analysis report using the stronger model."""
        from backend.llm.prompts import REPORT_SYSTEM, REPORT_USER

        metrics_block = "\n".join(f"- {k}: {v}" for k, v in metrics.items())
        npc_results_block = json.dumps(npc_results, indent=2)
        discussions_block = json.dumps(discussions[:15], indent=2)  # cap for token budget

        # Build optional context sections
        extra_sections = ""
        if archetype_breakdown:
            extra_sections += "\n## Per-Archetype Breakdown\n"
            for ab in archetype_breakdown:
                extra_sections += (
                    f"- {ab['archetype']} (n={ab['count']}): "
                    f"mean_interest={ab['mean_interest']}, "
                    f"adoption={ab['adoption_rate']:.0%} "
                    f"({ab['adopted_count']}/{ab['aware_count']} aware)\n"
                )
        if convergence:
            extra_sections += "\n## Convergence Analysis\n"
            extra_sections += json.dumps(convergence, indent=2) + "\n"
        if competitor_profiles:
            extra_sections += "\n## Competitor Intelligence\n"
            for cp in competitor_profiles:
                if cp.get("exists"):
                    extra_sections += (
                        f"- {cp['name']}: {cp.get('positioning', 'N/A')} "
                        f"(price: {cp.get('pricing', 'unknown')}, "
                        f"presence: {cp.get('market_presence', 'unknown')})\n"
                    )

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
        # Append extra context after the formatted prompt
        if extra_sections:
            prompt += "\n" + extra_sections

        return self._call_json(
            REPORT_SYSTEM, prompt, model=settings.report_model, max_tokens=4096
        )

    def generate_business_plan(
        self,
        idea: dict,
        report: dict,
        config: dict,
        engine_version: str = "v1",
    ) -> dict:
        """Generate a structured business plan from simulation results."""
        from backend.llm.prompts import BUSINESS_PLAN_SYSTEM, BUSINESS_PLAN_USER

        metrics = report.get("metrics", {})
        analysis = report.get("analysis", {})
        npc_results = report.get("npc_results", [])
        adoption = report.get("adoption_breakdown", {})

        metrics_block = "\n".join(f"- {k}: {v}" for k, v in metrics.items())

        adoption_block = "No adoption data available."
        if adoption:
            blockers = adoption.get('top_blockers', [])
            blocker_parts = [f"{b['blocker']} ({b['count']} NPCs)" for b in blockers]
            adoption_block = (
                f"- Adoption rate: {adoption.get('adoption_rate', 0):.0%}\n"
                f"- Adopted: {adoption.get('adopted_count', 0)}/{adoption.get('aware_count', 0)} aware\n"
                f"- Top blockers: {', '.join(blocker_parts)}"
            )

        # Compact NPC summaries — only aware NPCs (unaware ones add no signal)
        npc_summaries = []
        for n in npc_results:
            if n.get("stance") == "unaware":
                continue
            summary = {
                "name": n.get("name"),
                "archetype": n.get("archetype", "unknown"),
                "interest": n.get("interest_score"),
                "stance": n.get("stance"),
                "would_pay": n.get("would_pay"),
                "adopted": n.get("adopted"),
                "objections": n.get("objections", []),
                "reasoning": n.get("reasoning", "")[:150],
            }
            npc_summaries.append(summary)

        objections_block = "None recorded."
        top_obj = analysis.get("top_objections", [])
        if top_obj:
            objections_block = "\n".join(
                f"- [{o['severity']}] {o['objection']} ({o['frequency']} NPCs)"
                for o in top_obj
            )

        segments_block = "None identified."
        segments = analysis.get("segments", [])
        if segments:
            segments_block = "\n".join(
                f"- {s['name']} ({s['size']} NPCs): {s['typical_reaction']} — driver: {s.get('key_driver', 'N/A')}"
                for s in segments
            )

        # Extra context sections
        extra_sections = ""
        archetype_breakdown = report.get("archetype_breakdown", [])
        if archetype_breakdown:
            extra_sections += "### Archetype Breakdown\n"
            for ab in archetype_breakdown:
                extra_sections += (
                    f"- {ab['archetype']} (n={ab['count']}): "
                    f"mean_interest={ab['mean_interest']}, "
                    f"adoption={ab.get('adoption_rate', 0):.0%}\n"
                )

        convergence = report.get("convergence", {})
        if convergence and convergence.get("final_state"):
            fs = convergence["final_state"]
            extra_sections += f"\n### Convergence\n- Result: {fs.get('result_class', 'unknown')}, polarized={fs.get('polarized', False)}, converged={fs.get('converged', False)}\n"

        competitor_profiles = report.get("competitor_profiles", [])
        if competitor_profiles:
            extra_sections += "\n### Competitor Intelligence\n"
            for cp in competitor_profiles:
                if cp.get("exists"):
                    extra_sections += (
                        f"- {cp['name']}: {cp.get('positioning', 'N/A')} "
                        f"(price: {cp.get('pricing', 'unknown')}, "
                        f"presence: {cp.get('market_presence', 'unknown')})\n"
                    )

        prompt = BUSINESS_PLAN_USER.format(
            idea_title=idea.get("title", ""),
            idea_description=idea.get("description", ""),
            idea_category=idea.get("category", "general"),
            stage=idea.get("stage", "concept"),
            target_audience=idea.get("target_audience", "general public"),
            price_point=idea.get("price_point", "not specified"),
            monetization_approach=idea.get("monetization_approach", "not specified"),
            differentiator=idea.get("differentiator", ""),
            known_strengths=idea.get("known_strengths", ""),
            known_risks=idea.get("known_risks", ""),
            existing_alternatives=idea.get("existing_alternatives", ""),
            population_size=config.get("population_size", 30),
            num_ticks=config.get("num_ticks", 8),
            engine_version=engine_version,
            metrics_block=metrics_block,
            adoption_block=adoption_block,
            npc_results_block=json.dumps(npc_summaries, indent=2),
            objections_block=objections_block,
            segments_block=segments_block,
            extra_sections=extra_sections,
        )

        return self._call_json_v2(
            BUSINESS_PLAN_SYSTEM, prompt, model=settings.report_model, max_tokens=6000
        )

    # ── V2 Methods ───────────────────────────────────────────────────────

    def _call_with_metadata(
        self,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> tuple[str, str]:
        """Like _call but also returns stop_reason. Returns (text, stop_reason)."""
        model = model or settings.reaction_model
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return response.content[0].text, response.stop_reason
            except (
                anthropic.APITimeoutError,
                anthropic.RateLimitError,
                anthropic.InternalServerError,
                anthropic.APIConnectionError,
            ) as exc:
                last_exc = exc
                delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
                logger.warning(
                    "LLM call failed (attempt %d/%d, retrying in %.1fs): %s",
                    attempt + 1, MAX_RETRIES, delay, exc,
                )
                time.sleep(delay)
        raise last_exc  # type: ignore[misc]

    def _repair_truncated_json(self, raw: str) -> dict | list:
        """Attempt to repair truncated JSON from max_tokens cutoff.

        Strategy 1: Use raw_decode to find the longest valid JSON prefix.
        Strategy 2: For arrays, extract complete objects one by one.
        Raises json.JSONDecodeError if nothing is recoverable.
        """
        decoder = json.JSONDecoder()

        # Strategy 1: try to decode a complete top-level value from the start
        try:
            obj, _ = decoder.raw_decode(raw.strip())
            logger.warning("Repaired truncated JSON via raw_decode (strategy 1)")
            return obj
        except json.JSONDecodeError:
            pass

        # Strategy 2: for arrays, extract complete objects one by one
        stripped = raw.strip()
        if stripped.startswith("["):
            items: list = []
            # Skip past the opening bracket
            idx = 1
            while idx < len(stripped):
                # Skip whitespace and commas
                while idx < len(stripped) and stripped[idx] in " \t\r\n,":
                    idx += 1
                if idx >= len(stripped) or stripped[idx] == "]":
                    break
                try:
                    obj, end = decoder.raw_decode(stripped, idx)
                    items.append(obj)
                    idx = end
                except json.JSONDecodeError:
                    # Hit the truncated part, stop here
                    break

            if items:
                logger.warning(
                    "Repaired truncated JSON array: recovered %d complete objects",
                    len(items),
                )
                return items

        raise json.JSONDecodeError(
            "Could not recover any valid JSON from truncated response",
            raw,
            0,
        )

    def _call_json_v2(
        self,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> dict | list:
        """V2 JSON call with truncation detection and repair."""
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            raw = ""
            try:
                raw, stop_reason = self._call_with_metadata(
                    system, user, model, max_tokens,
                )
                if stop_reason == "max_tokens":
                    logger.warning(
                        "Response truncated (max_tokens=%d), attempting repair",
                        max_tokens,
                    )
                    return self._repair_truncated_json(raw)
                cleaned = _strip_markdown_fences(raw)
                return json.loads(cleaned)
            except json.JSONDecodeError as exc:
                last_exc = exc
                logger.warning(
                    "JSON parse failed (attempt %d/%d): %s — raw[:200]: %s",
                    attempt + 1, MAX_RETRIES, exc, raw[:200] if raw else "",
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY)
        raise last_exc  # type: ignore[misc]

    def build_world_context(self, idea: dict):
        """Layer 1: Generate structured market context for V2 simulation."""
        from backend.llm.prompts import V2_WORLD_BUILDER_SYSTEM, V2_WORLD_BUILDER_USER
        from backend.simulation.world_builder import WorldContext

        try:
            prompt = V2_WORLD_BUILDER_USER.format(
                idea_title=idea.get("title", ""),
                idea_description=idea.get("description", ""),
                idea_category=idea.get("category", "general"),
                idea_stage=idea.get("stage", "concept"),
                target_audience=idea.get("target_audience", "general public"),
                price_point=idea.get("price_point", "not specified"),
                existing_alternatives=idea.get("existing_alternatives", "none listed"),
            )

            # Use default model (Haiku) — world context is factual/structural,
            # doesn't need Sonnet-level reasoning. ~70% cost savings.
            result = self._call_json_v2(
                V2_WORLD_BUILDER_SYSTEM,
                prompt,
                max_tokens=2048,
            )

            if not isinstance(result, dict):
                logger.warning(
                    "build_world_context expected dict, got %s; using default",
                    type(result),
                )
                return WorldContext.default()

            return WorldContext(**result)
        except Exception:
            logger.exception("build_world_context failed, returning default")
            return WorldContext.default()

    def enrich_npcs(
        self,
        npc_profiles: list[dict],
        world_context: dict,
        idea: dict,
    ) -> list[dict]:
        """Layer 2: Generate pre-existing category relationships for each NPC."""
        from backend.llm.prompts import (
            V2_NPC_ENRICHMENT_SYSTEM,
            V2_NPC_ENRICHMENT_USER,
            format_v2_persona_for_prompt,
        )

        world_block = "\n".join(f"- {k}: {v}" for k, v in world_context.items())
        personas_block = "\n---\n".join(
            format_v2_persona_for_prompt(npc) for npc in npc_profiles
        )

        prompt = V2_NPC_ENRICHMENT_USER.format(
            idea_title=idea.get("title", ""),
            idea_description=idea.get("description", ""),
            idea_category=idea.get("category", "general"),
            world_context_block=world_block,
            personas_block=personas_block,
        )

        dynamic_max_tokens = max(1024, len(npc_profiles) * 350)

        try:
            result = self._call_json_v2(
                V2_NPC_ENRICHMENT_SYSTEM, prompt, max_tokens=dynamic_max_tokens,
            )
            if not isinstance(result, list):
                logger.warning(
                    "enrich_npcs expected list, got %s", type(result),
                )
                return []
            return result
        except Exception:
            logger.exception("enrich_npcs failed")
            return []

    def v2_batch_react(
        self,
        enriched_profiles: list[dict],
        idea: dict,
        world_context: dict,
    ) -> list[dict]:
        """Layer 3: Get V2 reactions where LLM generates interest_score directly."""
        from backend.llm.prompts import (
            V2_REACTION_SYSTEM,
            V2_REACTION_USER,
            build_extra_context,
            format_v2_persona_for_prompt,
        )

        world_summary = "\n".join(f"- {k}: {v}" for k, v in world_context.items())
        personas_block = "\n---\n".join(
            format_v2_persona_for_prompt(npc) for npc in enriched_profiles
        )

        prompt = V2_REACTION_USER.format(
            idea_title=idea.get("title", ""),
            idea_description=idea.get("description", ""),
            idea_category=idea.get("category", "general"),
            idea_stage=idea.get("stage", "concept"),
            target_audience=idea.get("target_audience", "general public"),
            price_point=idea.get("price_point", "not specified"),
            extra_context=build_extra_context(idea),
            world_context_summary=world_summary,
            personas_block=personas_block,
        )

        dynamic_max_tokens = max(2048, len(enriched_profiles) * 600)

        try:
            result = self._call_json_v2(
                V2_REACTION_SYSTEM, prompt, max_tokens=dynamic_max_tokens,
            )
            if not isinstance(result, list):
                logger.warning(
                    "v2_batch_react expected list, got %s", type(result),
                )
                return []
            return result
        except Exception:
            logger.exception("v2_batch_react failed")
            return []


    # ------------------------------------------------------------------
    # Competitor enrichment
    # ------------------------------------------------------------------

    def enrich_competitors(self, idea: dict, alternatives_raw: str) -> list[dict]:
        """Enrich a comma-separated list of alternatives into structured competitor profiles.

        Returns a list of dicts, one per competitor.  Falls back to an empty
        list on failure so the simulation can still proceed.
        """
        from backend.llm.prompts import (
            COMPETITOR_ENRICHMENT_SYSTEM,
            COMPETITOR_ENRICHMENT_USER,
        )

        alternatives = alternatives_raw.strip()
        if not alternatives:
            return []

        try:
            prompt = COMPETITOR_ENRICHMENT_USER.format(
                idea_title=idea.get("title", ""),
                idea_category=idea.get("category", "general"),
                idea_description=idea.get("description", ""),
                price_point=idea.get("price_point", "not specified"),
                alternatives=alternatives,
            )

            # Use default model (Haiku) — competitor verification is factual,
            # doesn't need Sonnet-level reasoning. ~70% cost savings.
            result = self._call_json(
                COMPETITOR_ENRICHMENT_SYSTEM,
                prompt,
                max_tokens=2048,
            )

            if isinstance(result, list):
                return result
            logger.warning(
                "enrich_competitors expected list, got %s; returning empty",
                type(result),
            )
            return []
        except Exception:
            logger.exception("enrich_competitors failed, returning empty list")
            return []


# Singleton
llm_client = LLMClient()
