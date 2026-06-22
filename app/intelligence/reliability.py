import os
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from sqlalchemy.orm import Session
from app.db.models import EvidenceArtifact
from app.graph.driver import get_neo4j_client

logger = logging.getLogger(__name__)

# Configurable weights via env vars
W_SOURCE = float(os.getenv("W_SOURCE", "0.20"))
W_CHAIN  = float(os.getenv("W_CHAIN", "0.25"))
W_CORR   = float(os.getenv("W_CORR", "0.25"))
W_ACQ    = float(os.getenv("W_ACQ", "0.15"))
W_TS     = float(os.getenv("W_TS", "0.15"))

CONFIG_PATH = Path(__file__).parent.parent / "config" / "source_reliability.json"

def _load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load source reliability config: {e}")
        return {
            "source_reliability": {
                "cellebrite_ufed": 0.95,
                "autopsy": 0.90,
                "magnet_axiom": 0.90,
                "msab_xry": 0.90,
                "manual_upload": 0.60,
                "osint": 0.50,
                "stylometric_heuristic": 0.30,
                "unknown": 0.40
            },
            "acquisition_confidence": {
                "physical_extraction": 0.95,
                "filesystem_extraction": 0.85,
                "logical_extraction": 0.75,
                "cloud_legal_process": 0.80,
                "manual_upload": 0.60,
                "regex_extraction": 0.70,
                "nlp_extraction_confirmed": 0.85,
                "nlp_extraction_unconfirmed": 0.55,
                "osint": 0.45
            }
        }

@dataclass
class EvidenceReliabilityScore:
    artifact_id: str
    source_reliability: float
    chain_confidence: float
    corroboration_score: float
    acquisition_confidence: float
    timestamp_integrity: float
    composite_score: float
    score_basis: str

def compute_reliability(artifact_id: str, case_id: str, db: Session) -> Optional[EvidenceReliabilityScore]:
    import uuid as pyuuid
    aid = pyuuid.UUID(artifact_id) if isinstance(artifact_id, str) else artifact_id
    
    artifact = db.query(EvidenceArtifact).filter(
        EvidenceArtifact.artifact_id == aid
    ).first()
    if not artifact:
        logger.warning(f"Artifact {artifact_id} not found in DB")
        return None

    # Load lookup values
    config = _load_config()
    source_lookup = config.get("source_reliability", {})
    acq_lookup = config.get("acquisition_confidence", {})

    # 1. Source Reliability
    source_tool = artifact.source_tool or "unknown"
    source_reliability = source_lookup.get(source_tool.lower(), source_lookup.get("unknown", 0.40))

    # 2. Acquisition Confidence
    acq_method = artifact.acquisition_method
    if acq_method is None or acq_method == "":
        acquisition_confidence = source_lookup.get("unknown", 0.40)
    else:
        acquisition_confidence = acq_lookup.get(acq_method.lower(), source_lookup.get("unknown", 0.40))

    # 3. Read Certificate from Neo4j
    client = get_neo4j_client()
    cert_list = client.execute_read(
        """
        MATCH (c:EvidenceIntegrityCertificate {artifact_id: $aid, case_id: $cid})
        RETURN c.hash_verified AS hv, c.chain_verified AS cv,
               c.timestamp_integrity_score AS tis, c.corroboration_count AS corr
        """,
        {"aid": str(aid), "cid": str(case_id)}
    )

    if cert_list:
        cert = cert_list[0]
        chain_confidence = 1.0 if cert.get("cv", False) else 0.0
        corr_count = cert.get("corr", 0)
        corroboration_score = 1.0 if corr_count >= 2 else 0.5 if corr_count == 1 else 0.0
        timestamp_integrity = float(cert.get("tis", 0.5))
    else:
        chain_confidence = 1.0 if len(artifact.chain_of_custody_log or []) > 0 else 0.7
        corroboration_score = 0.0
        timestamp_integrity = 0.5

    # 4. Composite Score
    composite_score = (
        source_reliability * W_SOURCE +
        chain_confidence * W_CHAIN +
        corroboration_score * W_CORR +
        acquisition_confidence * W_ACQ +
        timestamp_integrity * W_TS
    )
    # Ensure W_SOURCE + W_CHAIN + W_CORR + W_ACQ + W_TS = 1.0
    total_weights = W_SOURCE + W_CHAIN + W_CORR + W_ACQ + W_TS
    if total_weights > 0:
        composite_score = composite_score / total_weights

    # 5. Score Basis Narrative
    corr_desc = f"{corr_count} independent sources" if cert_list else "no independent sources"
    chain_desc = "verified chain" if chain_confidence == 1.0 else "unverified chain"
    acq_desc = f"{acq_method} extraction" if acq_method else "unknown extraction method"
    score_basis = f"Source: {source_tool} ({source_reliability:.2f}), {corr_desc}, {chain_desc}, {acq_desc}"

    score = EvidenceReliabilityScore(
        artifact_id=str(aid),
        source_reliability=round(source_reliability, 4),
        chain_confidence=round(chain_confidence, 4),
        corroboration_score=round(corroboration_score, 4),
        acquisition_confidence=round(acquisition_confidence, 4),
        timestamp_integrity=round(timestamp_integrity, 4),
        composite_score=round(composite_score, 4),
        score_basis=score_basis
    )

    # Write back to PostgreSQL
    artifact.composite_reliability_score = score.composite_score
    db.commit()

    return score
