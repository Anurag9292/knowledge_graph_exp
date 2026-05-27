"""Experiment session and run models for tracking graph executions."""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


class ExperimentSession(Base):
    """A session groups multiple runs of the same graph for iterative refinement.

    experiment_memory_json stores cross-run memory:
        - corrections: list of user corrections applied across runs
        - best_outputs: dict of best outputs per node
        - etc.
    """

    __tablename__ = "experiment_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    graph_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("graph_definitions.id"), nullable=False
    )
    input_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_document_path: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    experiment_memory_json: Mapped[Optional[Any]] = mapped_column(
        JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=func.now()
    )

    # Relationships
    runs: Mapped[list["ExperimentRun"]] = relationship(
        "ExperimentRun", back_populates="session", lazy="selectin"
    )


class ExperimentRun(Base):
    """A single execution of a graph within a session.

    graph_snapshot_json: full copy of the graph definition at time of run
    config_json: any run-specific overrides (model, temperature, etc.)
    """

    __tablename__ = "experiment_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("experiment_sessions.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    graph_snapshot_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    config_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    total_tokens_used: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    total_duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Relationships
    session: Mapped["ExperimentSession"] = relationship(
        "ExperimentSession", back_populates="runs"
    )
    node_executions: Mapped[list["NodeExecution"]] = relationship(
        "NodeExecution", back_populates="run", lazy="selectin"
    )
