"""Crime Simulation & Synthetic Dataset Generator.

Provides POST /cases/simulate which creates a complete, legally safe synthetic
investigation with pre-seeded Neo4j entities, Postgres artifacts, and chain-of-
custody records — without touching any real case data.

Supported scenario templates:
  financial_phishing    — Phishing domain, OTP bypass, ATM withdrawals, GPS logs
  insider_trading       — Employee chat leaks, broker account, exfiltration timestamp
  ransomware_extortion  — Tor exit IP, crypto wallet hops, victim email, ransom demand
"""

import hashlib
import io
import json
import random
import string
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Case, CaseStatus, ClassificationTag, EvidenceArtifact
from app.graph import crud as graph_crud
from app.storage.minio_client import get_minio_client

router = APIRouter(tags=["simulation"])


# ── Request / Response ───────────────────────────────────────────────────

class SimulationRequest(BaseModel):
    scenario: str                         # financial_phishing | insider_trading | ransomware_extortion
    suspects: int = 2                     # number of suspects (1–5)
    timeline_days: int = 14              # how many days the crime spans
    contradiction_density: str = "medium" # low | medium | high
    seed: int | None = None               # reproducibility seed


class SimulationResult(BaseModel):
    case_id: str
    scenario: str
    suspects_created: int
    artifacts_created: int
    events_created: int
    contradictions_planted: int
    summary_md: str
    download_url: str                     # endpoint to GET the mock evidence ZIP


# ── Helpers ──────────────────────────────────────────────────────────────

def _rng(seed: int | None) -> random.Random:
    return random.Random(seed)


def _fake_name(rng: random.Random) -> str:
    first = rng.choice(["Arjun", "Priya", "Vikram", "Neha", "Rahul",
                         "Sneha", "Amit", "Kavya", "Rohan", "Divya",
                         "Sanjay", "Meera", "Rajesh", "Pooja", "Arun"])
    last  = rng.choice(["Sharma", "Patel", "Kumar", "Reddy", "Singh",
                         "Gupta", "Joshi", "Nair", "Iyer", "Rao",
                         "Verma", "Shah", "Mehta", "Pillai", "Bhat"])
    return f"{first} {last}"


def _fake_phone(rng: random.Random) -> str:
    return "+91" + "".join(rng.choices(string.digits, k=10))


def _fake_email(rng: random.Random, name: str) -> str:
    domain = rng.choice(["gmail.com", "yahoo.com", "outlook.com",
                          "protonmail.com", "rediffmail.com"])
    slug = name.lower().replace(" ", ".") + str(rng.randint(10, 999))
    return f"{slug}@{domain}"


def _fake_ip(rng: random.Random) -> str:
    return ".".join(str(rng.randint(1, 254)) for _ in range(4))


def _fake_mac(rng: random.Random) -> str:
    return ":".join(f"{rng.randint(0, 255):02x}" for _ in range(6))


def _fake_wallet(rng: random.Random) -> str:
    return "1" + "".join(rng.choices(string.ascii_letters + string.digits, k=33))


def _fake_imei(rng: random.Random) -> str:
    return "".join(rng.choices(string.digits, k=15))


def _ts(base: datetime, delta_hours: float) -> str:
    return (base + timedelta(hours=delta_hours)).isoformat()


def _hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_artifact(
    db: Session,
    minio,
    case_id: uuid.UUID,
    content: bytes,
    source_tool: str,
    ts: datetime,
    classification: ClassificationTag = ClassificationTag.evidentiary,
) -> EvidenceArtifact:
    """Write a synthetic artifact to MinIO + Postgres, return the ORM object."""
    artifact_id = uuid.uuid4()
    content_pointer = f"{case_id}/{artifact_id}"
    content_hash = _hash(content)

    try:
        minio.upload_bytes(content_pointer, content)
    except Exception:
        pass  # MinIO unavailable — record metadata only

    artifact = EvidenceArtifact(
        artifact_id=artifact_id,
        case_id=case_id,
        source_tool=source_tool,
        source_device_id=None,
        collection_timestamp_utc=ts,
        original_timezone="UTC",
        content_hash=content_hash,
        previous_record_hash=None,
        record_hash=_hash(content_hash.encode()),
        content_pointer=content_pointer,
        classification_tag=classification,
        chain_of_custody_log=[
            {"actor": "SIM_ENGINE", "action": "created", "ts": ts.isoformat()}
        ],
    )
    db.add(artifact)
    return artifact


