"""Schema constraints and indexes for Neo4j.

Applies uniqueness constraints on the 'id' property for all node labels
and creates indexes on case_id for case-scoped nodes. Idempotent — safe
to run multiple times (uses IF NOT EXISTS).
"""

import logging
from app.graph.driver import Neo4jClient

logger = logging.getLogger(__name__)

# All node labels that require a unique 'id' constraint
ALL_NODE_LABELS = [
    "Person",
    "Device",
    "Account",
    "Location",
    "Organization",
    "Event",
    "IdentityFacet",
    "CrimeCategory",
    "LegalSection",
    "LegalElement",
    "Hypothesis",
    "Assumption",
    "Contradiction",
    "EvidenceGap",
    "CaseAnchor",
    "BehavioralBaseline",
    "BehavioralAnomaly",
    "DeceptionAssessment",
    "InvestigationAction",
    # Phase 6 — Legal Intelligence
    "EvidenceMapping",
    "LegalQualification",
    "EvidenceSufficiencyReport",
    "ProceduralComplianceRecord",
    "ChargesheetReadinessReport",
    # Phase 7 — Court Intelligence
    "DefenseSimulation",
    "EvidenceIntegrityCertificate",
    "CourtReadinessReport",
    "ConvictionRiskProfile",
    # Phase 8 — Cross Case Intelligence
    "CasePattern",
    "PlaybookTemplate",
    "PlaybookStepCompletion",
    "BehavioralFingerprint",
    # Phase 9 — Autonomous Investigation
    "HypothesisCandidate",
    "AIREAuditAction",
    # Phase 10 — National Scale Multi-Tenancy
    "Agency",
    "Investigator",
    "DeconflictionIndex",
    "DeconflictionAlert",
    "NationalThreatSignal",
    "ThreatAdvisory",
    # Legal Intelligence Upgrade
    "LegalReasoningTrace",
    # 6A — Legal Knowledge Graph Extension
    "Statute",
    "Chapter",
    "Definition",
    "Exception",
    "Punishment",
    "BurdenOfProof",
    "CaseLaw",
    "JudicialInterpretation",
]

# Node labels that are case-scoped (have a case_id property)
CASE_SCOPED_LABELS = [
    "Person",
    "Device",
    "Account",
    "Location",
    "Organization",
    "Event",
    "IdentityFacet",
    "Hypothesis",
    "Assumption",
    "Contradiction",
    "EvidenceGap",
    "CaseAnchor",
    "BehavioralBaseline",
    "BehavioralAnomaly",
    "DeceptionAssessment",
    "InvestigationAction",
    # Phase 6
    "EvidenceMapping",
    "LegalQualification",
    "EvidenceSufficiencyReport",
    "ProceduralComplianceRecord",
    "ChargesheetReadinessReport",
    # Phase 7
    "DefenseSimulation",
    "EvidenceIntegrityCertificate",
    "CourtReadinessReport",
    "ConvictionRiskProfile",
    # Phase 8
    "PlaybookStepCompletion",
    # Phase 9
    "HypothesisCandidate",
    "AIREAuditAction",
    # Legal Intelligence Upgrade
    "LegalReasoningTrace",
    # Phase 10
    "Investigator",
    "DeconflictionAlert",
]

# Global reference labels (no case_id)
GLOBAL_LABELS = [
    "CrimeCategory",
    "LegalSection",
    "LegalElement",
    # Phase 8 — global methodology graph
    "CasePattern",
    "PlaybookTemplate",
    "BehavioralFingerprint",
    # Phase 10
    "Agency",
    "DeconflictionIndex",
    "NationalThreatSignal",
    "ThreatAdvisory",
    # 6A — Legal Knowledge Graph Extension
    "Statute",
    "Chapter",
    "Definition",
    "Exception",
    "Punishment",
    "BurdenOfProof",
    "CaseLaw",
    "JudicialInterpretation",
]


def apply_constraints(client: Neo4jClient) -> list[str]:
    """
    Apply all schema constraints and indexes idempotently.
    Returns a list of constraint/index names that were processed.
    """
    applied = []

    with client.get_session() as session:
        # Unique constraint on 'id' for every node label
        for label in ALL_NODE_LABELS:
            constraint_name = f"constraint_{label.lower()}_id_unique"
            query = (
                f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.id IS UNIQUE"
            )
            session.run(query)
            applied.append(constraint_name)
            logger.info("Applied constraint: %s", constraint_name)

        # Index on case_id for case-scoped nodes
        for label in CASE_SCOPED_LABELS:
            index_name = f"index_{label.lower()}_case_id"
            query = (
                f"CREATE INDEX {index_name} IF NOT EXISTS "
                f"FOR (n:{label}) ON (n.case_id)"
            )
            session.run(query)
            applied.append(index_name)
            logger.info("Applied index: %s", index_name)

        # Composite index on case_id + classification_tag for case-scoped nodes
        for label in CASE_SCOPED_LABELS:
            index_name = f"index_{label.lower()}_case_classification"
            query = (
                f"CREATE INDEX {index_name} IF NOT EXISTS "
                f"FOR (n:{label}) ON (n.case_id, n.classification_tag)"
            )
            session.run(query)
            applied.append(index_name)
            logger.info("Applied composite index: %s", index_name)

    logger.info("Applied %d constraints/indexes total", len(applied))
    return applied


def get_existing_constraints(client: Neo4jClient) -> list[dict]:
    """List all existing constraints in the database."""
    return client.execute_read("SHOW CONSTRAINTS")


def get_existing_indexes(client: Neo4jClient) -> list[dict]:
    """List all existing indexes in the database."""
    return client.execute_read("SHOW INDEXES")
