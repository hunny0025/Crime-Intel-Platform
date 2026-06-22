"""Section 65B / Section 63 BSA 2023 compliance certificate generation engine."""

import uuid
from io import BytesIO
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.db.models import Case, EvidenceArtifact

def generate_65b_certificate_draft(case_id: str, artifact_id: str, investigator_name: str, db: Session) -> dict:
    """Generate structured content and wording for a Section 65B (BSA Section 63) certificate."""
    try:
        case_uuid = uuid.UUID(case_id)
        artifact_uuid = uuid.UUID(artifact_id)
    except ValueError:
        raise ValueError("Invalid case_id or artifact_id format")

    case = db.query(Case).filter(Case.case_id == case_uuid).first()
    if not case:
        raise ValueError("Case not found")

    artifact = db.query(EvidenceArtifact).filter(
        EvidenceArtifact.artifact_id == artifact_uuid,
        EvidenceArtifact.case_id == case_uuid
    ).first()
    if not artifact:
        raise ValueError("Evidence artifact not found")

    ts_str = artifact.collection_timestamp_utc.isoformat() if artifact.collection_timestamp_utc else "N/A"
    device_id = artifact.source_device_id or "Unknown Device"
    tool_name = artifact.source_tool or "Unknown Forensic Tool"
    acq_method = artifact.acquisition_method or "Forensic Extraction"
    content_hash = artifact.content_hash or "N/A"

    wording = (
        f"I, {investigator_name}, hereby certify that the electronic record/digital artifact "
        f"with ID {artifact_id} was extracted from the device with ID {device_id} using {tool_name}. "
        f"The extraction was completed on {ts_str} UTC using {acq_method}. "
        f"I declare that during the material period, the computer system and digital device from which "
        f"the electronic record was retrieved were operating properly and were under lawful control. "
        f"The cryptographic SHA-256 hash value of the electronic record is verified as: {content_hash}. "
        f"This certificate is generated under Section 63 of the Bharatiya Sakshya Adhiniyam, 2023 (BSA 2023), "
        f"validating electronic evidence admissibility."
    )

    return {
        "case_id": case_id,
        "artifact_id": artifact_id,
        "investigator_name": investigator_name,
        "wording": wording,
        "statute": "Bharatiya Sakshya Adhiniyam, 2023 Section 63 (formerly IEA Section 65B)",
        "hash_value": content_hash,
        "collection_timestamp": ts_str,
        "device_info": {
            "source_device_id": device_id,
            "acquisition_method": acq_method
        },
        "declarations": [
            "The electronic record was produced by the computer system during the period when it was used regularly.",
            "Throughout the material period, the computer system was operating properly.",
            "The information contained in the electronic record reproduces or is derived from information fed into the computer system in the ordinary course of activities."
        ]
    }

def generate_65b_pdf(draft: dict) -> bytes:
    """Generate a PDF document representing the Section 65B certificate draft."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    except ImportError:
        # Fallback if reportlab is not available
        buffer = BytesIO()
        buffer.write(f"SECTION 65B / SECTION 63 BSA 2023 COMPLIANCE CERTIFICATE DRAFT\n\n".encode('utf-8'))
        buffer.write(f"Case ID: {draft['case_id']}\n".encode('utf-8'))
        buffer.write(f"Artifact ID: {draft['artifact_id']}\n".encode('utf-8'))
        buffer.write(f"Investigator: {draft['investigator_name']}\n".encode('utf-8'))
        buffer.write(f"Statute: {draft['statute']}\n".encode('utf-8'))
        buffer.write(f"SHA-256 Hash: {draft['hash_value']}\n".encode('utf-8'))
        buffer.write(f"Timestamp: {draft['collection_timestamp']}\n".encode('utf-8'))
        buffer.write(f"Device ID: {draft['device_info']['source_device_id']}\n".encode('utf-8'))
        buffer.write(f"Acquisition Method: {draft['device_info']['acquisition_method']}\n\n".encode('utf-8'))
        buffer.write(f"Declarations:\n".encode('utf-8'))
        for d in draft['declarations']:
            buffer.write(f"- {d}\n".encode('utf-8'))
        buffer.write(f"\nWording:\n{draft['wording']}\n\n".encode('utf-8'))
        buffer.write(f"Signature: ___________________________\n".encode('utf-8'))
        buffer.write(f"Name: {draft['investigator_name']}\n".encode('utf-8'))
        return buffer.getvalue()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        alignment=1,  # Center
        spaceAfter=20
    )
    normal_style = styles['Normal']

    story.append(Paragraph("<b>CERTIFICATE UNDER SECTION 63 OF THE BHARATIYA SAKSHYA ADHINIYAM, 2023</b>", title_style))
    story.append(Paragraph("<b>(Statutory Certificate under old Section 65B of the Indian Evidence Act, 1872)</b>", styles['Heading3']))
    story.append(Spacer(1, 15))

    story.append(Paragraph(f"<b>Case ID:</b> {draft['case_id']}", normal_style))
    story.append(Paragraph(f"<b>Artifact ID:</b> {draft['artifact_id']}", normal_style))
    story.append(Paragraph(f"<b>Investigator:</b> {draft['investigator_name']}", normal_style))
    story.append(Paragraph(f"<b>Statute:</b> {draft['statute']}", normal_style))
    story.append(Paragraph(f"<b>SHA-256 Hash Value:</b> {draft['hash_value']}", normal_style))
    story.append(Paragraph(f"<b>Collection Timestamp:</b> {draft['collection_timestamp']}", normal_style))
    story.append(Paragraph(f"<b>Source Device ID:</b> {draft['device_info']['source_device_id']}", normal_style))
    story.append(Paragraph(f"<b>Acquisition Method:</b> {draft['device_info']['acquisition_method']}", normal_style))
    story.append(Spacer(1, 20))

    story.append(Paragraph("<b>Statutory Declarations:</b>", styles['Heading4']))
    for decl in draft['declarations']:
        story.append(Paragraph(f"- {decl}", normal_style))
        story.append(Spacer(1, 5))
    story.append(Spacer(1, 15))

    story.append(Paragraph("<b>Certificate Wording:</b>", styles['Heading4']))
    story.append(Paragraph(draft['wording'], normal_style))
    story.append(Spacer(1, 30))

    story.append(Paragraph("___________________________", normal_style))
    story.append(Paragraph("Signature of Certifying Officer", normal_style))
    story.append(Paragraph(f"Name: {draft['investigator_name']}", normal_style))
    story.append(Paragraph(f"Date: ________________________", normal_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
