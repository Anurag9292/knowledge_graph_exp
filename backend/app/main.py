import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import settings
from app.models.database import Base, engine, async_session
from app.models.graph import GraphDefinition
from app.api.graphs import router as graphs_router
from app.api.experiments import router as experiments_router
from app.api.agents import router as agents_router
from app.api.documents import router as documents_router
from app.api.evals import router as evals_router
from app.api.ws import router as ws_router

# Import built-in agents so they register with AgentRegistry on startup
import app.agents.builtin  # noqa: F401

logger = logging.getLogger(__name__)


# ─── Default Pipeline Definition ──────────────────────────────────────────────

DEFAULT_PIPELINE = {
    "name": "Knowledge Graph Pipeline",
    "description": "Default end-to-end pipeline: analyze structure → extract ontology → extract relationships → resolve entities → build knowledge graph. Ready to use out of the box.",
    "nodes": [
        {
            "id": "node_structure",
            "agent_type": "structure_inferrer",
            "position_x": 50,
            "position_y": 200,
            "config": {},
        },
        {
            "id": "node_ontology",
            "agent_type": "ontology_extractor",
            "position_x": 350,
            "position_y": 100,
            "config": {},
        },
        {
            "id": "node_relationships",
            "agent_type": "relationship_extractor",
            "position_x": 350,
            "position_y": 320,
            "config": {},
        },
        {
            "id": "node_resolver",
            "agent_type": "entity_resolver",
            "position_x": 650,
            "position_y": 200,
            "config": {},
        },
        {
            "id": "node_kg",
            "agent_type": "kg_builder",
            "position_x": 950,
            "position_y": 200,
            "config": {},
        },
    ],
    "edges": [
        {
            "id": "edge_struct_to_ontology",
            "source_node_id": "node_structure",
            "target_node_id": "node_ontology",
            "data_mapping": {},
            "edge_type": "default",
        },
        {
            "id": "edge_struct_to_rel",
            "source_node_id": "node_structure",
            "target_node_id": "node_relationships",
            "data_mapping": {},
            "edge_type": "default",
        },
        {
            "id": "edge_ontology_to_resolver",
            "source_node_id": "node_ontology",
            "target_node_id": "node_resolver",
            "data_mapping": {"entities": "entities"},
            "edge_type": "default",
        },
        {
            "id": "edge_rel_to_resolver",
            "source_node_id": "node_relationships",
            "target_node_id": "node_resolver",
            "data_mapping": {},
            "edge_type": "default",
        },
        {
            "id": "edge_resolver_to_kg",
            "source_node_id": "node_resolver",
            "target_node_id": "node_kg",
            "data_mapping": {},
            "edge_type": "default",
        },
    ],
}


async def _seed_default_pipeline() -> None:
    """Seed the default KG pipeline if no graphs exist yet."""
    async with async_session() as db:
        result = await db.execute(select(GraphDefinition).limit(1))
        if result.scalars().first() is not None:
            return  # Graphs already exist, skip seeding

        graph = GraphDefinition(
            name=DEFAULT_PIPELINE["name"],
            description=DEFAULT_PIPELINE["description"],
            nodes_json=DEFAULT_PIPELINE["nodes"],
            edges_json=DEFAULT_PIPELINE["edges"],
        )
        db.add(graph)
        await db.commit()
        logger.info(f"Seeded default pipeline: '{graph.name}' (id={graph.id})")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: create DB tables on startup, seed defaults."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _seed_default_pipeline()
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    description="Graph-based multi-agent document ingestion platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(graphs_router, prefix="/api")
app.include_router(experiments_router, prefix="/api")
app.include_router(agents_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(evals_router, prefix="/api")
app.include_router(ws_router, prefix="/api")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": settings.APP_NAME}
