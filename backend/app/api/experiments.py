"""Experiment and Run management API endpoints."""

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.engine.compiler import compile_graph
from app.engine.executor import ExecutionEngine
from app.models.database import async_session, get_db
from app.models.execution import NodeExecution
from app.models.experiment import ExperimentRun, ExperimentSession
from app.models.graph import GraphDefinition
from app.parsers.base import ParsedDocument

router = APIRouter(prefix="/experiments", tags=["experiments"])

# Global registry of active execution engines (run_id -> ExecutionEngine)
_active_engines: dict[str, ExecutionEngine] = {}


# ─── Request / Response Schemas ───────────────────────────────────────────────


class ExperimentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    graph_id: str
    input_text: Optional[str] = None
    input_document_path: Optional[str] = None


class ExperimentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    experiment_memory_json: Optional[dict[str, Any]] = None


class RunResponse(BaseModel):
    id: str
    session_id: str
    status: str
    graph_snapshot_json: Optional[dict[str, Any]] = None
    config_json: Optional[dict[str, Any]] = None
    total_tokens_used: int = 0
    total_duration_ms: Optional[int] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str

    model_config = {"from_attributes": True}


class NodeExecutionResponse(BaseModel):
    id: str
    run_id: str
    node_id: str
    agent_type_name: str
    status: str
    iteration: int = 0
    system_prompt: Optional[str] = None
    input_data_json: Optional[dict[str, Any]] = None
    output_data_json: Optional[dict[str, Any]] = None
    memory_before_json: Optional[dict[str, Any]] = None
    memory_after_json: Optional[dict[str, Any]] = None
    logs_json: Optional[list[dict[str, Any]]] = None
    tool_calls_json: Optional[list[dict[str, Any]]] = None
    tokens_used: int = 0
    duration_ms: Optional[int] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


class RunDetailResponse(RunResponse):
    node_executions: list[NodeExecutionResponse] = []


class ExperimentResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    graph_id: str
    input_text: Optional[str]
    input_document_path: Optional[str]
    experiment_memory_json: Optional[dict[str, Any]]
    created_at: str
    updated_at: Optional[str]
    run_count: int = 0

    model_config = {"from_attributes": True}


class ExperimentDetailResponse(ExperimentResponse):
    runs: list[RunResponse] = []


