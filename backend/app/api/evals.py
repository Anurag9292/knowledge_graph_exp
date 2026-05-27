"""Evaluation management API endpoints."""

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.eval import EvalConfig, EvalResult
from app.models.experiment import ExperimentRun

router = APIRouter(prefix="/evals", tags=["evals"])


# ─── Request / Response Schemas ───────────────────────────────────────────────


class EvalConfigCreate(BaseModel):
    name: str
    description: Optional[str] = None
    criteria_json: Optional[list[dict[str, Any]]] = None
    scoring_type: str = "llm_judge"
    ground_truth_json: Optional[dict[str, Any]] = None
    model: str = "gpt-4o"


class EvalConfigResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    criteria_json: Optional[list[dict[str, Any]]]
    scoring_type: str
    ground_truth_json: Optional[dict[str, Any]]
    model: str
    created_at: str

    model_config = {"from_attributes": True}


class EvalRunRequest(BaseModel):
    eval_config_id: str
    run_ids: list[str]


class EvalResultResponse(BaseModel):
    id: str
    run_id: str
    eval_config_id: str
    overall_score: float
    criteria_scores_json: Optional[dict[str, Any]]
    details_json: Optional[dict[str, Any]]
    created_at: str

    model_config = {"from_attributes": True}


class EvalRunResponse(BaseModel):
    """Response for a batch eval run request."""
    eval_config_id: str
    results: list[EvalResultResponse]
    errors: list[dict[str, str]] = []


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _config_to_response(config: EvalConfig) -> EvalConfigResponse:
    return EvalConfigResponse(
        id=config.id,
        name=config.name,
        description=config.description,
        criteria_json=config.criteria_json,
        scoring_type=config.scoring_type,
        ground_truth_json=config.ground_truth_json,
        model=config.model,
        created_at=config.created_at.isoformat() if config.created_at else "",
    )


def _result_to_response(result: EvalResult) -> EvalResultResponse:
    return EvalResultResponse(
        id=result.id,
        run_id=result.run_id,
        eval_config_id=result.eval_config_id,
        overall_score=result.overall_score,
        criteria_scores_json=result.criteria_scores_json,
        details_json=result.details_json,
        created_at=result.created_at.isoformat() if result.created_at else "",
    )


async def _evaluate_run(
    run: ExperimentRun,
    config: EvalConfig,
    db: AsyncSession,
) -> EvalResult:
    """
    Evaluate a single run against an eval config.

    In a full implementation, this would:
    - For 'llm_judge': call an LLM to score the outputs
    - For 'exact_match': compare outputs to ground truth
    - For 'similarity': compute embedding similarity scores

    For now, returns a placeholder score based on run status.
    """
    criteria = config.criteria_json or []
    criteria_scores: dict[str, Any] = {}
    details: dict[str, Any] = {"method": config.scoring_type}

    if config.scoring_type == "llm_judge":
        # Placeholder: in real implementation, call the LLM judge
        # Score based on run status and completeness
        base_score = 0.0
        if run.status == "completed":
            base_score = 0.7
        elif run.status == "failed":
            base_score = 0.0
        elif run.status == "cancelled":
            base_score = 0.2

        for criterion in criteria:
            crit_name = criterion.get("name", "unknown")
            weight = criterion.get("weight", 1.0)
            # Placeholder scoring — real impl would call LLM
            criteria_scores[crit_name] = {
                "score": base_score,
                "weight": weight,
                "explanation": f"Placeholder score for '{crit_name}' (run status: {run.status})",
            }

        # Compute weighted average
        if criteria_scores:
            total_weight = sum(c.get("weight", 1.0) for c in criteria_scores.values())
            overall_score = (
                sum(c["score"] * c.get("weight", 1.0) for c in criteria_scores.values())
                / total_weight
                if total_weight > 0
                else base_score
            )
        else:
            overall_score = base_score

        details["run_status"] = run.status
        details["total_tokens"] = run.total_tokens_used

    elif config.scoring_type == "exact_match":
        # Compare run outputs to ground truth
        ground_truth = config.ground_truth_json or {}
        # Placeholder: real impl would compare node outputs
        overall_score = 0.5
        details["ground_truth_keys"] = list(ground_truth.keys())

    elif config.scoring_type == "similarity":
        # Compute embedding similarity
        overall_score = 0.5
        details["method"] = "cosine_similarity"

    else:
        overall_score = 0.0
        details["error"] = f"Unknown scoring type: {config.scoring_type}"

    eval_result = EvalResult(
        id=str(uuid.uuid4()),
        run_id=run.id,
        eval_config_id=config.id,
        overall_score=overall_score,
        criteria_scores_json=criteria_scores,
        details_json=details,
    )
    db.add(eval_result)
    return eval_result


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/configs", response_model=EvalConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_eval_config(
    body: EvalConfigCreate,
    db: AsyncSession = Depends(get_db),
) -> EvalConfigResponse:
    """Create an evaluation configuration."""
    config = EvalConfig(
        name=body.name,
        description=body.description,
        criteria_json=body.criteria_json,
        scoring_type=body.scoring_type,
        ground_truth_json=body.ground_truth_json,
        model=body.model,
    )
    db.add(config)
    await db.flush()
    await db.refresh(config)
    return _config_to_response(config)