# ── Scenario: Financial Phishing ─────────────────────────────────────────

def _scenario_financial_phishing(
    case_id: str, case_uuid: uuid.UUID, suspects: int,
    timeline_days: int, contradiction_density: str, seed: int | None,
    db: Session,
) -> dict:
    rng = _rng(seed)
    base_time = datetime.now(timezone.utc) - timedelta(days=timeline_days)

    suspect_names = [_fake_name(rng) for _ in range(suspects)]
    victim_name = _fake_name(rng)
    phishing_domain = f"sbi-secure-{rng.randint(1000,9999)}.xyz"
    atm_location = rng.choice(["Connaught Place ATM, Delhi", "MG Road ATM, Bangalore",
                                "Marine Lines ATM, Mumbai", "Park Street ATM, Kolkata"])
    atm_lat, atm_lon = rng.uniform(12.0, 28.0), rng.uniform(72.0, 88.0)

    artifacts_raw = {}  # filename → bytes for ZIP

    # ── Graph nodes ──────────────────────────────────────────────────────
    person_ids = []
    for name in suspect_names:
        node = graph_crud.create_node("Person", {
            "case_id": case_id,
            "display_name": name,
            "role": "suspect",
            "classification_tag": "evidentiary",
        })
        person_ids.append(node["id"])

    victim_node = graph_crud.create_node("Person", {
        "case_id": case_id,
        "display_name": victim_name,
        "role": "victim",
        "classification_tag": "evidentiary",
    })

    # Phishing domain → Account node
    domain_node = graph_crud.create_node("Account", {
        "case_id": case_id,
        "account_type": "domain",
        "platform": "web",
        "value": phishing_domain,
        "classification_tag": "evidentiary",
    })

    # ATM location
    location_node = graph_crud.create_node("Location", {
        "case_id": case_id,
        "location_type": "atm",
        "address": atm_location,
        "coordinates": f"{atm_lat:.4f},{atm_lon:.4f}",
        "classification_tag": "evidentiary",
    })

    # Devices
    device_ids = []
    for i, name in enumerate(suspect_names):
        dev = graph_crud.create_node("Device", {
            "case_id": case_id,
            "device_type": "mobile",
            "identifiers": [_fake_imei(rng), _fake_mac(rng)],
            "classification_tag": "evidentiary",
        })
        device_ids.append(dev["id"])
        if person_ids:
            graph_crud.create_relationship(
                person_ids[i % len(person_ids)], dev["id"], "USES_DEVICE",
                properties={"confidence": 0.95, "evidence_basis": []}
            )

    # ── Events timeline ──────────────────────────────────────────────────
    events_created = 0

    # Event 1: Phishing domain registered
    ev1 = graph_crud.create_node("Event", {
        "case_id": case_id,
        "event_type": "domain_registration",
        "valid_from": _ts(base_time, 0),
        "valid_to": _ts(base_time, 0.5),
        "confidence": 0.98,
        "classification_tag": "evidentiary",
    })
    events_created += 1
    if person_ids:
        graph_crud.create_relationship(person_ids[0], ev1["id"], "PARTICIPATED_IN",
            properties={"confidence": 0.9, "evidence_basis": []})
    graph_crud.create_relationship(domain_node["id"], ev1["id"], "INVOLVED_IN",
        properties={"confidence": 1.0, "evidence_basis": []})

    # Event 2: Victim receives phishing SMS
    sms_content = (
        f"Dear Customer, Your SBI account is temporarily blocked. "
        f"Verify now: http://{phishing_domain}/verify?token="
        + "".join(rng.choices(string.ascii_lowercase + string.digits, k=16))
    )
    ev2 = graph_crud.create_node("Event", {
        "case_id": case_id,
        "event_type": "sms_phishing",
        "valid_from": _ts(base_time, 24),
        "valid_to": _ts(base_time, 24),
        "confidence": 0.99,
        "classification_tag": "evidentiary",
    })
    events_created += 1
    graph_crud.create_relationship(victim_node["id"], ev2["id"], "PARTICIPATED_IN",
        properties={"confidence": 1.0, "evidence_basis": []})

    # Event 3: OTP entered on phishing site
    ev3 = graph_crud.create_node("Event", {
        "case_id": case_id,
        "event_type": "credential_compromise",
        "valid_from": _ts(base_time, 24.5),
        "valid_to": _ts(base_time, 25),
        "confidence": 0.95,
        "classification_tag": "evidentiary",
    })
    events_created += 1

    # Event 4: ATM withdrawal
    amount = rng.randint(20000, 200000)
    ev4 = graph_crud.create_node("Event", {
        "case_id": case_id,
        "event_type": "cash_withdrawal",
        "valid_from": _ts(base_time, timeline_days * 24 - 6),
        "valid_to": _ts(base_time, timeline_days * 24 - 5.5),
        "confidence": 0.97,
        "classification_tag": "evidentiary",
        "amount_inr": amount,
    })
    events_created += 1
    if person_ids:
        graph_crud.create_relationship(person_ids[0], ev4["id"], "PARTICIPATED_IN",
            properties={"confidence": 0.88, "evidence_basis": []})
    graph_crud.create_relationship(location_node["id"], ev4["id"], "AT",
        properties={"confidence": 1.0, "evidence_basis": []})

    # COMMUNICATED_WITH between suspects
    if len(person_ids) >= 2:
        graph_crud.create_relationship(person_ids[0], person_ids[1], "COMMUNICATED_WITH",
            properties={"confidence": 0.85, "valid_from": _ts(base_time, 12),
                        "valid_to": _ts(base_time, 13), "evidence_basis": []})

    # ── Contradictions (planted) ─────────────────────────────────────────
    contradictions_planted = 0
    if contradiction_density in ("medium", "high"):
        # GPS contradiction: suspect at two places simultaneously
        contra_loc = rng.choice(["Chandni Chowk, Delhi", "Bandra West, Mumbai"])
        c1 = graph_crud.create_node("Contradiction", {
            "case_id": case_id,
            "contradiction_type": "co_location_conflict",
            "severity": "high",
            "description": (
                f"{suspect_names[0]} is recorded at {atm_location} and "
                f"{contra_loc} within the same 15-minute window."
            ),
            "details": "GPS logs conflict with CCTV placement.",
        })
        contradictions_planted += 1

    if contradiction_density == "high":
        c2 = graph_crud.create_node("Contradiction", {
            "case_id": case_id,
            "contradiction_type": "timeline_gap",
            "severity": "medium",
            "description": "Phishing domain WHOIS shows registration 3 days AFTER first victim SMS was sent.",
            "details": "Server-side timestamp anomaly — possible log tampering.",
        })
        contradictions_planted += 1

    # ── Artifacts ────────────────────────────────────────────────────────
    try:
        minio = get_minio_client()
    except Exception:
        minio = None

    now = datetime.now(timezone.utc)
    artifact_count = 0

    # SMS log CSV
    sms_csv = "timestamp,from,to,content\n"
    sms_csv += f"{_ts(base_time, 24)},{_fake_phone(rng)},{_fake_phone(rng)},{sms_content}\n"
    for i in range(5):
        sms_csv += (
            f"{_ts(base_time, rng.uniform(20, 100))},"
            f"{_fake_phone(rng)},{_fake_phone(rng)},"
            f"Normal message {i}\n"
        )
    sms_bytes = sms_csv.encode()
    artifacts_raw["sms_log.csv"] = sms_bytes
    if minio:
        _write_artifact(db, minio, case_uuid, sms_bytes, "raw_csv_sim", now)
    artifact_count += 1

    # Browser history JSON (victim's phone)
    browser_history = [
        {"timestamp": _ts(base_time, 24.3), "url": f"http://{phishing_domain}/verify",
         "title": "Secure Verification", "device": "victim_phone"},
        {"timestamp": _ts(base_time, 20), "url": "https://www.sbi.co.in", "title": "SBI Home", "device": "victim_phone"},
    ]
    browser_bytes = json.dumps(browser_history, indent=2).encode()
    artifacts_raw["browser_history.json"] = browser_bytes
    if minio:
        _write_artifact(db, minio, case_uuid, browser_bytes, "raw_json_sim", now)
    artifact_count += 1

    # GPS log
    gps_entries = []
    for h in range(0, timeline_days * 24, 6):
        gps_entries.append({
            "timestamp": _ts(base_time, h),
            "lat": f"{atm_lat + rng.uniform(-0.01, 0.01):.6f}",
            "lon": f"{atm_lon + rng.uniform(-0.01, 0.01):.6f}",
            "device_imei": _fake_imei(rng),
            "accuracy_m": rng.randint(5, 50),
        })
    gps_bytes = json.dumps(gps_entries, indent=2).encode()
    artifacts_raw["gps_log.json"] = gps_bytes
    if minio:
        _write_artifact(db, minio, case_uuid, gps_bytes, "raw_json_sim", now)
    artifact_count += 1

    # ATM transaction CSV
    atm_csv = "timestamp,location,amount_inr,account_last4,status\n"
    atm_csv += f"{_ts(base_time, timeline_days * 24 - 6)},{atm_location},{amount},{rng.randint(1000,9999)},SUCCESS\n"
    atm_bytes = atm_csv.encode()
    artifacts_raw["atm_transactions.csv"] = atm_bytes
    if minio:
        _write_artifact(db, minio, case_uuid, atm_bytes, "raw_csv_sim", now)
    artifact_count += 1

    db.commit()

    summary_md = f"""## 🎭 Simulation: Financial Phishing
- **Suspects**: {', '.join(suspect_names)}
- **Victim**: {victim_name}
- **Phishing Domain**: `{phishing_domain}`
- **ATM Location**: {atm_location}
- **Withdrawal Amount**: ₹{amount:,}
- **Timeline**: {timeline_days} days
- **Events**: {events_created} | **Artifacts**: {artifact_count} | **Contradictions**: {contradictions_planted}

### Investigation Leads
1. Trace domain registrant via WHOIS
2. Match ATM CCTV with suspect GPS coordinates
3. Subpoena SMS gateway provider for sender IP
4. Verify co-location contradiction for {suspect_names[0]}
"""

    return {
        "suspects_created": suspects,
        "artifacts_created": artifact_count,
        "events_created": events_created,
        "contradictions_planted": contradictions_planted,
        "summary_md": summary_md,
        "zip_files": artifacts_raw,
    }


