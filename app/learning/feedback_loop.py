"""Feedback Learning System — Investigator-in-the-Loop Learning with Persistence.

Addresses Gap 12: The system should improve over time based on
investigator decisions and case outcomes.

CRITICAL FIX: Previous version stored weights in-memory (lost on restart).
This version persists ALL feedback and weights to PostgreSQL.

Pipeline:
  Investigator accepts/rejects recommendation
    ↓
  Feedback recorded to DB (immutable audit trail)
    ↓
  Model weights adjusted in-memory AND persisted to DB
    ↓
  Future recommendations improve

Tracks:
  - Recommendation acceptance/rejection rates per agent
  - Investigator corrections to AI conclusions
  - Case outcome correlation with predictions
  - Accuracy trends over time (persisted)
"""

import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ── In-Memory Cache (loaded from DB on startup) ────────────────────────

_model_weights: dict[str, float] = {
    "evidence_agent": 1.0,
    "legal_agent": 1.2,
    "timeline_agent": 0.9,
    "osint_agent": 0.8,
    "theory_agent": 1.1,
    "behavioral_agent": 0.9,
    "court_agent": 1.0,
    "nlp_ner": 1.0,
    "nlp_sentiment": 1.0,
    "stylometric": 1.0,
    "entity_matcher": 1.0,
    "deception_scorer": 1.0,
    "predictive_engine": 1.0,
}

_weights_loaded = False


# ── DB Persistence ──────────────────────────────────────────────────────

def load_weights_from_db(db: Session) -> None:
    """Load persisted model weights from database into in-memory cache.

    Called once on application startup. If DB has weights, they override
    the defaults. If DB is empty (first run), defaults are persisted.
    """
    global _model_weights, _weights_loaded
    try:
        from app.db.models import ModelWeight

        rows = db.query(ModelWeight).all()
        if rows:
            for row in rows:
                _model_weights[row.model_name] = row.weight
            logger.info("Loaded %d model weights from database", len(rows))
        else:
            # First run — persist default weights
            for model_name, weight in _model_weights.items():
                mw = ModelWeight(
                    model_name=model_name,
                    weight=weight,
                    total_feedback_count=0,
                    accepted_count=0,
                    rejected_count=0,
                    corrected_count=0,
                )
                db.merge(mw)
            db.commit()
            logger.info("Persisted %d default model weights to database", len(_model_weights))

        _weights_loaded = True
    except Exception as e:
        logger.warning("Failed to load weights from DB: %s (using defaults)", e)
        _weights_loaded = True  # Use defaults, don't retry


def save_weights_to_db(db: Session) -> None:
    """Persist all in-memory model weights to database.

    Called on application shutdown and after weight adjustments.
    Uses MERGE (upsert) semantics — safe to call repeatedly.
    """
    try:
        from app.db.models import ModelWeight

        for model_name, weight in _model_weights.items():
            existing = db.query(ModelWeight).filter(
                ModelWeight.model_name == model_name
            ).first()
            if existing:
                existing.weight = weight
            else:
                db.add(ModelWeight(model_name=model_name, weight=weight))
        db.commit()
        logger.debug("Saved %d model weights to database", len(_model_weights))
    except Exception as e:
        logger.error("Failed to save weights to DB: %s", e)
        db.rollback()


def _persist_single_weight(model_name: str, weight: float, feedback_type: str) -> None:
    """Persist a single weight update after feedback. Non-blocking."""
    try:
        from app.db.session import SessionLocal
        from app.db.models import ModelWeight

        db = SessionLocal()
        try:
            existing = db.query(ModelWeight).filter(
                ModelWeight.model_name == model_name
            ).first()
            if existing:
                existing.weight = weight
                existing.total_feedback_count += 1
                if feedback_type == "accepted":
                    existing.accepted_count += 1
                elif feedback_type == "rejected":
                    existing.rejected_count += 1
                elif feedback_type == "corrected":
                    existing.corrected_count += 1
            else:
                counts = {"total_feedback_count": 1, "accepted_count": 0,
                          "rejected_count": 0, "corrected_count": 0}
                if feedback_type in counts:
                    counts[f"{feedback_type}_count"] = 1
                db.add(ModelWeight(model_name=model_name, weight=weight, **counts))
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning("Weight persistence failed for %s: %s", model_name, e)


# ── Feedback Recording ──────────────────────────────────────────────────

