"""Evaluation configuration and result models."""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class EvalConfig(Base):
    """Defines evaluation criteria and scoring methodology.

    criteria_json: list of {name, description, weight, scoring_method}
    ground_truth_json: expected output for ground truth comparison
    """

    __tablename__ = "eval_configs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    criteria_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    scoring_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="llm_judge"
    )
    ground_truth_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    model: Mapped[str] = mapped_column(
        String(100), nullable=False, default="gpt-4o"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class EvalResult(Base):
    """Stores the result of evaluating an experiment run.

    criteria_scores_json: dict of {criterion_name: score}
    details_json: detailed explanation from LLM judge or scoring function
    """

    __tablename__ = "eval_results"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("experiment_runs.id"), nullable=False
    )
    eval_config_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_configs.id"), nullable=False
    )
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    criteria_scores_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    details_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
