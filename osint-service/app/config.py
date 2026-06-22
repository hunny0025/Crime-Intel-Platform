"""OSINT Service configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://cip:cip_secret@postgres:5432/crime_intel"
    NEO4J_URI: str = "bolt://neo4j:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "crimeintel2024"
    NEO4J_DATABASE: str = "neo4j"

    # OSINT API credentials (all optional — adapters check availability)
    CRT_SH_URL: str = "https://crt.sh"

    # Social platform API keys (empty = adapter unavailable)
    TWITTER_BEARER_TOKEN: str = ""
    GITHUB_TOKEN: str = ""

    # Blockchain explorer API keys
    BLOCKCHAIN_API_KEY: str = ""
    ETHERSCAN_API_KEY: str = ""

    APP_NAME: str = "OSINT Intelligence Service"
    APP_VERSION: str = "0.1.0"

    class Config:
        env_prefix = ""


settings = Settings()

# Sanitize DATABASE_URL to avoid SQLAlchemy dialect issues with postgres:// (e.g. on Render)
if settings.DATABASE_URL.startswith("postgres://"):
    settings.DATABASE_URL = settings.DATABASE_URL.replace("postgres://", "postgresql://", 1)

