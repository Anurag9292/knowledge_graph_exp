"""Query Evaluation API — multi-agent Cypher-based KG evaluation."""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.database import async_session, get_db
from app.models.query_eval import QueryEvalConfig, QueryEvalRun
from app.models.execution import NodeExecution
from app.models.experiment import ExperimentRun, ExperimentSession
from app.services.neo4j import Neo4jService
from app.agents.registry import AgentRegistry
from app.agents.base import AgentInput

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query-eval", tags=["query-eval"])


# ─── Request / Response Schemas ───────────────────────────────────────────────


class QueryItem(BaseModel):
    question: str
    ground_truth: str
    difficulty: Optional[str] = "medium"
    tags: Optional[list[str]] = None


class QueryEvalConfigCreate(BaseModel):
    name: str
    description: Optional[str] = None
    queries: list[QueryItem]
    scoring_model: str = "gpt-4.1"


class QueryEvalConfigResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    queries_json: Optional[list[dict[str, Any]]]
    scoring_model: str
    created_at: str
    query_count: int = 0

    model_config = {"from_attributes": True}


class QueryEvalRunCreate(BaseModel):
    config_id: str
    ingestion_run_id: str


class QueryEvalRunResponse(BaseModel):
    id: str
    config_id: str
    ingestion_run_id: str
    status: str
    overall_score: Optional[float]
    queries_evaluated: int
    queries_passed: int
    query_results_json: Optional[list[dict[str, Any]]]
    neo4j_stats_json: Optional[dict[str, Any]]
    total_duration_ms: Optional[int]
    started_at: Optional[str]
    completed_at: Optional[str]
    error_message: Optional[str]
    created_at: str

    model_config = {"from_attributes": True}


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _dt_to_str(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _config_to_response(config: QueryEvalConfig) -> QueryEvalConfigResponse:
    queries = config.queries_json or []
    return QueryEvalConfigResponse(
        id=config.id,
        name=config.name,
        description=config.description,
        queries_json=queries,
        scoring_model=config.scoring_model,
        created_at=config.created_at.isoformat() if config.created_at else "",
        query_count=len(queries),
    )


def _run_to_response(run: QueryEvalRun) -> QueryEvalRunResponse:
    return QueryEvalRunResponse(
        id=run.id,
        config_id=run.config_id,
        ingestion_run_id=run.ingestion_run_id,
        status=run.status,
        overall_score=run.overall_score,
        queries_evaluated=run.queries_evaluated,
        queries_passed=run.queries_passed,
        query_results_json=run.query_results_json,
        neo4j_stats_json=run.neo4j_stats_json,
        total_duration_ms=run.total_duration_ms,
        started_at=_dt_to_str(run.started_at),
        completed_at=_dt_to_str(run.completed_at),
        error_message=run.error_message,
        created_at=run.created_at.isoformat() if run.created_at else "",
    )


# ─── Query Eval Config Endpoints ─────────────────────────────────────────────


@router.post("/configs", response_model=QueryEvalConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_query_eval_config(
    body: QueryEvalConfigCreate,
    db: AsyncSession = Depends(get_db),
) -> QueryEvalConfigResponse:
    """Create a query evaluation configuration (test suite)."""
    config = QueryEvalConfig(
        name=body.name,
        description=body.description,
        queries_json=[q.model_dump() for q in body.queries],
        scoring_model=body.scoring_model,
    )
    db.add(config)
    await db.flush()
    await db.refresh(config)
    return _config_to_response(config)


@router.get("/configs", response_model=list[QueryEvalConfigResponse])
async def list_query_eval_configs(
    db: AsyncSession = Depends(get_db),
) -> list[QueryEvalConfigResponse]:
    """List all query evaluation configurations."""
    result = await db.execute(
        select(QueryEvalConfig).order_by(QueryEvalConfig.created_at.desc())
    )
    configs = result.scalars().all()
    return [_config_to_response(c) for c in configs]


@router.get("/configs/{config_id}", response_model=QueryEvalConfigResponse)
async def get_query_eval_config(
    config_id: str,
    db: AsyncSession = Depends(get_db),
) -> QueryEvalConfigResponse:
    """Get a specific query evaluation configuration."""
    config = await db.get(QueryEvalConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Config '{config_id}' not found")
    return _config_to_response(config)


@router.put("/configs/{config_id}", response_model=QueryEvalConfigResponse)
async def update_query_eval_config(
    config_id: str,
    body: QueryEvalConfigCreate,
    db: AsyncSession = Depends(get_db),
) -> QueryEvalConfigResponse:
    """Update a query evaluation configuration."""
    config = await db.get(QueryEvalConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Config '{config_id}' not found")
    config.name = body.name
    config.description = body.description
    config.queries_json = [q.model_dump() for q in body.queries]
    config.scoring_model = body.scoring_model
    await db.flush()
    await db.refresh(config)
    return _config_to_response(config)


@router.post("/configs/auto-generate", response_model=QueryEvalConfigResponse, status_code=status.HTTP_201_CREATED)
async def auto_generate_config(
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> QueryEvalConfigResponse:
    """Auto-generate a test suite from an ingestion run's input text."""
    from app.services.llm import get_llm_service

    ingestion_run_id = body.get("ingestion_run_id")
    if not ingestion_run_id:
        raise HTTPException(status_code=400, detail="ingestion_run_id is required")

    # Get the experiment session to access input text
    run = await db.get(ExperimentRun, ingestion_run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{ingestion_run_id}' not found")

    session = await db.get(ExperimentSession, run.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Experiment session not found")

    input_text = session.input_text or ""
    if len(input_text) < 100:
        raise HTTPException(status_code=400, detail="Input text too short to generate questions")

    # Generate questions using LLM
    llm = get_llm_service()
    messages = [
        {
            "role": "system",
            "content": """You are a knowledge graph evaluation expert. Given a document text, generate exactly 10 questions with ground truth answers that can be answered by querying a knowledge graph built from this text.

Generate:
- 3 EASY questions (single-hop, direct facts: "What is X?", "Where is Y located?", "Who created Z?")
- 4 MEDIUM questions (multi-hop, connecting 2 entities: "What is the relationship between X and Y?")
- 3 HARD questions (complex, requiring 3+ entities or reasoning)

You MUST output valid JSON:
{
  "questions": [
    {"question": "...", "ground_truth": "...", "difficulty": "easy"},
    {"question": "...", "ground_truth": "...", "difficulty": "medium"},
    {"question": "...", "ground_truth": "...", "difficulty": "hard"}
  ]
}

Guidelines:
- Questions should be answerable from the text content
- Ground truth should be concise, factual answers
- Use specific entity names from the text"""
        },
        {
            "role": "user",
            "content": f"Generate 10 evaluation questions for this document:\n\n{input_text[:6000]}"
        },
    ]

    result = await llm.structured_output(
        messages=messages,
        model="gpt-4.1-mini",
        temperature=0.3,
        max_tokens=4096,
    )

    questions = result.get("questions", [])
    if not questions:
        raise HTTPException(status_code=500, detail="LLM failed to generate questions")

    # Create the config
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    config = QueryEvalConfig(
        name=f"Auto: {session.name} — {timestamp}",
        description=f"Auto-generated test suite for run {ingestion_run_id} ({len(questions)} questions: 3 easy, 4 medium, 3 hard)",
        queries_json=questions,
        scoring_model="gpt-4.1",
    )
    db.add(config)
    await db.flush()
    await db.refresh(config)
    return _config_to_response(config)


@router.delete("/configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_query_eval_config(
    config_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a query evaluation configuration."""
    config = await db.get(QueryEvalConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Config '{config_id}' not found")
    await db.delete(config)
    await db.flush()


# ─── Query Eval Run Endpoints ────────────────────────────────────────────────


@router.post("/run", response_model=QueryEvalRunResponse, status_code=status.HTTP_201_CREATED)
async def create_query_eval_run(
    body: QueryEvalRunCreate,
    db: AsyncSession = Depends(get_db),
) -> QueryEvalRunResponse:
    """
    Start a query evaluation run.
    
    This will:
    1. Load the KG from the ingestion run into Neo4j
    2. Load the grand schema from the ingestion run
    3. For each query in the config:
       a. Plan sub-queries
       b. Generate Cypher for each sub-query
       c. Execute Cypher against Neo4j
       d. Synthesize an answer
       e. Score against ground truth
    4. Aggregate results
    """
    # Validate config exists
    config = await db.get(QueryEvalConfig, body.config_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Config '{body.config_id}' not found")

    # Validate ingestion run exists and is completed
    ingestion_run = await db.get(ExperimentRun, body.ingestion_run_id)
    if not ingestion_run:
        raise HTTPException(status_code=404, detail=f"Ingestion run '{body.ingestion_run_id}' not found")
    if ingestion_run.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Ingestion run must be completed (current: {ingestion_run.status})",
        )

    # Create the eval run record
    eval_run = QueryEvalRun(
        config_id=body.config_id,
        ingestion_run_id=body.ingestion_run_id,
        status="pending",
    )
    db.add(eval_run)
    await db.flush()
    await db.refresh(eval_run)
    eval_run_id = eval_run.id
    await db.commit()

    # Launch background execution
    asyncio.create_task(
        _execute_eval_run(
            eval_run_id=eval_run_id,
            config_id=body.config_id,
            ingestion_run_id=body.ingestion_run_id,
        )
    )

    return _run_to_response(eval_run)


@router.get("/runs", response_model=list[QueryEvalRunResponse])
async def list_query_eval_runs(
    config_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> list[QueryEvalRunResponse]:
    """List query evaluation runs, optionally filtered by config."""
    stmt = select(QueryEvalRun).order_by(QueryEvalRun.created_at.desc())
    if config_id:
        stmt = stmt.where(QueryEvalRun.config_id == config_id)
    result = await db.execute(stmt)
    runs = result.scalars().all()
    return [_run_to_response(r) for r in runs]


@router.get("/runs/{run_id}", response_model=QueryEvalRunResponse)
async def get_query_eval_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> QueryEvalRunResponse:
    """Get detailed results of a query evaluation run."""
    run = await db.get(QueryEvalRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Eval run '{run_id}' not found")
    return _run_to_response(run)


# ─── Background Evaluation Orchestration ─────────────────────────────────────


async def _execute_eval_run(
    eval_run_id: str,
    config_id: str,
    ingestion_run_id: str,
) -> None:
    """Background task: orchestrates the full multi-agent query evaluation."""
    logger.info(f"[QueryEval {eval_run_id}] Starting evaluation...")
    start_time = time.time()

    try:
        # Update status to running
        async with async_session() as db:
            run = await db.get(QueryEvalRun, eval_run_id)
            if run:
                run.status = "running"
                run.started_at = datetime.now(timezone.utc)
                await db.commit()

        # 1. Load the grand schema from the ingestion run
        grand_schema = await _load_grand_schema(ingestion_run_id)
        logger.info(f"[QueryEval {eval_run_id}] Schema loaded: {len(grand_schema.get('entity_catalog', []))} entities")

        # 2. Load KG into Neo4j
        neo4j_stats = await _load_kg_to_neo4j(ingestion_run_id, grand_schema)
        logger.info(f"[QueryEval {eval_run_id}] KG loaded into Neo4j: {neo4j_stats}")

        # 3. Load the query config
        async with async_session() as db:
            config = await db.get(QueryEvalConfig, config_id)
            queries = config.queries_json or []

        # 4. Evaluate each query
        query_results = []
        total_score = 0.0
        queries_passed = 0

        for i, query_item in enumerate(queries):
            question = query_item.get("question", "")
            ground_truth = query_item.get("ground_truth", "")
            logger.info(f"[QueryEval {eval_run_id}] Evaluating query {i+1}/{len(queries)}: {question[:50]}...")

            result = await _evaluate_single_query(
                question=question,
                ground_truth=ground_truth,
                grand_schema=grand_schema,
                run_id=ingestion_run_id,
            )
            query_results.append(result)
            score = result.get("score", 0.0)
            total_score += score
            if score >= 0.7:
                queries_passed += 1

        # 5. Compute aggregate scores
        overall_score = total_score / len(queries) if queries else 0.0
        total_duration = int((time.time() - start_time) * 1000)

        # 6. Persist results
        async with async_session() as db:
            run = await db.get(QueryEvalRun, eval_run_id)
            if run:
                run.status = "completed"
                run.overall_score = overall_score
                run.queries_evaluated = len(queries)
                run.queries_passed = queries_passed
                run.query_results_json = query_results
                run.neo4j_stats_json = neo4j_stats
                run.total_duration_ms = total_duration
                run.completed_at = datetime.now(timezone.utc)
                await db.commit()

        logger.info(
            f"[QueryEval {eval_run_id}] ✓ Complete! "
            f"Score: {overall_score:.2f}, Passed: {queries_passed}/{len(queries)}"
        )

    except Exception as e:
        logger.error(f"[QueryEval {eval_run_id}] ✗ FAILED: {e}")
        import traceback
        logger.error(traceback.format_exc())
        async with async_session() as db:
            run = await db.get(QueryEvalRun, eval_run_id)
            if run:
                run.status = "failed"
                run.error_message = str(e)
                run.completed_at = datetime.now(timezone.utc)
                await db.commit()


async def _load_grand_schema(ingestion_run_id: str) -> dict[str, Any]:
    """Load the grand schema from a completed ingestion run."""
    async with async_session() as db:
        # Find the schema_exporter node execution for this run
        stmt = select(NodeExecution).where(
            NodeExecution.run_id == ingestion_run_id,
            NodeExecution.agent_type_name == "schema_exporter",
        )
        result = await db.execute(stmt)
        node_exec = result.scalar_one_or_none()

        if not node_exec or not node_exec.output_data_json:
            raise ValueError(f"No schema export found for run {ingestion_run_id}")

        return node_exec.output_data_json.get("grand_schema", {})


async def _load_kg_to_neo4j(ingestion_run_id: str, grand_schema: dict[str, Any]) -> dict[str, Any]:
    """Load the KG data into Neo4j from the grand schema's entity catalog."""
    # Get nodes from entity_catalog
    nodes = []
    for entity in grand_schema.get("entity_catalog", []):
        nodes.append({
            "id": entity.get("id", ""),
            "label": entity.get("name", ""),
            "type": entity.get("label", "Entity"),
            "properties": entity.get("properties", {}),
        })

    # Get edges from relationship_types examples + try to reconstruct from schema
    edges = []
    for rel_type, rel_info in grand_schema.get("relationship_types", {}).items():
        for example in rel_info.get("examples", []):
            source_name = example.get("source", "")
            target_name = example.get("target", "")
            # Find node IDs by name
            source_id = source_name.lower().replace(" ", "_")
            target_id = target_name.lower().replace(" ", "_")
            edges.append({
                "source": source_id,
                "target": target_id,
                "type": rel_type,
                "properties": example.get("properties", {}),
            })

    # Also try loading from the kg_builder's output directly
    async with async_session() as db:
        stmt = select(NodeExecution).where(
            NodeExecution.run_id == ingestion_run_id,
            NodeExecution.agent_type_name == "kg_builder",
        )
        result = await db.execute(stmt)
        kg_exec = result.scalar_one_or_none()

        if kg_exec and kg_exec.output_data_json:
            kg_data = kg_exec.output_data_json
            graph_data = kg_data.get("graph_data", {})
            if graph_data.get("nodes"):
                nodes = graph_data["nodes"]
            if graph_data.get("edges"):
                edges = graph_data["edges"]

    # Clear ALL existing data in Neo4j before loading (ensures clean evaluation state)
    await Neo4jService.clear_graph()

    # Load into Neo4j
    stats = await Neo4jService.load_kg(
        nodes=nodes,
        edges=edges,
        run_id=ingestion_run_id,
    )
    return stats


async def _evaluate_single_query(
    question: str,
    ground_truth: str,
    grand_schema: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    """Evaluate a single query through the full multi-agent pipeline with trace."""
    result = {
        "question": question,
        "ground_truth": ground_truth,
        "sub_queries": [],
        "cypher_statements": [],
        "query_results": [],
        "answer": "",
        "score": 0.0,
        "reasoning": "",
        "pipeline_trace": [],
        "schema_context": {
            "node_labels": list(grand_schema.get("node_labels", {}).keys()),
            "relationship_types": list(grand_schema.get("relationship_types", {}).keys()),
            "entity_count": len(grand_schema.get("entity_catalog", [])),
            "entity_names": [e.get("name", "") for e in grand_schema.get("entity_catalog", [])[:100]],
            "constraints_count": len(grand_schema.get("constraints", [])),
        },
    }

    try:
        # Step 1: Query Planning
        step_start = time.time()
        planner = AgentRegistry.create_instance("query_planner", node_id="eval_planner")
        plan_input = AgentInput(
            data={"question": question, "grand_schema": grand_schema},
            shared_state={},
        )
        plan_output = await planner.process(plan_input)
        sub_queries = plan_output.data.get("sub_queries", [])
        analysis = plan_output.data.get("analysis", "")
        result["sub_queries"] = sub_queries
        result["pipeline_trace"].append({
            "agent": "query_planner",
            "step": 1,
            "duration_ms": int((time.time() - step_start) * 1000),
            "input_summary": f"Question: {question[:100]}",
            "output_summary": f"{len(sub_queries)} sub-queries planned",
            "full_output": {"analysis": analysis, "sub_queries": sub_queries},
        })

        if not sub_queries:
            result["answer"] = "Could not decompose the query into sub-queries."
            result["score"] = 0.0
            return result

        # Step 2 & 3: Cypher Generation + Execution for each sub-query
        all_query_results = []
        for sq in sub_queries:
            # Generate Cypher
            step_start = time.time()
            generator = AgentRegistry.create_instance("cypher_generator", node_id="eval_cypher_gen")
            gen_input = AgentInput(
                data={"sub_query": sq, "grand_schema": grand_schema, "question": question},
                shared_state={},
            )
            gen_output = await generator.process(gen_input)
            cypher = gen_output.data.get("cypher", "")
            parameters = gen_output.data.get("parameters", {})
            explanation = gen_output.data.get("explanation", "")
            gen_duration = int((time.time() - step_start) * 1000)

            result["cypher_statements"].append({
                "sub_query_id": sq.get("id", ""),
                "intent": sq.get("intent", ""),
                "cypher": cypher,
                "parameters": parameters,
                "explanation": explanation,
            })
            result["pipeline_trace"].append({
                "agent": "cypher_generator",
                "step": 2,
                "duration_ms": gen_duration,
                "input_summary": f"Intent: {sq.get('intent', '')[:80]}",
                "output_summary": f"Cypher: {cypher[:80]}..." if cypher else "No Cypher generated",
                "full_output": {"cypher": cypher, "parameters": parameters, "explanation": explanation},
            })

            # Execute Cypher
            step_start = time.time()
            if cypher:
                executor = AgentRegistry.create_instance("cypher_executor", node_id="eval_executor")
                exec_input = AgentInput(
                    data={"cypher": cypher, "parameters": parameters, "run_id": run_id},
                    shared_state={},
                )
                exec_output = await executor.process(exec_input)
                exec_results = exec_output.data.get("results", [])
                exec_error = exec_output.data.get("error")
                query_result = {
                    "sub_query_id": sq.get("id", ""),
                    "intent": sq.get("intent", ""),
                    "cypher": cypher,
                    "results": exec_results,
                    "error": exec_error,
                }
            else:
                exec_results = []
                exec_error = "No Cypher generated"
                query_result = {
                    "sub_query_id": sq.get("id", ""),
                    "intent": sq.get("intent", ""),
                    "cypher": "",
                    "results": [],
                    "error": exec_error,
                }
            exec_duration = int((time.time() - step_start) * 1000)
            all_query_results.append(query_result)
            result["pipeline_trace"].append({
                "agent": "cypher_executor",
                "step": 3,
                "duration_ms": exec_duration,
                "input_summary": f"Cypher: {cypher[:60]}..." if cypher else "N/A",
                "output_summary": f"{len(exec_results)} results returned" if not exec_error else f"Error: {exec_error}",
                "full_output": {"results": exec_results[:10], "error": exec_error, "total_results": len(exec_results)},
            })

        result["query_results"] = all_query_results

        # Step 4: Answer Synthesis
        step_start = time.time()
        synthesizer = AgentRegistry.create_instance("answer_synthesizer", node_id="eval_synthesizer")
        synth_input = AgentInput(
            data={"question": question, "query_results": all_query_results},
            shared_state={},
        )
        synth_output = await synthesizer.process(synth_input)
        answer = synth_output.data.get("answer", "")
        confidence = synth_output.data.get("confidence", 0.0)
        gaps = synth_output.data.get("gaps", [])
        result["answer"] = answer
        result["pipeline_trace"].append({
            "agent": "answer_synthesizer",
            "step": 4,
            "duration_ms": int((time.time() - step_start) * 1000),
            "input_summary": f"{len(all_query_results)} sub-query results",
            "output_summary": f"Answer ({len(answer)} chars), confidence: {confidence:.2f}",
            "full_output": {"answer": answer, "confidence": confidence, "gaps": gaps},
        })

        # Step 5: Scoring
        step_start = time.time()
        scorer = AgentRegistry.create_instance("eval_scorer", node_id="eval_scorer")
        score_input = AgentInput(
            data={"question": question, "answer": answer, "ground_truth": ground_truth},
            shared_state={},
        )
        score_output = await scorer.process(score_input)
        overall_score = score_output.data.get("overall_score", 0.0)
        reasoning = score_output.data.get("reasoning", "")
        criteria_scores = score_output.data.get("criteria_scores", {})
        result["score"] = overall_score
        result["reasoning"] = reasoning
        result["criteria_scores"] = criteria_scores
        result["pipeline_trace"].append({
            "agent": "eval_scorer",
            "step": 5,
            "duration_ms": int((time.time() - step_start) * 1000),
            "input_summary": f"Answer vs ground truth ({len(ground_truth)} chars)",
            "output_summary": f"Score: {overall_score:.2f}",
            "full_output": {"overall_score": overall_score, "criteria_scores": criteria_scores, "reasoning": reasoning},
        })

    except Exception as e:
        logger.error(f"Error evaluating query '{question[:50]}...': {e}")
        result["error"] = str(e)
        result["score"] = 0.0

    return result
