from pydantic_settings import BaseSettings, SettingsConfigDict


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
    NEO4J_DATABASE: str = "graphingest_eval"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Application
    APP_NAME: str = "GraphIngest"
    DEBUG: bool = False


settings = Settings()


def get_settings() -> Settings:
    """Get the application settings instance."""
    return settings
