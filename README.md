# Crime Intel Platform

A forensic intelligence platform with immutable evidence chain-of-custody, config-driven ingestion adapters, a knowledge graph investigation layer, OSINT intelligence, behavioral analysis, deception detection, and event-driven architecture.

## Architecture

The platform consists of three services:

| Service | Port | Description |
|---|---|---|
| **Core API** (`app`) | 8000 | Evidence processing, case management, knowledge graph, reasoning engines |
| **OSINT Service** (`osint-service`) | 8001 | External intelligence gathering (internet egress enabled) |
| **Deception Detection** (`deception-detection`) | 8002 | Media/text manipulation assessment (GPU-beneficial) |

### Service Separation

**The OSINT service is architecturally separate from the evidence-processing core.**

- The OSINT service **never reads** from `evidence_artifacts` or the chain-of-custody store.
- It **only writes** new nodes/relationships into the Neo4j graph tagged `classification_tag="public_osint"`.
- It has **internet egress enabled** (unlike core services, which require no external network access).
- All OSINT-derived entities carry `confidence ≤ 0.8` — they are intelligence leads, not confirmed evidence.

## Tech Stack

- **API**: Python 3.11 + FastAPI
- **Case Registry**: PostgreSQL 15 + SQLAlchemy + Alembic
- **Evidence Store**: MinIO (S3-compatible) with SHA-256 hash-chaining
- **Knowledge Graph**: Neo4j (community edition)
- **Event Bus**: Apache Kafka (Confluent Platform)
- **Orchestration**: Docker Compose

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Ports 5432, 7474, 7687, 8000, 8001, 8002, 9000, 9001, 9092 available

### Start the Stack

```bash
docker-compose up --build -d
```

Wait 30-60 seconds for all services to initialize, then verify:

```bash
# Core API
curl http://localhost:8000/health

# OSINT Service
curl http://localhost:8001/health

# Deception Detection Service
curl http://localhost:8002/health
```

### Run Tests

```bash
# Core API tests
docker-compose exec app pytest tests/ -v

# OSINT Service tests (adapter + fuzzy matching — no live APIs needed)
docker-compose exec osint-service pytest tests/ -v
```

### Stop the Stack

```bash
docker-compose down -v
```

## Project Structure

```
crime-intel-platform/
├── docker-compose.yml              # All services (6 infra + 3 app)
├── Dockerfile                      # Core API container
├── requirements.txt
├── app/                            # Core API
│   ├── main.py
│   ├── db/                         # PostgreSQL models + migrations
│   ├── storage/                    # MinIO evidence store
│   ├── ingestion/                  # Config-driven adapters
│   ├── events/                     # Kafka producer/consumer
│   ├── graph/                      # Neo4j knowledge graph
│   ├── memory/                     # Investigation memory engine
│   ├── intelligence/               # Contradiction, Gap, Attention, Nav, Behavioral engines
│   └── routers/                    # API endpoints
├── osint-service/                  # OSINT Intelligence Service
│   ├── Dockerfile
│   ├── app/
│   │   ├── adapters/               # WHOIS, DNS, crt.sh, social, crypto
│   │   ├── resolution/             # Fuzzy entity matching
│   │   └── routers/                # Domain, attribution, social, crypto endpoints
│   └── tests/
├── deception-detection-service/    # Deception Detection Service
│   ├── Dockerfile
│   └── app/                        # Placeholder model + stylometric heuristic
├── tests/                          # Core API integration tests
└── fixtures/                       # Test data generators
```

## API Overview

### Core API (port 8000)

| Endpoint Group | Description |
|---|---|
| `GET /health` | Service connectivity check |
| `/cases` | Case CRUD + entity linking |
| `/cases/{id}/evidence` | Evidence upload + chain verification |
| `/cases/{id}/ingest` | Config-driven file ingestion |
| `/cases/{id}/graph/*` | Knowledge graph entity CRUD |
| `/cases/{id}/graph/identity-facet` | Identity resolution |
| `/cases/{id}/hypotheses` | Hypothesis management |
| `/cases/{id}/memory/*` | Investigation memory + belief replay |
| `/cases/{id}/intelligence/*` | Contradiction, Gap, Attention, Navigation |
| `/cases/{id}/graph/person/{id}/baseline/compute` | Behavioral baseline |
| `/cases/{id}/graph/person/{id}/anomalies/scan` | Anomaly detection |
| `/cases/{id}/deception/assess` | Deception assessment orchestration |
| `/reference/*` | Crime/Legal ontology reference data |

### OSINT Service (port 8001)

| Endpoint Group | Description |
|---|---|
| `GET /health` | OSINT service health |
| `POST /cases/{id}/osint/domain-lookup` | WHOIS + DNS + cert transparency |
| `GET /cases/{id}/osint/records` | List OSINT records (filterable) |
| `POST /cases/{id}/graph/person/{id}/attribution-candidates` | Fuzzy entity matching |
| `POST /cases/{id}/graph/suggested-identifier/{id}/confirm` | Confirm OSINT attribution |
| `POST /cases/{id}/graph/suggested-identifier/{id}/reject` | Reject attribution |
| `GET /cases/{id}/graph/person/{id}/attribution-profile` | Full attribution summary |
| `POST /cases/{id}/osint/social-graph/{id}/expand` | Social connection expansion |
| `GET /cases/{id}/osint/social-graph/{id}/communities` | Community detection |
| `POST /cases/{id}/osint/crypto/{id}/trace` | Cryptocurrency wallet tracing |
| `GET /cases/{id}/osint/crypto/{id}/cluster` | Common-input-ownership clusters |
| `GET /cases/{id}/osint/crypto/{id}/flow` | Multi-hop money flow |

### Deception Detection Service (port 8002)

| Endpoint Group | Description |
|---|---|
| `POST /detect/media` | Image/video/audio deepfake detection |
| `POST /detect/text` | Stylometric text analysis |

