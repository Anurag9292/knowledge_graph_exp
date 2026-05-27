"""Graph definition model for storing agent pipeline DAGs."""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class GraphDefinition(Base):
    """Represents a directed acyclic graph of agent nodes and edges.

    nodes_json stores a list of node definitions, each with:
        - id: str
        - agent_type_id: str
        - position_x: float
        - position_y: float
        - config: dict (system_prompt override, model override, memory_config, tools)

    edges_json stores a list of edge definitions, each with:
        - id: str
        - source_node_id: str
        - target_node_id: str
        - data_mapping: dict
    """

    __tablename__ = "graph_definitions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    nodes_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    edges_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=func.now()
    )
