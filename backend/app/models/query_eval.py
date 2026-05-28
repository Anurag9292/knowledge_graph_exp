"""Query evaluation configuration and result models for Phase 2."""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


class QueryEvalConfig(Base):
    """
    Defines a set of test queries with ground truth for evaluating a KG.
    
    Each config contains multiple queries, each with:
    - A natural language question
    - Expected ground truth answer
    - Optional difficulty rating
    """

    __tablename__ = "query_eval_configs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    
    # List of {question, ground_truth, difficulty, tags}
    queries_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    
    # Scoring configuration
    scoring_model: Mapped[str] = mapped_column(
        String(100), nullable=False, default="gpt-4.1"
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=func.now()
    )

    # Relationships
    eval_runs: Mapped[list["QueryEvalRun"]] = relationship(
        back_populates="config", cascade="all, delete-orphan"
    )


class QueryEvalRun(Base):
    """
    A single evaluation run — evaluates a specific ingestion run against a query config.
    
    Links an ingestion run_id to a query_eval_config and stores results.
    """

    __tablename__ = "query_eval_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    config_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("query_eval_configs.id"), nullable=False
    )
    # The ingestion run being evaluated
    ingestion_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("experiment_runs.id"), nullable=False
    )
    
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending"
    )  # pending, running, completed, failed
    
    # Aggregate scores
    overall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    queries_evaluated: Mapped[int] = mapped_column(Integer, default=0)
    queries_passed: Mapped[int] = mapped_column(Integer, default=0)
    
    # Detailed per-query results
    # List of {question, ground_truth, sub_queries, cypher_statements, results, answer, score, reasoning}
    query_results_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    
    # Neo4j loading stats
    neo4j_stats_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    
    # Timing
    total_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Relationships
    config: Mapped["QueryEvalConfig"] = relationship(back_populates="eval_runs")
