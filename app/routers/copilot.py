"""Investigation Copilot — Natural Language Query Interface.

Provides POST /cases/{case_id}/copilot/query which accepts a free-text question,
classifies it into one of several intent categories, executes the corresponding
Cypher/SQL query, and returns a richly-formatted Markdown response.

Supported intent categories (no external LLM required — regex + keyword routing):
  entity_connections    — "Who is connected to X?" / "Show connections for Wallet Y"
  contradictions        — "Find contradictions involving Suspect A"
  evidence_gaps         — "What evidence is missing?" / "List gaps"
  hypothesis_support    — "Which evidence supports hypothesis X?"
  legal_readiness       — "Is this case court ready?" / "Explain the readiness score"
  timeline              — "Show timeline for case" / "What happened between X and Y?"
  evidence_list         — "List all evidence" / "What files do we have?"
  case_summary          — "Summarize the case" / "Give me a case overview"
  reasoning_explanation — "Why did the system flag X?" / "Explain recommendation"
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Case, EvidenceArtifact, InvestigationAction, ActionType, ActionStatus, MemoryRecordType
from app.graph.driver import get_neo4j_client
from app.graph import crud

router = APIRouter(tags=["copilot"])


# ── Request / Response schemas ───────────────────────────────────────────

class CopilotQuery(BaseModel):
    query: str
    context: dict | None = None   # optional extra context (e.g. node_id hints)


class CopilotResponse(BaseModel):
    intent: str
    confidence: float
    response_md: str              # Markdown-formatted answer
    entities_referenced: list[str] = []
    suggested_actions: list[str] = []
    query_time_ms: float = 0.0


# ── Intent Classifier ────────────────────────────────────────────────────

# Each intent is defined by a list of (regex_pattern, weight) tuples.
# The intent with the highest total weight wins.
_INTENT_PATTERNS: dict[str, list[tuple[str, float]]] = {
    "entity_connections": [
        (r"\bconnect(ed|ion|s)?\b", 2.0),
        (r"\bwho\b.*\bknow[s]?\b", 1.5),
        (r"\blink(ed|s)?\b", 1.0),
        (r"\brelat(ed|ion)?\b", 1.0),
        (r"\bwallet\b", 0.5),
        (r"\bnetwork\b", 0.5),
    ],
    "contradictions": [
        (r"\bcontradiction[s]?\b", 3.0),
        (r"\bconflict[s]?\b", 2.0),
        (r"\binconsisten(t|cy|cies)\b", 2.0),
        (r"\bmismatch\b", 1.5),
        (r"\bdisagreem?e?n?t?\b", 1.0),
    ],
    "evidence_gaps": [
        (r"\bgap[s]?\b", 3.0),
        (r"\bmissing evidence\b", 3.0),
        (r"\bwhat.*missing\b", 2.5),
        (r"\bnot collected\b", 2.0),
        (r"\bunresolved\b", 1.5),
    ],
    "hypothesis_support": [
        (r"\bhypothes[ei]s\b", 2.5),
        (r"\bsupport(s|ed|ing)?\b", 1.5),
        (r"\btheory\b", 2.0),
        (r"\bevidence.*for\b", 1.5),
        (r"\bwhat.*proves?\b", 1.5),
    ],
    "legal_readiness": [
        (r"\bcourt[\s-]?read(y|iness)\b", 3.0),
        (r"\bchargesheet\b", 2.5),
        (r"\bprosecution\b", 2.0),
        (r"\blegal\b", 1.5),
        (r"\bsection\b", 1.0),
        (r"\bbnss?\b", 1.5),
        (r"\bita?\b", 0.5),
        (r"\breadiness\s*score\b", 2.5),
    ],
    "timeline": [
        (r"\btimeline\b", 3.0),
        (r"\bwhen\b.*\bhappen(ed|s)?\b", 2.0),
        (r"\bsequence\b", 1.5),
        (r"\bchrono(logical)?\b", 2.0),
        (r"\bbetween\b.*\band\b", 1.0),
        (r"\bevent[s]?\b", 0.8),
    ],
    "evidence_list": [
        (r"\blist.*evidence\b", 3.0),
        (r"\bshow.*file[s]?\b", 2.0),
        (r"\bwhat files?\b", 2.0),
        (r"\bartifact[s]?\b", 1.5),
        (r"\bdigital evidence\b", 2.0),
    ],
    "case_summary": [
        (r"\bsummar(y|ize|ise)\b", 3.0),
        (r"\boverview\b", 2.5),
        (r"\bbrief(ing)?\b", 2.0),
        (r"\bwhat.*case.*about\b", 2.0),
        (r"\bstatus\b", 1.0),
    ],
    "reasoning_explanation": [
        (r"\bwhy\b.*\b(flag|recommend|suggest|score)\b", 3.0),
        (r"\bexplain\b", 2.0),
        (r"\breason(ing|s)?\b", 2.0),
        (r"\bhow.*decided\b", 2.0),
        (r"\bconfidence\b", 1.5),
    ],
}


def _classify_intent(query: str) -> tuple[str, float]:
    """Return (intent_name, confidence_0_to_1) for the query."""
    q = query.lower()
    scores: dict[str, float] = {}
    for intent, patterns in _INTENT_PATTERNS.items():
        score = 0.0
        for pattern, weight in patterns:
            if re.search(pattern, q):
                score += weight
        scores[intent] = score

    if all(v == 0 for v in scores.values()):
        return "case_summary", 0.4  # safe fallback

    best_intent = max(scores, key=lambda k: scores[k])
    max_possible = sum(w for _, w in _INTENT_PATTERNS[best_intent])
    confidence = min(scores[best_intent] / max_possible, 1.0)
    return best_intent, round(confidence, 2)


def _extract_entity_name(query: str) -> str | None:
    """Try to pull a quoted name or capitalised noun phrase from the query."""
    # Quoted
    m = re.search(r'"([^"]+)"', query)
    if m:
        return m.group(1)
    m = re.search(r"'([^']+)'", query)
    if m:
        return m.group(1)
    # After keywords like "for", "involving", "about", "connected to"
    m = re.search(r"(?:for|involving|about|connected to|of)\s+([A-Z][a-zA-Z0-9\s]{2,30})", query)
    if m:
        return m.group(1).strip()
    return None


# ── Neo4j helpers ────────────────────────────────────────────────────────

def _neo4j_query(cypher: str, params: dict) -> list[dict]:
    try:
        client = get_neo4j_client()
        return client.execute_read(cypher, params)
    except Exception:
        return []


# ── Intent Executors ─────────────────────────────────────────────────────

def _exec_entity_connections(case_id: str, query: str, db: Session) -> dict:
    name = _extract_entity_name(query) or ""
    rows = _neo4j_query(
        """
        MATCH (n {case_id: $case_id})
        WHERE toLower(n.display_name) CONTAINS toLower($name)
           OR toLower(n.value) CONTAINS toLower($name)
        WITH n LIMIT 5
        MATCH (n)-[r]-(neighbor)
        RETURN n {.*} AS node, type(r) AS rel_type,
               neighbor {.*} AS neighbor, r {.*} AS rel_props
        LIMIT 50
        """,
        {"case_id": case_id, "name": name},
    )

    if not rows:
        return {
            "response_md": f"## 🔍 Entity Connections\n\nNo entities found matching **`{name or 'your query'}`** in this case.\n\n> Try searching by exact name or check the Knowledge Graph view.",
            "entities": [],
            "actions": ["Open Knowledge Graph", "Check entity names in Case Explorer"],
        }

    # Build response
    grouped: dict[str, list] = {}
    for row in rows:
        nid = row["node"].get("id", "?")
        if nid not in grouped:
            grouped[nid] = {"node": row["node"], "connections": []}
        grouped[nid]["connections"].append({
            "rel": row["rel_type"],
            "neighbor": row["neighbor"],
        })

    md = f"## 🔗 Entity Connections — `{name or 'All Entities'}`\n\n"
    for nid, data in list(grouped.items())[:5]:
        n = data["node"]
        label = n.get("display_name") or n.get("value") or nid
        md += f"### {label}\n"
        md += f"- **Type**: {n.get('_labels', ['Entity'])[0] if '_labels' in n else 'Entity'}\n"
        for conn in data["connections"][:8]:
            nb = conn["neighbor"]
            nb_name = nb.get("display_name") or nb.get("value") or nb.get("id", "?")
            md += f"- `{conn['rel']}` → **{nb_name}**\n"
        md += "\n"

    return {
        "response_md": md,
        "entities": [g["node"].get("id", "") for g in grouped.values()],
        "actions": ["View in Knowledge Graph", "Run OSINT enrichment", "Check cross-case links"],
    }


def _exec_contradictions(case_id: str, query: str, db: Session) -> dict:
    name = _extract_entity_name(query) or ""
    rows = _neo4j_query(
        """
        MATCH (c:Contradiction {case_id: $case_id})
        OPTIONAL MATCH (c)-[:INVOLVES]->(n)
        WHERE $name = '' OR toLower(n.display_name) CONTAINS toLower($name)
        RETURN c {.*} AS contradiction,
               collect(DISTINCT n {.*}) AS involved_nodes
        ORDER BY c.severity DESC
        LIMIT 20
        """,
        {"case_id": case_id, "name": name},
    )

    if not rows:
        return {
            "response_md": "## ✅ Contradictions\n\nNo contradictions detected in this case. The evidence is internally consistent.\n\n> Run **Contradiction Monitor** to trigger a fresh scan.",
            "entities": [],
            "actions": ["Run Contradiction Scan", "View Evidence"],
        }

    severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}
    md = f"## ⚠️ Contradictions{' — involving ' + name if name else ''}\n\n"
    md += f"**{len(rows)} contradiction(s) found.**\n\n"
    for row in rows:
        c = row["contradiction"]
        sev = c.get("severity", "low")
        icon = severity_icon.get(sev, "⚪")
        md += f"### {icon} {c.get('description', 'Unnamed contradiction')}\n"
        md += f"- **Severity**: {sev.upper()}\n"
        md += f"- **Type**: {c.get('contradiction_type', 'Unknown')}\n"
        if c.get("details"):
            md += f"- **Details**: {c['details']}\n"
        nodes = row.get("involved_nodes", [])
        if nodes:
            names = [n.get("display_name") or n.get("value") or "?" for n in nodes if n]
            md += f"- **Involved**: {', '.join(names)}\n"
        md += "\n"

    return {
        "response_md": md,
        "entities": [],
        "actions": ["Open Contradiction Monitor", "Re-run contradiction scan", "Resolve contradiction"],
    }


def _exec_evidence_gaps(case_id: str, query: str, db: Session) -> dict:
    rows = _neo4j_query(
        """
        MATCH (g:EvidenceGap {case_id: $case_id, status: 'open'})
        RETURN g {.*} AS gap
        ORDER BY g.urgency DESC
        LIMIT 20
        """,
        {"case_id": case_id},
    )

    if not rows:
        return {
            "response_md": "## ✅ Evidence Gaps\n\nNo open evidence gaps found. All critical evidence tracks are accounted for.\n\n> Run **Evidence Gap Scan** to detect new gaps.",
            "entities": [],
            "actions": ["Run Gap Scan"],
        }

    urgency_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}
    md = f"## 🕳️ Evidence Gaps — {len(rows)} Open\n\n"
    for row in rows:
        g = row["gap"]
        urg = g.get("urgency", "low")
        icon = urgency_icon.get(urg, "⚪")
        md += f"### {icon} {g.get('gap_type', 'Unknown gap')}\n"
        md += f"- **Urgency**: {urg.upper()}\n"
        if g.get("description"):
            md += f"- **Description**: {g['description']}\n"
        if g.get("recommended_action"):
            md += f"- **Recommended Action**: {g['recommended_action']}\n"
        md += "\n"

    return {
        "response_md": md,
        "entities": [],
        "actions": ["Open Evidence Gaps view", "Request digital forensics", "Issue subpoena"],
    }


def _exec_hypothesis_support(case_id: str, query: str, db: Session) -> dict:
    name = _extract_entity_name(query) or ""
    rows = _neo4j_query(
        """
        MATCH (h:Hypothesis {case_id: $case_id})
        WHERE $name = '' OR toLower(h.narrative) CONTAINS toLower($name)
        RETURN h {.*} AS hypothesis
        ORDER BY h.probability DESC
        LIMIT 10
        """,
        {"case_id": case_id, "name": name},
    )

    if not rows:
        return {
            "response_md": "## 🔬 Hypotheses\n\nNo hypotheses found for this case.\n\n> Use **Theory Workspace** to create and evaluate hypotheses.",
            "entities": [],
            "actions": ["Open Theory Workspace"],
        }

    md = f"## 🔬 Hypothesis Support Analysis\n\n"
    for row in rows:
        h = row["hypothesis"]
        prob = h.get("probability", 0.0)
        prob_pct = int(float(prob) * 100) if prob else 0
        status = h.get("status", "candidate")

        md += f"### {h.get('narrative', 'Unnamed hypothesis')[:100]}\n"
        md += f"- **Probability**: {prob_pct}%\n"
        md += f"- **Status**: `{status}`\n"
        md += f"- **Scenario Type**: {h.get('scenario_type', 'Unknown')}\n"
        if h.get("supporting_evidence_ids"):
            ev_ids = h["supporting_evidence_ids"]
            md += f"- **Supporting Evidence**: {len(ev_ids)} artifact(s) linked\n"
        if h.get("predicates"):
            md += "- **Predicates**:\n"
            for p in (h["predicates"] or [])[:5]:
                md += f"  - `{p}`\n"
        md += "\n"

    return {
        "response_md": md,
        "entities": [],
        "actions": ["Open Theory Workspace", "Evaluate hypothesis", "Link evidence"],
    }


def _exec_legal_readiness(case_id: str, query: str, db: Session) -> dict:
    rows = _neo4j_query(
        """
        MATCH (r:CourtReadiness {case_id: $case_id})
        RETURN r {.*} AS readiness
        ORDER BY r.computed_at DESC LIMIT 1
        """,
        {"case_id": case_id},
    )
    legal_rows = _neo4j_query(
        """
        MATCH (q:LegalQualification {case_id: $case_id, status: 'confirmed'})
        RETURN q.section_id AS section, q.confidence AS confidence
        LIMIT 10
        """,
        {"case_id": case_id},
    )

    md = "## ⚖️ Legal & Court Readiness\n\n"

    if rows:
        r = rows[0]["readiness"]
        score = r.get("composite_score", 0)
        grade = r.get("grade", "?")
        md += f"### Readiness Score: **{score:.0f} / 100** — Grade `{grade}`\n\n"
        md += f"| Component | Score |\n|---|---|\n"
        for k in ("legal_score", "integrity_score", "defense_score", "procedural_score"):
            if k in r:
                label = k.replace("_score", "").replace("_", " ").title()
                md += f"| {label} | {r[k]:.0f} |\n"
        md += "\n"

        # Explain blockers
        if r.get("section_65b_missing"):
            md += "> 🔴 **Critical**: Section 65B certificate is missing — this will cap court readiness.\n\n"
        if r.get("hash_integrity_failed"):
            md += "> 🔴 **Critical**: Hash integrity check failed — evidence admissibility at risk.\n\n"
    else:
        md += "> No court readiness score computed yet. Run **Court Simulation → Readiness** to generate one.\n\n"

    if legal_rows:
        md += "### Confirmed Legal Sections\n"
        for lr in legal_rows:
            md += f"- **Section {lr.get('section', '?')}** — Confidence: {int(float(lr.get('confidence', 0)) * 100)}%\n"

    return {
        "response_md": md,
        "entities": [],
        "actions": ["Open Court Simulation", "Generate chargesheet", "Run compliance scan"],
    }


def _exec_timeline(case_id: str, query: str, db: Session) -> dict:
    rows = _neo4j_query(
        """
        MATCH (e:Event {case_id: $case_id})
        WHERE e.valid_from IS NOT NULL
        RETURN e {.*} AS event
        ORDER BY e.valid_from ASC
        LIMIT 30
        """,
        {"case_id": case_id},
    )

    if not rows:
        return {
            "response_md": "## 📅 Timeline\n\nNo timestamped events found for this case.\n\n> Upload evidence with timestamps or manually create event nodes in the Knowledge Graph.",
            "entities": [],
            "actions": ["Upload Evidence", "Open Knowledge Graph"],
        }

    md = f"## 📅 Case Timeline — {len(rows)} Event(s)\n\n"
    for row in rows:
        e = row["event"]
        ts = e.get("valid_from", "Unknown time")
        ev_type = e.get("event_type", "event")
        confidence = e.get("confidence", 1.0)
        conf_str = f"{int(float(confidence) * 100)}%" if confidence else "?"
        md += f"- **{ts[:19] if ts else '?'}** — `{ev_type}` (confidence: {conf_str})\n"
        if e.get("artifact_id"):
            md += f"  - Evidence: `{e['artifact_id'][:8]}...`\n"
    md += "\n"

    return {
        "response_md": md,
        "entities": [],
        "actions": ["Open Timeline Analysis", "Filter by date range", "Export timeline"],
    }


def _exec_evidence_list(case_id: str, query: str, db: Session) -> dict:
    artifacts = (
        db.query(EvidenceArtifact)
        .filter(EvidenceArtifact.case_id == uuid.UUID(case_id))
        .order_by(EvidenceArtifact.collection_timestamp_utc.desc())
        .limit(30)
        .all()
    )

    if not artifacts:
        return {
            "response_md": "## 📦 Evidence\n\nNo evidence artifacts found for this case.\n\n> Use **Evidence Vault** to upload files.",
            "entities": [],
            "actions": ["Open Evidence Vault", "Ingest forensic export"],
        }

    md = f"## 📦 Evidence Artifacts — {len(artifacts)} Items\n\n"
    md += "| # | Source Tool | Collected | Chain Valid |\n|---|---|---|---|\n"
    for i, a in enumerate(artifacts, 1):
        ts = a.collection_timestamp_utc.strftime("%Y-%m-%d %H:%M") if a.collection_timestamp_utc else "?"
        chain = "✅" if a.record_hash else "⚠️"
        md += f"| {i} | `{a.source_tool or '?'}` | {ts} | {chain} |\n"

    return {
        "response_md": md,
        "entities": [],
        "actions": ["Open Evidence Vault", "Verify chain of custody", "Export evidence list"],
    }


def _exec_case_summary(case_id: str, query: str, db: Session) -> dict:
    from app.memory.reader import get_investigation_state
    state = get_investigation_state(case_id, db=db)
    if "error" in state:
        return {
            "response_md": "Error: Case not found",
            "entities": [],
            "actions": [],
        }

    case_meta = state["case_metadata"]
    artifact_count = len(state["evidence_artifacts"])

    # Aggregate node labels counts
    label_counts = {}
    for n in state["attention_entities"]:
        label = n.get("label", "Node")
        label_counts[label] = label_counts.get(label, 0) + 1

    hyp_count = len(state["hypotheses"])
    contra_count = len(state["contradictions"])
    gap_count = len([g for g in state["gaps"] if g["status"] == "open"])

    md = f"## 🗂️ Case Summary\n\n"
    md += f"- **Case Type**: {case_meta['case_type']}\n"
    md += f"- **Status**: `{case_meta['status']}`\n"
    md += f"- **Classification**: `{case_meta['classification_tag']}`\n"
    md += f"- **Created**: {case_meta['created_at'][:16] if case_meta['created_at'] else '?'}\n\n"

    md += f"### Evidence & Graph\n"
    md += f"- **Evidence Artifacts**: {artifact_count}\n"
    for label, count in label_counts.items():
        md += f"- **{label} Nodes (Top Attention)**: {count}\n"
    md += f"- **Hypotheses**: {hyp_count}\n"
    md += f"- **Contradictions**: {contra_count}\n"
    md += f"- **Open Evidence Gaps**: {gap_count}\n"

    md += "\n### Quick Actions\n"
    md += "- Type **\"show contradictions\"** to see conflicts\n"
    md += "- Type **\"is this case court ready?\"** for legal status\n"
    md += "- Type **\"show evidence gaps\"** for missing evidence\n"

    return {
        "response_md": md,
        "entities": [],
        "actions": ["Open Dashboard", "Run AIRE analysis", "Generate court readiness report"],
    }


def _exec_reasoning_explanation(case_id: str, query: str, db: Session) -> dict:
    from app.memory.reader import get_investigation_state
    state = get_investigation_state(case_id, db=db)
    if "error" in state:
        return {
            "response_md": "Error: Case not found",
            "entities": [],
            "actions": [],
        }

    records = list(state["diary"])
    records.reverse()
    records = records[:10]

    md = "## 🤖 Reasoning Explanation\n\n"
    if not records:
        md += "> No reasoning traces available yet. Run **AIRE Analysis** to generate an investigation report.\n\n"
        return {
            "response_md": md,
            "entities": [],
            "actions": ["Trigger AIRE analysis", "Open Reasoning Traces view"],
        }

    md += "The following reasoning steps were recently logged by the AIRE engine:\n\n"
    for r in records:
        ts = r["timestamp"][:19] if r["timestamp"] else "?"
        md += f"### `{r['record_type']}` — {ts}\n"
        md += f"- **Description**: {r['description']}\n"
        if r["reasoning"]:
            md += f"- **Reasoning**: {r['reasoning'][:300]}\n"
        if r["beliefs_after"]:
            md += "- **Updated Beliefs**:\n"
            for hyp_id, prob in list(r["beliefs_after"].items())[:4]:
                md += f"  - Hypothesis `{hyp_id[:8]}...`: **{int(float(prob) * 100)}%**\n"
        md += "\n"

    return {
        "response_md": md,
        "entities": [],
        "actions": ["Open Reasoning Traces", "Re-run AIRE", "Export reasoning log"],
    }


# ── Intent Router ────────────────────────────────────────────────────────

_EXECUTOR_MAP = {
    "entity_connections": _exec_entity_connections,
    "contradictions": _exec_contradictions,
    "evidence_gaps": _exec_evidence_gaps,
    "hypothesis_support": _exec_hypothesis_support,
    "legal_readiness": _exec_legal_readiness,
    "timeline": _exec_timeline,
    "evidence_list": _exec_evidence_list,
    "case_summary": _exec_case_summary,
    "reasoning_explanation": _exec_reasoning_explanation,
}


# ── Endpoint ─────────────────────────────────────────────────────────────

@router.post("/cases/{case_id}/copilot/query", response_model=CopilotResponse)
def copilot_query(
    case_id: str,
    body: CopilotQuery,
    db: Session = Depends(get_db),
):
    """
    Natural language investigation copilot.
    Accepts a free-text query, classifies it, executes the appropriate
    intelligence query, and returns a structured Markdown response.
    """
    # Validate case
    try:
        case_uuid = uuid.UUID(case_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid case_id format")

    case = db.query(Case).filter(Case.case_id == case_uuid).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    t_start = datetime.now(timezone.utc)
    intent, confidence = _classify_intent(body.query)

    executor = _EXECUTOR_MAP.get(intent, _EXECUTOR_MAP["case_summary"])
    result = executor(case_id, body.query, db)

    elapsed_ms = (datetime.now(timezone.utc) - t_start).total_seconds() * 1000

    return CopilotResponse(
        intent=intent,
        confidence=confidence,
        response_md=result["response_md"],
        entities_referenced=result.get("entities", []),
        suggested_actions=result.get("actions", []),
        query_time_ms=round(elapsed_ms, 1),
    )


@router.get("/cases/{case_id}/copilot/intents")
def list_intents(case_id: str, db: Session = Depends(get_db)):
    """Return the list of supported query intents with example queries."""
    return {
        "intents": [
            {
                "name": "entity_connections",
                "description": "Find how entities are connected in the case graph",
                "examples": [
                    "Who is connected to Wallet X?",
                    "Show connections for Suspect A",
                    "Find linked accounts",
                ],
            },
            {
                "name": "contradictions",
                "description": "Detect conflicting evidence or timeline inconsistencies",
                "examples": [
                    "Find contradictions involving Suspect A",
                    "Show all conflicts in the evidence",
                    "Are there any inconsistencies?",
                ],
            },
            {
                "name": "evidence_gaps",
                "description": "Identify missing or uncollected evidence",
                "examples": [
                    "What evidence is missing?",
                    "Show open evidence gaps",
                    "What should we collect next?",
                ],
            },
            {
                "name": "hypothesis_support",
                "description": "Analyse evidence support for theories and hypotheses",
                "examples": [
                    "Which evidence supports the phishing hypothesis?",
                    "Show theories ranked by probability",
                ],
            },
            {
                "name": "legal_readiness",
                "description": "Assess court readiness and legal section mapping",
                "examples": [
                    "Is this case court ready?",
                    "Explain the readiness score",
                    "What legal sections apply?",
                ],
            },
            {
                "name": "timeline",
                "description": "Show chronological sequence of case events",
                "examples": [
                    "Show the case timeline",
                    "What happened between Jan 1 and Feb 1?",
                ],
            },
            {
                "name": "evidence_list",
                "description": "List all evidence artifacts in the case",
                "examples": [
                    "List all evidence",
                    "What files do we have?",
                    "Show all artifacts",
                ],
            },
            {
                "name": "case_summary",
                "description": "Provide a high-level overview of the case",
                "examples": [
                    "Summarize the case",
                    "Give me an overview",
                    "What is this case about?",
                ],
            },
            {
                "name": "reasoning_explanation",
                "description": "Explain AIRE reasoning steps and AI recommendations",
                "examples": [
                    "Why did the system flag this suspect?",
                    "Explain the recommendation",
                    "Show reasoning traces",
                ],
            },
        ]
    }


class CopilotExecuteTool(BaseModel):
    tool: str
    parameters: dict


@router.post("/cases/{case_id}/copilot/execute-tool")
def execute_copilot_tool(
    case_id: str,
    body: CopilotExecuteTool,
    db: Session = Depends(get_db),
):
    try:
        case_uuid = uuid.UUID(case_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid case_id format")

    case = db.query(Case).filter(Case.case_id == case_uuid).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    tool = body.tool
    params = body.parameters

    if tool == "record_investigative_action":
        action_type = params.get("action_type")
        target_ref = params.get("target_ref")
        priority_score = params.get("priority_score", 0.0)

        if not action_type or not target_ref:
            raise HTTPException(status_code=400, detail="Missing required parameters action_type or target_ref")

        try:
            act_type = ActionType(action_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid action_type: {action_type}")

        action_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        # 1. Save to Neo4j
        client = get_neo4j_client()
        desc = f"Action proposed via Copilot: {action_type} on {target_ref}"
        try:
            client.execute_write(
                """
                CREATE (a:InvestigationAction {
                    id: $aid, case_id: $cid,
                    action_type: $action_type,
                    target_ref: $target_ref, description: $desc,
                    status: 'pending', priority: $priority,
                    created_at: $now
                })
                """,
                {
                    "aid": str(action_id),
                    "cid": case_id,
                    "action_type": action_type,
                    "target_ref": target_ref,
                    "desc": desc,
                    "priority": float(priority_score),
                    "now": now.isoformat()
                }
            )
        except Exception as e:
            logger.warning("Failed to save action to Neo4j: %s", e)

        # 2. Save to Postgres
        action = InvestigationAction(
            action_id=action_id,
            case_id=case_uuid,
            action_type=act_type,
            target_ref=target_ref,
            priority_score=float(priority_score),
            status=ActionStatus.pending,
            created_at=now,
            status_updated_at=now,
        )
        db.add(action)

        # 3. Write a MemoryRecord (beliefs/audit log entry)
        from app.memory.writer import write_memory_record
        write_memory_record(
            db=db,
            case_id=case_id,
            record_type=MemoryRecordType.lead_pursued,
            description=f"Action proposed via Copilot tool: {action_type} for {target_ref} (priority={priority_score:.2f})",
            actor="system:copilot_tool",
            graph_refs=[target_ref],
        )
        db.commit()

        return {"id": str(action_id), "status": "created"}

    elif tool == "add_case_diary_note":
        record_type = params.get("record_type")
        description = params.get("description")
        actor = params.get("actor")
        reasoning = params.get("reasoning")

        if not record_type or not description or not actor:
            raise HTTPException(status_code=400, detail="Missing required parameters record_type, description, or actor")

        if actor.startswith("system:"):
            raise HTTPException(status_code=400, detail="Manual records must have a human actor, not 'system:*'")

        try:
            rec_type = MemoryRecordType(record_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid record_type: {record_type}")

        if rec_type not in {MemoryRecordType.decision_made, MemoryRecordType.lead_status_changed}:
            raise HTTPException(status_code=400, detail="Manual diary note type must be decision_made or lead_status_changed")

        from app.memory.writer import write_memory_record
        record = write_memory_record(
            db=db,
            case_id=case_id,
            record_type=rec_type,
            description=description,
            actor=actor,
            reasoning=reasoning,
        )
        db.commit()

        return {"id": str(record.record_id), "status": "created"}

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported tool: {tool}")


@router.get("/cases/{case_id}/strategy")
def get_case_strategy(case_id: str, db: Session = Depends(get_db)):
    try:
        case_uuid = uuid.UUID(case_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid case_id format")

    case = db.query(Case).filter(Case.case_id == case_uuid).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    client = get_neo4j_client()

    # 1. Fetch hypotheses
    hypotheses = client.execute_read(
        """
        MATCH (h:Hypothesis {case_id: $case_id})
        RETURN h.id AS id, h.narrative AS narrative, h.probability AS probability, h.status AS status
        ORDER BY h.probability DESC
        """,
        {"case_id": case_id}
    )
    active_hypotheses = [
        {
            "id": h["id"],
            "narrative": h["narrative"],
            "probability": h["probability"],
            "status": h["status"]
        } for h in hypotheses
    ]

    # 2. Fetch key contradictions
    contradictions = client.execute_read(
        """
        MATCH (c:Contradiction {case_id: $case_id})
        OPTIONAL MATCH (c)-[:INVOLVES]->(n)
        RETURN c.id AS id, c.description AS description, c.severity AS severity,
               c.contradiction_type AS contradiction_type,
               collect(coalesce(n.display_name, n.value, n.id)) AS involved_nodes
        ORDER BY c.severity DESC
        """,
        {"case_id": case_id}
    )
    key_contradictions = [
        {
            "id": c["id"],
            "description": c["description"],
            "severity": c["severity"],
            "contradiction_type": c["contradiction_type"],
            "involved_nodes": [x for x in c["involved_nodes"] if x]
        } for c in contradictions
    ]

    # 3. Fetch critical gaps
    gaps = client.execute_read(
        """
        MATCH (g:EvidenceGap {case_id: $case_id, status: 'open'})
        RETURN g.id AS id, g.gap_type AS gap_type, g.description AS description, g.urgency AS urgency
        ORDER BY g.urgency DESC
        """,
        {"case_id": case_id}
    )
    critical_gaps = [
        {
            "id": g["id"],
            "gap_type": g["gap_type"],
            "description": g["description"],
            "urgency": g["urgency"]
        } for g in gaps
    ]

    # 4. Generate recommendations (exactly 3)
    recs = []
    # Add gap recommendations
    for g in critical_gaps:
        recs.append(f"Investigate evidence gap: {g['description']} (Urgency: {g['urgency']})")
    # Add contradiction recommendations
    for c in key_contradictions:
        recs.append(f"Resolve contradiction: {c['description']} (Severity: {c['severity']})")

    # Fallback/default recommendations to make sure we have at least 3
    if len(recs) < 3:
        recs.append("Generate court readiness report to assess legal proof sufficiency.")
    if len(recs) < 3:
        recs.append("Run OSINT intelligence scan to enrich entity connectivity.")
    if len(recs) < 3:
        recs.append("Trigger AIRE autonomous reasoning to update hypothesis probabilities.")

    # Slice to exactly 3 recommendations
    recommendations = recs[:3]

    return {
        "active_hypotheses": active_hypotheses,
        "key_contradictions": key_contradictions,
        "critical_gaps": critical_gaps,
        "recommendations": recommendations
    }
