"""Agent type model defining reusable agent templates."""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class AgentType(Base):
    """Defines a reusable agent type with default configuration.

    input_schema_json: list of {field_name, type, description, required}
    output_schema_json: list of {field_name, type, description}
    tools_json: list of {name, description, parameters, implementation_type, implementation_code}
    memory_config_json: {type, initial_state, max_tokens, overflow_strategy, persistence, sharing, injection_mode}
    """

    __tablename__ = "agent_types"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    default_system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_model: Mapped[str] = mapped_column(
        String(100), nullable=False, default="gpt-4o"
    )
    default_temperature: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.2
    )
    default_max_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=4096
    )
    vision_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    input_schema_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    output_schema_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    tools_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    memory_config_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=func.now()
    )
