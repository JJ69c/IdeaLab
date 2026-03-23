"""Reference asset analysis — extract structured signals from visual assets.

Converts uploaded images (screenshots, photos, mockups) into a structured
AssetSignals object via a single LLM vision call. These signals then feed
into both the ProductProfile (product-level) and per-NPC adjustments
(individual-level), so NPCs never react to raw images directly.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Mapping from file extension to MIME type for the vision API
_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


@dataclass(frozen=True)
class AssetSignals:
    """Structured signals extracted from reference assets via LLM vision.

    All float fields are 0-1. These are the dimensions that shape how NPCs
    perceive the product's visual presentation.
    """

    perceived_polish: float       # How professionally crafted does this look?
    trustworthiness: float        # Does this look legitimate and safe?
    clarity: float                # Is the value prop / purpose immediately clear?
    visual_appeal: float          # Is it aesthetically pleasing?
    premium_feel: float           # Premium vs. budget impression
    usability_impression: float   # Does it look easy/intuitive to use?
    differentiation_signal: float # Does it look distinct from typical products?
    summary: str                  # 1-2 sentence overall impression

    def to_dict(self) -> dict:
        return {
            "perceived_polish": round(self.perceived_polish, 3),
            "trustworthiness": round(self.trustworthiness, 3),
            "clarity": round(self.clarity, 3),
            "visual_appeal": round(self.visual_appeal, 3),
            "premium_feel": round(self.premium_feel, 3),
            "usability_impression": round(self.usability_impression, 3),
            "differentiation_signal": round(self.differentiation_signal, 3),
            "summary": self.summary,
        }


def load_image_as_content_block(file_path: str) -> dict | None:
    """Load an image file and return an Anthropic vision content block."""
    path = Path(file_path)
    if not path.exists():
        logger.warning("Asset file not found: %s", file_path)
        return None

    ext = path.suffix.lower()
    media_type = _MIME_TYPES.get(ext)
    if not media_type:
        logger.warning("Unsupported image type: %s", ext)
        return None

    data = path.read_bytes()
    b64 = base64.standard_b64encode(data).decode("ascii")

    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": b64,
        },
    }


def analyze_assets(
    asset_file_paths: list[str],
    asset_metadata: list[dict],
    idea: dict,
) -> AssetSignals | None:
    """Analyze reference assets via a single LLM vision call.

    Args:
        asset_file_paths: List of file paths to uploaded images.
        asset_metadata: List of dicts with keys: asset_type, url, note.
        idea: The idea dict (title, description, category, stage).

    Returns:
        AssetSignals if analysis succeeds, None if no valid images or LLM fails.
    """
    from backend.llm.client import llm_client

    # Build image content blocks
    image_blocks = []
    for fp in asset_file_paths:
        block = load_image_as_content_block(fp)
        if block:
            image_blocks.append(block)

    # Build asset description text
    descriptions = []
    for i, meta in enumerate(asset_metadata):
        desc = f"Asset {i + 1}: type={meta.get('asset_type', 'unknown')}"
        if meta.get("url"):
            desc += f", url={meta['url']}"
        if meta.get("note"):
            desc += f", note: {meta['note']}"
        descriptions.append(desc)

    # URL-only assets (no images uploaded) get a text-only analysis.
    # The LLM rates based on what the URL and description imply about
    # the product, without actually seeing visuals.
    has_urls = any(meta.get("url") for meta in asset_metadata)
    if not image_blocks and not has_urls:
        logger.info("No valid images or URLs to analyze")
        return None

    result = llm_client.analyze_assets(
        image_blocks=image_blocks,
        idea=idea,
        asset_descriptions="\n".join(descriptions),
    )

    if result is None:
        return None

    # Parse into AssetSignals with safety defaults
    try:
        return AssetSignals(
            perceived_polish=_clamp(result.get("perceived_polish", 0.5)),
            trustworthiness=_clamp(result.get("trustworthiness", 0.5)),
            clarity=_clamp(result.get("clarity", 0.5)),
            visual_appeal=_clamp(result.get("visual_appeal", 0.5)),
            premium_feel=_clamp(result.get("premium_feel", 0.5)),
            usability_impression=_clamp(result.get("usability_impression", 0.5)),
            differentiation_signal=_clamp(result.get("differentiation_signal", 0.5)),
            summary=result.get("summary", ""),
        )
    except Exception:
        logger.exception("Failed to parse asset analysis result")
        return None


def compute_asset_adjustment(signals: AssetSignals, personality: dict) -> float:
    """Per-NPC adjustment based on how visual assets land with this persona.

    Returns a delta in [-0.10, +0.10]. Smaller range than compute_npc_adjustment
    because assets are a secondary signal, not the primary evaluation.
    """
    delta = 0.0

    tech = personality.get("tech_savviness", 0.5)
    price_sens = personality.get("price_sensitivity", 0.5)
    skepticism = personality.get("skepticism", 0.5)
    openness = personality.get("openness", 0.5)

    # Tech-savvy people are more critical of visual polish.
    # High polish + high tech → boost (they appreciate craft).
    # Low polish + high tech → penalty (they notice flaws).
    polish_effect = (signals.perceived_polish - 0.5) * tech * 0.08
    delta += polish_effect

    # Premium feel vs price sensitivity.
    # Premium-looking + not price-sensitive → positive (feels quality).
    # Premium-looking + price-sensitive → slight negative (feels expensive).
    delta += signals.premium_feel * (1 - price_sens) * 0.06
    delta -= signals.premium_feel * price_sens * 0.04

    # Visual appeal is broadly positive, amplified by openness
    delta += signals.visual_appeal * openness * 0.05

    # Skeptics discount usability impressions from screenshots
    delta += signals.usability_impression * (1 - skepticism * 0.5) * 0.04

    return max(-0.10, min(0.10, round(delta, 4)))


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))
