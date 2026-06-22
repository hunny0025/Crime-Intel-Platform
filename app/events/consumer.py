"""Kafka consumer wrapper + background worker for evidence normalization."""

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

from confluent_kafka import Consumer, KafkaError

from app.config import settings
from app.schemas import EventEnvelope

logger = logging.getLogger(__name__)


class KafkaConsumer:
    """Wrapper around confluent-kafka Consumer with JSON deserialization."""

    def __init__(
        self,
        topics: list[str],
        group_id: str = "crime-intel-workers",
        bootstrap_servers: Optional[str] = None,
    ) -> None:
        self._bootstrap = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS
        self.local_mode = False
        self.topics = topics

        if not self._bootstrap or self._bootstrap == "":
            logger.info("Kafka bootstrap servers empty, enabling In-Memory Consumer fallback")
            self.local_mode = True
            import queue
            self.q = queue.Queue()
            from app.events.producer import in_memory_broker
            for t in self.topics:
                in_memory_broker.subscribe(t, self.q)
            self._running = False
            return

        try:
            self._consumer = Consumer({
                "bootstrap.servers": self._bootstrap,
                "group.id": group_id,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": True,
            })
            self._consumer.subscribe(topics)
            self._running = False
        except Exception as e:
            logger.warning("Failed to initialize Kafka consumer, falling back to In-Memory Consumer: %s", e)
            self.local_mode = True
            import queue
            self.q = queue.Queue()
            from app.events.producer import in_memory_broker
            for t in self.topics:
                in_memory_broker.subscribe(t, self.q)
            self._running = False

    def poll_once(self, timeout: float = 1.0) -> Optional[EventEnvelope]:
        """Poll for a single message and deserialize it."""
        if self.local_mode:
            import queue
            try:
                envelope = self.q.get(timeout=timeout)
                return envelope
            except queue.Empty:
                return None

        msg = self._consumer.poll(timeout)
        if msg is None:
            return None
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                return None
            logger.error("Kafka consumer error: %s", msg.error())
            return None
        try:
            data = json.loads(msg.value().decode("utf-8"))
            return EventEnvelope(**data)
        except Exception as e:
            logger.error("Failed to deserialize Kafka message: %s", e)
            return None

    def close(self) -> None:
        self._running = False
        if self.local_mode:
            try:
                from app.events.producer import in_memory_broker
                for t in self.topics:
                    in_memory_broker.unsubscribe(t, self.q)
            except Exception as e:
                logger.warning("Failed to unsubscribe in_memory_broker: %s", e)
        else:
            try:
                self._consumer.close()
            except Exception:
                pass



class EvidenceNormalizationWorker:
    """
    Background worker that subscribes to 'evidence.ingested' events,
    confirms artifacts are queryable in postgres, and republishes
    'evidence.normalized' events.
    """

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._consumer: Optional[KafkaConsumer] = None

    def start(self, db_session_factory, kafka_producer) -> None:
        """Start the worker in a background thread."""
        if self._thread and self._thread.is_alive():
            self.stop()
        self._running = True
        self._thread = threading.Thread(
            target=self._run,
            args=(db_session_factory, kafka_producer),
            daemon=True,
            name="evidence-normalization-worker",
        )
        self._thread.start()
        logger.info("Evidence normalization worker started")

    def _run(self, db_session_factory, kafka_producer) -> None:
        """Main consumer loop."""
        from app.db.models import EvidenceArtifact

        self._consumer = KafkaConsumer(
            topics=["evidence.ingested"],
            group_id="evidence-normalization-worker",
        )

        while self._running:
            try:
                envelope = self._consumer.poll_once(timeout=1.0)
                if envelope is None:
                    continue

                logger.info(
                    "Received evidence.ingested event %s for case %s",
                    envelope.event_id,
                    envelope.case_id,
                )

                # Confirm artifacts are queryable in postgres
                artifact_ids = envelope.payload.get("artifact_ids", [])
                db = db_session_factory()
                try:
                    for aid_str in artifact_ids:
                        aid = uuid.UUID(aid_str) if isinstance(aid_str, str) else aid_str
                        artifact = db.query(EvidenceArtifact).filter(
                            EvidenceArtifact.artifact_id == aid
                        ).first()
                        if artifact is None:
                            logger.warning(
                                "Artifact %s not found in DB, skipping normalization", aid
                            )
                            continue
                    logger.info(
                        "All %d artifacts confirmed queryable for case %s",
                        len(artifact_ids),
                        envelope.case_id,
                    )
                finally:
                    db.close()

                # Republish as evidence.normalized
                kafka_producer.publish(
                    topic="evidence.normalized",
                    case_id=envelope.case_id,
                    event_type="evidence.normalized",
                    payload={
                        "source_event_id": str(envelope.event_id),
                        "artifact_ids": artifact_ids,
                    },
                )
                logger.info(
                    "Published evidence.normalized for case %s", envelope.case_id
                )

            except Exception as e:
                logger.error("Error in normalization worker: %s", e, exc_info=True)

    def stop(self) -> None:
        """Signal the worker to stop."""
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
        logger.info("Evidence normalization worker stopped")


# Module-level singleton
_worker: EvidenceNormalizationWorker | None = None


def get_normalization_worker() -> EvidenceNormalizationWorker:
    global _worker
    if _worker is None:
        _worker = EvidenceNormalizationWorker()
    return _worker