# ── Scenario: Insider Trading ─────────────────────────────────────────────

def _scenario_insider_trading(
    case_id: str, case_uuid: uuid.UUID, suspects: int,
    timeline_days: int, contradiction_density: str, seed: int | None,
    db: Session,
) -> dict:
    rng = _rng(seed)
    base_time = datetime.now(timezone.utc) - timedelta(days=timeline_days)

    suspect_names = [_fake_name(rng) for _ in range(max(suspects, 2))]
    company = rng.choice(["Reliance Industries", "Infosys Ltd", "HDFC Bank", "TCS", "Wipro"])
    insider_name = suspect_names[0]
    broker_name = suspect_names[1]
    stock_gain = rng.randint(500000, 5000000)

    artifacts_raw = {}
    try:
        minio = get_minio_client()
    except Exception:
        minio = None

    now = datetime.now(timezone.utc)
    events_created = 0
    artifact_count = 0
    contradictions_planted = 0

    # People
    person_ids = []
    for name in suspect_names:
        node = graph_crud.create_node("Person", {
            "case_id": case_id,
            "display_name": name,
            "role": "suspect",
            "classification_tag": "evidentiary",
        })
        person_ids.append(node["id"])

    # Org node
    company_node = graph_crud.create_node("Organization", {
        "case_id": case_id,
        "org_type": "listed_company",
        "name": company,
        "classification_tag": "evidentiary",
    })
    graph_crud.create_relationship(person_ids[0], company_node["id"], "EMPLOYED_BY",
        properties={"confidence": 1.0, "evidence_basis": []})

    # Broker account
    broker_acc = graph_crud.create_node("Account", {
        "case_id": case_id,
        "account_type": "demat",
        "platform": "zerodha",
        "value": f"ZR{rng.randint(100000,999999)}",
        "classification_tag": "evidentiary",
    })
    graph_crud.create_relationship(person_ids[1], broker_acc["id"], "OWNS",
        properties={"confidence": 0.95, "evidence_basis": []})

    # Events
    ev1 = graph_crud.create_node("Event", {
        "case_id": case_id,
        "event_type": "confidential_info_access",
        "valid_from": _ts(base_time, 0),
        "valid_to": _ts(base_time, 1),
        "confidence": 0.97,
        "classification_tag": "evidentiary",
    })
    events_created += 1
    graph_crud.create_relationship(person_ids[0], ev1["id"], "PARTICIPATED_IN",
        properties={"confidence": 0.97, "evidence_basis": []})

    ev2 = graph_crud.create_node("Event", {
        "case_id": case_id,
        "event_type": "encrypted_chat_tip",
        "valid_from": _ts(base_time, 2),
        "valid_to": _ts(base_time, 2.5),
        "confidence": 0.88,
        "classification_tag": "evidentiary",
    })
    events_created += 1
    graph_crud.create_relationship(person_ids[0], person_ids[1], "COMMUNICATED_WITH",
        properties={"confidence": 0.88, "valid_from": _ts(base_time, 2), "valid_to": _ts(base_time, 2.5), "evidence_basis": []})

    ev3 = graph_crud.create_node("Event", {
        "case_id": case_id,
        "event_type": "bulk_stock_purchase",
        "valid_from": _ts(base_time, 5),
        "valid_to": _ts(base_time, 5),
        "confidence": 1.0,
        "classification_tag": "evidentiary",
        "amount_inr": stock_gain,
    })
    events_created += 1
    graph_crud.create_relationship(person_ids[1], ev3["id"], "PARTICIPATED_IN",
        properties={"confidence": 1.0, "evidence_basis": []})

    ev4 = graph_crud.create_node("Event", {
        "case_id": case_id,
        "event_type": "stock_sale_profit",
        "valid_from": _ts(base_time, timeline_days * 24 - 24),
        "valid_to": _ts(base_time, timeline_days * 24 - 20),
        "confidence": 1.0,
        "classification_tag": "evidentiary",
    })
    events_created += 1

    if contradiction_density in ("medium", "high"):
        c1 = graph_crud.create_node("Contradiction", {
            "case_id": case_id,
            "contradiction_type": "alibi_conflict",
            "severity": "high",
            "description": f"{insider_name} claims to have been on leave on the day of confidential data access. HR records show otherwise.",
            "details": "VPN access logs contradict leave request approval.",
        })
        contradictions_planted += 1

    # Artifacts: Chat export, trade records
    chat_json = [
        {"ts": _ts(base_time, 2.1), "sender": insider_name, "msg": f"Result announcement next week. Big surprise. Buy now."},
        {"ts": _ts(base_time, 2.2), "sender": broker_name, "msg": "How much time do I have?"},
        {"ts": _ts(base_time, 2.3), "sender": insider_name, "msg": "48 hours. Delete this."},
    ]
    chat_bytes = json.dumps(chat_json, indent=2).encode()
    artifacts_raw["signal_chat_export.json"] = chat_bytes
    if minio:
        _write_artifact(db, minio, case_uuid, chat_bytes, "raw_json_sim", now)
    artifact_count += 1

    trade_csv = "timestamp,scrip,qty,price,order_type,account\n"
    trade_csv += f"{_ts(base_time, 5)},{company.split()[0]},5000,{rng.randint(1000,4000)},BUY,{broker_acc.get('value','ZR000000')}\n"
    trade_csv += f"{_ts(base_time, timeline_days*24-24)},{company.split()[0]},5000,{rng.randint(2000,8000)},SELL,{broker_acc.get('value','ZR000000')}\n"
    trade_bytes = trade_csv.encode()
    artifacts_raw["demat_trade_records.csv"] = trade_bytes
    if minio:
        _write_artifact(db, minio, case_uuid, trade_bytes, "raw_csv_sim", now)
    artifact_count += 1

    db.commit()

    summary_md = f"""## 🏦 Simulation: Insider Trading
- **Insider**: {insider_name} (employee at {company})
- **Broker Contact**: {broker_name}
- **Estimated Gain**: ₹{stock_gain:,}
- **Timeline**: {timeline_days} days
- **Events**: {events_created} | **Artifacts**: {artifact_count} | **Contradictions**: {contradictions_planted}

### Investigation Leads
1. Obtain SEBI trade order records for demat account
2. Subpoena Signal/WhatsApp encrypted chat data
3. Pull VPN/access logs from company IT department
4. Correlate information-access timestamp with trade execution
"""

    return {
        "suspects_created": suspects,
        "artifacts_created": artifact_count,
        "events_created": events_created,
        "contradictions_planted": contradictions_planted,
        "summary_md": summary_md,
        "zip_files": artifacts_raw,
    }


