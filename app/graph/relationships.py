"""Relationship type constants for the knowledge graph.

These are not enforced by Neo4j (it allows any relationship type) but serve as
a shared vocabulary across the codebase to prevent typos and enable grep-ability.

Every relationship (except the global LegalSection/CrimeCategory reference ones)
supports these properties:
    - valid_from (datetime, nullable)
    - valid_to (datetime, nullable)
    - confidence (float 0-1)
    - evidence_basis (list of artifact_id strings)
"""

# ── Investigation Ontology Relationships ─────────────────────────────────

OWNS = "OWNS"
CONTROLS = "CONTROLS"
HAS_IDENTIFIER = "HAS_IDENTIFIER"
SUGGESTED_IDENTIFIER = "SUGGESTED_IDENTIFIER"  # Phase 4: fuzzy-matched, pending review
AT = "AT"
COMMUNICATED_WITH = "COMMUNICATED_WITH"
CO_LOCATED_WITH = "CO_LOCATED_WITH"
PARTICIPATED_IN = "PARTICIPATED_IN"
TRANSFERRED_TO = "TRANSFERRED_TO"

# ── Social / OSINT Relationships ─────────────────────────────────────────

FOLLOWS = "FOLLOWS"
MEMBER_OF = "MEMBER_OF"
SAME_ENTITY_CLUSTER = "SAME_ENTITY_CLUSTER"  # Phase 4: crypto clustering

# ── Behavioral / Deception Relationships ─────────────────────────────────

HAS_BASELINE = "HAS_BASELINE"
HAS_ANOMALY = "HAS_ANOMALY"
ASSESSED = "ASSESSED"  # DeceptionAssessment → EvidenceArtifact/OSINTRecord

# ── Reasoning Ontology Relationships ─────────────────────────────────────

SUPPORTED_BY = "SUPPORTED_BY"
CONTRADICTED_BY = "CONTRADICTED_BY"
PREDICTED_BY = "PREDICTED_BY"
REQUIRES_ASSUMPTION = "REQUIRES_ASSUMPTION"
INVOLVES = "INVOLVES"
RELATES_TO = "RELATES_TO"

# ── Causal Reasoning (Phase 5) ─────────────────────────────────────────────

CAUSED = "CAUSED"           # Event → Event (causal, distinct from temporal)
ADDRESSES = "ADDRESSES"     # InvestigationAction → Contradiction/EvidenceGap

# ── Financial Flow Relationships ─────────────────────────────────────────────

INITIATED = "INITIATED"         # Person/Account → Event (transaction initiation)
CREDITED_TO = "CREDITED_TO"     # Event/Account → Account (funds received)
DEFRAUDED_BY = "DEFRAUDED_BY"   # Victim → Suspect/Account
FUNDED_BY = "FUNDED_BY"         # Organization/Account ← financial source

# ── Communication Relationships ───────────────────────────────────────────────

CONTACTED = "CONTACTED"         # Person/Account → Person (initiated contact)
COMMUNICATED_VIA = "COMMUNICATED_VIA"  # Person → Account (used channel)

# ── Infrastructure Relationships ──────────────────────────────────────────────

HOSTS = "HOSTS"                 # Device/Server → Account/Domain
TUNNELS_TO = "TUNNELS_TO"       # VPN/Proxy → Server
CONNECTED_TO = "CONNECTED_TO"   # Device → Network node
OPERATES = "OPERATES"           # Person → Device/Service
LOCATED_AT = "LOCATED_AT"       # Node → Location

# ── Investigation Event Relationships ─────────────────────────────────────────

FILED = "FILED"                     # Person → Event (complaint/FIR)
SUBJECT_OF = "SUBJECT_OF"           # Person → Event (arrest/warrant)
VERIFIED_BY = "VERIFIED_BY"         # Event/Artifact → Person (witness/officer)
REGISTERED_AT = "REGISTERED_AT"     # Account/Domain → Event (registration)
IMPERSONATED = "IMPERSONATED"       # Person → Organization (fraud persona)
EMPLOYED_BY = "EMPLOYED_BY"        # Person → Organization
LAST_KNOWN_AT = "LAST_KNOWN_AT"    # Person → Location

# ── Crime / Legal Ontology Relationships ─────────────────────────────────

MAPS_TO_LEGAL_SECTION = "MAPS_TO_LEGAL_SECTION"
SATISFIES_ELEMENT = "SATISFIES_ELEMENT"
CLASSIFIED_AS = "CLASSIFIED_AS"
HAS_CHILD_CATEGORY = "HAS_CHILD_CATEGORY"
HAS_ELEMENT = "HAS_ELEMENT"

# ── All relationship types (for validation) ──────────────────────────────

ALL_RELATIONSHIP_TYPES = {
    OWNS, CONTROLS, HAS_IDENTIFIER, SUGGESTED_IDENTIFIER, AT,
    COMMUNICATED_WITH, CO_LOCATED_WITH, PARTICIPATED_IN, TRANSFERRED_TO,
    FOLLOWS, MEMBER_OF, SAME_ENTITY_CLUSTER,
    HAS_BASELINE, HAS_ANOMALY, ASSESSED,
    SUPPORTED_BY, CONTRADICTED_BY, PREDICTED_BY, REQUIRES_ASSUMPTION,
    INVOLVES, RELATES_TO,
    CAUSED, ADDRESSES,
    MAPS_TO_LEGAL_SECTION, SATISFIES_ELEMENT, CLASSIFIED_AS,
    HAS_CHILD_CATEGORY, HAS_ELEMENT,
    # Financial flow
    INITIATED, CREDITED_TO, DEFRAUDED_BY, FUNDED_BY,
    # Communication
    CONTACTED, COMMUNICATED_VIA,
    # Infrastructure
    HOSTS, TUNNELS_TO, CONNECTED_TO, OPERATES, LOCATED_AT,
    # Investigation events
    FILED, SUBJECT_OF, VERIFIED_BY, REGISTERED_AT,
    IMPERSONATED, EMPLOYED_BY, LAST_KNOWN_AT,
}

# Relationships that are global (not case-scoped) and don't carry
# the standard evidence-backed properties
GLOBAL_RELATIONSHIP_TYPES = {
    MAPS_TO_LEGAL_SECTION, SATISFIES_ELEMENT, HAS_CHILD_CATEGORY, HAS_ELEMENT,
}

# Relationships that require evidence_basis and standard properties
EVIDENCE_BACKED_RELATIONSHIP_TYPES = ALL_RELATIONSHIP_TYPES - GLOBAL_RELATIONSHIP_TYPES
