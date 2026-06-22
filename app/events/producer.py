"""Kafka producer wrapper using confluent-kafka."""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient, NewTopic

from app.config import settings
from app.schemas import EventEnvelope

logger = logging.getLogger(__name__)


class KafkaProducer:
    """Wrapper around confluent-kafka Producer with JSON serialization."""

    TOPICS = [
        "evidence.ingested",
        "evidence.normalized",
        "graph.updated",
        "legal.updated",
        "osint.graph.updated",
    ]

    def __init__(self, bootstrap_servers: Optional[str] = None) -> None:
        self._bootstrap = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS
        self._producer = Producer({"bootstrap.servers": self._bootstrap})
        self._ensure_topics()

    def _ensure_topics(self) -> None:
        """Create topics if they do not exist."""
        try:
            admin = AdminClient({"bootstrap.servers": self._bootstrap})
            existing = admin.list_topics(timeout=5).topics.keys()
            new_topics = [
                NewTopic(t, num_partitions=1, replication_factor=1)
                for t in self.TOPICS
                if t not in existing
            ]
            if new_topics:
                futures = admin.create_topics(new_topics)
                for topic, future in futures.items():
                    try:
                        future.result()
                        logger.info("Created Kafka topic: %s", topic)
                    except Exception as e:
                        logger.warning("Topic creation issue for %s: %s", topic, e)
        except Exception as e:
            logger.warning("Could not ensure Kafka topics: %s", e)

    def publish(
        self,
        topic: str,
        case_id: uuid.UUID,
        event_type: str,
        payload: dict,
    ) -> EventEnvelope:
        """Publish an event to a Kafka topic. Returns the event envelope."""
        envelope = EventEnvelope(
            event_id=uuid.uuid4(),
            case_id=case_id,
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            payload=payload,
        )

        self._producer.produce(
            topic=topic,
            key=str(case_id),
            value=envelope.model_dump_json(),
            callback=self._delivery_callback,
        )
        self._producer.flush(timeout=5)
        return envelope

    def _delivery_callback(self, err, msg) -> None:
        if err:
            logger.error("Kafka delivery failed: %s", err)
        else:
            logger.info("Kafka message delivered to %s [%d] @ %d", msg.topic(), msg.partition(), msg.offset())

    def health_check(self) -> bool:
        """Check connectivity to Kafka."""
        try:
            admin = AdminClient({"bootstrap.servers": self._bootstrap})
            admin.list_topics(timeout=5)
            return True
        except Exception:
            return False

    def close(self) -> None:
        self._producer.flush(timeout=10)


# Module-level singleton
_producer: KafkaProducer | None = None


def get_kafka_producer() -> KafkaProducer:
    """Return the Kafka producer singleton."""
    global _producer
    if _producer is None:
        _producer = KafkaProducer()
    return _producer
