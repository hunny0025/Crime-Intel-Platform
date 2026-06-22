import uuid
import pytest
from app.db.models import Case, ActionType, ActionStatus, MemoryRecordType, InvestigationAction

def test_copilot_execute_tool_record_action(client, created_case, db_session):
    case_id = created_case["case_id"]

    # 1. Propose/Execute record_investigative_action
    response = client.post(
        f"/cases/{case_id}/copilot/execute-tool",
        json={
            "tool": "record_investigative_action",
            "parameters": {
                "action_type": "review_contradiction",
                "target_ref": "contradiction-node-id-123",
                "priority_score": 0.95
            }
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "created"
    action_id = data["id"]

    # 2. Check Postgres table
    action = db_session.query(InvestigationAction).filter(
        InvestigationAction.action_id == uuid.UUID(action_id)
    ).first()
    assert action is not None
    assert action.action_type == ActionType.review_contradiction
    assert action.target_ref == "contradiction-node-id-123"
    assert action.priority_score == 0.95
    assert action.status == ActionStatus.pending

    # 3. Check action queue endpoint
    queue_resp = client.get(f"/cases/{case_id}/action-queue", params={"status": "pending"})
    assert queue_resp.status_code == 200
    queue_data = queue_resp.json()
    assert any(act["action_id"] == action_id for act in queue_data)


def test_copilot_execute_tool_add_note(client, created_case, db_session):
    case_id = created_case["case_id"]

    # 1. Add note
    response = client.post(
        f"/cases/{case_id}/copilot/execute-tool",
        json={
            "tool": "add_case_diary_note",
            "parameters": {
                "record_type": "decision_made",
                "description": "Custom strategy decision made via copilot.",
                "actor": "detective_holmes",
                "reasoning": "Suspect transaction pattern matches shell company timeline."
            }
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "created"
    record_id = data["id"]

    # 2. Check case diary reconstruction
    diary_resp = client.get(f"/cases/{case_id}/diary")
    assert diary_resp.status_code == 200
    diary_data = diary_resp.json()
    found = False
    for rec in diary_data["diary"]:
        if rec["record_id"] == record_id:
            found = True
            assert rec["record_type"] == "decision_made"
            assert rec["actor"] == "detective_holmes"
            assert rec["description"] == "Custom strategy decision made via copilot."
            break
    assert found is True


def test_copilot_strategy_brief(client, created_case):
    case_id = created_case["case_id"]

    # Retrieve strategy brief
    strategy_resp = client.get(f"/cases/{case_id}/strategy")
    assert strategy_resp.status_code == 200
    strategy_data = strategy_resp.json()

    assert "active_hypotheses" in strategy_data
    assert "key_contradictions" in strategy_data
    assert "critical_gaps" in strategy_data
    assert "recommendations" in strategy_data
    assert len(strategy_data["recommendations"]) == 3