# ── Scenario: Ransomware Extortion ────────────────────────────────────────

def _scenario_ransomware_extortion(
    case_id: str, case_uuid: uuid.UUID, suspects: int,
    timeline_days: int, contradiction_density: str, seed: int | None,
    db: Session,
) -> dict:
    rng = _rng(seed)
    base_time = datetime.now(timezone.utc) - timedelta(days=timeline_days)

    suspect_names = [_fake_name(rng) for _ in range(suspects)]
    victim_org = rng.choice(["City Hospital", "State Power Grid", "Municipal Corporation",
                              "District Court Servers", "University IT Infrastructure"])
    tor_ip = f"10.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(1,254)}"
    wallet = _fake_wallet(rng)
    ransom_btc = round(rng.uniform(0.5, 5.0), 4)
    ransom_inr = int(ransom_btc * 6500000)

    artifacts_raw = {}
    try:
        minio = get_minio_client()
    except Exception:
        minio = None

    now = datetime.now(timezone.utc)
    events_created = 0
    artifact_count = 0
    contradictions_planted = 0

    # Suspect nodes
    person_ids = []
    for name in suspect_names:
        node = graph_crud.create_node("Person", {
            "case_id": case_id,
            "display_name": name,
            "role": "suspect",
            "classification_tag": "evidentiary",
        })
        person_ids.append(node["id"])

    # C2 server device
    c2_device = graph_crud.create_node("Device", {
        "case_id": case_id,
        "device_type": "server",
        "identifiers": [tor_ip],
        "classification_tag": "evidentiary",
    })

    # Crypto wallet account
    wallet_acc = graph_crud.create_node("Account", {
        "case_id": case_id,
        "account_type": "crypto_wallet",
        "platform": "bitcoin",
        "value": wallet,
        "classification_tag": "evidentiary",
    })
    if person_ids:
        graph_crud.create_relationship(person_ids[0], wallet_acc["id"], "OWNS",
            properties={"confidence": 0.78, "evidence_basis": []})

    # Events
    ev1 = graph_crud.create_node("Event", {
        "case_id": case_id,
        "event_type": "initial_access_phishing",
        "valid_from": _ts(base_time, 0),
        "valid_to": _ts(base_time, 1),
        "confidence": 0.91,
        "classification_tag": "evidentiary",
    })
    events_created += 1

    ev2 = graph_crud.create_node("Event", {
        "case_id": case_id,
        "event_type": "lateral_movement",
        "valid_from": _ts(base_time, 24),
        "valid_to": _ts(base_time, 72),
        "confidence": 0.85,
        "classification_tag": "evidentiary",
    })
    events_created += 1

    ev3 = graph_crud.create_node("Event", {
        "case_id": case_id,
        "event_type": "data_exfiltration",
        "valid_from": _ts(base_time, 72),
        "valid_to": _ts(base_time, 96),
        "confidence": 0.93,
        "classification_tag": "evidentiary",
    })
    events_created += 1

    ev4 = graph_crud.create_node("Event", {
        "case_id": case_id,
        "event_type": "ransomware_deployment",
        "valid_from": _ts(base_time, 96),
        "valid_to": _ts(base_time, 97),
        "confidence": 1.0,
        "classification_tag": "evidentiary",
    })
    events_created += 1

    ev5 = graph_crud.create_node("Event", {
        "case_id": case_id,
        "event_type": "ransom_demand_email",
        "valid_from": _ts(base_time, 97),
        "valid_to": _ts(base_time, 97.5),
        "confidence": 1.0,
        "classification_tag": "evidentiary",
    })
    events_created += 1

    ev6 = graph_crud.create_node("Event", {
        "case_id": case_id,
        "event_type": "crypto_transaction",
        "valid_from": _ts(base_time, timeline_days * 24 - 12),
        "valid_to": _ts(base_time, timeline_days * 24 - 12),
        "confidence": 1.0,
        "classification_tag": "evidentiary",
        "btc_amount": ransom_btc,
    })
    events_created += 1
    graph_crud.create_relationship(wallet_acc["id"], ev6["id"], "INVOLVED_IN",
        properties={"confidence": 1.0, "evidence_basis": []})

    if contradiction_density in ("medium", "high"):
        c1 = graph_crud.create_node("Contradiction", {
            "case_id": case_id,
            "contradiction_type": "timestamp_forgery",
            "severity": "high",
            "description": "Ransomware binary compilation timestamp is 6 months in the future — metadata manipulation likely.",
            "details": "PE header timestamp vs file system creation time conflict.",
        })
        contradictions_planted += 1

    if contradiction_density == "high":
        c2 = graph_crud.create_node("Contradiction", {
            "case_id": case_id,
            "contradiction_type": "wallet_attribution_conflict",
            "severity": "medium",
            "description": f"Wallet {wallet[:20]}... attributed to two separate TOR exit nodes in different countries simultaneously.",
            "details": "Blockchain timestamp cross-reference required.",
        })
        contradictions_planted += 1

    # Artifacts
    ransom_note = f"""YOUR FILES HAVE BEEN ENCRYPTED

All data at {victim_org} has been encrypted with military-grade AES-256.

To recover your files, you must pay {ransom_btc} BTC to:
  Wallet: {wallet}

You have 72 hours. After that, we will publish all exfiltrated data publicly.

Contact us only via TOR: http://{tor_ip}/contact
"""
    note_bytes = ransom_note.encode()
    artifacts_raw["ransom_note.txt"] = note_bytes
    if minio:
        _write_artifact(db, minio, case_uuid, note_bytes, "raw_txt_sim", now)
    artifact_count += 1

    network_log = "timestamp,src_ip,dst_ip,dst_port,bytes,protocol\n"
    for h in range(0, 96, 4):
        network_log += (
            f"{_ts(base_time, h)},{_fake_ip(rng)},{tor_ip},"
            f"{rng.choice([443, 80, 8443, 4444])},{rng.randint(100,50000)},TCP\n"
        )
    net_bytes = network_log.encode()
    artifacts_raw["network_connection_log.csv"] = net_bytes
    if minio:
        _write_artifact(db, minio, case_uuid, net_bytes, "raw_csv_sim", now)
    artifact_count += 1

    blockchain_trace = [
        {"txid": "".join(rng.choices(string.hexdigits, k=64)),
         "from": _fake_wallet(rng), "to": wallet,
         "amount_btc": ransom_btc,
         "timestamp": _ts(base_time, timeline_days * 24 - 12),
         "confirmations": rng.randint(3, 100)},
    ]
    bc_bytes = json.dumps(blockchain_trace, indent=2).encode()
    artifacts_raw["blockchain_trace.json"] = bc_bytes
    if minio:
        _write_artifact(db, minio, case_uuid, bc_bytes, "raw_json_sim", now)
    artifact_count += 1

    db.commit()

    summary_md = f"""## 💻 Simulation: Ransomware Extortion
- **Target Organisation**: {victim_org}
- **Suspects**: {', '.join(suspect_names)}
- **C2 Server**: `{tor_ip}` (TOR exit node)
- **Wallet**: `{wallet}`
- **Ransom Demanded**: {ransom_btc} BTC (≈ ₹{ransom_inr:,})
- **Timeline**: {timeline_days} days
- **Events**: {events_created} | **Artifacts**: {artifact_count} | **Contradictions**: {contradictions_planted}

### Investigation Leads
1. Deanonymise TOR exit node via timing correlation
2. Trace wallet hops via blockchain analysis
3. Submit malware binary to CERT-In for attribution
4. Recover encrypted files for decryption key cross-reference
"""

    return {
        "suspects_created": suspects,
        "artifacts_created": artifact_count,
        "events_created": events_created,
        "contradictions_planted": contradictions_planted,
        "summary_md": summary_md,
        "zip_files": artifacts_raw,
    }


