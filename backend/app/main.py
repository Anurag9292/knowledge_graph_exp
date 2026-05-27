from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models.database import Base, engine
from app.api.graphs import router as graphs_router
from app.api.experiments import router as experiments_router
from app.api.agents import router as agents_router
from app.api.documents import router as documents_router
from app.api.evals import router as evals_router
from app.api.ws import router as ws_router

# Import built-in agents so they register with AgentRegistry on startup
import app.agents.builtin  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: create DB tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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
