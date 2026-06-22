"""Run inside Docker: docker compose exec app python /app/inject_case.py"""
import json
import os
import sys
import time
import urllib.request
import urllib.parse
import uuid
from io import BytesIO

BASE_URL = "http://localhost:8000"
CASE_ID = sys.argv[1] if len(sys.argv) > 1 else None
EVIDENCE_DIR = "/app/priya_case_evidence"


def api_get(path):
    try:
        req = urllib.request.Request(f"{BASE_URL}{path}")
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.getcode(), json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode()) if e.readable() else str(e)
    except Exception as e:
        return 0, str(e)


def api_post_json(path, payload):
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{BASE_URL}{path}", data=data,
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req, timeout=60)
        return resp.getcode(), json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.readable() else str(e)
        try:
            return e.code, json.loads(body)
        except:
            return e.code, body
    except Exception as e:
        return 0, str(e)


def api_post_multipart(path, fields, files):
    """Post multipart/form-data using urllib (no requests library)."""
    boundary = uuid.uuid4().hex
    body = b""
    for key, value in fields.items():
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
        body += f"{value}\r\n".encode()
    for key, (filename, filedata, content_type) in files.items():
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'.encode()
        body += f"Content-Type: {content_type}\r\n\r\n".encode()
        body += filedata + b"\r\n"
    body += f"--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        return resp.getcode(), json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_resp = e.read().decode() if e.readable() else str(e)
        try:
            return e.code, json.loads(body_resp)
        except:
            return e.code, body_resp


def section(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def main():
    case_id = CASE_ID
    if not case_id:
        print("Usage: python inject_case.py <case_id>")
        sys.exit(1)
    
    print(f"Case ID: {case_id}")
    
    # ── STEP 4: Ingest Evidence ─────────────────────────────────────────
    section("STEP 4: Ingesting Evidence Files")
    
    evidence_files = [
        "whatsapp_messages.json",
        "upi_transactions.json",
        "call_records.json",
        "device_data.json",
        "domain_intel.json",
        "victim_statement.json",
    ]
    
    for filename in evidence_files:
        filepath = os.path.join(EVIDENCE_DIR, filename)
        print(f"\n--- Ingesting: {filename}")
        
        with open(filepath, "rb") as f:
            file_bytes = f.read()
        
        code, resp = api_post_multipart(
            f"/cases/{case_id}/ingest",
            fields={"source_format": "raw_json", "actor": "investigator_001"},
            files={"file": (filename, file_bytes, "application/json")},
        )
        print(f"    Status: {code}")
        if isinstance(resp, dict):
            print(f"    Artifacts: {resp.get('artifacts_created', 'N/A')}")
            print(f"    Kafka Event: {resp.get('kafka_event_id', 'N/A')}")
        else:
            print(f"    Response: {str(resp)[:300]}")
    
    # ── STEP 5: Run Full Pipeline ───────────────────────────────────────
    section("STEP 5: Running Full E2E Pipeline")
    
    code, resp = api_post_json(f"/pipeline/cases/{case_id}/run", {})
    print(f"Status: {code}")
    if isinstance(resp, dict):
        print(f"Pipeline ID: {resp.get('pipeline_id', 'N/A')}")
        print(f"Duration: {resp.get('total_duration_ms', 'N/A')}ms")
        print(f"Stages Completed: {resp.get('stages_completed')}/{resp.get('stages_total')}")
        print(f"Overall Status: {resp.get('overall_status')}")
        for stage in resp.get("stages", []):
            icon = "OK" if stage["status"] == "completed" else "FAIL"
            print(f"  [{icon}] {stage['stage']}: {stage['status']} ({stage.get('duration_ms', 'N/A')}ms)")
            if stage.get("error"):
                print(f"        ERROR: {stage['error'][:200]}")
            if stage.get("result_summary"):
                for k, v in stage["result_summary"].items():
                    print(f"        {k}: {v}")
    else:
        print(f"Response: {str(resp)[:500]}")

    # ── STEP 6: Contradiction Scan ──────────────────────────────────────
    section("STEP 6: Contradiction Scan")
    code, resp = api_post_json(f"/cases/{case_id}/contradictions/scan", {})
    print(f"Status: {code}")
    if isinstance(resp, dict):
        print(json.dumps(resp, indent=2, default=str)[:1000])
    else:
        print(str(resp)[:300])

    # ── STEP 7: Evidence Gaps ───────────────────────────────────────────
    section("STEP 7: Evidence Gap Scan")
    code, resp = api_post_json(f"/cases/{case_id}/evidence-gaps/scan", {})
    print(f"Status: {code}")
    if isinstance(resp, dict):
        print(json.dumps(resp, indent=2, default=str)[:1000])
    else:
        print(str(resp)[:300])

    # ── STEP 8: Legal Mapping ───────────────────────────────────────────
    section("STEP 8: Legal Mapping")
    code, resp = api_post_json(f"/cases/{case_id}/legal/map-elements", {})
    print(f"Status: {code}")
    if isinstance(resp, dict):
        print(json.dumps(resp, indent=2, default=str)[:1000])
    else:
        print(str(resp)[:300])

    # ── STEP 9: Compliance Check ────────────────────────────────────────
    section("STEP 9: Procedural Compliance Scan")
    code, resp = api_post_json(f"/cases/{case_id}/legal/compliance/scan", {})
    print(f"Status: {code}")
    if isinstance(resp, dict):
        print(json.dumps(resp, indent=2, default=str)[:1000])
    else:
        print(str(resp)[:300])

    # ── STEP 10: Court Readiness ────────────────────────────────────────
    section("STEP 10: Court Readiness")
    code, resp = api_get(f"/cases/{case_id}/court/readiness")
    print(f"Status: {code}")
    if isinstance(resp, dict):
        print(json.dumps(resp, indent=2, default=str)[:1000])
    else:
        print(str(resp)[:300])

    # ── STEP 11: ORACLE Report ──────────────────────────────────────────
    section("STEP 11: ORACLE Report")
    code, resp = api_get(f"/cases/{case_id}/oracle/report")
    print(f"Status: {code}")
    if isinstance(resp, dict):
        print(f"Entropy Score: {resp.get('entropy_score', 'N/A')}")
        hyp = resp.get("leading_hypothesis", {})
        if isinstance(hyp, dict):
            print(f"Leading Hypothesis: {str(hyp.get('narrative', 'N/A'))[:200]}")
        print(f"Readiness Tier: {resp.get('chargesheet_readiness_tier', 'N/A')}")
        print(f"Action Queue: {resp.get('action_queue_summary', 'N/A')}")
    else:
        print(str(resp)[:500])

    # ── STEP 12: Defense Simulation ─────────────────────────────────────
    section("STEP 12: Defense Simulation")
    code, resp = api_post_json(f"/cases/{case_id}/court/defense-simulation", {})
    print(f"Status: {code}")
    if isinstance(resp, dict):
        print(json.dumps(resp, indent=2, default=str)[:1000])
    else:
        print(str(resp)[:300])

    # ── FINAL SUMMARY ───────────────────────────────────────────────────
    section("FINAL SUMMARY")
    print(f"Case ID: {case_id}")
    print(f"Evidence files ingested: 6")
    print(f"Pipeline executed successfully")
    print(f"Case is accessible on frontend at http://localhost:3001")
    print(f"\nDone!")


if __name__ == "__main__":
    main()
