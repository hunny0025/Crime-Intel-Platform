"""
inject_knowledge_graph.py  — Phase 2: Wire Relationships

All nodes were created in Phase 1. This script re-runs full injection
(MERGE-safe — nodes already exist) and wires ALL relationships using
valid types from app/graph/relationships.py.

Run:
    $env:PYTHONIOENCODING="utf-8"; python scripts/inject_knowledge_graph.py
"""

import sys
import json
import urllib.request
import urllib.error

BASE     = "http://localhost:8000"
CASE_ID  = "9f09262e-ad29-475f-897e-78ca15c55494"

# ── Fixed UUIDs ───────────────────────────────────────────────────────────────
# Persons
PRIYA_ID       = "a1000001-0000-0000-0000-000000000001"
ROHIT_ID       = "a1000002-0000-0000-0000-000000000002"
KAVYA_ID       = "a1000003-0000-0000-0000-000000000003"
DINESH_ID      = "a1000004-0000-0000-0000-000000000004"
ANANYA_ID      = "a1000005-0000-0000-0000-000000000005"
# Organizations
PROFITSURE_ORG_ID = "b1000001-0000-0000-0000-000000000001"
SEBI_ORG_ID       = "b1000002-0000-0000-0000-000000000002"
MULE_BANK_ID      = "b1000003-0000-0000-0000-000000000003"
# Devices
ROHIT_PHONE_ID    = "c1000001-0000-0000-0000-000000000001"
PRIYA_PHONE_ID    = "c1000002-0000-0000-0000-000000000002"
SCAM_SERVER_ID    = "c1000003-0000-0000-0000-000000000003"
VPN_NODE_ID       = "c1000004-0000-0000-0000-000000000004"
# Accounts
ROHIT_WA_ID       = "d1000001-0000-0000-0000-000000000001"
PROFITSURE_UPI_ID = "d1000002-0000-0000-0000-000000000002"
MULE_ACC1_ID      = "d1000003-0000-0000-0000-000000000003"
MULE_ACC2_ID      = "d1000004-0000-0000-0000-000000000004"
ROHIT_TELE_ID     = "d1000005-0000-0000-0000-000000000005"
PROFITSURE_SITE   = "d1000006-0000-0000-0000-000000000006"
PRIYA_UPI_ID      = "d1000007-0000-0000-0000-000000000007"
CRYPTO_WALLET_ID  = "d1000008-0000-0000-0000-000000000008"
# Locations
MUMBAI_LOC_ID     = "e1000001-0000-0000-0000-000000000001"
SERVER_LOC_ID     = "e1000002-0000-0000-0000-000000000002"
# Events
TXN1_ID           = "f1000001-0000-0000-0000-000000000001"
TXN2_ID           = "f1000002-0000-0000-0000-000000000002"
TXN3_ID           = "f1000003-0000-0000-0000-000000000003"
ARREST_EVENT_ID   = "f1000004-0000-0000-0000-000000000004"
DOMAIN_REG_ID     = "f1000005-0000-0000-0000-000000000005"
COMPLAINT_ID      = "f1000006-0000-0000-0000-000000000006"

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _post(path, body):
    url  = f"{BASE}{path}"
    data = json.dumps(body).encode()
    req  = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()), None
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        return None, f"{e.code}: {err[:300]}"
    except Exception as e:
        return None, str(e)

def _get(path):
    url = f"{BASE}{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  [GET ERROR] {path}: {e}")
        return None

# ── Node creation helpers (idempotent — server uses CREATE so may dupe on re-run) ──

def _node(endpoint, body, label, name):
    result, err = _post(f"/cases/{CASE_ID}/graph/{endpoint}", body)
    if result and "id" in result:
        print(f"  [OK]  {label:14s}  {name[:50]}")
    else:
        print(f"  [ERR] {label:14s}  {name[:50]}  -> {err}")
    return result

def person(node_id, display_name, role):
    return _node("person", {
        "id": node_id, "case_id": CASE_ID,
        "display_name": display_name, "role": role,
        "classification_tag": "case_sensitive"
    }, "Person", display_name)

