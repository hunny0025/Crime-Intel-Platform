from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # PostgreSQL
    DATABASE_URL: str = "postgresql://cip:cip_secret@postgres:5432/crime_intel"
    TEST_DATABASE_URL: str = "postgresql://cip:cip_secret@postgres:5432/crime_intel_test"

    # MinIO
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "evidence"
    MINIO_SECURE: bool = False

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"

    # Neo4j
    NEO4J_URI: str = "bolt://neo4j:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "crimeintel2024"
    NEO4J_DATABASE: str = "neo4j"

    # App
    APP_NAME: str = "Crime Intel Platform"
    APP_VERSION: str = "0.1.0"

    # ── Security ────────────────────────────────────────────────────────
    # CORS: Explicit allowlist of origins. NO wildcards in production.
    # Override via env: ALLOWED_ORIGINS='["https://forensics.gov.in","https://intel.police.local"]'
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
    ]

    # API key for machine-to-machine calls (services, CI, monitoring)
    API_SECRET_KEY: str = "change-me-in-production-32-chars!"

    # Rate limiting: max requests per minute per IP
    RATE_LIMIT_PER_MINUTE: int = 120

    # Evidence encryption key (AES-256 for evidence-at-rest)
    EVIDENCE_ENCRYPTION_KEY: str = ""

    # Audit log retention days
    AUDIT_LOG_RETENTION_DAYS: int = 365 * 7  # 7 years per forensic standards

    model_config = ConfigDict(env_file=".env", extra="ignore")


settings = Settings()

# Sanitize DATABASE_URL to avoid SQLAlchemy dialect issues with postgres:// (e.g. on Render)
if settings.DATABASE_URL.startswith("postgres://"):
    settings.DATABASE_URL = settings.DATABASE_URL.replace("postgres://", "postgresql://", 1)

