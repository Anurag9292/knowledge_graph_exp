"""Experiment and Run management API endpoints."""

import asyncio
import logging
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.engine.compiler import compile_graph
from app.engine.executor import ExecutionEngine
from app.models.database import async_session, get_db
from app.models.execution import NodeExecution
from app.models.experiment import ExperimentRun, ExperimentSession
from app.models.graph import GraphDefinition
from app.parsers.base import ParsedDocument
from app.parsers.chunker import StructuralChunker
from app.models.query_eval import QueryEvalConfig
from app.services.llm import get_llm_service

logger = logging.getLogger(__name__)

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


def _maybe_inject_streaming_ingestion(
    graph_json: dict[str, Any],
    document_data: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Auto-switch to streaming ingestion pipeline if document exceeds threshold.

    If the document text is larger than STREAMING_THRESHOLD_CHARS and the graph
    doesn't already contain a streaming_ingestion node, inject one at the start
    of the pipeline and pre-chunk the document.

    Returns:
        (possibly_modified_graph_json, possibly_modified_document_data)
    """
    cfg = get_settings().ingestion
    raw_text = document_data.get("raw_text", "")

    if len(raw_text) <= cfg.STREAMING_THRESHOLD_CHARS:
        return graph_json, document_data

    # Check if streaming_ingestion is already in the graph
    nodes = graph_json.get("nodes", [])
    has_streaming = any(n.get("agent_type") == "streaming_ingestion" for n in nodes)
    if has_streaming:
        return graph_json, document_data

    logger.info(
        f"[Auto-Switch] Document ({len(raw_text)} chars) exceeds streaming threshold "
        f"({cfg.STREAMING_THRESHOLD_CHARS}). Pre-chunking with StructuralChunker..."
    )

    # Pre-chunk the document and attach chunk metadata to document_data
    chunker = StructuralChunker()
    chunks = chunker.chunk(raw_text, document_data.get("metadata"))
    logger.info(f"[Auto-Switch] Produced {len(chunks)} structural chunks")

    # Attach chunks to document data so agents can access them
    document_data = dict(document_data)
    document_data["chunks"] = [c.to_dict() for c in chunks]
    document_data["chunk_count"] = len(chunks)
    document_data["streaming_mode"] = True

    return graph_json, document_data


async def _execute_run_background(
    run_id: str,
    graph_json: dict[str, Any],
    document_data: dict[str, Any],
    experiment_memory: dict[str, Any] | None,
) -> None:
    """Background task that executes a graph run and persists results."""
    logger.info(f"[Run {run_id}] Starting background execution...")
    logger.info(f"[Run {run_id}] Graph: {len(graph_json.get('nodes', []))} nodes, {len(graph_json.get('edges', []))} edges")
    engine: ExecutionEngine | None = None
    try:
        # Auto-switch: inject streaming ingestion if document is large
        graph_json, document_data = _maybe_inject_streaming_ingestion(graph_json, document_data)

        compiled = compile_graph(graph_json)
        logger.info(f"[Run {run_id}] Graph compiled. Execution order: {compiled.execution_order}")

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
        logger.info(f"[Run {run_id}] Status set to 'running'")

        # Execute and collect events
        async for event in engine.execute_all():
            logger.info(f"[Run {run_id}] Event: {event.event_type} node={event.node_id}")

        # Persist results
        logger.info(f"[Run {run_id}] Execution complete. Persisting {len(engine.node_results)} node results...")
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
        logger.info(f"[Run {run_id}] \u2713 Run completed successfully!")

        # Auto-generate a test suite for this run
        try:
            await _auto_generate_test_suite(run_id, document_data)
        except Exception as gen_exc:
            logger.warning(f"[Run {run_id}] Auto test suite generation failed (non-fatal): {gen_exc}")

    except Exception as exc:
        logger.error(f"[Run {run_id}] \u2717 FAILED: {exc}")
        logger.error(traceback.format_exc())
        # Mark run as failed
        try:
            async with async_session() as db:
                run = await db.get(ExperimentRun, run_id)
                if run:
                    run.status = "failed"
                    run.error_message = str(exc)
                    run.completed_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception as db_exc:
            logger.error(f"[Run {run_id}] Failed to update DB with error status: {db_exc}")
    finally:
        _active_engines.pop(run_id, None)


async def _auto_generate_test_suite(run_id: str, document_data: dict[str, Any]) -> None:
    """Auto-generate a test suite (3 easy, 4 medium, 3 hard questions) from the input text."""
    raw_text = document_data.get("raw_text", "")
    if not raw_text or len(raw_text) < 100:
        logger.info(f"[Run {run_id}] Skipping auto test suite — input text too short")
        return

    logger.info(f"[Run {run_id}] Generating auto test suite from input text ({len(raw_text)} chars)...")

    # Use LLM to generate questions
    llm = get_llm_service()
    messages = [
        {
            "role": "system",
            "content": """You are a knowledge graph evaluation expert. Given a document text, generate exactly 10 questions that can be answered by querying a knowledge graph built from this text.

Generate:
- 3 EASY questions (single-hop, direct facts: "What is X?", "Where is Y located?", "Who created Z?")
- 4 MEDIUM questions (multi-hop, connecting 2 entities: "What is the relationship between X and Y?", "Which entities are connected to X via relationship R?")
- 3 HARD questions (complex, requiring 3+ entities or reasoning: "What path connects X to Y?", "Which entities share property P?")

You MUST output valid JSON:
{
  "questions": [
    {"question": "...", "ground_truth": "...", "difficulty": "easy"},
    {"question": "...", "ground_truth": "...", "difficulty": "easy"},
    {"question": "...", "ground_truth": "...", "difficulty": "easy"},
    {"question": "...", "ground_truth": "...", "difficulty": "medium"},
    {"question": "...", "ground_truth": "...", "difficulty": "medium"},
    {"question": "...", "ground_truth": "...", "difficulty": "medium"},
    {"question": "...", "ground_truth": "...", "difficulty": "medium"},
    {"question": "...", "ground_truth": "...", "difficulty": "hard"},
    {"question": "...", "ground_truth": "...", "difficulty": "hard"},
    {"question": "...", "ground_truth": "...", "difficulty": "hard"}
  ]
}

Guidelines:
- Questions should be answerable from the text content
- Ground truth should be concise, factual answers
- Easy questions test single facts
- Medium questions require connecting 2 pieces of information
- Hard questions require synthesis across multiple facts
- Use specific entity names from the text"""
        },
        {
            "role": "user",
            "content": f"Generate 10 evaluation questions for this document:\n\n{raw_text[:6000]}"
        },
    ]

    try:
        result = await llm.structured_output(
            messages=messages,
            model="gpt-4.1-mini",
            temperature=0.3,
            max_tokens=4096,
        )

        questions = result.get("questions", [])
        if not questions:
            logger.warning(f"[Run {run_id}] LLM returned no questions")
            return

        # Create the eval config
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        async with async_session() as db:
            config = QueryEvalConfig(
                name=f"Auto: Run {run_id[:8]} — {timestamp}",
                description=f"Auto-generated test suite for run {run_id} ({len(questions)} questions: 3 easy, 4 medium, 3 hard)",
                queries_json=questions,
                scoring_model="gpt-4.1",
            )
            db.add(config)
            await db.commit()

        logger.info(f"[Run {run_id}] \u2713 Auto test suite created: {len(questions)} questions")

    except Exception as e:
        logger.error(f"[Run {run_id}] Failed to generate test suite: {e}")


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

    # Commit the run record NOW so the background task can find it
    await db.commit()

    logger.info(f"[Run {run_id}] Created run record, launching background execution...")

    # Launch background execution using asyncio.create_task
    asyncio.create_task(
        _execute_run_background(
            run_id=run_id,
            graph_json=graph_snapshot,
            document_data=document_data,
            experiment_memory=session.experiment_memory_json,
        )
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


@router.get("/{session_id}/runs/{run_id}/schema")
async def get_run_schema(
    session_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Retrieve the grand schema exported during an ingestion run.
    
    The grand schema is a Cypher-optimized JSON file containing:
    - All node labels (entity types) with descriptions and property keys
    - All relationship types with source/target constraints
    - A full entity catalog (exact names for Cypher matching)
    - Aliases for fuzzy input handling
    - Ready-to-use Cypher query pattern templates
    - Structural constraints (valid from/to combinations)
    
    This file is intended to be passed to a multi-agent query system
    to enable accurate Cypher query generation at retrieval time.
    """
    # Load run with node executions
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

    if run.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run '{run_id}' has not completed (status: {run.status}). Schema is only available after successful completion.",
        )

    # Find the schema_exporter node execution
    schema_output = None
    for ne in run.node_executions:
        if ne.agent_type_name == "schema_exporter" and ne.output_data_json:
            schema_output = ne.output_data_json
            break

    if not schema_output:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No schema export found for run '{run_id}'. "
                "The pipeline may not include the schema_exporter agent."
            ),
        )

    grand_schema = schema_output.get("grand_schema")
    if not grand_schema:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schema exporter ran but produced no grand_schema output.",
        )

    return {
        "run_id": run_id,
        "session_id": session_id,
        "schema": grand_schema,
        "schema_file_path": schema_output.get("schema_file_path"),
        "stats": schema_output.get("stats", {}),
    }


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


