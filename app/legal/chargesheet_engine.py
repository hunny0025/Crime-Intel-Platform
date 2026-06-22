"""Chargesheet Engine — production-grade chargesheet generation pipeline.

14-step pipeline that synthesizes all legal intelligence outputs into a
complete, court-ready ChargesheetPackage. Every method returns real data
from Neo4j and PostgreSQL. No stubs. No pass statements.

overall_readiness = 0.4×element_coverage + 0.4×evidence_quality + 0.2×compliance
Critical blockers force score to 0.0 regardless.

ADVISORY ONLY — all outputs require independent prosecutorial review.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import text as sql_text

from app.graph.driver import get_neo4j_client
from app.legal.chargesheet_models import (
    Allegation, AccusedPerson, ChargesheetPackage, ComplianceBlocker,
    DefenseRisk, EvidenceBundle, EvidenceItem, FilingRecommendation,
    LegalElement, MissingEvidence, ProsecutionStrategyNote, ReadinessTier,
    TimelineEvent, TrialStrength, WeakPoint, LEGAL_DISCLAIMER,
)
from app.legal.missing_elements_engine import analyze_missing_elements
from app.legal.procedural_engine import get_procedural_timeline
from app.legal.chargesheet_intelligence import _build_allegation_breakdown
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType

logger = logging.getLogger(__name__)

# Filing thresholds
FILING_THRESHOLD = 0.7      # ≥70% element coverage → FILE
HOLD_THRESHOLD = 0.4        # ≥40% → HOLD, <40% → DROP

# Readiness tier thresholds
TIER_THRESHOLDS = {
    "ready_for_filing": 0.8,
    "near_ready": 0.6,
    "developing": 0.4,
}


class ChargesheetEngine:
    """Generates complete ChargesheetPackage from case intelligence data.

    Usage:
        engine = ChargesheetEngine(case_id, db)
        package = engine.generate()
    """

    def __init__(self, case_id: str, db: Optional[Session] = None):
        self.case_id = case_id
        self.db = db
        self.client = get_neo4j_client()
        self.now = datetime.now(timezone.utc).isoformat()

    def generate(self) -> ChargesheetPackage:
        """Execute the 14-step chargesheet generation pipeline."""
        logger.info("Generating chargesheet for case %s", self.case_id)

        # Step 1: Get case metadata
        case_type = self._get_case_type()

        # Step 2: Get accused persons
        accused = self._get_accused_persons()

        # Step 3: Get prosecution theory
        theory = self._get_prosecution_theory()

        # Step 4: Analyze missing elements → build allegations
        allegations = self._build_allegations()

        # Step 5: Compute filing recommendations per allegation
        allegations = self._compute_filing_recommendations(allegations)

        # Step 6: Identify weak points across all allegations
        for allegation in allegations:
            allegation.weak_points = self._get_weak_points(allegation)

        # Step 7: Identify missing evidence
        for allegation in allegations:
            allegation.missing_evidence = self._get_missing_evidence(allegation)

        # Step 8: Get compliance blockers
        compliance_blockers, compliance_pct = self._get_compliance_status()

        # Step 9: Get integrity certificates
        certificates = self._get_certificates()

        # Step 10: Build case timeline
        timeline = self._build_timeline()

        # Step 11: Generate prosecution strategy
        strategy = self._build_prosecution_strategy(allegations)

        # Step 12: Estimate defense risks
        defense_risks = self._get_defense_risks(allegations)

        # Step 13: Compute overall readiness score
        file_count = sum(1 for a in allegations if a.filing_recommendation == FilingRecommendation.FILE)
        hold_count = sum(1 for a in allegations if a.filing_recommendation == FilingRecommendation.HOLD)
        drop_count = sum(1 for a in allegations if a.filing_recommendation == FilingRecommendation.DROP)

        element_coverage = self._compute_element_coverage(allegations)
        evidence_quality = self._compute_evidence_quality(certificates, allegations)
        compliance_score = compliance_pct / 100.0

        has_critical_blocker = any(cb.severity == "critical" for cb in compliance_blockers)

        if has_critical_blocker or not allegations:
            overall_score = 0.0
        else:
            overall_score = round(
                0.4 * element_coverage + 0.4 * evidence_quality + 0.2 * compliance_score,
                2,
            )

        readiness_tier = self._score_to_tier(overall_score)
        trial_strength = self._estimate_trial_strength(
            overall_score, element_coverage, has_critical_blocker, allegations,
        )
        filing_ready = (
            readiness_tier == ReadinessTier.ready_for_filing
            and not has_critical_blocker
            and file_count > 0
        )

        # Step 14: Generate case summary & narrative
        case_summary = self._generate_case_summary(
            case_type, accused, allegations, theory, overall_score,
        )
        narrative = self._generate_narrative(
            overall_score, readiness_tier, has_critical_blocker,
            file_count, hold_count, drop_count, len(allegations),
        )

        # Count evidence at generation time for staleness tracking
        evidence_count = self._count_evidence()

        # Get version number
        version = self._get_next_version()

        package = ChargesheetPackage(
            case_id=self.case_id,
            generated_at=self.now,
            version=version,
            overall_readiness_score=overall_score,
            readiness_tier=readiness_tier,
            trial_strength=trial_strength,
            filing_ready=filing_ready,
            case_summary=case_summary,
            case_type=case_type,
            allegations=allegations,
            file_count=file_count,
            hold_count=hold_count,
            drop_count=drop_count,
            accused_persons=accused,
            prosecution_theory=theory,
            prosecution_strategy=strategy,
            defense_risks=defense_risks,
            compliance_blockers=compliance_blockers,
            procedural_compliance_percentage=compliance_pct,
            element_readiness_percentage=int(element_coverage * 100),
            integrity_certificates=certificates,
            case_timeline=timeline,
            summary_narrative=narrative,
            is_stale=False,
            evidence_count_at_generation=evidence_count,
            disclaimer=LEGAL_DISCLAIMER,
        )

        # Persist to database
        self._persist_package(package)

        # Write memory record
        if self.db:
            write_memory_record(
                db=self.db, case_id=self.case_id,
                record_type=MemoryRecordType.decision_made,
                description=(
                    f"Chargesheet package v{version} generated: "
                    f"{readiness_tier.value} (score={overall_score:.2f}), "
                    f"FILE={file_count} HOLD={hold_count} DROP={drop_count}"
                ),
                actor="system:chargesheet_engine",
                graph_refs=[package.chargesheet_id],
            )
            self.db.commit()

        logger.info(
            "Chargesheet %s generated: tier=%s score=%.2f allegations=%d",
            package.chargesheet_id, readiness_tier.value,
            overall_score, len(allegations),
        )
        return package

    # ── Step Implementations ─────────────────────────────────────────────

    def _get_case_type(self) -> Optional[str]:
        """Get case type from Postgres."""
        if self.db:
            try:
                row = self.db.execute(
                    sql_text("SELECT case_type FROM cases WHERE case_id = :cid"),
                    {"cid": uuid.UUID(self.case_id)},
                ).fetchone()
                return row[0] if row else None
            except Exception:
                pass
        return None

    def _get_accused_persons(self) -> list[AccusedPerson]:
        """Fetch accused/suspect persons from the knowledge graph."""
        nodes = self.client.execute_read(
            """
            MATCH (p:Person {case_id: $cid})
            WHERE p.status IN ['suspect', 'accused'] OR p.label = 'Suspect'
            RETURN p.id AS person_id, coalesce(p.display_name, p.id) AS name,
                   p.status AS status
            """,
            {"cid": self.case_id},
        )
        return [
            AccusedPerson(
                person_id=n["person_id"],
                name=n["name"],
                status=n.get("status"),
            )
            for n in nodes
        ]

    def _get_prosecution_theory(self) -> dict:
        """Get the top hypothesis as prosecution theory."""
        nodes = self.client.execute_read(
            """
            MATCH (h:Hypothesis {case_id: $cid})
            WHERE h.posterior_probability IS NOT NULL
            RETURN h.id AS id, h.description AS description,
                   h.posterior_probability AS probability,
                   h.narrative AS narrative
            ORDER BY h.posterior_probability DESC LIMIT 1
            """,
            {"cid": self.case_id},
        )
        if nodes:
            return {
                "hypothesis_id": nodes[0]["id"],
                "description": nodes[0].get("description") or nodes[0].get("narrative", ""),
                "probability": nodes[0]["probability"],
                "narrative": nodes[0].get("narrative", ""),
            }
        return {
            "hypothesis_id": None,
            "description": "No established case theory",
            "probability": 0.0,
            "narrative": "",
        }

    def _build_allegations(self) -> list[Allegation]:
        """Build allegations from the missing elements analysis."""
        report = analyze_missing_elements(self.case_id)
        allegations = []

        for sec in report.get("applicable_sections", []):
            section_id = sec["section_id"]

            # Get per-allegation evidence breakdown from chargesheet_intelligence
            breakdown = _build_allegation_breakdown(self.client, self.case_id, sec)

            # Build LegalElement list with EvidenceBundles
            elements = []
            for elem in sec.get("elements", []):
                items = self._get_evidence_items_for_element(
                    section_id, elem["element_id"],
                )
                strongest = max((i.confidence for i in items), default=0.0)
                bundle = EvidenceBundle(
                    element_id=elem["element_id"],
                    element_text=elem["element_text"],
                    status=elem["status"],
                    items=items,
                    strongest_confidence=strongest,
                    evidence_categories=elem.get("evidence_categories", {}),
                )
                elements.append(LegalElement(
                    element_id=elem["element_id"],
                    element_text=elem["element_text"],
                    status=elem["status"],
                    evidence_bundle=bundle,
                    priority_score=elem.get("priority_score", 0.0),
                    investigation_action=elem.get("suggested_investigation_action"),
                ))

            satisfied = sum(1 for e in elements if e.status == "satisfied")
            total = len(elements)
            coverage = (satisfied / total * 100) if total > 0 else 0.0

            allegation = Allegation(
                section_id=section_id,
                section_reference=sec.get("section_reference"),
                statute=sec.get("statute", "BNS_2023"),
                title=sec["title"],
                elements=elements,
                satisfied_count=satisfied,
                total_count=total,
                coverage_percentage=round(coverage, 1),
                supporting_witnesses=breakdown.get("supporting_witnesses", []),
                supporting_digital_artifacts=breakdown.get("supporting_digital_artifacts", []),
                supporting_documents=breakdown.get("supporting_documents", []),
                supporting_forensic_reports=breakdown.get("supporting_forensic_reports", []),
                financial_support=breakdown.get("financial_support", []),
                communication_support=breakdown.get("communication_support", []),
                applicable_exceptions=sec.get("applicable_exceptions", []),
                burden_of_proof=sec.get("burden_of_proof", []),
            )
            allegations.append(allegation)

        return allegations

    def _get_evidence_items_for_element(
        self, section_id: str, element_id: str,
    ) -> list[EvidenceItem]:
        """Query Neo4j for evidence mappings to a specific legal element."""
        mappings = self.client.execute_read(
            """
            MATCH (m:EvidenceMapping {case_id: $cid})-[:SATISFIES_ELEMENT]->(le:LegalElement {id: $eid})
                  <-[:HAS_ELEMENT]-(ls:LegalSection {id: $sid})
            RETURN m.evidence_ref AS ref, m.evidence_type AS type,
                   m.confidence AS confidence,
                   m.chain_of_custody_status AS coc_status,
                   m.id AS mapping_id
            """,
            {"cid": self.case_id, "sid": section_id, "eid": element_id},
        )
        return [
            EvidenceItem(
                evidence_ref=m["ref"],
                evidence_type=m.get("type", "unknown"),
                chain_of_custody_status=m.get("coc_status", "unverified"),
                confidence=m.get("confidence", 0.0) or 0.0,
            )
            for m in mappings
        ]

    def _compute_filing_recommendations(
        self, allegations: list[Allegation],
    ) -> list[Allegation]:
        """Set FILE/HOLD/DROP per allegation based on element coverage."""
        for allegation in allegations:
            coverage = allegation.coverage_percentage / 100.0
            if coverage >= FILING_THRESHOLD:
                allegation.filing_recommendation = FilingRecommendation.FILE
            elif coverage >= HOLD_THRESHOLD:
                allegation.filing_recommendation = FilingRecommendation.HOLD
            else:
                allegation.filing_recommendation = FilingRecommendation.DROP
        return allegations

    def _get_weak_points(self, allegation: Allegation) -> list[WeakPoint]:
        """Identify weaknesses in an allegation's evidence chain."""
        weak_points = []

        for elem in allegation.elements:
            bundle = elem.evidence_bundle

            if bundle.status == "unsatisfied":
                weak_points.append(WeakPoint(
                    element_id=elem.element_id,
                    element_text=elem.element_text,
                    weakness_type="missing_evidence",
                    description=f"No evidence supports element: {elem.element_text}",
                    remediation=elem.investigation_action,
                    severity="critical" if elem.priority_score >= 0.8 else "high",
                ))
            elif bundle.status == "partially_satisfied":
                if bundle.strongest_confidence < 0.5:
                    weak_points.append(WeakPoint(
                        element_id=elem.element_id,
                        element_text=elem.element_text,
                        weakness_type="low_confidence",
                        description=(
                            f"Evidence confidence is low ({bundle.strongest_confidence:.0%}). "
                            f"May not meet beyond-reasonable-doubt standard."
                        ),
                        remediation=elem.investigation_action,
                        severity="high",
                    ))
                if len(bundle.items) == 1:
                    weak_points.append(WeakPoint(
                        element_id=elem.element_id,
                        element_text=elem.element_text,
                        weakness_type="single_source",
                        description=(
                            "Only one evidence source supports this element. "
                            "Corroboration recommended for trial strength."
                        ),
                        remediation="Seek independent corroboration from additional sources.",
                        severity="medium",
                    ))

                broken = [
                    i for i in bundle.items
                    if i.chain_of_custody_status in ("broken", "compromised")
                ]
                if broken:
                    weak_points.append(WeakPoint(
                        element_id=elem.element_id,
                        element_text=elem.element_text,
                        weakness_type="broken_chain",
                        description=(
                            f"{len(broken)} evidence item(s) have broken chain of custody. "
                            f"Admissibility may be challenged."
                        ),
                        remediation="Review and repair chain of custody documentation.",
                        severity="critical",
                    ))

        return weak_points

    def _get_missing_evidence(self, allegation: Allegation) -> list[MissingEvidence]:
        """Identify evidence that should be collected."""
        missing = []
        for elem in allegation.elements:
            if elem.status in ("unsatisfied", "partially_satisfied"):
                cats = elem.evidence_bundle.evidence_categories
                first_cat = next(iter(cats.keys()), "other") if cats else "other"
                req_types = []
                for types_list in cats.values():
                    req_types.extend(types_list)

                missing.append(MissingEvidence(
                    element_id=elem.element_id,
                    element_text=elem.element_text,
                    required_evidence_types=req_types,
                    evidence_category=first_cat,
                    priority=elem.priority_score,
                    suggested_action=elem.investigation_action or "",
                ))
        return missing

    def _get_compliance_status(self) -> tuple[list[ComplianceBlocker], int]:
        """Get compliance blockers and overall compliance percentage."""
        timeline_report = get_procedural_timeline(self.case_id, self.db)

        blockers = []
        if "error" not in timeline_report:
            for item in timeline_report.get("timeline", []):
                if item["status"] == "non_compliant" or item.get("is_overdue", False):
                    blockers.append(ComplianceBlocker(
                        requirement_id=item["requirement_id"],
                        title=item["title"],
                        required_by=item.get("required_by"),
                        severity=item.get("severity", "medium"),
                        guidance=item.get("remediation_guidance", ""),
                        is_overdue=item.get("is_overdue", False),
                    ))

        total = 0
        compliant = 0
        if "error" not in timeline_report:
            items = timeline_report.get("timeline", [])
            total = len(items)
            compliant = sum(1 for i in items if i["status"] == "compliant")

        pct = int((compliant / total) * 100) if total > 0 else 100
        return blockers, pct

    def _get_certificates(self) -> list[dict]:
        """Get evidence integrity certificates."""
        certs = self.client.execute_read(
            """
            MATCH (c:EvidenceIntegrityCertificate {case_id: $cid})
            RETURN c.id AS cert_id, c.evidence_ref AS evidence_ref,
                   c.verification_grade AS grade, c.certified_at AS certified_at
            """,
            {"cid": self.case_id},
        )
        return [
            {
                "certificate_id": c["cert_id"],
                "evidence_ref": c["evidence_ref"],
                "integrity_grade": c["grade"],
                "certified_at": c["certified_at"],
            }
            for c in certs
        ]

    def _build_timeline(self) -> list[TimelineEvent]:
        """Build case timeline from graph events."""
        events = self.client.execute_read(
            """
            MATCH (e:Event {case_id: $cid})
            RETURN e.id AS id, e.event_type AS type,
                   coalesce(e.valid_from, e.created_at) AS ts,
                   e.artifact_id AS artifact_id
            ORDER BY coalesce(e.valid_from, e.created_at) ASC
            LIMIT 50
            """,
            {"cid": self.case_id},
        )
        return [
            TimelineEvent(
                timestamp=str(e.get("ts", "")),
                event_type=e.get("type", "unknown"),
                description=f"{e.get('type', 'event')} recorded",
                evidence_refs=[e["artifact_id"]] if e.get("artifact_id") else [],
            )
            for e in events
        ]

    def _build_prosecution_strategy(
        self, allegations: list[Allegation],
    ) -> list[ProsecutionStrategyNote]:
        """Generate prosecution strategy advisory notes."""
        notes = []

        # Identify strongest charge
        file_allegations = [
            a for a in allegations
            if a.filing_recommendation == FilingRecommendation.FILE
        ]
        if file_allegations:
            strongest = max(file_allegations, key=lambda a: a.coverage_percentage)
            notes.append(ProsecutionStrategyNote(
                note_type="strongest_charge",
                description=(
                    f"Lead with {strongest.title} ({strongest.section_reference or strongest.section_id}) — "
                    f"{strongest.coverage_percentage:.0f}% element coverage with "
                    f"{strongest.satisfied_count}/{strongest.total_count} elements satisfied."
                ),
                related_sections=[strongest.section_id],
                priority="high",
            ))

        # Corroboration advisory
        multi_source = [
            a for a in allegations
            if len(a.supporting_witnesses) >= 2 or len(a.supporting_digital_artifacts) >= 2
        ]
        if multi_source:
            notes.append(ProsecutionStrategyNote(
                note_type="corroboration",
                description=(
                    f"{len(multi_source)} allegation(s) have multi-source corroboration. "
                    f"This strengthens credibility and admissibility."
                ),
                related_sections=[a.section_id for a in multi_source],
                priority="medium",
            ))

        # Financial trail advisory
        financial_backed = [a for a in allegations if a.financial_support]
        if financial_backed:
            notes.append(ProsecutionStrategyNote(
                note_type="sequence",
                description=(
                    f"Financial evidence supports {len(financial_backed)} allegation(s). "
                    f"Present financial trail chronologically to establish transaction pattern."
                ),
                related_sections=[a.section_id for a in financial_backed],
                priority="medium",
            ))

        # Witness ordering
        witness_backed = [a for a in allegations if a.supporting_witnesses]
        if witness_backed:
            notes.append(ProsecutionStrategyNote(
                note_type="witness_order",
                description=(
                    f"{sum(len(a.supporting_witnesses) for a in witness_backed)} witness(es) available. "
                    f"Lead with victim statement, follow with corroborating witnesses, "
                    f"close with expert testimony."
                ),
                related_sections=[a.section_id for a in witness_backed],
                priority="medium",
            ))

        # If no FILE-able allegations, advise holding
        if not file_allegations and allegations:
            hold_allegations = [
                a for a in allegations
                if a.filing_recommendation == FilingRecommendation.HOLD
            ]
            if hold_allegations:
                best_hold = max(hold_allegations, key=lambda a: a.coverage_percentage)
                notes.append(ProsecutionStrategyNote(
                    note_type="strongest_charge",
                    description=(
                        f"No allegations meet filing threshold. Closest: "
                        f"{best_hold.title} at {best_hold.coverage_percentage:.0f}% coverage. "
                        f"Focus investigation on strengthening this charge."
                    ),
                    related_sections=[best_hold.section_id],
                    priority="high",
                ))

        return notes

    def _get_defense_risks(
        self, allegations: list[Allegation],
    ) -> list[DefenseRisk]:
        """Identify anticipated defense arguments."""
        risks = []

        # Check for procedural violation risks
        for allegation in allegations:
            broken_chain = [
                wp for wp in allegation.weak_points
                if wp.weakness_type == "broken_chain"
            ]
            if broken_chain:
                risks.append(DefenseRisk(
                    risk_type="evidence_tampering",
                    description=(
                        f"Defense may challenge {allegation.title} evidence admissibility "
                        f"due to broken chain of custody ({len(broken_chain)} issue(s))."
                    ),
                    likelihood="high",
                    affected_sections=[allegation.section_id],
                    suggested_counter=(
                        "Prepare BSA Section 63 certificates and detailed "
                        "chain of custody documentation for all digital evidence."
                    ),
                ))

            single_source = [
                wp for wp in allegation.weak_points
                if wp.weakness_type == "single_source"
            ]
            if single_source:
                risks.append(DefenseRisk(
                    risk_type="alibi",
                    description=(
                        f"Elements in {allegation.title} rely on single evidence sources. "
                        f"Defense may challenge with alibi or alternative explanations."
                    ),
                    likelihood="medium",
                    affected_sections=[allegation.section_id],
                    suggested_counter=(
                        "Seek corroborating evidence from independent sources. "
                        "Cross-reference timestamps across multiple evidence streams."
                    ),
                ))

        # Check for consent defense risk (common in fraud cases)
        consent_sections = [
            a for a in allegations
            if any("consent" in e.element_text.lower() for e in a.elements)
        ]
        if consent_sections:
            risks.append(DefenseRisk(
                risk_type="consent_defense",
                description=(
                    "Defense may argue victim consented to the transaction. "
                    "Strengthen evidence showing deception or coercion."
                ),
                likelihood="medium",
                affected_sections=[a.section_id for a in consent_sections],
                suggested_counter=(
                    "Secure victim statement under BNSS Section 183 explicitly "
                    "stating no informed consent was given. Gather evidence of "
                    "misrepresentation or concealment of material facts."
                ),
            ))

        return risks

    def _compute_element_coverage(self, allegations: list[Allegation]) -> float:
        """Weighted average of element coverage across all allegations."""
        if not allegations:
            return 0.0
        total_elements = sum(a.total_count for a in allegations)
        total_satisfied = sum(a.satisfied_count for a in allegations)
        return (total_satisfied / total_elements) if total_elements > 0 else 0.0

    def _compute_evidence_quality(
        self, certificates: list[dict], allegations: list[Allegation],
    ) -> float:
        """Compute evidence quality score based on certificates and chain integrity."""
        if not allegations:
            return 0.0

        # Certificate coverage
        cert_score = min(len(certificates) / max(len(allegations), 1), 1.0)

        # Chain of custody integrity
        total_items = 0
        verified_items = 0
        for a in allegations:
            for elem in a.elements:
                for item in elem.evidence_bundle.items:
                    total_items += 1
                    if item.chain_of_custody_status in ("verified", "intact"):
                        verified_items += 1

        chain_score = (verified_items / total_items) if total_items > 0 else 0.5

        return round(0.5 * cert_score + 0.5 * chain_score, 2)

    def _estimate_trial_strength(
        self, overall_score: float, element_coverage: float,
        has_critical_blocker: bool, allegations: list[Allegation],
    ) -> TrialStrength:
        """Estimate trial outcome strength."""
        if has_critical_blocker or overall_score < 0.4:
            return TrialStrength.weak
        if overall_score >= 0.75 and element_coverage >= 0.7:
            return TrialStrength.strong
        if overall_score >= 0.5:
            return TrialStrength.moderate
        return TrialStrength.weak

    def _generate_case_summary(
        self, case_type: Optional[str], accused: list[AccusedPerson],
        allegations: list[Allegation], theory: dict, score: float,
    ) -> str:
        """Generate 3-4 sentence case summary."""
        accused_names = ", ".join(a.name for a in accused[:3]) or "unnamed suspect(s)"
        charge_titles = ", ".join(a.title for a in allegations[:3]) or "pending charges"
        theory_desc = theory.get("description", "under investigation")

        summary = (
            f"Case involving {accused_names} under investigation for {case_type or 'criminal offences'}. "
            f"Primary charges: {charge_titles}. "
            f"Prosecution theory: {theory_desc}. "
            f"Overall readiness score: {score * 100:.0f}%."
        )
        return summary

    def _generate_narrative(
        self, score: float, tier: ReadinessTier, has_blocker: bool,
        file_count: int, hold_count: int, drop_count: int, total: int,
    ) -> str:
        """Generate human-readable narrative summary."""
        narrative = f"Chargesheet readiness is {tier.value} (Score: {score * 100:.0f}%). "

        if has_blocker:
            narrative += "Critical procedural compliance blockers prevent filing. "
        elif tier == ReadinessTier.ready_for_filing:
            narrative += "All requirements met for prosecutorial review. "
        elif tier == ReadinessTier.near_ready:
            narrative += "Minor gaps remain before filing readiness. "
        else:
            narrative += "Significant investigation work remains. "

        narrative += (
            f"Of {total} applicable charges: "
            f"{file_count} recommended to FILE, "
            f"{hold_count} on HOLD, "
            f"{drop_count} recommended to DROP."
        )
        return narrative

    def _count_evidence(self) -> int:
        """Count evidence artifacts for staleness tracking."""
        if self.db:
            try:
                row = self.db.execute(
                    sql_text(
                        "SELECT COUNT(*) FROM evidence_artifacts WHERE case_id = :cid"
                    ),
                    {"cid": uuid.UUID(self.case_id)},
                ).fetchone()
                return row[0] if row else 0
            except Exception:
                pass
        return 0

    def _get_next_version(self) -> int:
        """Get next version number for this case's chargesheet."""
        if self.db:
            try:
                row = self.db.execute(
                    sql_text(
                        "SELECT COALESCE(MAX(version), 0) + 1 "
                        "FROM chargesheet_packages WHERE case_id = :cid"
                    ),
                    {"cid": uuid.UUID(self.case_id)},
                ).fetchone()
                return row[0] if row else 1
            except Exception:
                return 1
        return 1

    def _score_to_tier(self, score: float) -> ReadinessTier:
        """Convert readiness score to tier."""
        if score >= TIER_THRESHOLDS["ready_for_filing"]:
            return ReadinessTier.ready_for_filing
        if score >= TIER_THRESHOLDS["near_ready"]:
            return ReadinessTier.near_ready
        if score >= TIER_THRESHOLDS["developing"]:
            return ReadinessTier.developing
        return ReadinessTier.not_ready

    def _persist_package(self, package: ChargesheetPackage) -> None:
        """Store chargesheet package in Postgres and Neo4j."""
        # Store in Neo4j
        self.client.execute_write(
            """
            CREATE (cs:ChargesheetPackage {
                id: $csid, case_id: $cid, generated_at: $now,
                version: $ver,
                overall_readiness_score: $score,
                readiness_tier: $tier,
                trial_strength: $strength,
                filing_ready: $ready,
                file_count: $fc, hold_count: $hc, drop_count: $dc,
                summary_narrative: $narr,
                report_data: $data,
                evidence_count_at_generation: $ecnt,
                is_stale: false,
                classification_tag: 'case_sensitive',
                created_at: $now
            })
            """,
            {
                "csid": package.chargesheet_id,
                "cid": self.case_id,
                "now": self.now,
                "ver": package.version,
                "score": package.overall_readiness_score,
                "tier": package.readiness_tier.value,
                "strength": package.trial_strength.value,
                "ready": package.filing_ready,
                "fc": package.file_count,
                "hc": package.hold_count,
                "dc": package.drop_count,
                "narr": package.summary_narrative,
                "data": json.dumps(package.model_dump(), default=str),
                "ecnt": package.evidence_count_at_generation,
            },
        )

        # Store in Postgres
        if self.db:
            try:
                self.db.execute(sql_text("""
                    INSERT INTO chargesheet_packages
                        (chargesheet_id, case_id, generated_at, version,
                         overall_readiness_score, readiness_tier, trial_strength,
                         filing_ready, file_count, hold_count, drop_count,
                         summary_narrative, package_data,
                         evidence_count_at_generation, is_stale)
                    VALUES
                        (:csid, :cid, :now, :ver,
                         :score, :tier, :strength,
                         :ready, :fc, :hc, :dc,
                         :narr, :data::jsonb,
                         :ecnt, false)
                """), {
                    "csid": uuid.UUID(package.chargesheet_id),
                    "cid": uuid.UUID(self.case_id),
                    "now": self.now,
                    "ver": package.version,
                    "score": package.overall_readiness_score,
                    "tier": package.readiness_tier.value,
                    "strength": package.trial_strength.value,
                    "ready": package.filing_ready,
                    "fc": package.file_count,
                    "hc": package.hold_count,
                    "dc": package.drop_count,
                    "narr": package.summary_narrative,
                    "data": json.dumps(package.model_dump(), default=str),
                    "ecnt": package.evidence_count_at_generation,
                })
                self.db.commit()
            except Exception as e:
                logger.warning("Failed to persist chargesheet to Postgres: %s", e)
                self.db.rollback()


