from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel


class IngestionConfig(BaseModel):
    """Streaming ingestion configuration — all tunables in one place."""

    # ─── Auto-Streaming Threshold ────────────────────────────────────────────
    # Documents above this char count automatically use the streaming pipeline
    STREAMING_THRESHOLD_CHARS: int = 5000

    # ─── Chunking Parameters ─────────────────────────────────────────────────
    CHUNK_TARGET_SIZE: int = 3000       # Ideal chunk size (chars)
    CHUNK_MAX_SIZE: int = 5000          # Max chunk size (tables/code blocks can exceed target)
    CHUNK_MIN_SIZE: int = 500           # Don't create chunks smaller than this (merge with neighbor)
    CHUNK_OVERLAP: int = 200            # Context overlap between adjacent chunks

    # ─── Structural Detection ────────────────────────────────────────────────
    # Heading patterns for section boundary detection (regex)
    HEADING_PATTERNS: list[str] = [
        r"^#{1,6}\s+.+",              # Markdown headings: # Title, ## Section
        r"^={2,}\s*.+\s*={2,}$",      # Wiki-style: == Heading ==
        r"^[A-Z][A-Z\s]{4,}$",        # ALL-CAPS lines (common in plain text docs)
        r"^\d+\.\s+[A-Z]",            # Numbered sections: 1. Introduction
    ]
    TABLE_DETECTION: bool = True        # Detect and keep tables intact
    CODE_BLOCK_DETECTION: bool = True   # Detect and keep code blocks intact
    LIST_BLOCK_DETECTION: bool = True   # Detect and keep list blocks intact

    # ─── Model Escalation (Complexity Scorer → Model Map) ────────────────────
    MODEL_TIER_DEFAULT: str = "gpt-4.1-mini"
    MODEL_TIER_COMPLEX: str = "gpt-4.1"
    MODEL_TIER_VISION: str = "gpt-4o"

    # Complexity score thresholds
    COMPLEXITY_THRESHOLD_ESCALATE: int = 5  # Score >= this → MODEL_TIER_COMPLEX

    # Complexity scoring weights
    COMPLEXITY_WEIGHT_TABLE: int = 3        # Each table in chunk adds this
    COMPLEXITY_WEIGHT_CODE: int = 2         # Code blocks add this
    COMPLEXITY_WEIGHT_LENGTH_PER_1K: int = 1  # Per 1000 chars above target
    COMPLEXITY_WEIGHT_NESTED: int = 2       # Nested structures (lists in lists, etc.)
    COMPLEXITY_WEIGHT_DENSE_ENTITIES: int = 2  # High entity density estimate

    # ─── Schema Evolution ────────────────────────────────────────────────────
    SCHEMA_DEDUP_EXACT_MATCH: bool = True   # Skip adding types that already exist by name
    SCHEMA_MAX_TYPES_PER_CHUNK: int = 10    # Cap new types proposed per chunk

    # ─── Processing Limits ───────────────────────────────────────────────────
    MAX_CHUNKS_PER_DOCUMENT: int = 100      # Safety limit
    MAX_CONCURRENT_CHUNK_CALLS: int = 1     # Sequential by default (maintains context)
    CHUNK_TIMEOUT_SECONDS: int = 60         # Per-chunk LLM timeout


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # API Keys
    OPENAI_API_KEY: str = ""

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./db/graphingest.db"

    # Neo4j
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"
    NEO4J_DATABASE: str = "neo4j"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Application
    APP_NAME: str = "GraphIngest"
    DEBUG: bool = False

    # Ingestion
    ingestion: IngestionConfig = IngestionConfig()


settings = Settings()


def get_settings() -> Settings:
    """Get the application settings instance."""
    return settings