class RunCreateResponse(BaseModel):
    run_id: str
    status: str


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _dt_to_str(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _run_to_response(run: ExperimentRun) -> RunResponse:
    return RunResponse(
        id=run.id,
        session_id=run.session_id,
        status=run.status,
        graph_snapshot_json=run.graph_snapshot_json,
        config_json=run.config_json,
        total_tokens_used=run.total_tokens_used,
        total_duration_ms=run.total_duration_ms,
        started_at=_dt_to_str(run.started_at),
        completed_at=_dt_to_str(run.completed_at),
        error_message=run.error_message,
        created_at=run.created_at.isoformat() if run.created_at else "",
    )


def _node_exec_to_response(ne: NodeExecution) -> NodeExecutionResponse:
    return NodeExecutionResponse(
        id=ne.id,
        run_id=ne.run_id,
        node_id=ne.node_id,
        agent_type_name=ne.agent_type_name,
        status=ne.status,
        iteration=ne.iteration,
        system_prompt=ne.system_prompt,
        input_data_json=ne.input_data_json,
        output_data_json=ne.output_data_json,
        memory_before_json=ne.memory_before_json,
        memory_after_json=ne.memory_after_json,
        logs_json=ne.logs_json,
        tool_calls_json=ne.tool_calls_json,
        tokens_used=ne.tokens_used,
        duration_ms=ne.duration_ms,
        started_at=_dt_to_str(ne.started_at),
        completed_at=_dt_to_str(ne.completed_at),
        error_message=ne.error_message,
    )


def _experiment_to_response(
    session: ExperimentSession, run_count: int = 0
) -> ExperimentResponse:
    return ExperimentResponse(
        id=session.id,
        name=session.name,
        description=session.description,
        graph_id=session.graph_id,
        input_text=session.input_text,
        input_document_path=session.input_document_path,
        experiment_memory_json=session.experiment_memory_json,
        created_at=session.created_at.isoformat() if session.created_at else "",
        updated_at=_dt_to_str(session.updated_at),
        run_count=run_count,
    )


# ─── Background Execution ────────────────────────────────────────────────────


async def _execute_run_background(
    run_id: str,
    graph_json: dict[str, Any],
    document_data: dict[str, Any],
    experiment_memory: dict[str, Any] | None,
) -> None:
    """Background task that executes a graph run and persists results."""
    engine: ExecutionEngine | None = None
    try:
        compiled = compile_graph(graph_json)
        engine = ExecutionEngine(compiled)
        engine.run_id = run_id
        engine.set_document(document_data)
        engine.set_experiment_memory(experiment_memory)
        _active_engines[run_id] = engine

        # Update run status to running
        async with async_session() as db:
            run = await db.get(ExperimentRun, run_id)
            if run:
                run.status = "running"
                run.started_at = datetime.now(timezone.utc)
                await db.commit()

        # Execute and collect events
        async for event in engine.execute_all():
            # Stream events are also consumed by WebSocket clients (see ws.py)
            pass

        # Persist results
        async with async_session() as db:
            run = await db.get(ExperimentRun, run_id)
            if run:
                run.status = "completed" if not engine.is_cancelled else "cancelled"
                run.total_tokens_used = engine.total_tokens
                run.total_duration_ms = (
                    int((time.time() - engine.started_at) * 1000)
                    if engine.started_at
                    else 0
                )
                run.completed_at = datetime.now(timezone.utc)

                # Persist node executions
                for result in engine.node_results:
                    node_exec = NodeExecution(
                        id=str(uuid.uuid4()),
                        run_id=run_id,
                        node_id=result.node_id,
                        agent_type_name=result.agent_type,
                        status=result.status,
                        iteration=result.iteration,
                        system_prompt=result.system_prompt,
                        input_data_json=result.input_data,
                        output_data_json=result.output_data,
                        memory_before_json=result.memory_before,
                        memory_after_json=result.memory_after,
                        logs_json=result.logs,
                        tool_calls_json=result.tool_calls,
                        tokens_used=result.tokens_used,
                        duration_ms=result.duration_ms,
                        error_message=result.error,
                    )
                    db.add(node_exec)

                await db.commit()

    except Exception as exc:
        # Mark run as failed
        async with async_session() as db:
            run = await db.get(ExperimentRun, run_id)
            if run:
                run.status = "failed"
                run.error_message = str(exc)
                run.completed_at = datetime.now(timezone.utc)
                await db.commit()
    finally:
        _active_engines.pop(run_id, None)


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED)
async def create_experiment(
    body: ExperimentCreate,
    db: AsyncSession = Depends(get_db),
) -> ExperimentResponse:
    """Create a new experiment session."""
    # Verify graph exists
    graph = await db.get(GraphDefinition, body.graph_id)
    if not graph:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Graph '{body.graph_id}' not found",
        )

    if not body.input_text and not body.input_document_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either input_text or input_document_path must be provided",
        )

    session = ExperimentSession(
        name=body.name,
        description=body.description,
        graph_id=body.graph_id,
        input_text=body.input_text,
        input_document_path=body.input_document_path,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return _experiment_to_response(session, run_count=0)


@router.get("", response_model=list[ExperimentResponse])
async def list_experiments(
    db: AsyncSession = Depends(get_db),
) -> list[ExperimentResponse]:
    """List all experiments with run counts."""
    # Subquery for run counts
    run_count_subq = (
        select(
            ExperimentRun.session_id,
            func.count(ExperimentRun.id).label("run_count"),
        )
        .group_by(ExperimentRun.session_id)
        .subquery()
    )

    stmt = (
        select(ExperimentSession, run_count_subq.c.run_count)
        .outerjoin(
            run_count_subq,
            ExperimentSession.id == run_count_subq.c.session_id,
        )
        .order_by(ExperimentSession.created_at.desc())
    )

    result = await db.execute(stmt)
    rows = result.all()
    return [
        _experiment_to_response(row[0], run_count=row[1] or 0) for row in rows
    ]


@router.get("/{session_id}", response_model=ExperimentDetailResponse)
async def get_experiment(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> ExperimentDetailResponse:
    """Get experiment details with its runs."""
    stmt = (
        select(ExperimentSession)
        .options(selectinload(ExperimentSession.runs))
        .where(ExperimentSession.id == session_id)
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment '{session_id}' not found",
        )

    runs = [_run_to_response(r) for r in session.runs]
    return ExperimentDetailResponse(
        id=session.id,
        name=session.name,
        description=session.description,
        graph_id=session.graph_id,
        input_text=session.input_text,
        input_document_path=session.input_document_path,
        experiment_memory_json=session.experiment_memory_json,
        created_at=session.created_at.isoformat() if session.created_at else "",
        updated_at=_dt_to_str(session.updated_at),
        run_count=len(runs),
        runs=runs,
    )


@router.put("/{session_id}", response_model=ExperimentResponse)
async def update_experiment(
    session_id: str,
    body: ExperimentUpdate,
    db: AsyncSession = Depends(get_db),
) -> ExperimentResponse:
    """Update experiment name, description, or experiment memory."""
    session = await db.get(ExperimentSession, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment '{session_id}' not found",
        )

    if body.name is not None:
        session.name = body.name
    if body.description is not None:
        session.description = body.description
    if body.experiment_memory_json is not None:
        session.experiment_memory_json = body.experiment_memory_json

    await db.flush()
    await db.refresh(session)

    # Count runs
    run_count_result = await db.execute(
        select(func.count(ExperimentRun.id)).where(
            ExperimentRun.session_id == session_id
        )
    )
    run_count = run_count_result.scalar() or 0
    return _experiment_to_response(session, run_count=run_count)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_experiment(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete experiment and all its runs."""
    session = await db.get(ExperimentSession, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment '{session_id}' not found",
        )

    # Delete node executions for all runs in this session
    runs_stmt = select(ExperimentRun.id).where(
        ExperimentRun.session_id == session_id
    )
    runs_result = await db.execute(runs_stmt)
    run_ids = [r[0] for r in runs_result.all()]

    for run_id in run_ids:
        node_execs_stmt = select(NodeExecution).where(
            NodeExecution.run_id == run_id
        )
        node_execs_result = await db.execute(node_execs_stmt)
        for ne in node_execs_result.scalars().all():
            await db.delete(ne)

    # Delete runs
    for run_id in run_ids:
        run = await db.get(ExperimentRun, run_id)
        if run:
            await db.delete(run)

    await db.delete(session)
    await db.flush()


# ─── Run Endpoints ────────────────────────────────────────────────────────────


@router.post(
    "/{session_id}/runs",
    response_model=RunCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_run(
    session_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> RunCreateResponse:
    """Start a new run for an experiment (triggers execution in background)."""
    # Load session
    session = await db.get(ExperimentSession, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment '{session_id}' not found",
        )

    # Load graph
    graph = await db.get(GraphDefinition, session.graph_id)
    if not graph:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Graph '{session.graph_id}' not found",
        )

    # Build graph JSON snapshot
    graph_snapshot = {
        "nodes": graph.nodes_json or [],
        "edges": graph.edges_json or [],
    }

    # Parse input into document data
    if session.input_text:
        parsed = ParsedDocument(
            raw_text=session.input_text,
            pages=[{"page_num": 1, "text": session.input_text}],
            metadata={"page_count": 1, "format": "text"},
        )
    elif session.input_document_path:
        # For file-based input, use the raw path as text for now
        # (full parsing would go through the document parser pipeline)
        parsed = ParsedDocument(
            raw_text=f"[Document: {session.input_document_path}]",
            pages=[],
            metadata={"path": session.input_document_path, "format": "file"},
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Experiment has no input_text or input_document_path",
        )

    document_data = parsed.to_document_data()

    # Create run record
    run = ExperimentRun(
        session_id=session_id,
        status="pending",
        graph_snapshot_json=graph_snapshot,
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    run_id = run.id

    # Launch background execution
    background_tasks.add_task(
        _execute_run_background,
        run_id=run_id,
        graph_json=graph_snapshot,
        document_data=document_data,
        experiment_memory=session.experiment_memory_json,
    )

    return RunCreateResponse(run_id=run_id, status="pending")


@router.get("/{session_id}/runs", response_model=list[RunResponse])
async def list_runs(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[RunResponse]:
    """List all runs for an experiment."""
    # Verify session exists
    session = await db.get(ExperimentSession, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment '{session_id}' not found",
        )

    result = await db.execute(
        select(ExperimentRun)
        .where(ExperimentRun.session_id == session_id)
        .order_by(ExperimentRun.created_at.desc())
    )
    runs = result.scalars().all()
    return [_run_to_response(r) for r in runs]


@router.get("/{session_id}/runs/{run_id}", response_model=RunDetailResponse)
async def get_run(
    session_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> RunDetailResponse:
    """Get full run details including all node executions."""
    stmt = (
        select(ExperimentRun)
        .options(selectinload(ExperimentRun.node_executions))
        .where(
            ExperimentRun.id == run_id,
            ExperimentRun.session_id == session_id,
        )
    )
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found in experiment '{session_id}'",
        )

    node_executions = [_node_exec_to_response(ne) for ne in run.node_executions]

    return RunDetailResponse(
        id=run.id,
        session_id=run.session_id,
        status=run.status,
        graph_snapshot_json=run.graph_snapshot_json,
        config_json=run.config_json,
        total_tokens_used=run.total_tokens_used,
        total_duration_ms=run.total_duration_ms,
        started_at=_dt_to_str(run.started_at),
        completed_at=_dt_to_str(run.completed_at),
        error_message=run.error_message,
        created_at=run.created_at.isoformat() if run.created_at else "",
        node_executions=node_executions,
    )


@router.post("/{session_id}/runs/{run_id}/pause", status_code=status.HTTP_200_OK)
async def pause_run(
    session_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Pause a running execution."""
    engine = _active_engines.get(run_id)
    if not engine:
        # Check if run exists
        run = await db.get(ExperimentRun, run_id)
        if not run or run.session_id != session_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run '{run_id}' not found",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run '{run_id}' is not currently active (status: {run.status})",
        )

    engine.pause()

    # Update DB status
    async with async_session() as db_session:
        run = await db_session.get(ExperimentRun, run_id)
        if run:
            run.status = "paused"
            await db_session.commit()

    return {"status": "paused", "run_id": run_id}


@router.post("/{session_id}/runs/{run_id}/resume", status_code=status.HTTP_200_OK)
async def resume_run(
    session_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Resume a paused execution."""
    engine = _active_engines.get(run_id)
    if not engine:
        run = await db.get(ExperimentRun, run_id)
        if not run or run.session_id != session_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run '{run_id}' not found",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run '{run_id}' is not currently active (status: {run.status})",
        )

    engine.resume()

    # Update DB status
    async with async_session() as db_session:
        run = await db_session.get(ExperimentRun, run_id)
        if run:
            run.status = "running"
            await db_session.commit()

    return {"status": "running", "run_id": run_id}


@router.post("/{session_id}/runs/{run_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_run(
    session_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Cancel a running or paused execution."""
    engine = _active_engines.get(run_id)
    if not engine:
        run = await db.get(ExperimentRun, run_id)
        if not run or run.session_id != session_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run '{run_id}' not found",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run '{run_id}' is not currently active (status: {run.status})",
        )

    engine.cancel()

    # Update DB status
    async with async_session() as db_session:
        run = await db_session.get(ExperimentRun, run_id)
        if run:
            run.status = "cancelled"
            run.completed_at = datetime.now(timezone.utc)
            await db_session.commit()

    return {"status": "cancelled", "run_id": run_id}
