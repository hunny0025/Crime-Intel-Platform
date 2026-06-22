"""Explainability Engine — Rich explanation for every conclusion.

Addresses Gap 11: Every confidence score, recommendation, and conclusion
must be accompanied by a detailed, human-readable explanation showing
exactly which evidence supports it and which contradicts it.

Not just "Confidence = 93%", but:
  93% because:
    ✓ GPS agrees (weight: 0.25)
    ✓ Phone logs agree (weight: 0.20)
    ✓ Bank transfer agrees (weight: 0.20)
    ✓ Witness agrees (weight: 0.15)
    ✓ Timeline agrees (weight: 0.10)
    ✗ One contradiction remains (penalty: -0.07)
    → Total: 0.93 (93%)
"""

import logging
from datetime import datetime, timezone
from typing import Any

from app.graph.driver import get_neo4j_client

logger = logging.getLogger(__name__)


# ── Hypothesis Explainability ────────────────────────────────────────────

def explain_hypothesis(case_id: str, hypothesis_id: str) -> dict:
    """
    Generate a full explanation of a hypothesis's probability score.
    Returns supporting evidence, contradicting evidence, and weight breakdown.
    """
    client = get_neo4j_client()

    # Get hypothesis
    hyp_rows = client.execute_read(
        """
        MATCH (h:Hypothesis {id: $hid, case_id: $cid})
        RETURN h {.*} AS hypothesis
        """,
        {"hid": hypothesis_id, "cid": case_id},
    )
    if not hyp_rows:
        return {"error": f"Hypothesis {hypothesis_id} not found"}

    hyp = hyp_rows[0]["hypothesis"]
    probability = float(hyp.get("probability", 0))

    # Get supporting evidence
    supporting = client.execute_read(
        """
        MATCH (h:Hypothesis {id: $hid})-[:SUPPORTED_BY]->(e)
        RETURN e.id AS id, labels(e)[0] AS label, e.display_name AS name,
               e.event_type AS event_type, e.confidence AS confidence
        """,
        {"hid": hypothesis_id},
    )

    # Get contradicting evidence
    contradicting = client.execute_read(
        """
        MATCH (h:Hypothesis {id: $hid})-[:CONTRADICTED_BY]->(c)
        RETURN c.id AS id, labels(c)[0] AS label, c.description AS description,
               c.severity AS severity
        """,
        {"hid": hypothesis_id},
    )

    # Get involved entities
    involved = client.execute_read(
        """
        MATCH (h:Hypothesis {id: $hid})-[:INVOLVES|PREDICTED_BY]->(n)
        RETURN n.id AS id, labels(n)[0] AS label, n.display_name AS name,
               n.attention_value AS attention
        """,
        {"hid": hypothesis_id},
    )

    # Build weight breakdown
    evidence_weights = []
    total_support = 0.0

    for s in (supporting or []):
        conf = float(s.get("confidence", 0.7))
        weight = round(conf * 0.2, 3)
        total_support += weight
        evidence_weights.append({
            "evidence_id": s["id"],
            "evidence_type": s.get("event_type") or s.get("label"),
            "name": s.get("name") or s["id"][:12],
            "status": "supports",
            "confidence": conf,
            "weight": weight,
            "icon": "✓",
        })

    contradiction_penalty = 0.0
    for c in (contradicting or []):
        sev_penalty = {"high": 0.15, "medium": 0.08, "low": 0.03}.get(
            c.get("severity", "low"), 0.05
        )
        contradiction_penalty += sev_penalty
        evidence_weights.append({
            "evidence_id": c["id"],
            "evidence_type": "contradiction",
            "name": c.get("description", "")[:60],
            "status": "contradicts",
            "severity": c.get("severity", "unknown"),
            "penalty": sev_penalty,
            "icon": "✗",
        })

    # Reconstruct probability explanation
    base_prior = 0.5  # Default prior
    computed_prob = min(max(base_prior + total_support - contradiction_penalty, 0.01), 0.99)

    explanation_lines = []
    explanation_lines.append(f"**{int(probability * 100)}%** probability because:")
    explanation_lines.append("")

    for ew in evidence_weights:
        if ew["status"] == "supports":
            explanation_lines.append(
                f"  ✓ {ew['evidence_type'] or 'Evidence'} agrees "
                f"(confidence: {ew['confidence']:.0%}, weight: +{ew['weight']:.2f})"
            )
        else:
            explanation_lines.append(
                f"  ✗ {ew['name']} (severity: {ew.get('severity', '?')}, penalty: -{ew.get('penalty', 0):.2f})"
            )

    explanation_lines.append("")
    explanation_lines.append(f"→ Prior: {base_prior:.2f}")
    explanation_lines.append(f"→ Support total: +{total_support:.2f}")
    explanation_lines.append(f"→ Contradiction penalty: -{contradiction_penalty:.2f}")
    explanation_lines.append(f"→ Computed: {computed_prob:.2f} ({int(computed_prob * 100)}%)")
    explanation_lines.append("")
    explanation_lines.append(f"[Trace full proof dependency chain](/cases/{case_id}/explain/hypothesis/{hypothesis_id})")

    return {
        "hypothesis_id": hypothesis_id,
        "narrative": hyp.get("narrative", ""),
        "probability": probability,
        "probability_percent": int(probability * 100),
        "explanation_md": "\n".join(explanation_lines),
        "evidence_breakdown": evidence_weights,
        "supporting_count": len(supporting or []),
        "contradicting_count": len(contradicting or []),
        "involved_entities": [
            {"id": e["id"], "type": e["label"], "name": e.get("name"), "attention": e.get("attention")}
            for e in (involved or [])
        ],
        "computation": {
            "prior": base_prior,
            "support_total": round(total_support, 3),
            "contradiction_penalty": round(contradiction_penalty, 3),
            "computed_probability": round(computed_prob, 3),
        },
        "model": "explainability_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Court Readiness Explainability ───────────────────────────────────────

def explain_court_readiness(case_id: str) -> dict:
    """
    Explain why the court readiness score is what it is.
    Breaks down each component with supporting/blocking factors.
    """
    client = get_neo4j_client()

    readiness = client.execute_read(
        """
        MATCH (r:CourtReadiness {case_id: $cid})
        RETURN r {.*} AS readiness
        ORDER BY r.computed_at DESC LIMIT 1
        """,
        {"cid": case_id},
    )

    if not readiness:
        return {"error": "No court readiness score computed", "recommendation": "Run court readiness assessment"}

    r = readiness[0]["readiness"]
    score = float(r.get("composite_score", 0))
    grade = r.get("grade", "?")

    components = []
    factors = []

    for key in ["legal_score", "integrity_score", "defense_score", "procedural_score"]:
        if key in r:
            val = float(r[key])
            component_name = key.replace("_score", "").replace("_", " ").title()
            components.append({
                "name": component_name,
                "score": val,
                "status": "passing" if val >= 60 else "failing",
            })

            if val < 60:
                factors.append({
                    "type": "blocking",
                    "component": component_name,
                    "message": f"{component_name} score ({val:.0f}/100) is below prosecution threshold",
                    "icon": "🔴",
                })
            elif val < 80:
                factors.append({
                    "type": "warning",
                    "component": component_name,
                    "message": f"{component_name} score ({val:.0f}/100) is marginal",
                    "icon": "🟡",
                })
            else:
                factors.append({
                    "type": "passing",
                    "component": component_name,
                    "message": f"{component_name} score ({val:.0f}/100) meets standards",
                    "icon": "🟢",
                })

    # Specific blockers
    if r.get("section_65b_missing"):
        factors.append({
            "type": "critical_blocker",
            "component": "Legal",
            "message": "Section 65B IT Act certificate is MISSING — all digital evidence inadmissible without it",
            "icon": "🔴",
        })

    if r.get("hash_integrity_failed"):
        factors.append({
            "type": "critical_blocker",
            "component": "Integrity",
            "message": "Evidence hash integrity check FAILED — chain of custody compromised",
            "icon": "🔴",
        })

    # Build explanation
    explanation_lines = [
        f"## Court Readiness: {score:.0f}/100 (Grade {grade})",
        "",
        f"The case {'is' if score >= 70 else 'is NOT'} currently ready for prosecution.",
        "",
    ]

    for f in factors:
        explanation_lines.append(f"  {f['icon']} **{f['component']}**: {f['message']}")

    explanation_lines.append("")
    explanation_lines.append(f"[Trace full proof dependency chain](/cases/{case_id}/explain/court_readiness/{r.get('id', case_id)})")

    return {
        "case_id": case_id,
        "composite_score": score,
        "grade": grade,
        "components": components,
        "factors": factors,
        "explanation_md": "\n".join(explanation_lines),
        "critical_blockers": [f for f in factors if f["type"] == "critical_blocker"],
        "is_prosecution_ready": score >= 70 and not any(f["type"] == "critical_blocker" for f in factors),
        "model": "court_explainability_v1",
    }


# ── Contradiction Explainability ─────────────────────────────────────────

def explain_contradiction(case_id: str, contradiction_id: str) -> dict:
    """Explain why two pieces of evidence contradict each other."""
    client = get_neo4j_client()

    contra = client.execute_read(
        """
        MATCH (c:Contradiction {id: $cid_c, case_id: $cid})
        OPTIONAL MATCH (c)-[:INVOLVES]->(n)
        RETURN c {.*} AS contradiction,
               collect(DISTINCT n {.*, labels: labels(n)}) AS involved
        """,
        {"cid_c": contradiction_id, "cid": case_id},
    )

    if not contra:
        return {"error": "Contradiction not found"}

    c = contra[0]["contradiction"]
    involved = contra[0]["involved"]

    explanation = {
        "contradiction_id": contradiction_id,
        "type": c.get("contradiction_type", "unknown"),
        "severity": c.get("severity", "unknown"),
        "description": c.get("description", ""),
        "details": c.get("details", ""),
        "involved_entities": [
            {"id": n.get("id"), "type": n.get("labels", ["?"])[0] if n.get("labels") else "?",
             "name": n.get("display_name") or n.get("value")}
            for n in involved if n
        ],
        "possible_resolutions": [],
    }

    # Suggest resolutions based on type
    ctype = c.get("contradiction_type", "")
    if "co_location" in ctype or "temporal" in ctype:
        explanation["possible_resolutions"] = [
            "Verify GPS coordinates accuracy (GPS drift can cause false conflicts)",
            "Cross-reference with independent evidence (CCTV, witness statements)",
            "Check if timestamps are from different timezones",
            "Determine if location data is from device or network-based positioning",
        ]
    elif "timeline" in ctype:
        explanation["possible_resolutions"] = [
            "Verify server vs device timestamps",
            "Check for clock skew on evidence sources",
            "Determine if log tampering occurred",
        ]
    else:
        explanation["possible_resolutions"] = [
            "Gather additional corroborating evidence",
            "Interview witnesses for clarification",
            "Perform forensic analysis on source data",
        ]

    return explanation


# ── Generic Confidence Explainer ─────────────────────────────────────────

def explain_confidence(
    score: float,
    factors: list[dict],
) -> dict:
    """
    Generate a human-readable explanation for any confidence score.

    factors: list of {name, agrees: bool, weight, detail}
    """
    agreeing = [f for f in factors if f.get("agrees")]
    disagreeing = [f for f in factors if not f.get("agrees")]

    lines = [f"**{int(score * 100)}%** because:", ""]

    for f in agreeing:
        lines.append(f"  ✓ {f['name']} agrees (weight: {f.get('weight', 0):.2f})")
        if f.get("detail"):
            lines.append(f"    ↳ {f['detail']}")

    for f in disagreeing:
        lines.append(f"  ✗ {f['name']} disagrees (weight: -{f.get('weight', 0):.2f})")
        if f.get("detail"):
            lines.append(f"    ↳ {f['detail']}")

    lines.append("")
    total_agree = sum(f.get("weight", 0) for f in agreeing)
    total_disagree = sum(f.get("weight", 0) for f in disagreeing)
    lines.append(f"→ Supporting factors: +{total_agree:.2f}")
    lines.append(f"→ Contradicting factors: -{total_disagree:.2f}")
    lines.append(f"→ Net confidence: {int(score * 100)}%")

    return {
        "score": score,
        "score_percent": int(score * 100),
        "explanation_md": "\n".join(lines),
        "supporting_count": len(agreeing),
        "contradicting_count": len(disagreeing),
        "factors": factors,
    }


def build_explanation_chain(metric_type: str, metric_id: str, max_depth: int = 3) -> dict:
    """
    Traces the full proof dependency chain by traversing incoming relationships in Neo4j.
    """
    client = get_neo4j_client()
    visited = set()

    def traverse(node_id: str, depth: int) -> dict:
        if node_id in visited:
            return {
                "id": node_id,
                "label": "Cycle",
                "confidence": 1.0,
                "properties": {},
                "supports": []
            }
        visited.add(node_id)

        res = client.execute_read(
            """
            MATCH (n {id: $nid})
            RETURN n {.*} AS props, labels(n)[0] AS label
            """,
            {"nid": node_id}
        )
        if not res:
            return {
                "id": node_id,
                "label": "Unknown",
                "confidence": 1.0,
                "properties": {},
                "supports": []
            }

        props = res[0]["props"]
        label = res[0]["label"]

        # Parse confidence
        confidence = 1.0
        for k in ["confidence", "probability", "composite_score", "score", "value"]:
            if k in props and isinstance(props[k], (int, float)):
                confidence = float(props[k])
                break

        node_data = {
            "id": node_id,
            "label": label,
            "confidence": confidence,
            "properties": props,
            "supports": []
        }

        if depth >= max_depth:
            return node_data

        # Find incoming relationships (backwards dependencies)
        incoming = client.execute_read(
            """
            MATCH (n {id: $nid})<-[r]-(src)
            RETURN src.id AS src_id, type(r) AS rel_type, r.confidence AS r_conf
            """,
            {"nid": node_id}
        )

        for inc in incoming:
            src_id = inc["src_id"]
            if src_id:
                child_tree = traverse(src_id, depth + 1)
                child_tree["relationship_type"] = inc["rel_type"]
                child_tree["relationship_confidence"] = float(inc.get("r_conf") or 1.0)
                node_data["supports"].append(child_tree)

        return node_data

    return traverse(metric_id, 0)