def organization(node_id, name, org_type):
    return _node("organization", {
        "id": node_id, "case_id": CASE_ID,
        "name": name, "org_type": org_type,
        "classification_tag": "case_sensitive"
    }, "Organization", name)

def device(node_id, device_type, identifiers):
    return _node("device", {
        "id": node_id, "case_id": CASE_ID,
        "device_type": device_type, "identifiers": identifiers,
        "classification_tag": "case_sensitive"
    }, "Device", device_type)

def account(node_id, account_type, platform):
    return _node("account", {
        "id": node_id, "case_id": CASE_ID,
        "account_type": account_type, "platform": platform,
        "classification_tag": "case_sensitive"
    }, "Account", platform)

def location(node_id, location_type, address, coordinates=None):
    body = {
        "id": node_id, "case_id": CASE_ID,
        "location_type": location_type, "address": address,
        "classification_tag": "case_sensitive"
    }
    if coordinates:
        body["coordinates"] = coordinates
    return _node("location", body, "Location", address)

def event(node_id, event_type, valid_from, confidence=0.95):
    return _node("event", {
        "id": node_id, "case_id": CASE_ID,
        "event_type": event_type, "valid_from": valid_from,
        "confidence": confidence,
        "classification_tag": "case_sensitive"
    }, "Event", event_type)

# ── Relationship helper ───────────────────────────────────────────────────────

_rel_ok  = 0
_rel_err = 0

def rel(from_id, to_id, rel_type, confidence=0.9, label=""):
    global _rel_ok, _rel_err
    result, err = _post(f"/cases/{CASE_ID}/graph/relationships", {
        "from_node_id": from_id,
        "to_node_id": to_id,
        "relationship_type": rel_type,
        "confidence": confidence,
        "evidence_basis": []
    })
    short_from = from_id[:8]
    short_to   = to_id[:8]
    tag        = f"  [{label}]" if label else ""
    if result and "relationship_type" in result:
        _rel_ok += 1
        print(f"  [OK]  {rel_type:22s}  {short_from} -> {short_to}{tag}")
    else:
        _rel_err += 1
        print(f"  [ERR] {rel_type:22s}  {short_from} -> {short_to}  -> {err}")


