"""Graph CRUD API endpoints."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.compiler import compile_graph
from app.models.database import get_db
from app.models.graph import GraphDefinition

router = APIRouter(prefix="/graphs", tags=["graphs"])


# ─── Request / Response Schemas ───────────────────────────────────────────────


class GraphCreate(BaseModel):
    name: str
    description: Optional[str] = None
    nodes_json: list[dict[str, Any]] = []
    edges_json: list[dict[str, Any]] = []


class GraphUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    nodes_json: Optional[list[dict[str, Any]]] = None
    edges_json: Optional[list[dict[str, Any]]] = None


class GraphResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    nodes_json: list[dict[str, Any]]
    edges_json: list[dict[str, Any]]
    created_at: str
    updated_at: Optional[str]

    model_config = {"from_attributes": True}


class GraphValidationResponse(BaseModel):
    valid: bool
    execution_order: list[str] | None = None
    node_count: int = 0
    edge_count: int = 0
    errors: list[str] = []


# ─── Helper ───────────────────────────────────────────────────────────────────


def _graph_to_response(graph: GraphDefinition) -> GraphResponse:
    return GraphResponse(
        id=graph.id,
        name=graph.name,
        description=graph.description,
        nodes_json=graph.nodes_json or [],
        edges_json=graph.edges_json or [],
        created_at=graph.created_at.isoformat() if graph.created_at else "",
        updated_at=graph.updated_at.isoformat() if graph.updated_at else None,
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("", response_model=GraphResponse, status_code=status.HTTP_201_CREATED)
async def create_graph(
    body: GraphCreate,
    db: AsyncSession = Depends(get_db),
) -> GraphResponse:
    """Create a new graph definition."""
    graph = GraphDefinition(
        name=body.name,
        description=body.description,
        nodes_json=body.nodes_json,
        edges_json=body.edges_json,
    )
    db.add(graph)
    await db.flush()
    await db.refresh(graph)
    return _graph_to_response(graph)


@router.get("", response_model=list[GraphResponse])
async def list_graphs(
    db: AsyncSession = Depends(get_db),
) -> list[GraphResponse]:
    """List all saved graph definitions."""
    result = await db.execute(
        select(GraphDefinition).order_by(GraphDefinition.created_at.desc())
    )
    graphs = result.scalars().all()
    return [_graph_to_response(g) for g in graphs]


@router.get("/{graph_id}", response_model=GraphResponse)
async def get_graph(
    graph_id: str,
    db: AsyncSession = Depends(get_db),
) -> GraphResponse:
    """Get a specific graph definition."""
    graph = await db.get(GraphDefinition, graph_id)
    if not graph:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Graph '{graph_id}' not found",
        )
    return _graph_to_response(graph)


@router.put("/{graph_id}", response_model=GraphResponse)
async def update_graph(
    graph_id: str,
    body: GraphUpdate,
    db: AsyncSession = Depends(get_db),
) -> GraphResponse:
    """Update a graph definition (any subset of fields)."""
    graph = await db.get(GraphDefinition, graph_id)
    if not graph:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Graph '{graph_id}' not found",
        )

    if body.name is not None:
        graph.name = body.name
    if body.description is not None:
        graph.description = body.description
    if body.nodes_json is not None:
        graph.nodes_json = body.nodes_json
    if body.edges_json is not None:
        graph.edges_json = body.edges_json

    await db.flush()
    await db.refresh(graph)
    return _graph_to_response(graph)


@router.delete("/{graph_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_graph(
    graph_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a graph definition."""
    graph = await db.get(GraphDefinition, graph_id)
    if not graph:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Graph '{graph_id}' not found",
        )
    await db.delete(graph)
    await db.flush()


@router.post("/{graph_id}/validate", response_model=GraphValidationResponse)
async def validate_graph(
    graph_id: str,
    db: AsyncSession = Depends(get_db),
) -> GraphValidationResponse:
    """Validate a graph (check for cycles, missing agents, etc.)."""
    graph = await db.get(GraphDefinition, graph_id)
    if not graph:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Graph '{graph_id}' not found",
        )

    errors: list[str] = []
    nodes = graph.nodes_json or []
    edges = graph.edges_json or []

    if not nodes:
        errors.append("Graph has no nodes")

    # Validate agent types exist in the registry
    from app.agents.registry import AgentRegistry

    for node in nodes:
        agent_type = node.get("agent_type", "")
        if not agent_type:
            errors.append(f"Node '{node.get('id', '?')}' has no agent_type")
        else:
            cls = AgentRegistry.get_agent_class(agent_type)
            if cls is None and agent_type not in AgentRegistry._custom_configs:
                errors.append(
                    f"Node '{node.get('id', '?')}' references unknown agent type: '{agent_type}'"
                )

    # Try to compile (checks for cycles and edge validity)
    try:
        compiled = compile_graph({"nodes": nodes, "edges": edges})
        return GraphValidationResponse(
            valid=len(errors) == 0,
            execution_order=compiled.execution_order if not errors else None,
            node_count=len(nodes),
            edge_count=len(edges),
            errors=errors,
        )
    except ValueError as e:
        errors.append(str(e))
        return GraphValidationResponse(
            valid=False,
            execution_order=None,
            node_count=len(nodes),
            edge_count=len(edges),
            errors=errors,
        )
