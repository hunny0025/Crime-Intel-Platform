"""Defense Simulation Engine — adversarial stress-testing of prosecution case.

All outputs labeled SIMULATION=true. Six attack categories:
1. Chain of Custody  2. Timestamp  3. Attribution  4. Alternative Explanation
5. Procedural  6. Sufficiency
"""

import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType

logger = logging.getLogger(__name__)


def run_defense_simulation(case_id: str, db: Optional[Session] = None, categories: Optional[list[str]] = None) -> dict:
    """Run specified or all attack categories across the case."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()
    sim_id = str(uuid.uuid4())

    attack_vectors = []

    # Category 1 — Chain of Custody
    if not categories or "chain_of_custody" in categories:
        attack_vectors.extend(_chain_of_custody_attacks(client, case_id))

    # Category 2 — Timestamp
    if not categories or "timestamp" in categories:
        attack_vectors.extend(_timestamp_attacks(client, case_id))

    # Category 3 — Attribution
    if not categories or "attribution" in categories:
        attack_vectors.extend(_attribution_attacks(client, case_id))

    # Category 4 — Alternative Explanation
    if not categories or "alternative_explanation" in categories:
        attack_vectors.extend(_alternative_explanation_attacks(client, case_id))

    # Category 5 — Procedural
    if not categories or "procedural" in categories:
        attack_vectors.extend(_procedural_attacks(client, case_id))

    # Category 6 — Sufficiency
    if not categories or "sufficiency" in categories:
        attack_vectors.extend(_sufficiency_attacks(client, case_id))

    # Category 7 — Mens Rea
    if not categories or "mens_rea" in categories:
        attack_vectors.extend(_mens_rea_attacks(client, case_id))

    # Category 8 — Jurisdiction
    if not categories or "jurisdiction" in categories:
        attack_vectors.extend(_jurisdiction_attacks(client, case_id))

    # Category 9 — Digital Tampering
    if not categories or "digital_tampering" in categories:
        attack_vectors.extend(_tampering_attacks(client, case_id))

    # Enrich attack vectors with mitigation status and suggested actions
    for v in attack_vectors:
        _assess_mitigation_and_actions(client, case_id, v)

    # Sort by severity
    severity_order = {"critical": 0, "major": 1, "minor": 2}
    attack_vectors.sort(key=lambda v: severity_order.get(v.get("severity", "minor"), 3))

    # Compute vulnerability score (only count unmitigated critical/major vectors as vulnerability)
    total_checked = max(len(attack_vectors), 1)
    unmitigated_critical_major = sum(
        1 for v in attack_vectors
        if v.get("severity") in ("critical", "major") and v.get("mitigation_status") != "mitigated"
    )
    vulnerability_score = min(unmitigated_critical_major / total_checked, 1.0)

    # Store DefenseSimulation node
    client.execute_write(
        """
        CREATE (d:DefenseSimulation {
            id: $sid, case_id: $cid, generated_at: $now,
            simulation_type: 'full_case',
            overall_vulnerability_score: $vscore,
            attack_vector_count: $cnt,
            attack_vectors: $vectors,
            SIMULATION: true,
            classification_tag: 'case_sensitive', created_at: $now
        })
        """,
        {
            "sid": sim_id, "cid": case_id, "now": now,
            "vscore": vulnerability_score, "cnt": len(attack_vectors),
            "vectors": json.dumps(attack_vectors),
        },
    )

    if db:
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.decision_made,
            description=f"Defense simulation: {len(attack_vectors)} attack vectors, "
                        f"vulnerability={vulnerability_score:.2f}",
            actor="system:defense_simulator",
        )
        db.commit()

    return {
        "SIMULATION": True,
        "simulation_id": sim_id,
        "case_id": case_id,
        "generated_at": now,
        "overall_vulnerability_score": round(vulnerability_score, 4),
        "attack_vectors": attack_vectors,
        "summary": {
            "critical": sum(1 for v in attack_vectors if v["severity"] == "critical"),
            "major": sum(1 for v in attack_vectors if v["severity"] == "major"),
            "minor": sum(1 for v in attack_vectors if v["severity"] == "minor"),
            "mitigated": sum(1 for v in attack_vectors if v.get("mitigation_status") == "mitigated"),
            "partially_mitigated": sum(1 for v in attack_vectors if v.get("mitigation_status") == "partially_mitigated"),
            "unmitigated": sum(1 for v in attack_vectors if v.get("mitigation_status") == "unmitigated"),
        },
    }


def get_latest_simulation(case_id: str) -> dict:
    """Return most recent defense simulation."""
    client = get_neo4j_client()
    sim = client.execute_read(
        """
        MATCH (d:DefenseSimulation {case_id: $cid})
        RETURN d.id AS id, d.generated_at AS at,
               d.overall_vulnerability_score AS vscore,
               d.attack_vector_count AS cnt
        ORDER BY d.generated_at DESC LIMIT 1
        """,
        {"cid": case_id},
    )
    if not sim:
        return {"error": "No defense simulation found"}

    # Re-run to get fresh vectors (simulations are cheap)
    return run_defense_simulation(case_id)


def _chain_of_custody_attacks(client, case_id: str) -> list[dict]:
    """Category 1: scan for custody gaps."""
    attacks = []
    # Find artifacts with broken chains
    broken = client.execute_read(
        """
        MATCH (n)
        WHERE n.case_id = $cid AND n.hash_verified = false
        RETURN n.id AS id, coalesce(n.display_name, n.id) AS display
        """,
        {"cid": case_id},
    )
    for b in broken:
        attacks.append({
            "category": "chain_of_custody",
            "description": f"Defense can challenge admissibility of {b['display']} — "
                           f"hash verification failed, content integrity compromised.",
            "severity": "critical",
            "evidence_refs": [b["id"]],
            "recommended_counter": "Obtain witness statements from all personnel in the "
                                   "custody chain confirming handling and verify hash at "
                                   "each transfer point.",
        })

    # Check for any artifact without documented custody
    no_custody = client.execute_read(
        """
        MATCH (n)
        WHERE n.case_id = $cid AND n.source_tool IS NOT NULL
        AND n.chain_verified IS NULL
        RETURN n.id AS id, coalesce(n.display_name, n.id) AS display
        LIMIT 5
        """,
        {"cid": case_id},
    )
    for n in no_custody:
        attacks.append({
            "category": "chain_of_custody",
            "description": f"Chain of custody not verified for {n['display']}.",
            "severity": "major",
            "evidence_refs": [n["id"]],
            "recommended_counter": "Complete chain of custody verification for this artifact.",
        })

    return attacks


def _timestamp_attacks(client, case_id: str) -> list[dict]:
    """Category 2: low timestamp integrity scores."""
    attacks = []
    low_integrity = client.execute_read(
        """
        MATCH ()-[r]->()
        WHERE r.timestamp_integrity_score IS NOT NULL
        AND r.timestamp_integrity_score < 0.7
        RETURN r.id AS rid, r.timestamp_integrity_score AS score, type(r) AS rtype
        LIMIT 10
        """,
    )
    for r in low_integrity:
        attacks.append({
            "category": "timestamp",
            "description": f"Defense can argue timestamps in relationship {r['rtype']} "
                           f"(id: {r['rid']}) may have been manipulated — "
                           f"integrity score is {r['score']}.",
            "severity": "major" if r["score"] < 0.4 else "minor",
            "evidence_refs": [r["rid"]],
            "recommended_counter": "Seek corroborating timestamps from independent sources.",
        })
    return attacks


def _attribution_attacks(client, case_id: str) -> list[dict]:
    """Category 3: pending/weak attribution links."""
    attacks = []
    weak_attrib = client.execute_read(
        """
        MATCH (p:Person {case_id: $cid})-[r:SUGGESTED_IDENTIFIER]->(f:IdentityFacet)
        RETURN p.id AS pid, coalesce(p.display_name, p.id) AS person,
               f.id AS fid, coalesce(f.value, f.id) AS identifier,
               r.confidence AS conf
        """,
        {"cid": case_id},
    )
    for w in weak_attrib:
        attacks.append({
            "category": "attribution",
            "description": f"Defense can argue that {w['identifier']} has not been "
                           f"conclusively proven to belong to {w['person']} — "
                           f"attribution relies on probabilistic matching "
                           f"(confidence={w.get('conf', 'N/A')}).",
            "severity": "critical",
            "evidence_refs": [w["pid"], w["fid"]],
            "recommended_counter": "Obtain direct evidence linking the person to the "
                                   "identifier (login records, device seizure, confession).",
        })
    return attacks


def _alternative_explanation_attacks(client, case_id: str) -> list[dict]:
    """Category 4: active competing hypotheses."""
    attacks = []
    competing = client.execute_read(
        """
        MATCH (h:Hypothesis {case_id: $cid, status: 'active'})
        WITH h ORDER BY h.probability DESC
        WITH collect(h) AS all_hyps
        UNWIND all_hyps[1..] AS h
        WITH h
        WHERE h.probability > 0.1
        RETURN h.id AS id, h.narrative AS narrative, h.probability AS prob
        """,
        {"cid": case_id},
    )
    for c in competing:
        attacks.append({
            "category": "alternative_explanation",
            "description": f"Defense can argue evidence is consistent with alternative: "
                           f"'{c['narrative']}' (model assigns {c['prob']:.2f} probability).",
            "severity": "major" if c["prob"] > 0.2 else "minor",
            "evidence_refs": [c["id"]],
            "recommended_counter": "Present counter-narrative documentation showing this "
                                   "alternative was considered and why evidence disfavors it.",
        })
    return attacks


def _procedural_attacks(client, case_id: str) -> list[dict]:
    """Category 5: non-compliant procedural requirements."""
    attacks = []
    non_compliant = client.execute_read(
        """
        MATCH (r:ProceduralComplianceRecord {case_id: $cid})
        WHERE r.status = 'non_compliant'
        RETURN r.requirement_id AS req_id, r.non_compliance_severity AS severity,
               r.remediation_guidance AS guidance
        """,
        {"cid": case_id},
    )
    for nc in non_compliant:
        attacks.append({
            "category": "procedural",
            "description": f"Defense can challenge procedural compliance — "
                           f"{nc['req_id']} not satisfied.",
            "severity": nc.get("severity", "major"),
            "evidence_refs": [nc["req_id"]],
            "recommended_counter": nc.get("guidance", "Address procedural requirement."),
        })
    return attacks


def _sufficiency_attacks(client, case_id: str) -> list[dict]:
    """Category 6: weak evidence on 'satisfied' elements."""
    attacks = []
    weak = client.execute_read(
        """
        MATCH (m:EvidenceMapping {case_id: $cid})-[r:SATISFIES_ELEMENT]->(le:LegalElement)
        WHERE r.satisfaction_score < 0.6
        AND m.confirmation_status IN ['auto_suggested', 'investigator_confirmed']
        RETURN le.id AS eid, le.element_text AS text, r.satisfaction_score AS score
        """,
        {"cid": case_id},
    )
    return attacks


def _mens_rea_attacks(client, case_id: str) -> list[dict]:
    """Category 7: Challenges lack of intent/motive."""
    attacks = []
    weak_intent = client.execute_read(
        """
        MATCH (m:EvidenceMapping {case_id: $cid})-[r:SATISFIES_ELEMENT]->(le:LegalElement)
        WHERE (toLower(le.element_text) CONTAINS 'intent' OR toLower(le.element_text) CONTAINS 'fraudulent' OR toLower(le.element_text) CONTAINS 'dishonest')
        AND r.satisfaction_score < 0.7
        RETURN le.id AS eid, le.element_text AS text, r.satisfaction_score AS score
        """,
        {"cid": case_id}
    )
    for w in weak_intent:
        attacks.append({
            "category": "mens_rea",
            "description": f"Defense can argue absence of mens rea: intent element '{w['text'][:60]}' has weak evidence (score {w['score']:.2f}). They may claim accident or mistake of fact.",
            "severity": "major",
            "evidence_refs": [w["eid"]],
            "recommended_counter": "Collect corroborating communication records (emails, chats) or financial logs demonstrating planning and knowledge of the deception."
        })
    return attacks


def _jurisdiction_attacks(client, case_id: str) -> list[dict]:
    """Category 8: Challenges territorial jurisdiction or authority of the investigating agency."""
    attacks = []
    # Check if there is a Location node linked to the case
    locs = client.execute_read(
        """
        MATCH (l:Location {case_id: $cid})
        RETURN l.id AS lid, l.name AS name
        """,
        {"cid": case_id}
    )
    if not locs:
        attacks.append({
            "category": "jurisdiction",
            "description": "No formal crime scene or location node is linked to the case. Defense can raise jurisdictional challenges under BNSS Section 177/179.",
            "severity": "major",
            "evidence_refs": [],
            "recommended_counter": "Formally map and link a Location node with coordinates/jurisdiction details to the Case in the knowledge graph."
        })
    return attacks


def _tampering_attacks(client, case_id: str) -> list[dict]:
    """Category 9: Defense alleging deepfake, AI manipulation, or alteration of digital evidence."""
    attacks = []
    # Find artifacts without deception assessment or with high deception scores
    tampered = client.execute_read(
        """
        MATCH (da:DeceptionAssessment {case_id: $cid})-[:ASSESSED]->(n)
        WHERE da.deception_score > 0.5
        RETURN n.id AS nid, coalesce(n.display_name, n.id) AS display, da.deception_score AS score
        """,
        {"cid": case_id}
    )
    for t in tampered:
        attacks.append({
            "category": "digital_tampering",
            "description": f"Defense can claim digital evidence tampering or AI manipulation for {t['display']} (deception score is {t['score']:.2f}).",
            "severity": "critical" if t["score"] > 0.7 else "major",
            "evidence_refs": [t["nid"]],
            "recommended_counter": "Present a detailed forensic report, verify the hash chain from origin, and obtain a certificate under BSA Section 63.",
        })
    return attacks


def _assess_mitigation_and_actions(client, case_id: str, vector: dict) -> None:
    """Assess whether a defense vector is mitigated by counter-evidence in the graph,
    and populate suggested_investigative_actions.
    """
    category = vector.get("category", "")
    evidence_refs = vector.get("evidence_refs", [])

    status = "unmitigated"
    suggested_actions = []

    if category == "chain_of_custody":
        ref = evidence_refs[0] if evidence_refs else None
        if ref:
            # Check for EvidenceIntegrityCertificate
            certs = client.execute_read(
                """
                MATCH (c:EvidenceIntegrityCertificate {case_id: $cid, evidence_ref: $ref})
                RETURN c.verification_grade AS grade
                """,
                {"cid": case_id, "ref": ref}
            )
            if certs:
                grade = certs[0]["grade"]
                if grade in ("A", "B"):
                    status = "mitigated"
                elif grade in ("C", "D"):
                    status = "partially_mitigated"

        suggested_actions = [
            {"type": "evidence_collect", "action": "Formally record forensic imaging copy of original device with write-blocker details."},
            {"type": "witness_examine", "action": "Obtain witness statements from first responder who seized the device."},
            {"type": "forensic_request", "action": "Submit for bit-stream hash verification and generate FSL report."},
            {"type": "document_obtain", "action": "Obtain signed seizure memo (panchnama) under BNSS Section 185 with two independent witness signatures."}
        ]

    elif category == "timestamp":
        # Check if NTP server logs or corroborating timestamps exist
        # Check if there is an EvidenceIntegrityCertificate with A/B grade for the source
        ref = evidence_refs[0] if evidence_refs else None
        if ref:
            certs = client.execute_read(
                """
                MATCH (c:EvidenceIntegrityCertificate {case_id: $cid, evidence_ref: $ref})
                RETURN c.verification_grade AS grade
                """,
                {"cid": case_id, "ref": ref}
            )
            if certs and certs[0]["grade"] in ("A", "B"):
                status = "mitigated"

        suggested_actions = [
            {"type": "evidence_collect", "action": "Retrieve network operator logs and server NTP synchronization logs."},
            {"type": "witness_examine", "action": "Examine the systems administrator of the log server to verify timestamp clock drift."},
            {"type": "forensic_request", "action": "Request NTP drift analysis forensic verification."},
            {"type": "document_obtain", "action": "Request certified copy of timezone / ISP timestamp certificates."}
        ]

    elif category == "attribution":
        # Check if direct ownership or communication records exist with high confidence
        pids = [r for r in evidence_refs if r.startswith("pe-") or r.startswith("person-")]
        ref = pids[0] if pids else (evidence_refs[0] if evidence_refs else None)
        if ref:
            direct_rel = client.execute_read(
                """
                MATCH (p:Person {id: $pid})-[r:OWNS|USED|COMMUNICATED_WITH]-(n)
                RETURN max(r.confidence) AS max_conf
                """,
                {"pid": ref}
            )
            if direct_rel and direct_rel[0]["max_conf"] is not None:
                max_conf = direct_rel[0]["max_conf"]
                if max_conf >= 0.8:
                    status = "mitigated"
                elif max_conf >= 0.5:
                    status = "partially_mitigated"

        suggested_actions = [
            {"type": "evidence_collect", "action": "Obtain IP login history matching suspect's physical GPS location."},
            {"type": "witness_examine", "action": "Examine suspect's family members or primary email recovery contact."},
            {"type": "forensic_request", "action": "Run saved browser credentials and cookies forensic extraction."},
            {"type": "document_obtain", "action": "Obtain certified KYC documentation from the telecom/ISP service provider."}
        ]

    elif category == "alternative_explanation":
        # Check for hypothesis probability
        ref = evidence_refs[0] if evidence_refs else None
        if ref:
            hyp = client.execute_read(
                """
                MATCH (h:Hypothesis {id: $hid})
                RETURN h.probability AS prob
                """,
                {"hid": ref}
            )
            if hyp:
                prob = hyp[0]["prob"]
                if prob < 0.2:
                    status = "mitigated"
                elif prob < 0.4:
                    status = "partially_mitigated"

        suggested_actions = [
            {"type": "evidence_collect", "action": "Verify suspect's alibi using third-party GPS and surveillance records."},
            {"type": "witness_examine", "action": "Examine neutral witnesses who can disprove the alternative explanation."},
            {"type": "forensic_request", "action": "Perform digital timeline consistency validation check."},
            {"type": "document_obtain", "action": "Obtain certified logs or receipts refuting the alternative claim."}
        ]

    elif category == "procedural":
        ref = evidence_refs[0] if evidence_refs else None
        if ref:
            rec = client.execute_read(
                """
                MATCH (r:ProceduralComplianceRecord {case_id: $cid, requirement_id: $ref})
                RETURN r.status AS status
                """,
                {"cid": case_id, "ref": ref}
            )
            if rec:
                rec_status = rec[0]["status"]
                if rec_status == "compliant":
                    status = "mitigated"
                elif rec_status == "pending_manual_confirmation":
                    status = "partially_mitigated"

        suggested_actions = [
            {"type": "evidence_collect", "action": f"Obtain completed procedural proof / certificate for {ref}."},
            {"type": "witness_examine", "action": "Take statement from the investigating officer certifying the step execution."},
            {"type": "forensic_request", "action": "None required."},
            {"type": "document_obtain", "action": f"Ensure copy of the document satisfying {ref} is uploaded."}
        ]

    elif category == "sufficiency":
        ref = evidence_refs[0] if evidence_refs else None
        if ref:
            mapping = client.execute_read(
                """
                MATCH ()-[r:SATISFIES_ELEMENT]->(le:LegalElement {id: $eid})
                RETURN max(r.satisfaction_score) AS score
                """,
                {"eid": ref}
            )
            if mapping and mapping[0]["score"] is not None:
                score = mapping[0]["score"]
                if score >= 0.7:
                    status = "mitigated"
                elif score >= 0.5:
                    status = "partially_mitigated"

        suggested_actions = [
            {"type": "evidence_collect", "action": "Gather direct physical or log records supporting this legal element."},
            {"type": "witness_examine", "action": "Examine key victim or primary eyewitness to confirm the element ingredients."},
            {"type": "forensic_request", "action": "Perform corroborative forensic audit of data files."},
            {"type": "document_obtain", "action": "Obtain official business correspondence or contractual agreement proving the act."}
        ]

    elif category == "mens_rea":
        # Check if communication records exist for the case
        comms = client.execute_read(
            """
            MATCH (m:EvidenceMapping {case_id: $cid})
            WHERE m.evidence_type = 'communication_records'
            RETURN count(m) AS cnt
            """,
            {"cid": case_id}
        )
        if comms:
            cnt = comms[0]["cnt"]
            if cnt > 2:
                status = "mitigated"
            elif cnt > 0:
                status = "partially_mitigated"

        suggested_actions = [
            {"type": "evidence_collect", "action": "Search seized devices for suspicious chats, draft emails, or search queries showing intent."},
            {"type": "witness_examine", "action": "Examine co-conspirators or recipients of communications to prove intent."},
            {"type": "forensic_request", "action": "Perform forensic recovery of deleted chat databases on suspect's device."},
            {"type": "document_obtain", "action": "Obtain signed warning letters, contract terms, or threat notes indicating awareness."}
        ]

    elif category == "jurisdiction":
        locs = client.execute_read(
            """
            MATCH (l:Location {case_id: $cid})
            RETURN count(l) AS cnt
            """,
            {"cid": case_id}
        )
        if locs and locs[0]["cnt"] > 0:
            status = "mitigated"

        suggested_actions = [
            {"type": "evidence_collect", "action": "Obtain cell tower location (CDR) of suspect's phone to place them within the local jurisdiction."},
            {"type": "witness_examine", "action": "Verify jurisdiction boundaries with the local police station officers."},
            {"type": "forensic_request", "action": "Plot and overlay GPS coordinate history onto official jurisdiction maps."},
            {"type": "document_obtain", "action": "Ensure the official FIR logs details matching the territorial jurisdiction of the court."}
        ]

    elif category == "digital_tampering":
        ref = evidence_refs[0] if evidence_refs else None
        if ref:
            certs = client.execute_read(
                """
                MATCH (c:EvidenceIntegrityCertificate {case_id: $cid, evidence_ref: $ref})
                RETURN c.verification_grade AS grade
                """,
                {"cid": case_id, "ref": ref}
            )
            if certs and certs[0]["grade"] in ("A", "B"):
                status = "mitigated"

        suggested_actions = [
            {"type": "evidence_collect", "action": "Retrieve original raw media files with metadata and EXIF data intact."},
            {"type": "witness_examine", "action": "Examine the forensic analyst who conducted the digital deception audit."},
            {"type": "forensic_request", "action": "Request PRNU (Photo Response Non-Uniformity) camera fingerprinting analysis."},
            {"type": "document_obtain", "action": "Obtain OEM camera specifications and secure server upload logs."}
        ]

    vector["mitigation_status"] = status
    vector["suggested_investigative_actions"] = suggested_actions
