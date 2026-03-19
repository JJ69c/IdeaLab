"""NPC browsing routes."""

from fastapi import APIRouter

from backend.api.schemas.responses import NpcSummary
from backend.simulation.world import load_population

router = APIRouter(prefix="/api/npcs", tags=["npcs"])


@router.get("", response_model=list[NpcSummary])
async def list_npcs():
    """List all available NPC templates."""
    npcs = load_population()
    return [
        NpcSummary(
            id=npc.id,
            name=npc.name,
            age=npc.age,
            occupation=npc.occupation,
            income_level=npc.income_level,
            interests=npc.interests,
            personality_summary=(
                f"openness={npc.personality.openness}, "
                f"skepticism={npc.personality.skepticism}, "
                f"tech={npc.personality.tech_savviness}, "
                f"influence={npc.personality.social_influence}"
            ),
        )
        for npc in npcs
    ]


@router.get("/{npc_id}")
async def get_npc(npc_id: str):
    """Get full profile for a single NPC."""
    npcs = load_population()
    for npc in npcs:
        if npc.id == npc_id:
            return npc.to_profile_dict()
    return {"error": "NPC not found"}
