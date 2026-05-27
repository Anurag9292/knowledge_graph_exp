"""Agent type management API endpoints."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import AgentRegistry
from app.models.agent_type import AgentType
from app.models.database import get_db

router = APIRouter(prefix="/agents", tags=["agents"])


# ─── Request / Response Schemas ───────────────────────────────────────────────


class AgentTypeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    default_system_prompt: Optional[str] = None
    default_model: str = "gpt-4o"
    default_temperature: float = 0.2
    default_max_tokens: int = 4096
    vision_enabled: bool = False
    input_schema_json: Optional[list[dict[str, Any]]] = None
    output_schema_json: Optional[list[dict[str, Any]]] = None
    tools_json: Optional[list[dict[str, Any]]] = None
    memory_config_json: Optional[dict[str, Any]] = None


class AgentTypeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    default_system_prompt: Optional[str] = None
    default_model: Optional[str] = None
    default_temperature: Optional[float] = None
    default_max_tokens: Optional[int] = None
    vision_enabled: Optional[bool] = None
    input_schema_json: Optional[list[dict[str, Any]]] = None
    output_schema_json: Optional[list[dict[str, Any]]] = None
    tools_json: Optional[list[dict[str, Any]]] = None
    memory_config_json: Optional[dict[str, Any]] = None


class AgentTypeResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    category: Optional[str]
    default_system_prompt: Optional[str]
    default_model: str
    default_temperature: float
    default_max_tokens: int
    vision_enabled: bool
    input_schema_json: Optional[list[dict[str, Any]]]
    output_schema_json: Optional[list[dict[str, Any]]]
    tools_json: Optional[list[dict[str, Any]]]
    memory_config_json: Optional[dict[str, Any]]
    is_builtin: bool
    created_at: str
    updated_at: Optional[str]

    model_config = {"from_attributes": True}


class AgentTypeSummary(BaseModel):
    """Lightweight summary including built-in agents from registry."""
    id: Optional[str] = None
    name: str
    description: Optional[str]
    category: Optional[str]
    default_system_prompt: Optional[str] = None
    default_model: str
    default_temperature: float = 0.2
    default_max_tokens: int = 4096
    vision_enabled: bool
    is_builtin: bool


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _agent_type_to_response(at: AgentType) -> AgentTypeResponse:
    return AgentTypeResponse(
        id=at.id,
        name=at.name,
        description=at.description,
        category=at.category,
        default_system_prompt=at.default_system_prompt,
        default_model=at.default_model,
        default_temperature=at.default_temperature,
        default_max_tokens=at.default_max_tokens,
        vision_enabled=at.vision_enabled,
        input_schema_json=at.input_schema_json,
        output_schema_json=at.output_schema_json,
        tools_json=at.tools_json,
        memory_config_json=at.memory_config_json,
        is_builtin=at.is_builtin,
        created_at=at.created_at.isoformat() if at.created_at else "",
        updated_at=at.updated_at.isoformat() if at.updated_at else None,
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/types", response_model=list[AgentTypeSummary])
async def list_agent_types(
    db: AsyncSession = Depends(get_db),
) -> list[AgentTypeSummary]:
    """List all available agent types (built-in from registry + custom from DB)."""
    summaries: list[AgentTypeSummary] = []

    # Built-in agents from registry
    for agent_info in AgentRegistry.list_agents():
        if agent_info.get("is_builtin"):
            summaries.append(
                AgentTypeSummary(
                    id=None,
                    name=agent_info["name"],
                    description=agent_info.get("description"),
                    category=agent_info.get("category"),
                    default_system_prompt=agent_info.get("default_system_prompt"),
                    default_model=agent_info.get("default_model", "gpt-4o"),
                    default_temperature=agent_info.get("default_temperature", 0.2),
                    default_max_tokens=agent_info.get("default_max_tokens", 4096),
                    vision_enabled=agent_info.get("vision_enabled", False),
                    is_builtin=True,
                )
            )

    # Custom agents from DB
    result = await db.execute(
        select(AgentType).order_by(AgentType.created_at.desc())
    )
    db_types = result.scalars().all()
    for at in db_types:
        summaries.append(
            AgentTypeSummary(
                id=at.id,
                name=at.name,
                description=at.description,
                category=at.category,
                default_model=at.default_model,
                vision_enabled=at.vision_enabled,
                is_builtin=at.is_builtin,
            )
        )

    return summaries


@router.get("/types/{agent_type_id}", response_model=AgentTypeResponse)
async def get_agent_type(
    agent_type_id: str,
    db: AsyncSession = Depends(get_db),
) -> AgentTypeResponse:
    """Get a specific agent type definition by ID."""
    at = await db.get(AgentType, agent_type_id)
    if not at:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent type '{agent_type_id}' not found",
        )
    return _agent_type_to_response(at)


@router.post("/types", response_model=AgentTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_type(
    body: AgentTypeCreate,
    db: AsyncSession = Depends(get_db),
) -> AgentTypeResponse:
    """Create a custom agent type."""
    # Check for name uniqueness
    existing = await db.execute(
        select(AgentType).where(AgentType.name == body.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent type with name '{body.name}' already exists",
        )

    # Also check if it conflicts with a built-in agent name
    if AgentRegistry.get_agent_class(body.name) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Name '{body.name}' conflicts with a built-in agent type",
        )

    agent_type = AgentType(
        name=body.name,
        description=body.description,
        category=body.category,
        default_system_prompt=body.default_system_prompt,
        default_model=body.default_model,
        default_temperature=body.default_temperature,
        default_max_tokens=body.default_max_tokens,
        vision_enabled=body.vision_enabled,
        input_schema_json=body.input_schema_json,
        output_schema_json=body.output_schema_json,
        tools_json=body.tools_json,
        memory_config_json=body.memory_config_json,
        is_builtin=False,
    )
    db.add(agent_type)
    await db.flush()
    await db.refresh(agent_type)

    # Register in the runtime registry so it can be used immediately
    AgentRegistry.register_custom(
        name=body.name,
        config={
            "description": body.description or "",
            "category": body.category or "custom",
            "system_prompt": body.default_system_prompt or "",
            "model": body.default_model,
            "temperature": body.default_temperature,
            "max_tokens": body.default_max_tokens,
            "vision_enabled": body.vision_enabled,
            "tools": body.tools_json or [],
            "memory_config": body.memory_config_json or {},
        },
    )

    return _agent_type_to_response(agent_type)


@router.put("/types/{agent_type_id}", response_model=AgentTypeResponse)
async def update_agent_type(
    agent_type_id: str,
    body: AgentTypeUpdate,
    db: AsyncSession = Depends(get_db),
) -> AgentTypeResponse:
    """Update a custom agent type."""
    at = await db.get(AgentType, agent_type_id)
    if not at:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent type '{agent_type_id}' not found",
        )

    if at.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify a built-in agent type",
        )

    old_name = at.name

    if body.name is not None:
        # Check uniqueness
        existing = await db.execute(
            select(AgentType).where(AgentType.name == body.name, AgentType.id != agent_type_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Agent type with name '{body.name}' already exists",
            )
        at.name = body.name
    if body.description is not None:
        at.description = body.description
    if body.category is not None:
        at.category = body.category
    if body.default_system_prompt is not None:
        at.default_system_prompt = body.default_system_prompt
    if body.default_model is not None:
        at.default_model = body.default_model
    if body.default_temperature is not None:
        at.default_temperature = body.default_temperature
    if body.default_max_tokens is not None:
        at.default_max_tokens = body.default_max_tokens
    if body.vision_enabled is not None:
        at.vision_enabled = body.vision_enabled
    if body.input_schema_json is not None:
        at.input_schema_json = body.input_schema_json
    if body.output_schema_json is not None:
        at.output_schema_json = body.output_schema_json
    if body.tools_json is not None:
        at.tools_json = body.tools_json
    if body.memory_config_json is not None:
        at.memory_config_json = body.memory_config_json

    await db.flush()
    await db.refresh(at)

    # Update the runtime registry
    # Remove old registration if name changed
    if old_name != at.name and old_name in AgentRegistry._custom_configs:
        del AgentRegistry._custom_configs[old_name]

    AgentRegistry.register_custom(
        name=at.name,
        config={
            "description": at.description or "",
            "category": at.category or "custom",
            "system_prompt": at.default_system_prompt or "",
            "model": at.default_model,
            "temperature": at.default_temperature,
            "max_tokens": at.default_max_tokens,
            "vision_enabled": at.vision_enabled,
            "tools": at.tools_json or [],
            "memory_config": at.memory_config_json or {},
        },
    )

    return _agent_type_to_response(at)


@router.delete("/types/{agent_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent_type(
    agent_type_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a custom agent type (only non-builtin)."""
    at = await db.get(AgentType, agent_type_id)
    if not at:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent type '{agent_type_id}' not found",
        )

    if at.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete a built-in agent type",
        )

    # Remove from runtime registry
    AgentRegistry._custom_configs.pop(at.name, None)

    await db.delete(at)
    await db.flush()