# ─── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    sep = "=" * 70
    print(f"\n{sep}")
    print(f"  UPI FRAUD KNOWLEDGE GRAPH — Priya Sharma Case")
    print(f"  Case: {CASE_ID}")
    print(f"{sep}\n")

    # ── 1. NODES (idempotent — already created, skip duplication if server returns 500) ──
    print("[ PERSONS ]")
    person(PRIYA_ID,  "Priya Sharma",     "victim")
    person(ROHIT_ID,  "Rohit Verma",      "suspect")
    person(KAVYA_ID,  "Kavya Reddy",      "associate")
    person(DINESH_ID, "Dinesh Kulkarni",  "victim")
    person(ANANYA_ID, "Ananya Singh",     "witness")

    print("\n[ ORGANIZATIONS ]")
    organization(PROFITSURE_ORG_ID, "ProfitSure Pro Pvt Ltd (Shell)", "shell_company")
    organization(SEBI_ORG_ID,       "SEBI — Impersonated Regulator",  "regulatory_body")
    organization(MULE_BANK_ID,      "Axis Bank Mule Cluster",         "financial_institution")

    print("\n[ DEVICES ]")
    device(ROHIT_PHONE_ID, "smartphone",   ["IMEI:356938035643809", "+91-9876543210"])
    device(PRIYA_PHONE_ID, "smartphone",   ["IMEI:490154203237518", "+91-9823456789"])
    device(SCAM_SERVER_ID, "web_server",   ["IP:185.220.101.45", "profitsure-pro.com"])
    device(VPN_NODE_ID,    "vpn_node",     ["IP:45.142.212.100",  "PIA-Netherlands"])

    print("\n[ ACCOUNTS ]")
    account(ROHIT_WA_ID,       "social",    "WhatsApp +91-9876543210")
    account(PROFITSURE_UPI_ID, "financial", "UPI: profitsure@axisbank")
    account(MULE_ACC1_ID,      "financial", "Axis Bank A/C 919010056789012")
    account(MULE_ACC2_ID,      "financial", "Axis Bank A/C 919010098765432")
    account(ROHIT_TELE_ID,     "social",    "Telegram @ProfitSurePro_Official")
    account(PROFITSURE_SITE,   "web",       "profitsure-pro.com")
    account(PRIYA_UPI_ID,      "financial", "UPI: priya.sharma@hdfcbank")
    account(CRYPTO_WALLET_ID,  "crypto",    "USDT TRC20: TXkJdm7s9Y...")

    print("\n[ LOCATIONS ]")
    location(MUMBAI_LOC_ID, "address", "Andheri West, Mumbai MH-400053", "19.1360,72.8278")
    location(SERVER_LOC_ID, "address", "Hostinger APAC — Singapore DC",   "1.3521,103.8198")

    print("\n[ EVENTS ]")
    event(TXN1_ID,        "upi_transaction",     "2026-02-10T11:23:00Z", 0.99)
    event(TXN2_ID,        "upi_transaction",     "2026-02-15T14:07:00Z", 0.99)
    event(TXN3_ID,        "upi_transaction",     "2026-03-01T09:45:00Z", 0.99)
    event(DOMAIN_REG_ID,  "domain_registration", "2026-01-15T08:00:00Z", 0.92)
    event(COMPLAINT_ID,   "police_complaint",    "2026-03-10T16:30:00Z", 1.00)
    event(ARREST_EVENT_ID,"suspect_arrest",      "2026-04-05T10:15:00Z", 0.88)

    # ── 2. RELATIONSHIPS ────────────────────────────────────────────────────
    print(f"\n{sep}")
    print("  WIRING RELATIONSHIPS")
    print(f"{sep}")

    # Person CONTROLS accounts / devices / org
    print("\n  -- Ownership & Control --")
    rel(ROHIT_ID, ROHIT_WA_ID,          "CONTROLS",     0.95, "Rohit->WA")
    rel(ROHIT_ID, PROFITSURE_UPI_ID,    "CONTROLS",     0.95, "Rohit->UPI_sink")
    rel(ROHIT_ID, ROHIT_TELE_ID,        "CONTROLS",     0.90, "Rohit->Tele")
    rel(ROHIT_ID, PROFITSURE_SITE,      "CONTROLS",     0.90, "Rohit->Website")
    rel(ROHIT_ID, PROFITSURE_ORG_ID,    "CONTROLS",     0.92, "Rohit->Org")
    rel(PRIYA_ID, PRIYA_UPI_ID,         "CONTROLS",     1.00, "Priya->UPI")
    rel(KAVYA_ID, MULE_ACC1_ID,         "CONTROLS",     0.87, "Kavya->Mule1")
    rel(KAVYA_ID, MULE_ACC2_ID,         "CONTROLS",     0.83, "Kavya->Mule2")
    rel(KAVYA_ID, CRYPTO_WALLET_ID,     "CONTROLS",     0.75, "Kavya->Crypto")

    # OWNS — primary asset ownership
    print("\n  -- Asset Ownership --")
    rel(ROHIT_ID, ROHIT_PHONE_ID,       "OWNS",         0.95, "Rohit->Phone")
    rel(PRIYA_ID, PRIYA_PHONE_ID,       "OWNS",         1.00, "Priya->Phone")

    # OPERATES — person runs device/server
    print("\n  -- Operations --")
    rel(ROHIT_ID, SCAM_SERVER_ID,       "OPERATES",     0.85, "Rohit->Server")
    rel(ROHIT_ID, VPN_NODE_ID,          "OPERATES",     0.80, "Rohit->VPN")

    # MEMBER_OF / EMPLOYED_BY
    print("\n  -- Org Membership --")
    rel(KAVYA_ID,  PROFITSURE_ORG_ID,   "MEMBER_OF",    0.78, "Kavya->Org")
    rel(ANANYA_ID, MULE_BANK_ID,        "EMPLOYED_BY",  1.00, "Ananya->Bank")

    # IMPERSONATED
    print("\n  -- Impersonation --")
    rel(ROHIT_ID, SEBI_ORG_ID,          "IMPERSONATED", 0.97, "Rohit impersonates SEBI")

    # LOCATED_AT
    print("\n  -- Location Links --")
    rel(ROHIT_ID,          MUMBAI_LOC_ID,  "LOCATED_AT",   0.78, "Rohit location")
    rel(SCAM_SERVER_ID,    SERVER_LOC_ID,  "LOCATED_AT",   0.95, "Server->SG DC")
    rel(PROFITSURE_ORG_ID, SERVER_LOC_ID,  "LOCATED_AT",   0.85, "Org->SG DC")

    # LAST_KNOWN_AT
    rel(ROHIT_ID,  MUMBAI_LOC_ID,          "LAST_KNOWN_AT", 0.72, "Rohit last seen")

    # COMMUNICATED_WITH — peer-to-peer
    print("\n  -- Communications --")
    rel(ROHIT_ID, PRIYA_ID,              "COMMUNICATED_WITH", 0.99, "Rohit-Priya WA")
    rel(ROHIT_ID, DINESH_ID,             "COMMUNICATED_WITH", 0.80, "Rohit-Dinesh")

    # CONTACTED
    rel(ROHIT_WA_ID, PRIYA_ID,           "CONTACTED",    0.99, "WA->Priya")
    rel(ROHIT_WA_ID, DINESH_ID,          "CONTACTED",    0.80, "WA->Dinesh")
    rel(ROHIT_TELE_ID, PRIYA_ID,         "CONTACTED",    0.85, "Tele->Priya")

    # COMMUNICATED_VIA (person used channel)
    rel(ROHIT_ID, ROHIT_WA_ID,           "COMMUNICATED_VIA", 0.97, "Rohit via WA")
    rel(ROHIT_ID, ROHIT_TELE_ID,         "COMMUNICATED_VIA", 0.90, "Rohit via Tele")

    # Financial flow:  Priya UPI -> TXN -> ProfitSure UPI -> Mule -> Crypto
    print("\n  -- Financial Flow Chain --")
    rel(PRIYA_UPI_ID,       TXN1_ID,           "INITIATED",      0.99, "Priya pays TXN1")
    rel(PRIYA_UPI_ID,       TXN2_ID,           "INITIATED",      0.99, "Priya pays TXN2")
    rel(PRIYA_UPI_ID,       TXN3_ID,           "INITIATED",      0.99, "Priya pays TXN3")
    rel(TXN1_ID,            PROFITSURE_UPI_ID, "CREDITED_TO",    0.99, "TXN1->sink UPI")
    rel(TXN2_ID,            PROFITSURE_UPI_ID, "CREDITED_TO",    0.99, "TXN2->sink UPI")
    rel(TXN3_ID,            PROFITSURE_UPI_ID, "CREDITED_TO",    0.99, "TXN3->sink UPI")
    rel(PROFITSURE_UPI_ID,  MULE_ACC1_ID,      "TRANSFERRED_TO", 0.92, "UPI->Mule1")
    rel(PROFITSURE_UPI_ID,  MULE_ACC2_ID,      "TRANSFERRED_TO", 0.88, "UPI->Mule2")
    rel(MULE_ACC1_ID,       CRYPTO_WALLET_ID,  "TRANSFERRED_TO", 0.75, "Mule1->Crypto")
    rel(MULE_ACC2_ID,       CRYPTO_WALLET_ID,  "TRANSFERRED_TO", 0.71, "Mule2->Crypto")

    # DEFRAUDED_BY
    print("\n  -- Victim Links --")
    rel(PRIYA_ID,  ROHIT_ID,            "DEFRAUDED_BY",  0.99, "Priya victim")
    rel(DINESH_ID, ROHIT_ID,            "DEFRAUDED_BY",  0.84, "Dinesh victim")

    # Infrastructure
    print("\n  -- Infrastructure --")
    rel(SCAM_SERVER_ID, PROFITSURE_SITE, "HOSTS",        0.96, "Server hosts domain")
    rel(VPN_NODE_ID,    SCAM_SERVER_ID,  "TUNNELS_TO",   0.82, "VPN->Server")
    rel(ROHIT_PHONE_ID, VPN_NODE_ID,     "CONNECTED_TO", 0.79, "Phone->VPN")

    # Investigation Events
    print("\n  -- Investigation Events --")
    rel(PROFITSURE_SITE,   DOMAIN_REG_ID,   "REGISTERED_AT", 0.93, "Domain registration event")
    rel(PROFITSURE_ORG_ID, DOMAIN_REG_ID,   "PARTICIPATED_IN",0.88,"Org registered domain")
    rel(PRIYA_ID,          COMPLAINT_ID,    "FILED",          1.00, "Priya FIR")
    rel(ROHIT_ID,          ARREST_EVENT_ID, "SUBJECT_OF",     0.88, "Rohit arrested")
    rel(ANANYA_ID,         TXN1_ID,         "VERIFIED_BY",    0.95, "Bank verifies TXN1")
    rel(ANANYA_ID,         TXN2_ID,         "VERIFIED_BY",    0.95, "Bank verifies TXN2")
    rel(ANANYA_ID,         TXN3_ID,         "VERIFIED_BY",    0.95, "Bank verifies TXN3")

    # PARTICIPATED_IN (persons in events)
    print("\n  -- Participation --")
    rel(ROHIT_ID, TXN1_ID,              "PARTICIPATED_IN", 0.99, "Rohit TXN1")
    rel(ROHIT_ID, TXN2_ID,              "PARTICIPATED_IN", 0.99, "Rohit TXN2")
    rel(ROHIT_ID, TXN3_ID,              "PARTICIPATED_IN", 0.99, "Rohit TXN3")
    rel(PRIYA_ID, TXN1_ID,              "PARTICIPATED_IN", 0.99, "Priya TXN1")
    rel(PRIYA_ID, TXN2_ID,              "PARTICIPATED_IN", 0.99, "Priya TXN2")
    rel(PRIYA_ID, TXN3_ID,              "PARTICIPATED_IN", 0.99, "Priya TXN3")
    rel(KAVYA_ID, ARREST_EVENT_ID,      "PARTICIPATED_IN", 0.65, "Kavya mentioned in arrest")

    # INVOLVES (hypothesis/legal linking)
    print("\n  -- Involves --")
    rel(COMPLAINT_ID, ROHIT_ID,         "INVOLVES",     1.00, "Complaint->Suspect")
    rel(COMPLAINT_ID, PRIYA_ID,         "INVOLVES",     1.00, "Complaint->Victim")
    rel(ARREST_EVENT_ID, KAVYA_ID,      "INVOLVES",     0.60, "Arrest->Kavya")

    # RELATES_TO (general cross-links)
    print("\n  -- Relates_to cross-links --")
    rel(PROFITSURE_ORG_ID, PROFITSURE_UPI_ID, "RELATES_TO", 0.95, "Org->UPI")
    rel(PROFITSURE_ORG_ID, PROFITSURE_SITE,   "RELATES_TO", 0.95, "Org->Domain")

    # ── 3. VERIFY ──────────────────────────────────────────────────────────
    print(f"\n{sep}")
    print("  FINAL GRAPH SUMMARY")
    print(f"{sep}")

    summary = _get(f"/cases/{CASE_ID}/graph/summary")
    if summary:
        print("\nNode counts:")
        for label, count in sorted(summary.get("node_counts", {}).items()):
            print(f"  {label:36s}: {count}")
        print("\nRelationship counts:")
        for r, c in sorted(summary.get("relationship_counts", {}).items()):
            print(f"  {r:36s}: {c}")
    else:
        print("  [WARN] Could not retrieve summary.")

    print(f"\n  Relationships wired:  OK={_rel_ok}  ERR={_rel_err}")
    print(f"\n  >> Navigate to http://localhost:3000/graph to explore the graph.")
    print(f"{sep}\n")


if __name__ == "__main__":
    main()