# ── Scenario Dispatcher ───────────────────────────────────────────────────

_SCENARIOS = {
    "financial_phishing": _scenario_financial_phishing,
    "insider_trading": _scenario_insider_trading,
    "ransomware_extortion": _scenario_ransomware_extortion,
}


# ── Simulation ZIP store (in-memory cache, keyed by case_id) ─────────────

_zip_cache: dict[str, bytes] = {}


def _build_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("/cases/simulate", response_model=SimulationResult, status_code=201)
def simulate_case(body: SimulationRequest, db: Session = Depends(get_db)):
    """
    Generate a complete synthetic investigation case.
    Creates a new Case in Postgres, populates Neo4j with suspects/events/
    relationships/contradictions, writes synthetic evidence artifacts, and
    returns a download URL for the mock evidence ZIP.
    """
    scenario_fn = _SCENARIOS.get(body.scenario)
    if scenario_fn is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scenario '{body.scenario}'. "
                   f"Valid options: {sorted(_SCENARIOS.keys())}",
        )

    suspects = max(1, min(body.suspects, 5))
    timeline_days = max(1, min(body.timeline_days, 90))
    if body.contradiction_density not in ("low", "medium", "high"):
        raise HTTPException(status_code=400, detail="contradiction_density must be low|medium|high")

    # Create the Case
    case_uuid = uuid.uuid4()
    case = Case(
        case_id=case_uuid,
        case_type=f"SIM_{body.scenario.upper()}",
        status=CaseStatus.under_investigation,
        classification_tag=ClassificationTag.evidentiary,
        created_by="SIM_ENGINE",
    )
    db.add(case)
    db.flush()  # ensure case exists before foreign key writes

    case_id = str(case_uuid)

    # Run the scenario generator
    result = scenario_fn(
        case_id=case_id,
        case_uuid=case_uuid,
        suspects=suspects,
        timeline_days=timeline_days,
        contradiction_density=body.contradiction_density,
        seed=body.seed,
        db=db,
    )

    # Cache the ZIP for download
    zip_bytes = _build_zip(result["zip_files"])
    _zip_cache[case_id] = zip_bytes

    return SimulationResult(
        case_id=case_id,
        scenario=body.scenario,
        suspects_created=result["suspects_created"],
        artifacts_created=result["artifacts_created"],
        events_created=result["events_created"],
        contradictions_planted=result["contradictions_planted"],
        summary_md=result["summary_md"],
        download_url=f"/cases/{case_id}/simulate/download",
    )


