"""Node execution model tracking individual agent node runs."""

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


class NodeExecution(Base):
    """Tracks the execution of a single node within an experiment run.

    input_data_json: the data passed into this node
    output_data_json: the data produced by this node
    memory_before_json: agent memory state before execution
    memory_after_json: agent memory state after execution
    logs_json: list of {timestamp, level, message}
    tool_calls_json: list of {tool_name, input, output, timestamp}
    """

    __tablename__ = "node_executions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("experiment_runs.id"), nullable=False
    )
    node_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_type_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_data_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    output_data_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    memory_before_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    memory_after_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    logs_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    tool_calls_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    run: Mapped["ExperimentRun"] = relationship(
        "ExperimentRun", back_populates="node_executions"
    )