@router.get("/configs", response_model=list[EvalConfigResponse])
async def list_eval_configs(
    db: AsyncSession = Depends(get_db),
) -> list[EvalConfigResponse]:
    """List all evaluation configurations."""
    result = await db.execute(
        select(EvalConfig).order_by(EvalConfig.created_at.desc())
    )
    configs = result.scalars().all()
    return [_config_to_response(c) for c in configs]


@router.get("/configs/{config_id}", response_model=EvalConfigResponse)
async def get_eval_config(
    config_id: str,
    db: AsyncSession = Depends(get_db),
) -> EvalConfigResponse:
    """Get eval config details."""
    config = await db.get(EvalConfig, config_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Eval config '{config_id}' not found",
        )
    return _config_to_response(config)


@router.post("/run", response_model=EvalRunResponse)
async def run_evaluation(
    body: EvalRunRequest,
    db: AsyncSession = Depends(get_db),
) -> EvalRunResponse:
    """Run evaluation on specific runs."""
    # Load config
    config = await db.get(EvalConfig, body.eval_config_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Eval config '{body.eval_config_id}' not found",
        )

    if not body.run_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="run_ids list cannot be empty",
        )

    results: list[EvalResultResponse] = []
    errors: list[dict[str, str]] = []

    for run_id in body.run_ids:
        run = await db.get(ExperimentRun, run_id)
        if not run:
            errors.append({"run_id": run_id, "error": f"Run '{run_id}' not found"})
            continue

        if run.status not in ("completed", "failed", "cancelled"):
            errors.append({
                "run_id": run_id,
                "error": f"Run '{run_id}' is still in progress (status: {run.status})",
            })
            continue

        try:
            eval_result = await _evaluate_run(run, config, db)
            await db.flush()
            await db.refresh(eval_result)
            results.append(_result_to_response(eval_result))
        except Exception as exc:
            errors.append({"run_id": run_id, "error": str(exc)})

    return EvalRunResponse(
        eval_config_id=body.eval_config_id,
        results=results,
        errors=errors,
    )


@router.get("/results/{run_id}", response_model=list[EvalResultResponse])
async def get_eval_results(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[EvalResultResponse]:
    """Get all eval results for a specific run."""
    # Verify run exists
    run = await db.get(ExperimentRun, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        )

    result = await db.execute(
        select(EvalResult)
        .where(EvalResult.run_id == run_id)
        .order_by(EvalResult.created_at.desc())
    )
    eval_results = result.scalars().all()
    return [_result_to_response(r) for r in eval_results]