@router.get("/cases/{case_id}/simulate/download")
def download_simulation_zip(case_id: str):
    """Download the mock evidence ZIP for a simulated case."""
    zip_bytes = _zip_cache.get(case_id)
    if not zip_bytes:
        raise HTTPException(
            status_code=404,
            detail="Simulation ZIP not found. Re-run simulate to regenerate.",
        )
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=simulation_{case_id[:8]}.zip"},
    )


@router.get("/simulation/scenarios")
def list_scenarios():
    """Return available simulation scenario templates."""
    return {
        "scenarios": [
            {
                "id": "financial_phishing",
                "name": "Financial Phishing",
                "description": (
                    "Suspects register a spoofed banking domain, harvest victim OTP via SMS phishing, "
                    "and withdraw funds at an ATM. Generates: SMS logs, browser history, GPS tracks, ATM records."
                ),
                "icon": "💳",
                "difficulty": "beginner",
                "evidence_types": ["sms_log", "browser_history", "gps_log", "atm_transactions"],
            },
            {
                "id": "insider_trading",
                "name": "Insider Trading",
                "description": (
                    "A corporate employee tips off a broker contact about an upcoming announcement. "
                    "Generates: encrypted chat export, demat trade records, VPN access logs."
                ),
                "icon": "📈",
                "difficulty": "intermediate",
                "evidence_types": ["chat_export", "trade_records", "vpn_logs"],
            },
            {
                "id": "ransomware_extortion",
                "name": "Ransomware Extortion",
                "description": (
                    "Threat actor deploys ransomware against a critical-infrastructure target via a phishing "
                    "email, exfiltrates data through TOR, and demands Bitcoin ransom. "
                    "Generates: ransom note, network logs, blockchain trace."
                ),
                "icon": "🔐",
                "difficulty": "advanced",
                "evidence_types": ["ransom_note", "network_logs", "blockchain_trace"],
            },
        ]
    }
