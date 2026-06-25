# 👮 Crime Intelligence Platform (GPCSSI 2024)
### Integrated Case Analytics, OSINT Scraping, Deception Detection & Court Admissibility Engine

---

<div align="center">
  <img src="docs/images/gpcssi_logo.png" width="150" alt="GPCSSI Logo" />
  <br/>
  <b>Gurugram Cyber Police — GPCSSI 2024</b>
  <br/>
  <i>Keeping Gurugram Cyber Safe</i>
  <br/>
  
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.109.0-009688.svg?style=flat&logo=FastAPI)](https://fastapi.tiangolo.com)
  [![Next.js](https://img.shields.io/badge/Next.js-14.0.0-000000.svg?style=flat&logo=Next.js)](https://nextjs.org)
  [![Neo4j](https://img.shields.io/badge/Neo4j-5.15.0-008CC1.svg?style=flat&logo=Neo4j)](https://neo4j.com)
  [![Kafka](https://img.shields.io/badge/Apache%20Kafka-3.6.0-231F20.svg?style=flat&logo=Apache-Kafka)](https://kafka.apache.org/)
  [![MinIO](https://img.shields.io/badge/MinIO-S3-C1272D.svg?style=flat&logo=MinIO)](https://min.io/)
</div>

---

## 📖 Table of Contents
1. [Executive Summary](#-executive-summary)
2. [Microservices & System Ports](#-microservices--system-ports)
3. [Technology Stack](#-technology-stack)
4. [Project Directory Layout](#-project-directory-layout)
5. [Installation & Local Run Guide](#-installation--local-run-guide)
6. [Running the Test Suites](#-running-the-test-suites)
7. [Filing Readiness Criteria (BNSS / BSA 2023)](#-filing-readiness-criteria-bnss--bsa-2023)
8. [Documentation Links](#-documentation-links)

---

## 🔍 Executive Summary

The **Crime Intelligence Platform** is a distributed forensic intelligence environment developed during the GPCSSI 2024 internship for the **Gurugram Cyber Police**. 

The system collects fractured forensic records (CDRs, GPS files, bank transactions, and chat dumps), converts them into normalized schemas, structures them in a Neo4j knowledge graph, and automatically assesses case theories for factual consistency using the **Autonomous Investigation Reasoning Engine (AIRE)**. It incorporates procedural tracking under the new Indian Criminal Code (**Bharatiya Nagarik Suraksha Sanhita, 2023**) and prepares electronic certificates complying with **Section 65B of the Bharatiya Sakshya Adhiniyam, 2023**.

---

## ⚡ Microservices & System Ports

The platform relies on a divided service layer to ensure high-security air-gapping:

| Crate / Directory | Default Port | Description | Egress Policy |
| :--- | :--- | :--- | :--- |
| **Core API** (`app/`) | `8000` | Case dB registry, AIRE reasoning, Neo4j mapper, and legal engine. | **Strictly Air-gapped** (No Internet) |
| **OSINT Service** (`osint-service/`) | `8001` | Domain analysis, SSL registries, social expansion, and crypto-tracing. | **Internet Egress Enabled** |
| **Deception Detector** (`deception-...`) | `8002` | Media deepfake scanner (placeholder) & stylometric text z-score checks. | **Local Only** |
| **Frontend UI** (`crime-intel-frontend/`)| `3002` | Next.js dashboard UI for case workflows and readiness reviews. | **Client Local** |

---

## 🛠 Technology Stack

* **API Services:** Python 3.11 + FastAPI + SQLAlchemy + Alembic
* **Primary Database:** PostgreSQL 15 (Case properties and procedural timelines)
* **Knowledge Graph:** Neo4j (Entity linkages, phone nodes, bank logs, and IP locations)
* **Object Storage:** MinIO S3 (Immutable raw evidence stores utilizing SHA-256 hash chains)
* **Event Bus:** Apache Kafka (Confluent Platform for async ingestion normalizers)
* **Frontend UI:** Next.js (React client dashboard using Outfit/Inter typography)
* **Container Orchestration:** Containerized via Docker Compose

---

## 📂 Project Directory Layout

```
crime-intel-platform/
├── docker-compose.yml              # Microservice stack orchestration
├── requirements.txt                # Python core dependencies
├── render.yaml                     # Deployment configuration
├── app/                            # Core API Microservice (:8000)
│   ├── main.py                     # FastAPI entrypoint & audit middleware
│   ├── db/                         # SQL models, schema definitions
│   ├── storage/                    # S3 bucket configuration (MinIO)
│   ├── events/                     # Kafka normalizer consumer
│   ├── graph/                      # Neo4j query builder & loaded references
│   ├── legal/                      # Section 65B, chargesheet packaging
│   ├── reasoning/                  # HPL Lark parser, probabilistic engine
│   └── routers/                    # Endpoint controllers
├── osint-service/                  # OSINT Intelligence Service (:8001)
│   ├── app/
│   │   ├── adapters/               # WHOIS, crt.sh, social, and crypto tracers
│   │   └── routers/                # OSINT endpoints
│   └── tests/                      # OSINT unit tests
├── deception-detection-service/    # Deception detection service (:8002)
│   ├── app/                        # Stylometric checks and placeholder classifiers
│   └── requirements.txt
├── crime-intel-frontend/           # Next.js React Frontend Dashboard (:3002)
├── docs/                           # Project documentation folder
│   ├── crime_intel_guide.md        # Markdown guide using relative images
│   ├── crime_intel_report.html     # Interactive HTML dashboard report
│   └── images/                     # Screenshot assets folder
└── tests/                          # Integration test suites
```

---

## 🚀 Installation & Local Run Guide

### 1. Prerequisites
Ensure you have the following installed on your machine:
* [Docker Desktop](https://www.docker.com/products/docker-desktop/) (v20.10 or higher)
* Ports `5432`, `7474`, `7687`, `8000`, `8001`, `8002`, `9000`, `9001`, `9092`, and `3002` available.

### 2. Start the Stack
Boot all containers in detached mode:
```bash
docker-compose up --build -d
```
Wait 30-40 seconds for migrations and Neo4j constraints to bootstrap.

### 3. Verify Health Check
Ensure all microservices respond successfully:
```bash
# Core API
curl http://localhost:8000/health

# OSINT Service
curl http://localhost:8001/health

# Deception Detection Service
curl http://localhost:8002/health
```

### 4. Stop the Containers
To spin down containers and wipe temporary volumes:
```bash
docker-compose down -v
```

---

## 🧪 Running the Test Suites

### Complete Backend Tests
You can run the integration test suites against the running Docker stack:
```bash
# Execute core API tests (probabilistic, HPL, legal, etc.)
docker-compose exec app pytest tests/ -v

# Execute OSINT unit tests
docker-compose exec osint-service pytest tests/ -v
```

---

## ⚖ Filing Readiness Criteria (BNSS / BSA 2023)

Admissibility ratings are computed on a strict scale derived from the Court Readiness Index ($C_{readiness}$):

$$C_{readiness} = \left( 0.4 \times E_{coverage} + 0.4 \times Q_{evidence} + 0.2 \times P_{compliance} \right) \times (1 - B_{critical})$$

* **Filing Recommended (&ge;80%):** Case is complete. Chargesheet package is ready to be filed under BNSS Section 193.
* **Review Required (60%-79%):** Minor procedural gaps exist (e.g. missing Section 65B signatures).
* **Investigation Ongoing (&lt;60%):** Substantial evidentiary gaps. AI Copilot prompts are triggered to suggest corrective actions.

---

## 📄 Documentation Links

For deeper technical analyses, view the generated project reports:
* **Interactive HTML Report:** [docs/crime_intel_report.html](docs/crime_intel_report.html)
* **Markdown Technical Guide:** [docs/crime_intel_guide.md](docs/crime_intel_guide.md)

---
**Gurugram Cyber Police — GPCSSI 2024**  
*Keeping Gurugram Cyber Safe*  
