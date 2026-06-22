"""Multi-Agent AI Orchestrator — Collaborative Investigation Agents.

Addresses Gap 8: Instead of monolithic engine steps, each reasoning domain
is encapsulated as a specialized agent that produces typed outputs,
votes on conclusions, and reaches consensus.

Agent Roster:
  EvidenceAgent     — Manages evidence integrity, chain of custody, gaps
  LegalAgent        — Maps legal sections, procedural compliance, court readiness
  TimelineAgent     — Temporal reconstruction, sequence verification
  OSINTAgent        — Open-source intelligence enrichment
  TheoryAgent       — Hypothesis generation, Bayesian updating, elimination
  BehavioralAgent   — Behavioral baselines, anomaly detection, deception scoring
  CourtAgent        — Defense anticipation, chargesheet assembly, admissibility

Consensus Protocol:
  Each agent produces a typed Recommendation with confidence.
  The Orchestrator aggregates via weighted voting, resolves conflicts,
  and produces a unified InvestigationDirective.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Agent Protocol ──────────────────────────────────────────────────────

class AgentRole(str, Enum):
    evidence = "evidence"
    legal = "legal"
    timeline = "timeline"
    osint = "osint"
    theory = "theory"
    behavioral = "behavioral"
    court = "court"


class RecommendationType(str, Enum):
    action = "action"                # Do something
    alert = "alert"                  # Something needs attention
    update = "update"                # State change
    insight = "insight"              # New understanding
    contradiction = "contradiction"  # Conflicting information
    prediction = "prediction"        # Forward-looking assessment


@dataclass
class AgentRecommendation:
    """A typed output from a specialized agent."""
    agent_role: AgentRole
    rec_type: RecommendationType
    title: str
    description: str
    confidence: float                   # 0.0 – 1.0
    priority: float = 0.5              # 0.0 – 1.0
    evidence_basis: list[str] = field(default_factory=list)
    affected_entities: list[str] = field(default_factory=list)
    suggested_action: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "agent_role": self.agent_role.value,
            "rec_type": self.rec_type.value,
            "title": self.title,
            "description": self.description,
            "confidence": self.confidence,
            "priority": self.priority,
            "evidence_basis": self.evidence_basis,
            "affected_entities": self.affected_entities,
            "suggested_action": self.suggested_action,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


# ── Specialized Agents ──────────────────────────────────────────────────

class BaseAgent:
    role: AgentRole
    weight: float = 1.0

    def analyze(self, case_id: str, context: dict) -> list[AgentRecommendation]:
        raise NotImplementedError


class EvidenceAgent(BaseAgent):
    role = AgentRole.evidence
    weight = 1.0

    def analyze(self, case_id: str, context: dict) -> list[AgentRecommendation]:
        from app.graph.driver import get_neo4j_client
        client = get_neo4j_client()
        recs = []

        # Check for evidence without integrity hashes
        unhashed = client.execute_read(
            """
            MATCH (e:Event {case_id: $cid})
            WHERE e.content_hash IS NULL AND e.confidence IS NOT NULL
            RETURN count(e) AS cnt
            """,
            {"cid": case_id},
        )
        if unhashed and unhashed[0]["cnt"] > 0:
            recs.append(AgentRecommendation(
                agent_role=self.role,
                rec_type=RecommendationType.alert,
                title="Unhashed Evidence Detected",
                description=f"{unhashed[0]['cnt']} evidence nodes lack integrity hashes",
                confidence=0.95,
                priority=0.8,
                suggested_action="Run integrity verification on all evidence artifacts",
            ))

        # Check for evidence gaps
        gaps = client.execute_read(
            "MATCH (g:EvidenceGap {case_id: $cid, status: 'open'}) RETURN count(g) AS cnt",
            {"cid": case_id},
        )
        if gaps and gaps[0]["cnt"] > 0:
            recs.append(AgentRecommendation(
                agent_role=self.role,
                rec_type=RecommendationType.action,
                title="Open Evidence Gaps",
                description=f"{gaps[0]['cnt']} evidence gaps remain unresolved",
                confidence=0.90,
                priority=0.7,
                suggested_action="Review evidence gap list and initiate collection",
            ))

        return recs


class LegalAgent(BaseAgent):
    role = AgentRole.legal
    weight = 1.2

    def analyze(self, case_id: str, context: dict) -> list[AgentRecommendation]:
        from app.graph.driver import get_neo4j_client
        client = get_neo4j_client()
        recs = []

        # Check Section 65B compliance
        s65b = client.execute_read(
            """
            MATCH (c:ComplianceRequirement {case_id: $cid})
            WHERE c.requirement_type = 'section_65b' AND c.status <> 'satisfied'
            RETURN count(c) AS cnt
            """,
            {"cid": case_id},
        )
        if s65b and s65b[0]["cnt"] > 0:
            recs.append(AgentRecommendation(
                agent_role=self.role,
                rec_type=RecommendationType.alert,
                title="Section 65B Certificate Missing",
                description="Digital evidence requires Section 65B IT Act certification for court admissibility",
                confidence=1.0,
                priority=0.95,
                suggested_action="Prepare and attach Section 65B certificate",
            ))

        # Check court readiness
        readiness = client.execute_read(
            "MATCH (r:CourtReadiness {case_id: $cid}) RETURN r.composite_score AS score ORDER BY r.computed_at DESC LIMIT 1",
            {"cid": case_id},
        )
        if readiness and readiness[0]["score"]:
            score = float(readiness[0]["score"])
            if score < 50:
                recs.append(AgentRecommendation(
                    agent_role=self.role,
                    rec_type=RecommendationType.insight,
                    title=f"Court Readiness Low ({score:.0f}/100)",
                    description="Case is not ready for prosecution — significant gaps remain",
                    confidence=0.90,
                    priority=0.85,
                    suggested_action="Focus on evidence collection and legal compliance",
                ))

        return recs


class TimelineAgent(BaseAgent):
    role = AgentRole.timeline
    weight = 0.9

    def analyze(self, case_id: str, context: dict) -> list[AgentRecommendation]:
        from app.graph.driver import get_neo4j_client
        client = get_neo4j_client()
        recs = []

        # Check for temporal inconsistencies
        overlaps = client.execute_read(
            """
            MATCH (p:Person {case_id: $cid})-[:PARTICIPATED_IN]->(e1:Event),
                  (p)-[:PARTICIPATED_IN]->(e2:Event)
            WHERE e1.id < e2.id
            AND e1.valid_from IS NOT NULL AND e2.valid_from IS NOT NULL
            AND e1.valid_to IS NOT NULL
            AND e2.valid_from < e1.valid_to
            RETURN p.display_name AS person, count(*) AS overlaps
            """,
            {"cid": case_id},
        )
        for row in (overlaps or []):
            if row["overlaps"] > 0:
                recs.append(AgentRecommendation(
                    agent_role=self.role,
                    rec_type=RecommendationType.contradiction,
                    title=f"Timeline Overlap for {row['person']}",
                    description=f"{row['overlaps']} overlapping events detected",
                    confidence=0.85,
                    priority=0.75,
                    suggested_action="Verify event timestamps for accuracy",
                ))

        return recs


class OSINTAgent(BaseAgent):
    role = AgentRole.osint
    weight = 0.8

    def analyze(self, case_id: str, context: dict) -> list[AgentRecommendation]:
        from app.graph.driver import get_neo4j_client
        client = get_neo4j_client()
        recs = []

        # Find accounts not yet enriched
        unenriched = client.execute_read(
            """
            MATCH (a:Account {case_id: $cid})
            WHERE NOT EXISTS { MATCH (a)-[:ENRICHED_BY]->(:OSINTResult) }
            RETURN count(a) AS cnt
            """,
            {"cid": case_id},
        )
        if unenriched and unenriched[0]["cnt"] > 0:
            recs.append(AgentRecommendation(
                agent_role=self.role,
                rec_type=RecommendationType.action,
                title=f"{unenriched[0]['cnt']} Accounts Need OSINT Enrichment",
                description="Account entities exist without OSINT data",
                confidence=0.80,
                priority=0.6,
                suggested_action="Run OSINT enrichment pipeline",
            ))

        return recs


class TheoryAgent(BaseAgent):
    role = AgentRole.theory
    weight = 1.1

    def analyze(self, case_id: str, context: dict) -> list[AgentRecommendation]:
        from app.graph.driver import get_neo4j_client
        client = get_neo4j_client()
        recs = []

        # Check for low-probability hypotheses
        low_hyps = client.execute_read(
            """
            MATCH (h:Hypothesis {case_id: $cid, status: 'active'})
            WHERE h.probability < 0.2
            RETURN h.id AS id, h.narrative AS narrative, h.probability AS prob
            """,
            {"cid": case_id},
        )
        for h in (low_hyps or []):
            recs.append(AgentRecommendation(
                agent_role=self.role,
                rec_type=RecommendationType.insight,
                title=f"Low-Probability Hypothesis",
                description=f"'{h['narrative'][:60]}...' at {float(h['prob'])*100:.0f}% — consider elimination",
                confidence=0.85,
                priority=0.5,
                suggested_action="Evaluate if hypothesis should be eliminated",
                affected_entities=[h["id"]],
            ))

        # Check for high-attention entities without hypotheses
        orphans = client.execute_read(
            """
            MATCH (n {case_id: $cid})
            WHERE n.attention_value > 0.6
            AND NOT EXISTS { MATCH (h:Hypothesis)-[:INVOLVES|PREDICTED_BY]->(n) }
            RETURN n.id AS id, labels(n)[0] AS label, n.attention_value AS attn
            LIMIT 3
            """,
            {"cid": case_id},
        )
        for o in (orphans or []):
            recs.append(AgentRecommendation(
                agent_role=self.role,
                rec_type=RecommendationType.alert,
                title="Unexplained High-Attention Entity",
                description=f"{o['label']}[{o['id'][:8]}] has attention {o['attn']:.2f} but no hypothesis references it",
                confidence=0.80,
                priority=0.7,
                suggested_action="Consider generating a new hypothesis involving this entity",
                affected_entities=[o["id"]],
            ))

        return recs


class BehavioralAgent(BaseAgent):
    role = AgentRole.behavioral
    weight = 0.9

    def analyze(self, case_id: str, context: dict) -> list[AgentRecommendation]:
        from app.graph.driver import get_neo4j_client
        client = get_neo4j_client()
        recs = []

        anomalies = client.execute_read(
            """
            MATCH (a:BehavioralAnomaly {case_id: $cid})
            WHERE a.severity IN ['high', 'critical']
            RETURN a.description AS desc, a.severity AS sev, a.anomaly_type AS atype
            LIMIT 5
            """,
            {"cid": case_id},
        )
        for a in (anomalies or []):
            recs.append(AgentRecommendation(
                agent_role=self.role,
                rec_type=RecommendationType.alert,
                title=f"Behavioral Anomaly: {a['atype']}",
                description=a["desc"],
                confidence=0.85,
                priority=0.8 if a["sev"] == "critical" else 0.6,
                suggested_action="Investigate anomalous behavior pattern",
            ))

        return recs


class CourtAgent(BaseAgent):
    role = AgentRole.court
    weight = 1.0

    def analyze(self, case_id: str, context: dict) -> list[AgentRecommendation]:
        from app.graph.driver import get_neo4j_client
        client = get_neo4j_client()
        recs = []

        # Anticipate defense arguments
        contradictions = client.execute_read(
            """
            MATCH (c:Contradiction {case_id: $cid})
            WHERE c.severity = 'high'
            RETURN count(c) AS cnt
            """,
            {"cid": case_id},
        )
        if contradictions and contradictions[0]["cnt"] > 0:
            recs.append(AgentRecommendation(
                agent_role=self.role,
                rec_type=RecommendationType.alert,
                title="Defense Will Exploit Contradictions",
                description=f"{contradictions[0]['cnt']} high-severity contradictions will be targeted by defense counsel",
                confidence=0.92,
                priority=0.85,
                suggested_action="Resolve or explain all high-severity contradictions before filing chargesheet",
            ))

        return recs


# ── Agent Registry ──────────────────────────────────────────────────────

_AGENTS: list[BaseAgent] = [
    EvidenceAgent(),
    LegalAgent(),
    TimelineAgent(),
    OSINTAgent(),
    TheoryAgent(),
    BehavioralAgent(),
    CourtAgent(),
]


# ── Orchestrator ────────────────────────────────────────────────────────

def run_multi_agent_analysis(case_id: str, context: dict = None) -> dict:
    """
    Run all specialized agents and aggregate their recommendations
    into a unified investigation directive.
    """
    context = context or {}
    all_recs: list[dict] = []
    agent_statuses = {}

    for agent in _AGENTS:
        try:
            recs = agent.analyze(case_id, context)
            for rec in recs:
                all_recs.append(rec.to_dict())
            agent_statuses[agent.role.value] = {
                "status": "completed",
                "recommendations": len(recs),
            }
        except Exception as e:
            logger.error("Agent %s failed: %s", agent.role.value, e)
            agent_statuses[agent.role.value] = {
                "status": "error",
                "error": str(e),
            }

    # Consensus: group by rec_type, sort by weighted priority
    for rec in all_recs:
        agent_weight = next((a.weight for a in _AGENTS if a.role.value == rec["agent_role"]), 1.0)
        rec["weighted_priority"] = round(rec["priority"] * rec["confidence"] * agent_weight, 3)

    all_recs.sort(key=lambda r: r["weighted_priority"], reverse=True)

    # Build directive
    top_actions = [r for r in all_recs if r["rec_type"] == "action"][:5]
    top_alerts = [r for r in all_recs if r["rec_type"] == "alert"][:5]
    insights = [r for r in all_recs if r["rec_type"] == "insight"][:5]
    contradictions = [r for r in all_recs if r["rec_type"] == "contradiction"]

    return {
        "case_id": case_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_statuses": agent_statuses,
        "total_recommendations": len(all_recs),
        "directive": {
            "priority_actions": top_actions,
            "critical_alerts": top_alerts,
            "insights": insights,
            "contradictions": contradictions,
        },
        "all_recommendations": all_recs,
        "consensus_summary": _generate_consensus_summary(all_recs),
    }


def _generate_consensus_summary(recs: list[dict]) -> str:
    """Generate a human-readable summary of agent consensus."""
    if not recs:
        return "No recommendations generated. The investigation may need more evidence."

    action_count = sum(1 for r in recs if r["rec_type"] == "action")
    alert_count = sum(1 for r in recs if r["rec_type"] == "alert")
    contra_count = sum(1 for r in recs if r["rec_type"] == "contradiction")

    parts = []
    if alert_count:
        parts.append(f"{alert_count} critical alert(s) requiring immediate attention")
    if action_count:
        parts.append(f"{action_count} recommended action(s)")
    if contra_count:
        parts.append(f"{contra_count} contradiction(s) need resolution")

    top = recs[0] if recs else None
    if top:
        parts.append(f"Highest priority: {top['title']} ({top['agent_role']} agent, confidence: {top['confidence']:.0%})")

    return ". ".join(parts) + "."
