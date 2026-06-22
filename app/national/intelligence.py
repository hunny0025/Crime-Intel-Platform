"""National Crime Intelligence Layer (Prompt 53).

Aggregated intelligence across all agencies — national_analyst role only.
Threat signal detection and advisory distribution.
"""

import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from collections import Counter

from app.graph.driver import get_neo4j_client

logger = logging.getLogger(__name__)


def get_national_dashboard() -> dict:
    """NationalIntelligenceDashboard — aggregated stats (no individual case data)."""
    client = get_neo4j_client()

    # Active case volume by crime category and agency
    case_volume = client.execute_read(
        """
        MATCH (ca:CaseAnchor)
        WHERE ca.status IN ['open', 'under_investigation']
        OPTIONAL MATCH (ca)-[:CLASSIFIED_AS]->(cat:CrimeCategory)
        RETURN coalesce(ca.agency_id, 'unassigned') AS agency,
               coalesce(cat.name, 'unclassified') AS category,
               count(ca) AS count
        """,
    )

    # Methodology velocity — new CasePatterns
    methodology_velocity = client.execute_read(
        """
        MATCH (cp:CasePattern)
        RETURN count(cp) AS total_patterns,
               count(CASE WHEN cp.extracted_at > datetime() - duration('P30D')
                     THEN 1 END) AS new_last_30_days
        """,
    )

    # Evidence gap patterns across all cases
    gap_patterns = client.execute_read(
        """
        MATCH (g:EvidenceGap {status: 'open'})
        RETURN g.expected_evidence_type AS evidence_type, count(g) AS count
        ORDER BY count DESC LIMIT 10
        """,
    )

    # Deconfliction network — agency pair overlap
    decon_network = client.execute_read(
        """
        MATCH (da:DeconflictionAlert)
        WHERE da.status IN ['pending', 'acknowledged']
        RETURN da.our_agency_id AS agency_a,
               da.other_agency_id AS agency_b,
               count(da) AS overlap_count
        ORDER BY overlap_count DESC LIMIT 10
        """,
    )

    # Playbook effectiveness
    playbook_eff = client.execute_read(
        """
        MATCH (pt:PlaybookTemplate)
        RETURN pt.crime_category_id AS category,
               pt.derived_from_case_count AS case_count,
               pt.steps AS steps
        """,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "active_case_volume": case_volume,
        "methodology_velocity": methodology_velocity[0] if methodology_velocity else {},
        "evidence_gap_patterns": gap_patterns,
        "deconfliction_network": decon_network,
        "playbook_templates": len(playbook_eff),
    }


def detect_threat_signals() -> list:
    """Detect emerging national threat patterns from cross-agency hypotheses."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    # Aggregate active hypotheses across all cases
    hypothesis_patterns = client.execute_read(
        """
        MATCH (h:Hypothesis {status: 'active'})
        OPTIONAL MATCH (ca:CaseAnchor {case_id: h.case_id})-[:CLASSIFIED_AS]->(cat:CrimeCategory)
        RETURN cat.name AS category, h.narrative AS narrative,
               h.case_id AS case_id, ca.agency_id AS agency_id
        """,
    )

    # Group by crime category
    category_groups: dict[str, list] = {}
    for hp in hypothesis_patterns:
        cat = hp.get("category", "unknown")
        if cat not in category_groups:
            category_groups[cat] = []
        category_groups[cat].append(hp)

    signals = []
    for category, hyps in category_groups.items():
        case_ids = set(h.get("case_id", "") for h in hyps)
        agency_ids = set(h.get("agency_id", "") for h in hyps if h.get("agency_id"))

        # Signal threshold: 3+ cases across 2+ agencies
        if len(case_ids) >= 3 and len(agency_ids) >= 2:
            signal_id = str(uuid.uuid4())

            # Extract pattern description from narrative keywords
            narratives = [h.get("narrative", "") for h in hyps if h.get("narrative")]
            # Simple keyword extraction
            words = " ".join(narratives).lower().split()
            common_words = Counter(
                w for w in words if len(w) > 4 and w not in ("which", "their", "about", "could")
            ).most_common(5)
            pattern_desc = ", ".join(w[0] for w in common_words)

            signal_strength = min(len(case_ids) * len(agency_ids) / 20.0, 1.0)

            client.execute_write(
                """
                CREATE (ts:NationalThreatSignal {
                    id: $sid, crime_category: $cat,
                    hypothesis_pattern_description: $pattern,
                    case_count: $cases, agency_count: $agencies,
                    first_detected: $now, signal_strength: $strength,
                    status: 'active', created_at: $now
                })
                """,
                {
                    "sid": signal_id, "cat": category,
                    "pattern": pattern_desc,
                    "cases": len(case_ids),
                    "agencies": len(agency_ids),
                    "now": now, "strength": signal_strength,
                },
            )

            signals.append({
                "signal_id": signal_id,
                "crime_category": category,
                "hypothesis_pattern_description": pattern_desc,
                "case_count": len(case_ids),
                "agency_count": len(agency_ids),
                "signal_strength": round(signal_strength, 4),
            })

    return signals


def get_threat_signals() -> list:
    """Return active national threat signals."""
    client = get_neo4j_client()
    return client.execute_read(
        """
        MATCH (ts:NationalThreatSignal {status: 'active'})
        RETURN ts.id AS id, ts.crime_category AS category,
               ts.hypothesis_pattern_description AS pattern,
               ts.case_count AS cases, ts.agency_count AS agencies,
               ts.signal_strength AS strength, ts.first_detected AS detected
        ORDER BY ts.signal_strength DESC
        """,
    )


def create_threat_advisory(signal_id: str, advisory_text: str,
                           recommended_steps: list,
                           target_agencies: list = None) -> dict:
    """Create and distribute a ThreatAdvisory from a signal."""
    client = get_neo4j_client()
    advisory_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    targets = json.dumps(target_agencies or ["all"])

    client.execute_write(
        """
        MATCH (ts:NationalThreatSignal {id: $sid})
        CREATE (ta:ThreatAdvisory {
            id: $aid, signal_id: $sid,
            advisory_text: $text,
            recommended_steps: $steps,
            target_agencies: $targets,
            distributed_at: $now,
            created_at: $now
        })
        CREATE (ta)-[:DERIVED_FROM]->(ts)
        """,
        {
            "aid": advisory_id, "sid": signal_id,
            "text": advisory_text,
            "steps": json.dumps(recommended_steps),
            "targets": targets, "now": now,
        },
    )

    return {
        "advisory_id": advisory_id,
        "signal_id": signal_id,
        "distributed_at": now,
        "target_agencies": target_agencies or ["all"],
    }
