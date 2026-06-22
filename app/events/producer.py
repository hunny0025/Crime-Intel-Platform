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

import queue
import threading

class InMemoryBroker:
    """Thread-safe in-memory publish-subscribe broker for local development/deployment without Kafka."""
    def __init__(self):
        self.subscribers = {}
        self.lock = threading.Lock()

    def subscribe(self, topic: str, q: queue.Queue):
        with self.lock:
            if topic not in self.subscribers:
                self.subscribers[topic] = []
            if q not in self.subscribers[topic]:
                self.subscribers[topic].append(q)

    def unsubscribe(self, topic: str, q: queue.Queue):
        with self.lock:
            if topic in self.subscribers:
                if q in self.subscribers[topic]:
                    self.subscribers[topic].remove(q)

    def publish(self, topic: str, envelope: EventEnvelope):
        with self.lock:
            if topic in self.subscribers:
                for q in self.subscribers[topic]:
                    q.put(envelope)

in_memory_broker = InMemoryBroker()


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
        self.local_mode = False
        
        if not self._bootstrap or self._bootstrap == "":
            logger.info("Kafka bootstrap servers empty, enabling In-Memory Event Broker fallback")
            self.local_mode = True
            return

        try:
            self._producer = Producer({"bootstrap.servers": self._bootstrap})
            self._ensure_topics()
        except Exception as e:
            logger.warning("Failed to initialize Kafka producer, falling back to In-Memory Broker: %s", e)
            self.local_mode = True

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
        """Publish an event to a Kafka topic or local in-memory broker. Returns the event envelope."""
        envelope = EventEnvelope(
            event_id=uuid.uuid4(),
            case_id=case_id,
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            payload=payload,
        )

        if self.local_mode:
            logger.info("In-Memory Broker: publishing event %s to topic %s", envelope.event_id, topic)
            in_memory_broker.publish(topic, envelope)
            return envelope

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
        if self.local_mode:
            return True
        try:
            admin = AdminClient({"bootstrap.servers": self._bootstrap})
            admin.list_topics(timeout=5)
            return True
        except Exception:
            return False

    def close(self) -> None:
        if not self.local_mode:
            self._producer.flush(timeout=10)


# Module-level singleton
_producer: KafkaProducer | None = None


def get_kafka_producer() -> KafkaProducer:
    """Return the Kafka producer singleton."""
    global _producer
    if _producer is None:
        _producer = KafkaProducer()
    return _producer

