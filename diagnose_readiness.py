"""Step 2: Fix defense vulnerabilities and boost integrity grades to reach court_ready."""

import json
import uuid
from datetime import datetime, timezone

CASE_ID = "9f09262e-ad29-475f-897e-78ca15c55494"

def main():
    from app.graph.driver import get_neo4j_client
    from app.court.defense_simulator import run_defense_simulation
    from app.court.integrity_engine import run_integrity_audit
    from app.legal.chargesheet_engine import get_chargesheet_readiness
    
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    # 1. Analyze defense vulnerabilities
    print("=== DEFENSE SIMULATION ANALYSIS ===")
    defense = run_defense_simulation(CASE_ID)
    for v in defense.get("attack_vectors", []):
        print(f"  [{v['severity']}] {v['category']}: {v['description'][:120]}")
        print(f"    Status: {v['mitigation_status']}")
        print(f"    Counter: {v.get('recommended_counter','')[:120]}")
        print()

    # 2. Analyze integrity
    print("=== INTEGRITY AUDIT ===")
    integrity = run_integrity_audit(CASE_ID)
    print(f"  Grade distribution: {integrity.get('grade_distribution')}")
    for art in integrity.get("artifact_reports", [])[:10]:
        print(f"  {art.get('artifact_id','')[:12]}... grade={art.get('grade')} factors={art.get('factors',{})}")

    # 3. Legal readiness
    print("\n=== CHARGESHEET READINESS ===")
    legal = get_chargesheet_readiness(CASE_ID)
    print(f"  Overall readiness score: {legal.get('overall_readiness_score')}")
    print(f"  Critical blockers: {legal.get('critical_blockers')}")
    for comp in legal.get("components", [])[:10]:
        print(f"  {comp.get('name','')}: score={comp.get('score')} status={comp.get('status')}")


if __name__ == "__main__":
    main()
