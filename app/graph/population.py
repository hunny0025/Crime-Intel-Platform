"""Evidence-to-graph population pipeline.

Consumes 'evidence.normalized' Kafka events and populates the knowledge graph
with rule-based extraction (phone/email regex). LLM-based semantic extraction
is Phase 5's Evidence Interpretation Agent — this phase proves the wiring works.
"""

import json
import logging
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.db.models import EvidenceArtifact
from app.events.consumer import KafkaConsumer
from app.events.producer import get_kafka_producer
from app.graph import crud
from app.graph.identity import resolve_identity_facet

logger = logging.getLogger(__name__)

# ── Regex patterns ───────────────────────────────────────────────────────

PHONE_PATTERN = re.compile(r"[\+]?[\d\-\(\)\s]{7,15}")
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")


def extract_identifiers(text: str) -> dict:
    """Extract phone numbers and email addresses from text."""
    phones = list(set(PHONE_PATTERN.findall(text)))
    emails = list(set(EMAIL_PATTERN.findall(text)))
    # Filter out very short phone matches
    phones = [p.strip() for p in phones if len(re.sub(r"\D", "", p)) >= 7]
    return {"phones": phones, "emails": emails}


def process_communication_record(
    case_id: str,
    artifact: dict,
    content: dict,
    classification_tag: str,
) -> dict:
    """
    Process a communication_record artifact:
    1. Extract phone/email identifiers via NLP (with regex fallback)
    2. Resolve to Person + IdentityFacet via Identity Ontology
    3. Create Event node with intent and sentiment attributes
    4. Create COMMUNICATED_WITH + PARTICIPATED_IN relationships
    """
    new_node_ids = []
    new_rel_ids = []

    # Get text content
    text_content = ""
    if isinstance(content, dict):
        text_content = content.get("text") or content.get("body") or content.get("message") or content.get("text_content") or json.dumps(content)
    else:
        text_content = str(content)

    # 1. NLP extraction
    from app.ai.models import extract_entities_nlp, classify_communication_intent, analyze_sentiment_threat
    nlp_entities = extract_entities_nlp(text_content)

    nlp_phones = [e["value"] for e in nlp_entities if e["entity_type"] == "PHONE" and e.get("confidence", 0) > 0.8]
    nlp_emails = [e["value"] for e in nlp_entities if e["entity_type"] == "EMAIL" and e.get("confidence", 0) > 0.8]

    # 2. Regex fallback
    if not nlp_phones or not nlp_emails:
        identifiers = extract_identifiers(text_content)
        if not nlp_phones:
            nlp_phones = identifiers["phones"]
        if not nlp_emails:
            nlp_emails = identifiers["emails"]

    # Map NLP entity types to facet types
    ENTITY_TYPE_TO_FACET = {
        "PHONE": "phone_number",
        "EMAIL": "email",
        "CRYPTO_WALLET": "crypto_wallet_address",
        "UPI_ID": "upi_id",
        "SOCIAL_HANDLE": "social_handle",
        "IMEI": "device_imei",
        "PERSON": "person_name",
    }

    # Collect facets to resolve
    facets_to_resolve = []
    for phone in nlp_phones:
        facets_to_resolve.append(("phone_number", phone))
    for email in nlp_emails:
        facets_to_resolve.append(("email", email))

    for ent in nlp_entities:
        if ent.get("confidence", 0.0) > 0.8:
            etype = ent["entity_type"]
            if etype not in ["PHONE", "EMAIL"] and etype in ENTITY_TYPE_TO_FACET:
                facets_to_resolve.append((ENTITY_TYPE_TO_FACET[etype], ent["value"]))

    # Deduplicate facets to resolve
    seen_facets = set()
    deduped_facets = []
    for ftype, val in facets_to_resolve:
        key = (ftype, val)
        if key not in seen_facets:
            seen_facets.add(key)
            deduped_facets.append((ftype, val))

    # Resolve all persons from identifiers/facets
    resolved_persons = []
    for ftype, val in deduped_facets:
        result = resolve_identity_facet(
            case_id=case_id,
            facet_type=ftype,
            value=val,
            classification_tag=classification_tag,
        )
        if result.get("linked_persons"):
            person = result["linked_persons"][0]
            if person.get("id") not in [p.get("id") for p in resolved_persons]:
                resolved_persons.append(person)
        new_node_ids.append(result.get("id", ""))

    # Extract intent and sentiment using the model functions
    intent_res = classify_communication_intent(text_content)
    sentiment_res = analyze_sentiment_threat(text_content)
    intent = intent_res.get("primary_intent", "normal_conversation")
    sentiment = sentiment_res.get("sentiment", "neutral")

    # Create Event node
    artifact_id = artifact.get("artifact_id", str(uuid.uuid4()))
    timestamp = artifact.get("collection_timestamp_utc", datetime.now(timezone.utc).isoformat())

    event = crud.create_node("Event", {
        "case_id": case_id,
        "event_type": "communication",
        "valid_from": str(timestamp),
        "valid_to": str(timestamp),
        "confidence": 1.0,
        "artifact_id": str(artifact_id),
        "source_tool": artifact.get("source_tool"),
        "classification_tag": classification_tag,
        "intent": intent,
        "sentiment": sentiment,
    })
    new_node_ids.append(event.get("id", ""))

    # Create COMMUNICATED_WITH relationships between resolved persons
    for i in range(len(resolved_persons)):
        for j in range(i + 1, len(resolved_persons)):
            rel = crud.create_relationship(
                resolved_persons[i]["id"],
                resolved_persons[j]["id"],
                "COMMUNICATED_WITH",
                properties={
                    "evidence_basis": [str(artifact_id)],
                    "confidence": 1.0,
                    "valid_from": str(timestamp),
                    "valid_to": str(timestamp),
                },
            )
            new_rel_ids.append(f"{resolved_persons[i]['id']}->{resolved_persons[j]['id']}")

    # Create PARTICIPATED_IN relationships from persons to event
    for person in resolved_persons:
        crud.create_relationship(
            person["id"],
            event["id"],
            "PARTICIPATED_IN",
            properties={
                "evidence_basis": [str(artifact_id)],
                "confidence": 1.0,
            },
        )

    return {"new_node_ids": new_node_ids, "new_rel_ids": new_rel_ids}


