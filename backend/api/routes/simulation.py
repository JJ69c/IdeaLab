"""Simulation API routes — create, stream, and retrieve simulations."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.schemas.requests import AskNpcRequest, AssetReference, CreateSimulationRequest
from backend.api.schemas.responses import AskNpcResponse, SimulationDetail, SimulationSummary
from backend.db.database import SyncSession, async_session, get_db
from backend.db.models import Asset, SimulationEvent, SimulationRecord
from backend.simulation.engine import run_simulation
from backend.simulation.streamer import event_store
from backend.simulation.world import InjectedIdea, SimConfig

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/simulations", tags=["simulations"])


# ---------------------------------------------------------------------------
# POST — Create simulation (starts in background, returns immediately)
# ---------------------------------------------------------------------------

@router.post("", response_model=SimulationDetail)
async def create_simulation(
    request: CreateSimulationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a simulation and start it in the background.

    Returns immediately with status='running'. Use the SSE stream endpoint
    to watch events live, or poll GET /{id} until status='completed'.
    """
    record = SimulationRecord(
        idea_title=request.idea.title,
        idea_description=request.idea.description,
        idea_category=request.idea.category,
        idea_metadata={
            "target_audience": request.idea.target_audience,
            "price_point": request.idea.price_point,
        },
        config=request.config.model_dump(),
        status="running",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    sim_id = record.id
    idea = InjectedIdea(
        title=request.idea.title,
        description=request.idea.description,
        category=request.idea.category,
        stage=request.idea.stage,
        target_audience=request.idea.target_audience,
        problem_statement=request.idea.problem_statement,
        price_point=request.idea.price_point,
        existing_alternatives=request.idea.existing_alternatives,
        differentiator=request.idea.differentiator,
        known_strengths=request.idea.known_strengths,
        known_risks=request.idea.known_risks,
    )
    config = SimConfig(
        num_ticks=request.config.num_ticks,
        population_size=request.config.population_size,
        seed_count=request.config.seed_count,
    )

    # Resolve asset references to file paths for the background thread
    asset_file_paths: list[str] = []
    asset_metadata: list[dict] = []
    if request.asset_refs:
        sync_db = SyncSession()
        try:
            for ref in request.asset_refs:
                asset = sync_db.get(Asset, ref.asset_id)
                if asset and asset.file_path:
                    asset_file_paths.append(asset.file_path)
                    asset_metadata.append({
                        "asset_type": ref.asset_type,
                        "url": ref.url,
                        "note": ref.note,
                    })
        finally:
            sync_db.close()

    # Pre-register so SSE clients can connect before first emit
    event_store.register(sim_id)

    # Launch simulation in a background thread
    thread = threading.Thread(
        target=_run_simulation_thread,
        args=(sim_id, idea, config, asset_file_paths, asset_metadata),
        daemon=True,
    )
    thread.start()

    return SimulationDetail(
        id=record.id,
        idea_title=record.idea_title,
        idea_description=record.idea_description,
        idea_category=record.idea_category,
        config=record.config,
        status="running",
        created_at=record.created_at,
    )


def _run_simulation_thread(
    sim_id: str,
    idea: InjectedIdea,
    config: SimConfig,
    asset_file_paths: list[str] | None = None,
    asset_metadata: list[dict] | None = None,
):
    """Run the simulation in a background thread.

    Events are dual-written: pushed to the in-memory store for live SSE
    streaming AND persisted to the database for replay after restart.
    DB writes are committed at tick boundaries for crash resilience.
    """
    db_session = SyncSession()

    def emit(event: dict):
        # In-memory push for live SSE
        event_store.push(sim_id, event)
        # Persist to DB for replay
        try:
            db_event = SimulationEvent(
                simulation_id=sim_id,
                tick=event.get("tick", 0),
                npc_id=event.get("data", {}).get("npc_id"),
                event_type=event["type"],
                data=event,
            )
            db_session.add(db_event)
            # Commit at tick boundaries for crash resilience
            if event["type"] in ("tick_end", "simulation_complete", "error"):
                db_session.commit()
        except Exception:
            logger.warning("Failed to persist event for sim %s", sim_id, exc_info=True)

    try:
        # Analyze reference assets before simulation (single LLM vision call)
        asset_signals = None
        if asset_file_paths:
            from backend.simulation.asset_signals import analyze_assets
            logger.info("Analyzing %d reference assets for sim %s", len(asset_file_paths), sim_id)
            asset_signals = analyze_assets(
                asset_file_paths=asset_file_paths,
                asset_metadata=asset_metadata or [],
                idea=idea.to_dict(),
            )
            if asset_signals:
                logger.info("Asset signals: %s", asset_signals.to_dict())

        report = run_simulation(idea, config, emit=emit, asset_signals=asset_signals)

        # Final commit for any unflushed events
        db_session.commit()

        # Persist report to the simulation record
        record = db_session.get(SimulationRecord, sim_id)
        if record:
            record.status = "completed"
            record.completed_at = datetime.now(timezone.utc)
            record.report = report
            record.summary = report.get("analysis", {}).get("executive_summary", "")
            record.metrics = report.get("metrics", {})
            db_session.commit()

        logger.info("Simulation %s completed successfully", sim_id)

    except Exception:
        logger.exception("Simulation %s failed", sim_id)
        db_session.rollback()
        emit({"type": "error", "tick": 0, "data": {"message": "Simulation failed"}})
        db_session.commit()

        try:
            record = db_session.get(SimulationRecord, sim_id)
            if record:
                record.status = "failed"
                db_session.commit()
        except Exception:
            logger.warning("Failed to mark sim %s as failed", sim_id, exc_info=True)
    finally:
        db_session.close()
        event_store.mark_complete(sim_id)


# ---------------------------------------------------------------------------
# GET /stream — Server-Sent Events for live simulation watching
# ---------------------------------------------------------------------------

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.get("/{simulation_id}/stream")
async def stream_simulation(
    simulation_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Stream simulation events via SSE.

    Live mode: streams from in-memory store for running simulations.
    Replay mode: streams persisted events from DB for completed simulations.
    """
    # Live mode — in-memory store has this simulation
    if event_store.has_simulation(simulation_id):
        return StreamingResponse(
            _live_event_generator(simulation_id),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )

    # No in-memory data — check the database
    result = await db.execute(
        select(SimulationRecord).where(SimulationRecord.id == simulation_id)
    )
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="Simulation not found")

    if record.status in ("completed", "failed"):
        # Replay mode — serve persisted events from DB
        return StreamingResponse(
            _replay_event_generator(simulation_id),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )

    # Running but no in-memory data (server restarted mid-simulation)
    raise HTTPException(
        status_code=409,
        detail="Simulation is running but event stream unavailable (server restarted)",
    )


async def _live_event_generator(simulation_id: str):
    """Yield events from the in-memory store as they arrive."""
    cursor = 0
    while True:
        events = event_store.get_events_from(simulation_id, cursor)
        if events:
            for event in events:
                yield f"data: {json.dumps(event)}\n\n"
                cursor += 1
        elif event_store.is_complete(simulation_id):
            break
        else:
            await asyncio.sleep(0.3)


async def _replay_event_generator(simulation_id: str):
    """Yield persisted events from the database for replay.

    Uses its own async session to avoid dependency lifecycle issues
    with StreamingResponse.
    """
    async with async_session() as db:
        result = await db.execute(
            select(SimulationEvent)
            .where(SimulationEvent.simulation_id == simulation_id)
            .order_by(SimulationEvent.id)
        )
        db_events = result.scalars().all()

    for db_event in db_events:
        yield f"data: {json.dumps(db_event.data)}\n\n"
        # Small delay so the frontend can animate the replay
        await asyncio.sleep(0.05)


# ---------------------------------------------------------------------------
# GET endpoints — list, detail, report, events
# ---------------------------------------------------------------------------

@router.get("", response_model=list[SimulationSummary])
async def list_simulations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SimulationRecord).order_by(SimulationRecord.created_at.desc()).limit(50)
    )
    records = result.scalars().all()
    return [
        SimulationSummary(
            id=r.id, idea_title=r.idea_title, status=r.status,
            created_at=r.created_at, completed_at=r.completed_at, metrics=r.metrics,
        )
        for r in records
    ]


@router.get("/{simulation_id}", response_model=SimulationDetail)
async def get_simulation(simulation_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SimulationRecord).where(SimulationRecord.id == simulation_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return SimulationDetail(
        id=record.id, idea_title=record.idea_title,
        idea_description=record.idea_description, idea_category=record.idea_category,
        config=record.config, status=record.status,
        created_at=record.created_at, completed_at=record.completed_at,
        report=record.report, summary=record.summary, metrics=record.metrics,
    )


@router.get("/{simulation_id}/report")
async def get_report(simulation_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SimulationRecord).where(SimulationRecord.id == simulation_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if record.status != "completed":
        raise HTTPException(status_code=400, detail=f"Simulation status: {record.status}")
    return record.report


@router.get("/{simulation_id}/events")
async def get_events(
    simulation_id: str,
    tick: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(SimulationEvent).where(
        SimulationEvent.simulation_id == simulation_id
    )
    if tick is not None:
        query = query.where(SimulationEvent.tick == tick)
    query = query.order_by(SimulationEvent.id)

    result = await db.execute(query)
    events = result.scalars().all()
    return [
        {"id": e.id, "tick": e.tick, "npc_id": e.npc_id,
         "event_type": e.event_type, "data": e.data}
        for e in events
    ]


# ---------------------------------------------------------------------------
# POST — Ask an NPC a question (grounded in simulation state)
# ---------------------------------------------------------------------------

@router.post("/{simulation_id}/ask-npc", response_model=AskNpcResponse)
async def ask_npc(
    simulation_id: str,
    request: AskNpcRequest,
    db: AsyncSession = Depends(get_db),
):
    """Ask a selected NPC a question, grounded in their actual simulation state."""
    # Verify simulation exists
    sim_result = await db.execute(
        select(SimulationRecord).where(SimulationRecord.id == simulation_id)
    )
    record = sim_result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Simulation not found")

    # Gather NPC context from persisted events
    ctx = await _gather_npc_context(db, simulation_id, request.npc_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="NPC not found in this simulation")

    # If NPC is not yet aware, return a canned response
    if not ctx["current_state"].get("aware", False):
        return AskNpcResponse(
            npc_id=request.npc_id,
            npc_name=ctx["npc_profile"]["name"],
            question=request.question,
            answer="I haven't heard about this idea yet, so I can't really comment on it.",
            stance="unaware",
            interest_score=0.0,
        )

    # Build grounded prompt and call LLM
    from backend.llm.prompts import format_ask_npc_system
    from backend.llm.client import llm_client

    system_prompt = format_ask_npc_system(ctx)
    answer = llm_client.ask_npc(system_prompt, request.question)

    return AskNpcResponse(
        npc_id=request.npc_id,
        npc_name=ctx["npc_profile"]["name"],
        question=request.question,
        answer=answer,
        stance=ctx["current_state"].get("stance", "unaware"),
        interest_score=ctx["current_state"].get("interest_score", 0.0),
    )


async def _gather_npc_context(
    db: AsyncSession, simulation_id: str, npc_id: str
) -> dict | None:
    """Reconstruct NPC context from persisted simulation events.

    Returns a dict suitable for format_ask_npc_system(), or None if NPC not found.
    """
    result = await db.execute(
        select(SimulationEvent)
        .where(SimulationEvent.simulation_id == simulation_id)
        .order_by(SimulationEvent.id)
    )
    db_events = result.scalars().all()

    if not db_events:
        return None

    # Extract NPC profile from simulation_start event
    npc_profile = None
    idea = None
    for ev in db_events:
        if ev.event_type == "simulation_start":
            data = ev.data.get("data", {})
            idea = data.get("idea", {})
            for npc_init in data.get("npcs", []):
                if npc_init.get("id") == npc_id:
                    npc_profile = npc_init
                    break
            break

    if npc_profile is None:
        return None

    # Reconstruct current state and history from events
    current_state = {
        "aware": False,
        "stance": "unaware",
        "interest_score": 0.0,
        "reasoning": "",
        "objections": [],
        "emotional_reaction": "",
        "would_pay": False,
    }
    timeline = []
    discussions = []

    for ev in db_events:
        d = ev.data.get("data", {})

        if ev.event_type == "npc_aware" and d.get("npc_id") == npc_id:
            current_state["aware"] = True
            source = d.get("source", "")
            source_name = d.get("source_name", source)
            detail = (
                "Direct exposure to the idea"
                if source == "direct_exposure"
                else f"Heard about it from {source_name}"
            )
            timeline.append({"tick": ev.tick, "type": "aware", "detail": detail})

        elif ev.event_type == "npc_reaction" and d.get("npc_id") == npc_id:
            current_state["stance"] = d.get("stance", current_state["stance"])
            current_state["interest_score"] = d.get("interest_score", current_state["interest_score"])
            current_state["reasoning"] = d.get("reasoning", "")
            current_state["objections"] = d.get("objections", [])
            current_state["emotional_reaction"] = d.get("emotional_reaction", "")
            current_state["would_pay"] = d.get("would_pay", False)
            timeline.append({
                "tick": ev.tick, "type": "reaction",
                "detail": d.get("reasoning", "Formed an initial opinion"),
            })

        elif ev.event_type == "discussion_end":
            if d.get("npc_a_id") == npc_id:
                delta = d.get("a_delta", 0)
                current_state["stance"] = d.get("a_stance", current_state["stance"])
                current_state["interest_score"] = d.get("a_interest", current_state["interest_score"])
                partner_name = d.get("npc_b_name", "someone")
                timeline.append({
                    "tick": ev.tick, "type": "discussion",
                    "detail": f"Discussed with {partner_name}",
                    "delta": delta, "keyPoint": d.get("key_point", ""),
                    "partnerName": partner_name,
                })
                discussions.append({
                    "tick": ev.tick, "partner_name": partner_name,
                    "key_point": d.get("key_point", ""), "delta": delta,
                })
            elif d.get("npc_b_id") == npc_id:
                delta = d.get("b_delta", 0)
                current_state["stance"] = d.get("b_stance", current_state["stance"])
                current_state["interest_score"] = d.get("b_interest", current_state["interest_score"])
                partner_name = d.get("npc_a_name", "someone")
                timeline.append({
                    "tick": ev.tick, "type": "discussion",
                    "detail": f"Discussed with {partner_name}",
                    "delta": delta, "keyPoint": d.get("key_point", ""),
                    "partnerName": partner_name,
                })
                discussions.append({
                    "tick": ev.tick, "partner_name": partner_name,
                    "key_point": d.get("key_point", ""), "delta": delta,
                })

        elif ev.event_type == "npc_state_change" and d.get("npc_id") == npc_id:
            current_state["stance"] = d.get("new_stance", current_state["stance"])
            current_state["interest_score"] = d.get("interest_score", current_state["interest_score"])
            reason = d.get("reason", "")
            if reason == "peer_influence":
                timeline.append({
                    "tick": ev.tick, "type": "influence",
                    "detail": "Shifted by social pressure from peers",
                })

    return {
        "npc_profile": npc_profile,
        "idea": idea or {},
        "current_state": current_state,
        "timeline": timeline,
        "discussions": discussions,
    }