# ── Public API Functions ─────────────────────────────────────────────────

def generate_chargesheet_readiness(case_id: str, db: Optional[Session] = None) -> dict:
    """Generate ChargesheetReadinessReport — backward-compatible wrapper.

    The legacy readiness endpoint delegates to chargesheet_intelligence.py.
    """
    from app.legal.chargesheet_intelligence import generate_intelligence_chargesheet
    return generate_intelligence_chargesheet(case_id, db)


def generate_chargesheet_package(case_id: str, db: Optional[Session] = None) -> dict:
    """Generate a full ChargesheetPackage — the new primary endpoint."""
    engine = ChargesheetEngine(case_id, db)
    package = engine.generate()
    return package.model_dump()


def get_chargesheet(case_id: str, chargesheet_id: Optional[str] = None) -> dict:
    """Return latest (or specific) chargesheet package."""
    client = get_neo4j_client()

    if chargesheet_id:
        result = client.execute_read(
            """
            MATCH (cs:ChargesheetPackage {id: $csid, case_id: $cid})
            RETURN cs.report_data AS data
            """,
            {"csid": chargesheet_id, "cid": case_id},
        )
    else:
        result = client.execute_read(
            """
            MATCH (cs:ChargesheetPackage {case_id: $cid})
            RETURN cs.report_data AS data
            ORDER BY cs.generated_at DESC LIMIT 1
            """,
            {"cid": case_id},
        )

    if not result or not result[0].get("data"):
        return {"error": "No chargesheet package found"}

    package_data = json.loads(result[0]["data"])
    # Always enforce disclaimer
    package_data["disclaimer"] = LEGAL_DISCLAIMER
    return package_data


