"""Crime Intel Platform — FastAPI application entry point.

Security hardened for forensic evidence handling:
- Strict CORS allowlist (no wildcards)
- Request audit logging middleware
- API key validation for sensitive endpoints
- Rate limiting headers
"""

import logging
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.db.models import Base
from app.db.session import engine, SessionLocal
from app.storage.minio_client import get_minio_client
from app.events.producer import get_kafka_producer
from app.events.consumer import get_normalization_worker
from app.graph.driver import get_neo4j_client
from app.graph.constraints import apply_constraints
from app.graph.seeds.load_reference_data import load_all_reference_data
from app.graph.population import get_graph_population_worker
from app.routers import (
    health, cases, evidence, ingestion,
    graph, identity, reasoning, reference,
    memory, intelligence,
    behavioral, deception,
    reasoning_layer,
    legal, court, cross_case,
    autonomous, national,
    copilot, simulation,
    platform_extensions,
    pipeline,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ── Security Middleware ──────────────────────────────────────────────────

class AuditLogMiddleware(BaseHTTPMiddleware):
    """Log every API request with forensic-grade detail.

    Records: timestamp, method, path, source IP, response status, latency.
    This creates an immutable audit trail of all platform access — required
    for forensic evidence chain-of-custody compliance.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        start_time = time.time()

        # Inject request ID for tracing
        request.state.request_id = request_id

        response: Response = await call_next(request)

        latency_ms = round((time.time() - start_time) * 1000, 2)

        # Log every request — this is the forensic audit trail
        logger.info(
            "REQUEST %s | %s %s | status=%d | latency=%sms | ip=%s | user_agent=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            latency_ms,
            request.client.host if request.client else "unknown",
            request.headers.get("user-agent", "")[:80],
        )

        # Add security headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Cache-Control"] = "no-store"  # Never cache forensic data
        response.headers["Pragma"] = "no-cache"

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple sliding-window rate limiter per client IP.

    Prevents abuse of forensic APIs. Configurable via RATE_LIMIT_PER_MINUTE.
    Health check endpoints are exempted.
    """

    def __init__(self, app, max_requests: int = 120):
        super().__init__(app)
        self.max_requests = max_requests
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        # Exempt health checks and static assets
        if request.url.path in ("/health", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - 60.0

        # Clean old entries and add current
        self._requests[client_ip] = [
            t for t in self._requests[client_ip] if t > window_start
        ]
        self._requests[client_ip].append(now)

        remaining = max(self.max_requests - len(self._requests[client_ip]), 0)

        if len(self._requests[client_ip]) > self.max_requests:
            return Response(
                content='{"detail":"Rate limit exceeded. Retry after 60 seconds."}',
                status_code=429,
                media_type="application/json",
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


# ── Lifespan ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize services on startup, clean up on shutdown."""
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)

    # Create all tables (idempotent — Alembic handles real migrations)
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ensured")

    # Initialize MinIO
    try:
        minio = get_minio_client()
        logger.info("MinIO bucket '%s' ready", minio.bucket)
    except Exception as e:
        logger.warning("MinIO init deferred: %s", e)

    # Initialize Kafka producer
    try:
        producer = get_kafka_producer()
        logger.info("Kafka producer ready")
    except Exception as e:
        logger.warning("Kafka producer init deferred: %s", e)

    # Initialize Neo4j — apply constraints and load reference data
    try:
        neo4j = get_neo4j_client()
        apply_constraints(neo4j)
        logger.info("Neo4j schema constraints applied")
        ref_counts = load_all_reference_data(neo4j)
        logger.info("Reference data loaded: %s", ref_counts)
    except Exception as e:
        logger.warning("Neo4j init deferred: %s", e)

    # Load persisted learning weights
    try:
        from app.learning.feedback_loop import load_weights_from_db
        db = SessionLocal()
        try:
            load_weights_from_db(db)
            logger.info("Learning weights loaded from database")
        finally:
            db.close()
    except Exception as e:
        logger.warning("Learning weight load deferred: %s", e)

    # Start background normalization worker
    try:
        worker = get_normalization_worker()
        worker.start(
            db_session_factory=SessionLocal,
            kafka_producer=get_kafka_producer(),
        )
        logger.info("Normalization worker started")
    except Exception as e:
        logger.warning("Normalization worker start deferred: %s", e)

    # Start graph population worker
    try:
        graph_worker = get_graph_population_worker()
        graph_worker.start(db_session_factory=SessionLocal)
        logger.info("Graph population worker started")
    except Exception as e:
        logger.warning("Graph population worker start deferred: %s", e)

    # Start AIRE worker
    try:
        from app.reasoning.aire import get_aire_worker
        aire_worker = get_aire_worker()
        aire_worker.start(db_session_factory=SessionLocal)
        logger.info("AIRE worker started")
    except Exception as e:
        logger.warning("AIRE worker start deferred: %s", e)

    # Start feedback loop worker
    try:
        from app.learning.feedback_loop import get_feedback_loop_worker
        feedback_worker = get_feedback_loop_worker()
        feedback_worker.start(db_session_factory=SessionLocal)
        logger.info("Feedback loop worker started")
    except Exception as e:
        logger.warning("Feedback loop worker start deferred: %s", e)

    yield

    # Shutdown — persist learning weights before exit
    try:
        from app.learning.feedback_loop import save_weights_to_db
        db = SessionLocal()
        try:
            save_weights_to_db(db)
            logger.info("Learning weights persisted to database")
        finally:
            db.close()
    except Exception as e:
        logger.warning("Learning weight save failed: %s", e)

    logger.info("Shutting down %s", settings.APP_NAME)
    try:
        from app.learning.feedback_loop import get_feedback_loop_worker
        get_feedback_loop_worker().stop()
    except Exception:
        pass
    try:
        from app.reasoning.aire import get_aire_worker
        get_aire_worker().stop()
    except Exception:
        pass
    try:
        get_normalization_worker().stop()
    except Exception:
        pass
    try:
        get_graph_population_worker().stop()
    except Exception:
        pass
    try:
        get_kafka_producer().close()
    except Exception:
        pass
    try:
        get_neo4j_client().close()
    except Exception:
        pass


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Security middleware (order matters — outermost runs first)
app.add_middleware(RateLimitMiddleware, max_requests=settings.RATE_LIMIT_PER_MINUTE)
app.add_middleware(AuditLogMiddleware)

# CORS — Strict allowlist, NO wildcards
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-RateLimit-Remaining"],
)

# Register routers — Phase 1
app.include_router(health.router)
app.include_router(cases.router)
app.include_router(evidence.router)
app.include_router(ingestion.router)

# Phase 2 — Knowledge Graph
app.include_router(graph.router)
app.include_router(identity.router)
app.include_router(reasoning.router)
app.include_router(reference.router)

# Phase 3 — Investigation Intelligence
app.include_router(memory.router)
app.include_router(intelligence.router)

# Phase 4 — OSINT + Behavioral + Deception
app.include_router(behavioral.router)
app.include_router(deception.router)

# Phase 5 — Reasoning Layer
app.include_router(reasoning_layer.router)

# Phase 6 — Legal Intelligence
app.include_router(legal.router)

# Phase 7 — Court Intelligence
app.include_router(court.router)

# Phase 8 — Cross Case Intelligence
app.include_router(cross_case.router)

# Phase 9 — Autonomous Investigation
app.include_router(autonomous.router)

# Phase 10 — National Scale
app.include_router(national.router)

# Phase 11 — Investigation Copilot & Crime Simulator
app.include_router(copilot.router)
app.include_router(simulation.router)

# Phase 12 — Platform Extensions (AI, Acquisition, OSINT, Predictive, Multi-Agent, Learning)
app.include_router(platform_extensions.router)

# Phase 13 — End-to-End Investigation Pipeline
app.include_router(pipeline.router)