def process_generic_file(
    case_id: str,
    artifact: dict,
    content: dict,
    classification_tag: str,
) -> dict:
    """
    Process a generic_file artifact: create a placeholder Event node
    with event_type='file_artifact' referencing the artifact_id.
    Phase 5's richer extraction will pick these up.
    """
    artifact_id = artifact.get("artifact_id", str(uuid.uuid4()))
    source_tool = content.get("source_tool") or artifact.get("source_tool")

    event = crud.create_node("Event", {
        "case_id": case_id,
        "event_type": "file_artifact",
        "artifact_id": str(artifact_id),
        "source_tool": source_tool,
        "classification_tag": classification_tag,
    })

    return {"new_node_ids": [event.get("id", "")], "new_rel_ids": []}


def process_artifact(case_id: str, artifact_record: dict, content: dict) -> dict:
    """Dispatch processing based on canonical output type."""
    output_type = content.get("_canonical_output_type", "generic_file")
    classification_tag = artifact_record.get("classification_tag", "case_sensitive")
    if hasattr(classification_tag, "value"):
        classification_tag = classification_tag.value

    if output_type == "communication_record":
        return process_communication_record(case_id, artifact_record, content, classification_tag)
    else:
        return process_generic_file(case_id, artifact_record, content, classification_tag)


# ── Graph Population Worker ──────────────────────────────────────────────

class GraphPopulationWorker:
    """
    Background worker that consumes 'evidence.normalized' events,
    processes artifacts, and publishes 'graph.updated' events.
    """

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._consumer: Optional[KafkaConsumer] = None

    def start(self, db_session_factory) -> None:
        if self._thread and self._thread.is_alive():
            self.stop()
        self._running = True
        self._thread = threading.Thread(
            target=self._run,
            args=(db_session_factory,),
            daemon=True,
            name="graph-population-worker",
        )
        self._thread.start()
        logger.info("Graph population worker started")

    def _run(self, db_session_factory) -> None:
        self._consumer = KafkaConsumer(
            topics=["evidence.normalized"],
            group_id="graph-population-worker",
        )
        consumer = self._consumer

        while self._running:
            try:
                envelope = consumer.poll_once(timeout=1.0)
                if envelope is None:
                    continue

                logger.info(
                    "Graph population: processing event %s for case %s",
                    envelope.event_id, envelope.case_id,
                )

                case_id = str(envelope.case_id)
                artifact_ids = envelope.payload.get("artifact_ids", [])
                all_new_nodes = []
                all_new_rels = []

                db = db_session_factory()
                try:
                    for aid_str in artifact_ids:
                        aid = uuid.UUID(aid_str) if isinstance(aid_str, str) else aid_str
                        artifact = db.query(EvidenceArtifact).filter(
                            EvidenceArtifact.artifact_id == aid
                        ).first()
                        if artifact is None:
                            continue

                        # Try to parse artifact content from MinIO
                        try:
                            from app.storage.minio_client import get_minio_client
                            minio = get_minio_client()
                            raw = minio.download_bytes(artifact.content_pointer)
                            content = json.loads(raw.decode("utf-8"))
                        except Exception:
                            content = {}

                        artifact_dict = {
                            "artifact_id": str(artifact.artifact_id),
                            "source_tool": artifact.source_tool,
                            "collection_timestamp_utc": artifact.collection_timestamp_utc.isoformat()
                            if artifact.collection_timestamp_utc else None,
                            "classification_tag": artifact.classification_tag.value
                            if hasattr(artifact.classification_tag, "value")
                            else artifact.classification_tag,
                        }

                        result = process_artifact(case_id, artifact_dict, content)
                        all_new_nodes.extend(result["new_node_ids"])
                        all_new_rels.extend(result["new_rel_ids"])
                finally:
                    db.close()

                # Publish graph.updated event
                try:
                    producer = get_kafka_producer()
                    producer.publish(
                        topic="graph.updated",
                        case_id=envelope.case_id,
                        event_type="graph.updated",
                        payload={
                            "case_id": case_id,
                            "new_node_ids": all_new_nodes,
                            "new_relationship_ids": all_new_rels,
                            "source_event_id": str(envelope.event_id),
                        },
                    )
                    logger.info(
                        "Published graph.updated for case %s: %d nodes, %d rels",
                        case_id, len(all_new_nodes), len(all_new_rels),
                    )
                except Exception as e:
                    logger.warning("Failed to publish graph.updated: %s", e)

            except Exception as e:
                logger.error("Graph population error: %s", e, exc_info=True)

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
        logger.info("Graph population worker stopped")


_worker: GraphPopulationWorker | None = None


def get_graph_population_worker() -> GraphPopulationWorker:
    global _worker
    if _worker is None:
        _worker = GraphPopulationWorker()
    return _worker