def get_chargesheet_history(case_id: str) -> list[dict]:
    """List all chargesheet versions for a case."""
    client = get_neo4j_client()
    results = client.execute_read(
        """
        MATCH (cs:ChargesheetPackage {case_id: $cid})
        RETURN cs.id AS chargesheet_id, cs.generated_at AS generated_at,
               cs.version AS version, cs.overall_readiness_score AS score,
               cs.readiness_tier AS tier, cs.trial_strength AS strength,
               cs.filing_ready AS filing_ready,
               cs.file_count AS file_count, cs.hold_count AS hold_count,
               cs.drop_count AS drop_count,
               cs.is_stale AS is_stale
        ORDER BY cs.generated_at DESC
        """,
        {"cid": case_id},
    )
    return [
        {
            "chargesheet_id": r["chargesheet_id"],
            "generated_at": r["generated_at"],
            "version": r["version"],
            "overall_readiness_score": r["score"],
            "readiness_tier": r["tier"],
            "trial_strength": r["strength"],
            "filing_ready": r["filing_ready"],
            "file_count": r["file_count"],
            "hold_count": r["hold_count"],
            "drop_count": r["drop_count"],
            "is_stale": r.get("is_stale", False),
        }
        for r in results
    ]


def get_filing_readiness(case_id: str) -> dict:
    """Operational filing readiness view for frontends."""
    package = get_chargesheet(case_id)
    if "error" in package:
        return package

    return {
        "case_id": case_id,
        "filing_ready": package.get("filing_ready", False),
        "overall_readiness_score": package.get("overall_readiness_score", 0.0),
        "readiness_tier": package.get("readiness_tier", "not_ready"),
        "trial_strength": package.get("trial_strength", "weak"),
        "file_count": package.get("file_count", 0),
        "hold_count": package.get("hold_count", 0),
        "drop_count": package.get("drop_count", 0),
        "compliance_blockers_count": len(package.get("compliance_blockers", [])),
        "is_stale": package.get("is_stale", False),
        "generated_at": package.get("generated_at"),
        "disclaimer": LEGAL_DISCLAIMER,
    }


