"""OSINT Intelligence Service — FastAPI application.

This service is architecturally SEPARATE from the evidence-processing core.
It NEVER reads from evidence_artifacts or the chain-of-custody store.
It ONLY writes new nodes/relationships into Neo4j with classification_tag='public_osint'.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.graph_client import get_neo4j_client
from app.routers import domain, records, attribution, social, crypto

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)

    # Verify Neo4j connectivity
    try:
        neo4j = get_neo4j_client()
        if neo4j.health_check():
            logger.info("Neo4j connected")
        else:
            logger.warning("Neo4j connection failed")
    except Exception as e:
        logger.warning("Neo4j init deferred: %s", e)

    yield

    logger.info("Shutting down %s", settings.APP_NAME)
    try:
        get_neo4j_client().close()
    except Exception:
        pass


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(domain.router)     # Domain intelligence (Prompt 17)
app.include_router(records.router)    # OSINT records listing (Prompt 17)
app.include_router(attribution.router)  # Attribution engine (Prompt 18)
app.include_router(social.router)     # Social graph intelligence (Prompt 19)
app.include_router(crypto.router)     # Cryptocurrency intelligence (Prompt 22)


@app.get("/health")
def health():
    """Health check for OSINT service."""
    neo4j_ok = False
    try:
        neo4j_ok = get_neo4j_client().health_check()
    except Exception:
        pass

    return {
        "service": "osint-intelligence",
        "neo4j": "healthy" if neo4j_ok else "unhealthy",
    }
