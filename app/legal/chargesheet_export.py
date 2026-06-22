"""Chargesheet Export Engine — structured text export for prosecutors.

Generates a human-readable, structured document from a ChargesheetPackage.
The output is suitable for printing, PDF generation, or prosecutorial review.

ADVISORY ONLY — all outputs require independent prosecutorial review.
"""

import logging
from datetime import datetime

from app.legal.chargesheet_models import (
    ChargesheetPackage, FilingRecommendation, LEGAL_DISCLAIMER,
)

logger = logging.getLogger(__name__)


def export_chargesheet_text(package_data: dict) -> str:
    """Export a chargesheet package as structured plain text.

    Args:
        package_data: Dictionary from ChargesheetPackage.model_dump()

    Returns:
        Formatted text suitable for prosecutorial review.
    """
    lines = []
    _add = lines.append

    # Header
    _add("=" * 80)
    _add("CHARGESHEET INTELLIGENCE REPORT")
    _add("=" * 80)
    _add("")
    _add(f"Case ID:          {package_data.get('case_id', 'N/A')}")
    _add(f"Generated:        {package_data.get('generated_at', 'N/A')}")
    _add(f"Version:          {package_data.get('version', 'N/A')}")
    _add(f"Case Type:        {package_data.get('case_type', 'N/A')}")
    _add("")

    # Disclaimer (mandatory)
    _add("-" * 80)
    _add("LEGAL DISCLAIMER")
    _add("-" * 80)
    _add(LEGAL_DISCLAIMER)
    _add("")

    # Filing Readiness Summary
    _add("-" * 80)
    _add("FILING READINESS SUMMARY")
    _add("-" * 80)
    score = package_data.get("overall_readiness_score", 0)
    _add(f"Overall Readiness Score:  {score * 100:.0f}%")
    _add(f"Readiness Tier:          {package_data.get('readiness_tier', 'not_ready')}")
    _add(f"Trial Strength:          {package_data.get('trial_strength', 'weak')}")
    _add(f"Filing Ready:            {'YES' if package_data.get('filing_ready') else 'NO'}")
    _add(f"Element Coverage:        {package_data.get('element_readiness_percentage', 0)}%")
    _add(f"Procedural Compliance:   {package_data.get('procedural_compliance_percentage', 0)}%")
    _add("")

    file_c = package_data.get("file_count", 0)
    hold_c = package_data.get("hold_count", 0)
    drop_c = package_data.get("drop_count", 0)
    _add(f"Charges to FILE: {file_c}  |  On HOLD: {hold_c}  |  To DROP: {drop_c}")
    _add("")

    if package_data.get("is_stale"):
        _add("*** WARNING: This chargesheet is STALE — new evidence has arrived ***")
        _add(f"    Reason: {package_data.get('stale_reason', 'New evidence ingested')}")
        _add("")

    # Case Summary
    _add("-" * 80)
    _add("CASE SUMMARY")
    _add("-" * 80)
    _add(package_data.get("case_summary", "No summary available."))
    _add("")

    # Accused Persons
    accused = package_data.get("accused_persons", [])
    if accused:
        _add("-" * 80)
        _add("ACCUSED PERSONS")
        _add("-" * 80)
        for i, acc in enumerate(accused, 1):
            _add(f"  {i}. {acc.get('name', 'Unknown')}")
            _add(f"     ID: {acc.get('person_id', 'N/A')}")
            _add(f"     Status: {acc.get('status', 'N/A')}")
        _add("")

    # Prosecution Theory
    theory = package_data.get("prosecution_theory", {})
    if theory.get("hypothesis_id"):
        _add("-" * 80)
        _add("PROSECUTION THEORY")
        _add("-" * 80)
        _add(f"  {theory.get('description', 'N/A')}")
        _add(f"  Probability: {theory.get('probability', 0):.0%}")
        _add("")

    # Allegations (charges)
    allegations = package_data.get("allegations", [])
    if allegations:
        _add("-" * 80)
        _add(f"CHARGES ({len(allegations)} APPLICABLE)")
        _add("-" * 80)

        for i, alleg in enumerate(allegations, 1):
            rec = alleg.get("filing_recommendation", "HOLD")
            _add(f"\n  [{rec}] {i}. {alleg.get('title', 'N/A')}")
            _add(f"     Section: {alleg.get('section_reference') or alleg.get('section_id')}")
            _add(f"     Statute: {alleg.get('statute', 'N/A')}")
            _add(f"     Coverage: {alleg.get('coverage_percentage', 0):.0f}% "
                 f"({alleg.get('satisfied_count', 0)}/{alleg.get('total_count', 0)} elements)")

            # Elements
            elements = alleg.get("elements", [])
            if elements:
                _add(f"     Elements:")
                for elem in elements:
                    status_icon = {"satisfied": "✓", "partially_satisfied": "◐", "unsatisfied": "✗"}
                    icon = status_icon.get(elem.get("status", ""), "?")
                    _add(f"       {icon} {elem.get('element_text', 'N/A')}")

            # Weak points
            weak = alleg.get("weak_points", [])
            if weak:
                _add(f"     Weak Points ({len(weak)}):")
                for wp in weak:
                    _add(f"       [{wp.get('severity', 'medium').upper()}] "
                         f"{wp.get('description', 'N/A')}")

            # Supporting evidence counts
            witnesses = alleg.get("supporting_witnesses", [])
            digital = alleg.get("supporting_digital_artifacts", [])
            docs = alleg.get("supporting_documents", [])
            forensic = alleg.get("supporting_forensic_reports", [])
            financial = alleg.get("financial_support", [])

            support_parts = []
            if witnesses:
                support_parts.append(f"{len(witnesses)} witness(es)")
            if digital:
                support_parts.append(f"{len(digital)} digital artifact(s)")
            if docs:
                support_parts.append(f"{len(docs)} document(s)")
            if forensic:
                support_parts.append(f"{len(forensic)} forensic report(s)")
            if financial:
                support_parts.append(f"{len(financial)} financial record(s)")
            if support_parts:
                _add(f"     Supporting Evidence: {', '.join(support_parts)}")

    # Compliance Blockers
    blockers = package_data.get("compliance_blockers", [])
    if blockers:
        _add("")
        _add("-" * 80)
        _add(f"COMPLIANCE BLOCKERS ({len(blockers)})")
        _add("-" * 80)
        for cb in blockers:
            _add(f"  [{cb.get('severity', 'medium').upper()}] {cb.get('title', 'N/A')}")
            _add(f"    Required by: {cb.get('required_by', 'N/A')}")
            _add(f"    Guidance: {cb.get('guidance', 'N/A')}")

    # Prosecution Strategy
    strategy = package_data.get("prosecution_strategy", [])
    if strategy:
        _add("")
        _add("-" * 80)
        _add("PROSECUTION STRATEGY (Advisory)")
        _add("-" * 80)
        for note in strategy:
            _add(f"  [{note.get('priority', 'medium').upper()}] "
                 f"{note.get('description', 'N/A')}")

    # Defense Risks
    risks = package_data.get("defense_risks", [])
    if risks:
        _add("")
        _add("-" * 80)
        _add("ANTICIPATED DEFENSE RISKS")
        _add("-" * 80)
        for risk in risks:
            _add(f"  [{risk.get('likelihood', 'medium').upper()}] "
                 f"{risk.get('risk_type', 'N/A')}: {risk.get('description', 'N/A')}")
            _add(f"    Counter: {risk.get('suggested_counter', 'N/A')}")

    # Integrity Certificates
    certs = package_data.get("integrity_certificates", [])
    if certs:
        _add("")
        _add("-" * 80)
        _add(f"EVIDENCE INTEGRITY CERTIFICATES ({len(certs)})")
        _add("-" * 80)
        for cert in certs:
            _add(f"  Certificate: {cert.get('certificate_id', 'N/A')}")
            _add(f"    Evidence: {cert.get('evidence_ref', 'N/A')}")
            _add(f"    Grade: {cert.get('integrity_grade', 'N/A')}")

    # Narrative
    _add("")
    _add("-" * 80)
    _add("SUMMARY NARRATIVE")
    _add("-" * 80)
    _add(package_data.get("summary_narrative", "No narrative available."))

    # Footer disclaimer
    _add("")
    _add("=" * 80)
    _add("END OF CHARGESHEET INTELLIGENCE REPORT")
    _add("=" * 80)
    _add("")
    _add(LEGAL_DISCLAIMER)
    _add("")

    return "\n".join(lines)