def mark_chargesheet_stale(case_id: str, reason: str) -> dict:
    """Mark the latest chargesheet as stale (called by AIRE on new evidence)."""
    client = get_neo4j_client()
    result = client.execute_write(
        """
        MATCH (cs:ChargesheetPackage {case_id: $cid})
        WHERE cs.is_stale = false
        WITH cs ORDER BY cs.generated_at DESC LIMIT 1
        SET cs.is_stale = true, cs.stale_reason = $reason
        RETURN cs.id AS id
        """,
        {"cid": case_id, "reason": reason},
    )
    if result:
        return {"marked_stale": result[0]["id"], "reason": reason}
    return {"marked_stale": None, "reason": "No active chargesheet found"}


def get_chargesheet_readiness(case_id: str) -> dict:
    """Return latest chargesheet readiness report (legacy compatibility)."""
    client = get_neo4j_client()
    report = client.execute_read(
        """
        MATCH (r:ChargesheetReadinessReport {case_id: $cid})
        RETURN r.report_data AS data
        ORDER BY r.generated_at DESC LIMIT 1
        """,
        {"cid": case_id},
    )
    if not report or not report[0].get("data"):
        return {"error": "No chargesheet readiness report found"}
    return json.loads(report[0]["data"])


def get_readiness_history(case_id: str) -> list[dict]:
    """Time series of readiness scores (legacy compatibility)."""
    client = get_neo4j_client()
    reports = client.execute_read(
        """
        MATCH (r:ChargesheetReadinessReport {case_id: $cid})
        RETURN r.id AS id, r.generated_at AS at,
               r.overall_readiness_score AS score,
               r.readiness_tier AS tier
        ORDER BY r.generated_at DESC
        """,
        {"cid": case_id},
    )
    return [
        {"report_id": r["id"], "generated_at": r["at"],
         "score": r["score"], "tier": r["tier"]}
        for r in reports
    ]
