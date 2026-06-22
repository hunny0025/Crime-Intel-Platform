"""Health check endpoint — tests connectivity to postgres, minio, kafka, and neo4j."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.storage.minio_client import get_minio_client
from app.events.producer import get_kafka_producer
from app.graph.driver import get_neo4j_client

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Check connectivity to all backend services."""
    results = {}

    # PostgreSQL
    try:
        db.execute(text("SELECT 1"))
        results["postgres"] = "healthy"
    except Exception as e:
        results["postgres"] = f"unhealthy: {e}"

    # MinIO
    try:
        client = get_minio_client()
        if client.health_check():
            results["minio"] = "healthy"
        else:
            results["minio"] = "unhealthy"
    except Exception as e:
        results["minio"] = f"unhealthy: {e}"

    # Kafka
    try:
        producer = get_kafka_producer()
        if producer.health_check():
            results["kafka"] = "healthy"
        else:
            results["kafka"] = "unhealthy"
    except Exception as e:
        results["kafka"] = f"unhealthy: {e}"

    # Neo4j
    try:
        neo4j = get_neo4j_client()
        if neo4j.health_check():
            results["neo4j"] = "healthy"
        else:
            results["neo4j"] = "unhealthy"
    except Exception as e:
        results["neo4j"] = f"unhealthy: {e}"

    overall = all(v == "healthy" for v in results.values())
    return {"status": "healthy" if overall else "degraded", "services": results}
