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

from backend.api.auth import get_optional_user
from backend.api.schemas.requests import AskNpcRequest, AssetReference, CreateSimulationRequest
from backend.api.schemas.responses import AskNpcResponse, SimulationDetail, SimulationSummary
from backend.db.database import SyncSession, async_session, get_db
from backend.db.models import Asset, SimulationEvent, SimulationRecord
from backend.simulation.engine import run_simulation
from backend.simulation.streamer import event_store
from backend.simulation.world import InjectedIdea, SimConfig

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/simulations", tags=["simulations"])

# Maximum time (seconds) a simulation can run before being marked as failed.
SIMULATION_TIMEOUT_SECONDS = 15 * 60  # 15 minutes


# ---------------------------------------------------------------------------
# POST — Create simulation (starts in background, returns immediately)
# ---------------------------------------------------------------------------

@router.post("", response_model=SimulationDetail)
async def create_simulation(
    request: CreateSimulationRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Depends(get_optional_user),
):
    """Create a simulation and start it in the background.

    Returns immediately with status='running'. Use the SSE stream endpoint
    to watch events live, or poll GET /{id} until status='completed'.
    """
    # Variant lineage: validate parent and compute changed fields
    changed_fields = None
    root_simulation_id = None
    if request.parent_simulation_id:
        parent_result = await db.execute(
            select(SimulationRecord).where(
                SimulationRecord.id == request.parent_simulation_id
            )
        )
        parent = parent_result.scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent simulation not found")
        if parent.status != "completed":
            raise HTTPException(
                status_code=400,
                detail="Can only create variants from completed simulations",
            )
        changed_fields = _compute_changed_fields(request, parent)
        root_simulation_id = parent.root_simulation_id or parent.id

    idea_metadata = {
        "stage": request.idea.stage,
        "target_audience": request.idea.target_audience,
        "problem_statement": request.idea.problem_statement,
        "price_point": request.idea.price_point,
        "existing_alternatives": request.idea.existing_alternatives,
        "differentiator": request.idea.differentiator,
        "known_strengths": request.idea.known_strengths,
        "known_risks": request.idea.known_risks,
    }

    record = SimulationRecord(
        idea_title=request.idea.title,
        idea_description=request.idea.description,
        idea_category=request.idea.category,
        idea_metadata=idea_metadata,
        config=request.config.model_dump(),
        status="running",
        parent_simulation_id=request.parent_simulation_id,
        root_simulation_id=root_simulation_id,
        variant_name=request.variant_name,
        changed_fields=changed_fields,
        user_id=user_id,
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

    # Resolve asset references to file paths for the background thread.
    # Assets may be image uploads (with asset_id) or URL-only references.
    asset_file_paths: list[str] = []
    asset_metadata: list[dict] = []
    if request.asset_refs:
        sync_db = SyncSession()
        try:
            for ref in request.asset_refs:
                meta = {
                    "asset_type": ref.asset_type,
                    "url": ref.url,
                    "note": ref.note,
                }
                if ref.asset_id:
                    # Uploaded image — resolve to file path
                    asset = sync_db.get(Asset, ref.asset_id)
                    if asset and asset.file_path:
                        asset_file_paths.append(asset.file_path)
                        asset_metadata.append(meta)
                elif ref.url:
                    # URL-only asset — no file path, but still analyzed
                    asset_file_paths.append("")  # placeholder, skipped by load_image
                    asset_metadata.append(meta)
        finally:
            sync_db.close()

    # Pre-register so SSE clients can connect before first emit
    event_store.register(sim_id)

    # Launch simulation in a background thread with a timeout watchdog
    _launch_with_timeout(sim_id, idea, config, asset_file_paths, asset_metadata)

    return SimulationDetail(
        id=record.id,
        idea_title=record.idea_title,
        idea_description=record.idea_description,
        idea_category=record.idea_category,
        idea_metadata=record.idea_metadata,
        config=record.config,
        status="running",
        created_at=record.created_at,
        parent_simulation_id=record.parent_simulation_id,
        root_simulation_id=record.root_simulation_id,
        variant_name=record.variant_name,
        changed_fields=record.changed_fields,
    )


def _compute_changed_fields(
    request: CreateSimulationRequest, parent: SimulationRecord
) -> list[str]:
    """Compare request fields against parent's stored data to find what changed."""
    changed: list[str] = []
    parent_meta = parent.idea_metadata or {}
    parent_config = parent.config or {}

    # Compare top-level idea fields
    field_map = {
        "title": ("idea_title", request.idea.title, parent.idea_title),
        "description": ("idea_description", request.idea.description, parent.idea_description),
        "category": ("idea_category", request.idea.category, parent.idea_category),
    }
    for field_name, (_, new_val, old_val) in field_map.items():
        if str(new_val).strip() != str(old_val).strip():
            changed.append(field_name)

    # Compare metadata fields
    meta_fields = [
        "stage", "target_audience", "problem_statement", "price_point",
        "existing_alternatives", "differentiator", "known_strengths", "known_risks",
    ]
    for field in meta_fields:
        new_val = str(getattr(request.idea, field, "")).strip()
        old_val = str(parent_meta.get(field, "")).strip()
        if new_val != old_val:
            changed.append(field)

    # Compare config fields
    config_fields = ["num_ticks", "population_size", "seed_count"]
    for field in config_fields:
        new_val = getattr(request.config, field, None)
        old_val = parent_config.get(field)
        if new_val != old_val:
            changed.append(field)

    return changed


def _launch_with_timeout(
    sim_id: str,
    idea: InjectedIdea,
    config: SimConfig,
    asset_file_paths: list[str] | None = None,
    asset_metadata: list[dict] | None = None,
):
    """Launch the simulation thread and a watchdog that enforces a timeout.

    If the simulation thread doesn't finish within SIMULATION_TIMEOUT_SECONDS,
    the watchdog marks it as failed in the database and signals completion to
    the event store so SSE clients disconnect.  The daemon thread is then
    abandoned (Python will clean it up on process exit).
    """

    def _watchdog(worker: threading.Thread):
        worker.join(timeout=SIMULATION_TIMEOUT_SECONDS)
        if worker.is_alive():
            logger.error("Simulation %s timed out after %ds", sim_id, SIMULATION_TIMEOUT_SECONDS)
            # Emit error event so SSE clients see the timeout
            event_store.push(sim_id, {
                "type": "error",
                "tick": 0,
                "data": {"message": f"Simulation timed out after {SIMULATION_TIMEOUT_SECONDS // 60} minutes"},
            })
            event_store.mark_complete(sim_id)
            # Mark as failed in DB
            try:
                db_session = SyncSession()
                record = db_session.get(SimulationRecord, sim_id)
                if record and record.status == "running":
                    record.status = "failed"
                    db_session.commit()
                db_session.close()
            except Exception:
                logger.warning("Failed to mark timed-out sim %s as failed", sim_id, exc_info=True)

    worker = threading.Thread(
        target=_run_simulation_thread,
        args=(sim_id, idea, config, asset_file_paths, asset_metadata),
        daemon=True,
    )
    worker.start()

    watchdog = threading.Thread(target=_watchdog, args=(worker,), daemon=True)
    watchdog.start()


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
        # Purge any stale completed simulations to bound memory usage
        event_store.purge_stale()


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
    # Client has received all events — safe to free memory immediately
    event_store.cleanup(simulation_id)


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
async def list_simulations(
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Depends(get_optional_user),
):
    query = select(SimulationRecord)
    if user_id:
        query = query.where(SimulationRecord.user_id == user_id)
    query = query.order_by(SimulationRecord.created_at.desc()).limit(50)
    result = await db.execute(query)
    records = result.scalars().all()
    return [
        SimulationSummary(
            id=r.id, idea_title=r.idea_title, status=r.status,
            created_at=r.created_at, completed_at=r.completed_at, metrics=r.metrics,
            parent_simulation_id=r.parent_simulation_id,
            root_simulation_id=r.root_simulation_id,
            variant_name=r.variant_name,
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
        idea_metadata=record.idea_metadata,
        config=record.config, status=record.status,
        created_at=record.created_at, completed_at=record.completed_at,
        report=record.report, summary=record.summary, metrics=record.metrics,
        parent_simulation_id=record.parent_simulation_id,
        root_simulation_id=record.root_simulation_id,
        variant_name=record.variant_name, changed_fields=record.changed_fields,
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
# GET — Variant lineage endpoints
# ---------------------------------------------------------------------------

@router.get("/{simulation_id}/variants", response_model=list[SimulationSummary])
async def list_variants(simulation_id: str, db: AsyncSession = Depends(get_db)):
    """List all direct variants of a simulation."""
    result = await db.execute(
        select(SimulationRecord)
        .where(SimulationRecord.parent_simulation_id == simulation_id)
        .order_by(SimulationRecord.created_at.desc())
    )
    records = result.scalars().all()
    return [
        SimulationSummary(
            id=r.id, idea_title=r.idea_title, status=r.status,
            created_at=r.created_at, completed_at=r.completed_at, metrics=r.metrics,
            parent_simulation_id=r.parent_simulation_id,
            root_simulation_id=r.root_simulation_id,
            variant_name=r.variant_name,
        )
        for r in records
    ]


_FIELD_LABELS = {
    "title": "Idea Name", "description": "Description", "category": "Category",
    "stage": "Stage", "target_audience": "Target Audience",
    "problem_statement": "Problem Statement", "price_point": "Pricing",
    "existing_alternatives": "Alternatives", "differentiator": "Differentiator",
    "known_strengths": "Strengths", "known_risks": "Risks",
    "num_ticks": "Rounds", "population_size": "Population",
    "seed_count": "Initial Exposure",
}


def _build_changed_fields_detail(
    changed_fields: list[str],
    parent: SimulationRecord,
    variant: SimulationRecord,
) -> list[dict]:
    """Build detailed before/after for each changed field."""
    details = []
    parent_meta = parent.idea_metadata or {}
    parent_config = parent.config or {}
    variant_meta = variant.idea_metadata or {}
    variant_config = variant.config or {}

    for field in changed_fields:
        if field == "title":
            old_val, new_val = parent.idea_title, variant.idea_title
        elif field == "description":
            old_val, new_val = parent.idea_description, variant.idea_description
        elif field == "category":
            old_val, new_val = parent.idea_category, variant.idea_category
        elif field in ("num_ticks", "population_size", "seed_count"):
            old_val = str(parent_config.get(field, ""))
            new_val = str(variant_config.get(field, ""))
        else:
            old_val = str(parent_meta.get(field, ""))
            new_val = str(variant_meta.get(field, ""))

        details.append({
            "field": field,
            "label": _FIELD_LABELS.get(field, field),
            "old_value": old_val,
            "new_value": new_val,
        })
    return details


def _enrich_npc_archetypes(
    npc_results: list[dict], archetype_map: dict[str, str],
) -> None:
    """Fill in missing archetype fields on NPC results from archetype map."""
    if not archetype_map:
        return
    for npc in npc_results:
        if not npc.get("archetype"):
            npc_id = npc.get("npc_id") or npc.get("id")
            if npc_id and npc_id in archetype_map:
                npc["archetype"] = archetype_map[npc_id]


def _build_archetype_comparison(
    parent_report: dict, variant_report: dict,
) -> list[dict]:
    """Compare per-archetype interest and adoption between parent and variant."""
    from collections import defaultdict

    def _group_by_archetype(npc_results: list[dict]) -> dict[str, list[dict]]:
        groups: dict[str, list[dict]] = defaultdict(list)
        for npc in npc_results:
            arch = npc.get("archetype") or "unknown"
            groups[arch].append(npc)
        return groups

    parent_npcs = parent_report.get("npc_results", [])
    variant_npcs = variant_report.get("npc_results", [])

    parent_groups = _group_by_archetype(parent_npcs)
    variant_groups = _group_by_archetype(variant_npcs)

    all_archetypes = sorted(
        a for a in (set(parent_groups.keys()) | set(variant_groups.keys()))
        if a != "unknown"
    )
    if not all_archetypes:
        return []
    comparison = []

    for arch in all_archetypes:
        p_npcs = parent_groups.get(arch, [])
        v_npcs = variant_groups.get(arch, [])

        p_interest = (
            sum(n.get("interest_score", 0) for n in p_npcs) / len(p_npcs)
            if p_npcs else 0
        )
        v_interest = (
            sum(n.get("interest_score", 0) for n in v_npcs) / len(v_npcs)
            if v_npcs else 0
        )

        entry: dict = {
            "archetype": arch,
            "count": max(len(p_npcs), len(v_npcs)),
            "mean_interest_parent": round(p_interest, 3),
            "mean_interest_variant": round(v_interest, 3),
            "interest_delta": round(v_interest - p_interest, 3),
        }

        # Adoption rates if available
        p_adopted = [n for n in p_npcs if n.get("adopted")]
        v_adopted = [n for n in v_npcs if n.get("adopted")]
        if p_npcs:
            entry["adoption_rate_parent"] = round(len(p_adopted) / len(p_npcs), 3)
        if v_npcs:
            entry["adoption_rate_variant"] = round(len(v_adopted) / len(v_npcs), 3)

        # Dominant stance
        from collections import Counter
        if p_npcs:
            p_stances = Counter(n.get("stance", "unaware") for n in p_npcs)
            entry["dominant_stance_parent"] = p_stances.most_common(1)[0][0]
        if v_npcs:
            v_stances = Counter(n.get("stance", "unaware") for n in v_npcs)
            entry["dominant_stance_variant"] = v_stances.most_common(1)[0][0]

        comparison.append(entry)

    return comparison


@router.get("/{simulation_id}/compare/{variant_id}")
async def compare_simulations(
    simulation_id: str,
    variant_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Compare a parent simulation with one of its variants."""
    parent_result = await db.execute(
        select(SimulationRecord).where(SimulationRecord.id == simulation_id)
    )
    parent = parent_result.scalar_one_or_none()
    if not parent:
        raise HTTPException(status_code=404, detail="Parent simulation not found")

    variant_result = await db.execute(
        select(SimulationRecord).where(SimulationRecord.id == variant_id)
    )
    variant = variant_result.scalar_one_or_none()
    if not variant:
        raise HTTPException(status_code=404, detail="Variant simulation not found")

    if variant.parent_simulation_id != simulation_id:
        raise HTTPException(
            status_code=400, detail="Variant does not belong to this parent"
        )

    # Compute metrics delta
    parent_metrics = parent.metrics or {}
    variant_metrics = variant.metrics or {}
    metrics_delta = {}
    all_keys = set(parent_metrics.keys()) | set(variant_metrics.keys())
    for key in all_keys:
        p_val = parent_metrics.get(key, 0)
        v_val = variant_metrics.get(key, 0)
        if isinstance(p_val, (int, float)) and isinstance(v_val, (int, float)):
            metrics_delta[key] = round(v_val - p_val, 4)

    # Extract objections and segments from reports
    parent_report = parent.report or {}
    variant_report = variant.report or {}
    parent_analysis = parent_report.get("analysis", {})
    variant_analysis = variant_report.get("analysis", {})

    # Enrich NPC results with archetype data from simulation events if missing
    for sim_id, report in [(simulation_id, parent_report), (variant_id, variant_report)]:
        npcs = report.get("npc_results", [])
        if npcs and not any(n.get("archetype") for n in npcs):
            evt_result = await db.execute(
                select(SimulationEvent.data)
                .where(SimulationEvent.simulation_id == sim_id)
                .where(SimulationEvent.event_type == "simulation_start")
            )
            evt_row = evt_result.scalar_one_or_none()
            if evt_row:
                evt_data = evt_row if isinstance(evt_row, dict) else {}
                inner = evt_data.get("data", evt_data)
                arch_map = inner.get("npc_archetypes", {})
                _enrich_npc_archetypes(npcs, arch_map)

    # Build enhanced diff data
    changed_fields = variant.changed_fields or []
    changed_fields_detail = _build_changed_fields_detail(
        changed_fields, parent, variant,
    )
    archetype_comparison = _build_archetype_comparison(parent_report, variant_report)

    return {
        "parent": {
            "id": parent.id,
            "idea_title": parent.idea_title,
            "metrics": parent_metrics,
            "idea_metadata": parent.idea_metadata,
            "config": parent.config,
        },
        "variant": {
            "id": variant.id,
            "idea_title": variant.idea_title,
            "metrics": variant_metrics,
            "idea_metadata": variant.idea_metadata,
            "config": variant.config,
            "variant_name": variant.variant_name,
            "changed_fields": variant.changed_fields,
        },
        "diff": {
            "changed_fields": changed_fields,
            "changed_fields_detail": changed_fields_detail,
            "metrics_delta": metrics_delta,
            "parent_top_objections": parent_analysis.get("top_objections", []),
            "variant_top_objections": variant_analysis.get("top_objections", []),
            "parent_segments": parent_analysis.get("segments", []),
            "variant_segments": variant_analysis.get("segments", []),
            "parent_adoption_likelihood": parent_analysis.get("adoption_likelihood"),
            "variant_adoption_likelihood": variant_analysis.get("adoption_likelihood"),
            "parent_product_profile": parent_report.get("product_profile"),
            "variant_product_profile": variant_report.get("product_profile"),
            "parent_convergence": parent_report.get("convergence"),
            "variant_convergence": variant_report.get("convergence"),
            "parent_adoption_breakdown": parent_report.get("adoption_breakdown"),
            "variant_adoption_breakdown": variant_report.get("adoption_breakdown"),
            "archetype_comparison": archetype_comparison,
        },
    }


# ---------------------------------------------------------------------------
# POST — Generate comparison explanation (LLM call)
# ---------------------------------------------------------------------------

@router.post("/{simulation_id}/compare/{variant_id}/explain")
async def explain_comparison(
    simulation_id: str,
    variant_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Generate an AI explanation of WHY a variant produced different results."""
    parent_result = await db.execute(
        select(SimulationRecord).where(SimulationRecord.id == simulation_id)
    )
    parent = parent_result.scalar_one_or_none()
    if not parent:
        raise HTTPException(status_code=404, detail="Parent simulation not found")

    variant_result = await db.execute(
        select(SimulationRecord).where(SimulationRecord.id == variant_id)
    )
    variant = variant_result.scalar_one_or_none()
    if not variant:
        raise HTTPException(status_code=404, detail="Variant simulation not found")

    if variant.parent_simulation_id != simulation_id:
        raise HTTPException(
            status_code=400, detail="Variant does not belong to this parent"
        )

    if parent.status != "completed" or variant.status != "completed":
        raise HTTPException(
            status_code=400, detail="Both simulations must be completed"
        )

    # Gather data for explanation
    changed_fields = variant.changed_fields or []
    changed_fields_detail = _build_changed_fields_detail(
        changed_fields, parent, variant,
    )

    parent_metrics = parent.metrics or {}
    variant_metrics = variant.metrics or {}
    metrics_delta = {}
    for key in set(parent_metrics.keys()) | set(variant_metrics.keys()):
        p_val = parent_metrics.get(key, 0)
        v_val = variant_metrics.get(key, 0)
        if isinstance(p_val, (int, float)) and isinstance(v_val, (int, float)):
            metrics_delta[key] = round(v_val - p_val, 4)

    parent_report = parent.report or {}
    variant_report = variant.report or {}

    # Enrich NPC results with archetype data from simulation events if missing
    for sim_id, report in [(simulation_id, parent_report), (variant_id, variant_report)]:
        npcs = report.get("npc_results", [])
        if npcs and not any(n.get("archetype") for n in npcs):
            evt_result = await db.execute(
                select(SimulationEvent.data)
                .where(SimulationEvent.simulation_id == sim_id)
                .where(SimulationEvent.event_type == "simulation_start")
            )
            evt_row = evt_result.scalar_one_or_none()
            if evt_row:
                evt_data = evt_row if isinstance(evt_row, dict) else {}
                inner = evt_data.get("data", evt_data)
                arch_map = inner.get("npc_archetypes", {})
                _enrich_npc_archetypes(npcs, arch_map)

    archetype_comparison = _build_archetype_comparison(parent_report, variant_report)

    parent_summary = parent_report.get("analysis", {}).get(
        "executive_summary", "No summary available."
    )
    variant_summary = variant_report.get("analysis", {}).get(
        "executive_summary", "No summary available."
    )

    from backend.llm.client import llm_client
    explanation = llm_client.generate_comparison_explanation(
        changed_fields_detail=changed_fields_detail,
        metrics_delta=metrics_delta,
        archetype_comparison=archetype_comparison,
        parent_summary=parent_summary,
        variant_summary=variant_summary,
    )

    return explanation


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
    peer_warnings = []

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

        elif ev.event_type == "concern_applied" and d.get("npc_id") == npc_id:
            # Reconstruct peer warnings from enriched concern events
            for src in d.get("sources", []):
                peer_warnings.append({
                    "tick": ev.tick,
                    "source_name": src.get("source_name", "someone"),
                    "theme": src.get("theme", ""),
                    "content": src.get("content", ""),
                    "delta": src.get("delta", 0),
                })
            timeline.append({
                "tick": ev.tick, "type": "concern",
                "detail": f"Heard concerns from {len(d.get('sources', []))} peer(s)",
                "delta": d.get("delta", 0),
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
        "peer_warnings": peer_warnings,
    }