# ─── Compare Endpoint ─────────────────────────────────────────────────────────


@router.get("/compare/runs")
async def compare_runs(
    run_a: str,
    run_b: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Compare two runs side-by-side.
    
    Matches node executions by agent_type_name (not node_id) so runs
    from different pipelines can be compared.
    
    Returns per-agent comparison with input/output diffs and metrics.
    """
    # Load both runs with their node executions
    stmt_a = (
        select(ExperimentRun)
        .options(selectinload(ExperimentRun.node_executions))
        .where(ExperimentRun.id == run_a)
    )
    stmt_b = (
        select(ExperimentRun)
        .options(selectinload(ExperimentRun.node_executions))
        .where(ExperimentRun.id == run_b)
    )

    result_a = await db.execute(stmt_a)
    result_b = await db.execute(stmt_b)
    run_a_obj = result_a.scalar_one_or_none()
    run_b_obj = result_b.scalar_one_or_none()

    if not run_a_obj:
        raise HTTPException(status_code=404, detail=f"Run '{run_a}' not found")
    if not run_b_obj:
        raise HTTPException(status_code=404, detail=f"Run '{run_b}' not found")

    # Group node executions by agent_type_name
    a_by_type: dict[str, list] = {}
    for ne in run_a_obj.node_executions:
        a_by_type.setdefault(ne.agent_type_name, []).append(ne)

    b_by_type: dict[str, list] = {}
    for ne in run_b_obj.node_executions:
        b_by_type.setdefault(ne.agent_type_name, []).append(ne)

    all_types = sorted(set(a_by_type.keys()) | set(b_by_type.keys()))

    # Build comparisons
    comparisons = []
    for agent_type in all_types:
        a_nodes = a_by_type.get(agent_type, [])
        b_nodes = b_by_type.get(agent_type, [])

        for i in range(max(len(a_nodes), len(b_nodes))):
            ne_a = a_nodes[i] if i < len(a_nodes) else None
            ne_b = b_nodes[i] if i < len(b_nodes) else None

            def _node_metrics(ne):
                if not ne:
                    return None
                tokens = ne.tokens_used or 0
                duration = ne.duration_ms or 0
                tok_sec = round(tokens / (duration / 1000), 1) if duration > 0 and tokens > 0 else 0
                return {
                    "node_id": ne.node_id,
                    "status": ne.status,
                    "duration_ms": duration,
                    "tokens_used": tokens,
                    "tok_per_sec": tok_sec,
                    "input_data": ne.input_data_json,
                    "output_data": ne.output_data_json,
                    "error": ne.error_message,
                }

            comparisons.append({
                "agent_type": agent_type,
                "in_run_a": ne_a is not None,
                "in_run_b": ne_b is not None,
                "run_a": _node_metrics(ne_a),
                "run_b": _node_metrics(ne_b),
            })

    # Summary
    agents_matched = sum(1 for c in comparisons if c["in_run_a"] and c["in_run_b"])
    only_in_a = sum(1 for c in comparisons if c["in_run_a"] and not c["in_run_b"])
    only_in_b = sum(1 for c in comparisons if not c["in_run_a"] and c["in_run_b"])

    return {
        "run_a": {
            "id": run_a_obj.id,
            "session_id": run_a_obj.session_id,
            "status": run_a_obj.status,
            "total_duration_ms": run_a_obj.total_duration_ms,
            "total_tokens_used": run_a_obj.total_tokens_used,
            "started_at": _dt_to_str(run_a_obj.started_at),
        },
        "run_b": {
            "id": run_b_obj.id,
            "session_id": run_b_obj.session_id,
            "status": run_b_obj.status,
            "total_duration_ms": run_b_obj.total_duration_ms,
            "total_tokens_used": run_b_obj.total_tokens_used,
            "started_at": _dt_to_str(run_b_obj.started_at),
        },
        "comparisons": comparisons,
        "summary": {
            "agents_matched": agents_matched,
            "agents_only_in_a": only_in_a,
            "agents_only_in_b": only_in_b,
            "total_agents": len(comparisons),
        },
    }