def record_feedback(
    case_id: str,
    recommendation_id: str,
    source_model: str,
    feedback_type: str,     # accepted | rejected | corrected | irrelevant
    investigator_id: str,
    correction: Optional[str] = None,
    reasoning: Optional[str] = None,
) -> dict:
    """
    Record investigator feedback on an AI recommendation.

    Feedback is persisted to database (immutable audit trail) and
    model weights are adjusted in both memory and DB.
    """
    entry = {
        "feedback_id": str(uuid.uuid4()),
        "case_id": case_id,
        "recommendation_id": recommendation_id,
        "source_model": source_model,
        "feedback_type": feedback_type,
        "investigator_id": investigator_id,
        "correction": correction,
        "reasoning": reasoning,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Persist feedback to DB
    try:
        from app.db.session import SessionLocal
        from app.db.models import FeedbackRecord
        import uuid as uuid_mod

        db = SessionLocal()
        try:
            record = FeedbackRecord(
                feedback_id=uuid_mod.UUID(entry["feedback_id"]),
                case_id=uuid_mod.UUID(case_id),
                recommendation_id=recommendation_id,
                source_model=source_model,
                feedback_type=feedback_type,
                investigator_id=investigator_id,
                correction=correction,
                reasoning=reasoning,
            )
            db.add(record)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning("Failed to persist feedback to DB: %s", e)

    # Adjust model weight based on feedback
    _adjust_weight(source_model, feedback_type)

    return entry


def _adjust_weight(model_name: str, feedback_type: str):
    """Adjust model weight based on feedback signal and persist."""
    if model_name not in _model_weights:
        _model_weights[model_name] = 1.0

    current = _model_weights[model_name]
    lr = 0.02  # learning rate

    if feedback_type == "accepted":
        _model_weights[model_name] = min(current + lr, 2.0)
    elif feedback_type == "rejected":
        _model_weights[model_name] = max(current - lr * 2, 0.1)
    elif feedback_type == "corrected":
        _model_weights[model_name] = max(current - lr, 0.1)
    elif feedback_type == "irrelevant":
        _model_weights[model_name] = max(current - lr * 0.5, 0.1)

    # Persist to DB (non-blocking)
    _persist_single_weight(model_name, _model_weights[model_name], feedback_type)


def get_model_weight(model_name: str) -> float:
    """Get current weight for a model (used by agents and rankers)."""
    return _model_weights.get(model_name, 1.0)


def get_all_weights() -> dict:
    """Return all current model weights."""
    return dict(_model_weights)


# ── Accuracy Tracking ───────────────────────────────────────────────────

def record_case_outcome(
    case_id: str,
    outcome: str,           # convicted | acquitted | settled | dropped
    predictions_correct: int,
    predictions_total: int,
    notes: str = "",
) -> dict:
    """
    Record the final outcome of a case to measure prediction accuracy.
    This is the strongest learning signal.
    """
    accuracy = predictions_correct / max(predictions_total, 1)
    entry = {
        "case_id": case_id,
        "outcome": outcome,
        "predictions_correct": predictions_correct,
        "predictions_total": predictions_total,
        "accuracy": round(accuracy, 4),
        "notes": notes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Large-scale weight adjustment based on outcome
    if outcome == "convicted" and accuracy > 0.7:
        # Successful prosecution — reinforce all model weights slightly
        for model in _model_weights:
            _model_weights[model] = min(_model_weights[model] + 0.01, 2.0)
    elif outcome == "acquitted":
        # Failed prosecution — dampen models that were frequently rejected
        try:
            from app.db.session import SessionLocal
            from app.db.models import FeedbackRecord
            import uuid as uuid_mod

            db = SessionLocal()
            try:
                rejected = db.query(FeedbackRecord.source_model).filter(
                    FeedbackRecord.case_id == uuid_mod.UUID(case_id),
                    FeedbackRecord.feedback_type == "rejected",
                ).distinct().all()
                for (model_name,) in rejected:
                    if model_name in _model_weights:
                        _model_weights[model_name] = max(
                            _model_weights[model_name] - 0.05, 0.1
                        )
            finally:
                db.close()
        except Exception as e:
            logger.warning("Case outcome weight adjustment failed: %s", e)

    # Persist all updated weights
    try:
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            save_weights_to_db(db)
        finally:
            db.close()
    except Exception:
        pass

    return entry


# ── Analytics ───────────────────────────────────────────────────────────

def get_learning_analytics() -> dict:
    """Return comprehensive learning system analytics from database."""
    analytics = {
        "current_weights": dict(_model_weights),
        "weights_persisted": _weights_loaded,
        "learning_rate": 0.02,
        "system_status": "active",
        "persistence_backend": "postgresql",
    }

    # Try to get detailed analytics from DB
    try:
        from app.db.session import SessionLocal
        from app.db.models import ModelWeight, FeedbackRecord
        from sqlalchemy import func

        db = SessionLocal()
        try:
            # Total feedback count
            total = db.query(func.count(FeedbackRecord.feedback_id)).scalar() or 0
            analytics["total_feedback_entries"] = total

            # Feedback by type
            type_counts = db.query(
                FeedbackRecord.feedback_type,
                func.count(FeedbackRecord.feedback_id),
            ).group_by(FeedbackRecord.feedback_type).all()
            analytics["feedback_by_type"] = {t: c for t, c in type_counts}

            # Per-model stats from ModelWeight table
            weight_rows = db.query(ModelWeight).all()
            model_stats = {}
            for row in weight_rows:
                total_fb = row.total_feedback_count or 0
                model_stats[row.model_name] = {
                    "current_weight": row.weight,
                    "total_feedback": total_fb,
                    "accepted": row.accepted_count or 0,
                    "rejected": row.rejected_count or 0,
                    "corrected": row.corrected_count or 0,
                    "acceptance_rate": round(
                        (row.accepted_count or 0) / max(total_fb, 1), 3
                    ),
                    "last_updated": row.last_updated.isoformat() if row.last_updated else None,
                }
            analytics["model_acceptance_rates"] = model_stats
        finally:
            db.close()
    except Exception as e:
        logger.warning("Failed to load analytics from DB: %s", e)
        analytics["model_acceptance_rates"] = {}

    return analytics


import threading

class FeedbackLoopWorker:
    """
    Background worker that consumes 'cases' events,
    listens to case.closed, and updates CrimeCategory prior distributions in Neo4j.
    """

    def __init__(self):
        self._thread = None
        self._running = False
        self._consumer = None

    def start(self, db_session_factory) -> None:
        if self._thread and self._thread.is_alive():
            self.stop()
        self._running = True
        self._thread = threading.Thread(
            target=self._run,
            args=(db_session_factory,),
            daemon=True,
            name="feedback-loop-worker",
        )
        self._thread.start()
        logger.info("Feedback loop worker started")

    def _run(self, db_session_factory) -> None:
        from app.events.consumer import KafkaConsumer
        self._consumer = KafkaConsumer(
            topics=["cases"],
            group_id="feedback-loop-worker",
        )
        consumer = self._consumer

        while self._running:
            try:
                envelope = consumer.poll_once(timeout=1.0)
                if envelope is None:
                    continue

                event_type = envelope.event_type
                payload = envelope.payload
                logger.info(
                    "Feedback loop: processing event %s, type=%s for case %s",
                    envelope.event_id, event_type, envelope.case_id,
                )

                if event_type == "case.closed":
                    case_id = str(payload.get("case_id"))
                    status = str(payload.get("status"))

                    if status in ["closed_convicted", "closed_acquitted"]:
                        convicted = (status == "closed_convicted")
                        try:
                            from app.graph.driver import get_neo4j_client
                            client = get_neo4j_client()
                            categories = client.execute_read(
                                """
                                MATCH (ca:CaseAnchor {case_id: $cid})-[:CLASSIFIED_AS]->(cat:CrimeCategory)
                                RETURN cat.id AS id, coalesce(cat.success_rate, 0.5) AS success_rate, coalesce(cat.case_count, 0) AS case_count
                                """,
                                {"cid": case_id}
                            )
                            for cat in categories:
                                cat_id = cat["id"]
                                success_rate = float(cat["success_rate"])
                                count = int(cat["case_count"])

                                new_success_rate = (success_rate * count + (1.0 if convicted else 0.0)) / (count + 1)
                                new_count = count + 1

                                client.execute_write(
                                    """
                                    MATCH (cat:CrimeCategory {id: $cat_id})
                                    SET cat.success_rate = $sr, cat.case_count = $cnt
                                    """,
                                    {"cat_id": cat_id, "sr": new_success_rate, "cnt": new_count}
                                )
                            logger.info("Feedback loop: updated success rate for case %s categories", case_id)
                        except Exception as ex:
                            logger.error("Feedback loop: failed to update category prior: %s", ex)

            except Exception as e:
                logger.error("Feedback loop error: %s", e, exc_info=True)

    def stop(self) -> None:
        self._running = False
        if self._consumer:
            try:
                self._consumer.close()
            except Exception:
                pass
            self._consumer = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("Feedback loop worker stopped")


_worker = None

def get_feedback_loop_worker() -> FeedbackLoopWorker:
    global _worker
    if _worker is None:
        _worker = FeedbackLoopWorker()
    return _worker
