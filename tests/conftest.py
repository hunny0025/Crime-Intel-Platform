"""Shared test fixtures and configuration."""

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ── Lazy imports to avoid crashing when services are unavailable ──────────

_DB_AVAILABLE = False
_test_engine = None
_TestSessionLocal = None


def _get_settings():
    """Lazy import of settings to avoid import-time failures."""
    from app.config import settings
    return settings


def _init_test_db():
    """Initialize the test database engine lazily. Returns True if successful."""
    global _DB_AVAILABLE, _test_engine, _TestSessionLocal

    if _test_engine is not None:
        return _DB_AVAILABLE

    try:
        settings = _get_settings()
        TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", settings.TEST_DATABASE_URL)

        # Try to create test database
        main_db_url = settings.DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
        main_engine = create_engine(main_db_url, isolation_level="AUTOCOMMIT")
        try:
            with main_engine.connect() as conn:
                result = conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = 'crime_intel_test'")
                )
                if not result.fetchone():
                    conn.execute(text("CREATE DATABASE crime_intel_test"))
        finally:
            main_engine.dispose()

        _test_engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
        _TestSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=_test_engine
        )
        _DB_AVAILABLE = True
    except Exception:
        _DB_AVAILABLE = False

    return _DB_AVAILABLE


def _require_db():
    """Ensure DB is available or skip the test."""
    if not _init_test_db():
        pytest.skip("PostgreSQL not available")
    return _test_engine, _TestSessionLocal


# ── Session-scoped fixtures ──────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create all tables in the test database at the start of the test session."""
    if not _init_test_db():
        yield
        return
    from app.db.models import Base
    Base.metadata.create_all(bind=_test_engine)
    yield
    try:
        Base.metadata.drop_all(bind=_test_engine)
    except Exception:
        pass


@pytest.fixture(scope="session", autouse=True)
def setup_neo4j():
    """Apply Neo4j constraints and load reference data at session start."""
    try:
        from app.graph.driver import get_neo4j_client
        from app.graph.constraints import apply_constraints
        from app.graph.seeds.load_reference_data import load_all_reference_data

        neo4j = get_neo4j_client()
        if neo4j.health_check():
            apply_constraints(neo4j)
            load_all_reference_data(neo4j)
    except Exception:
        pass  # Neo4j may not be available; tests will skip as needed
    yield


# ── Per-test fixtures ────────────────────────────────────────────────────

@pytest.fixture()
def db_session():
    """Provide a transactional database session that rolls back after each test."""
    engine, SessionLocal = _require_db()
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db_session):
    """FastAPI TestClient with the DB dependency overridden to use the test session."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import get_db

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── MinIO Test Fixtures ──────────────────────────────────────────────────

@pytest.fixture(scope="session")
def test_minio_client():
    """MinIO client configured for tests, using a test bucket."""
    try:
        from app.storage.minio_client import MinIOClient
        client = MinIOClient()
        test_bucket = "evidence-test"
        client.bucket = test_bucket
        client.ensure_bucket()
        return client
    except Exception:
        pytest.skip("MinIO not available")


@pytest.fixture(autouse=True)
def _patch_minio(monkeypatch, request):
    """Override the MinIO client singleton to use the test bucket."""
    try:
        mc_client = request.getfixturevalue("test_minio_client")
        import app.storage.minio_client as mc
        monkeypatch.setattr(mc, "minio_client", mc_client)
    except pytest.skip.Exception:
        pass  # MinIO not available, skip patching


# ── Kafka Test Fixtures ──────────────────────────────────────────────────

@pytest.fixture(scope="session")
def test_kafka_producer():
    """Kafka producer for tests."""
    try:
        from app.events.producer import KafkaProducer
        producer = KafkaProducer()
        if not producer.health_check():
            pytest.skip("Kafka not available")
        return producer
    except Exception:
        pytest.skip("Kafka not available")


@pytest.fixture(autouse=True)
def _patch_kafka(monkeypatch, request):
    """Override the Kafka producer singleton to use the test producer."""
    try:
        producer = request.getfixturevalue("test_kafka_producer")
        import app.events.producer as kp
        monkeypatch.setattr(kp, "_producer", producer)
    except pytest.skip.Exception:
        pass  # Kafka not available, skip patching


# ── Neo4j Test Cleanup ──────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _cleanup_neo4j_test_data():
    """Clean up test-created case-scoped graph data after each test.
    Preserves global reference data (CrimeCategory, LegalSection, LegalElement)."""
    yield
    try:
        from app.graph.driver import get_neo4j_client
        neo4j = get_neo4j_client()
        if neo4j.health_check():
            neo4j.execute_write(
                """
                MATCH (n)
                WHERE n.case_id IS NOT NULL
                DETACH DELETE n
                """
            )
            # Do NOT call neo4j.close() here — it destroys the singleton
            # driver used by background Kafka consumer threads, causing
            # a segfault in confluent_kafka.cimpl during teardown.
    except Exception:
        pass


# ── Helper Fixtures ──────────────────────────────────────────────────────

@pytest.fixture()
def sample_case_data():
    """Sample data for creating a case."""
    return {
        "case_type": "homicide",
        "status": "open",
        "classification_tag": "case_sensitive",
        "created_by": "detective_smith",
    }


@pytest.fixture()
def created_case(client, sample_case_data):
    """Create and return a case for use in tests."""
    response = client.post("/cases", json=sample_case_data)
    assert response.status_code == 201
    return response.json()
