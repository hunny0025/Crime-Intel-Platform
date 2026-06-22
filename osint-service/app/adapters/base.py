"""Base OSINT adapter — all source adapters inherit from this."""

import uuid
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class OSINTResult:
    """Canonical result from an OSINT adapter."""
    def __init__(
        self,
        source_type: str,
        query: str,
        raw_result: dict,
        extracted_entities: list[dict],
        error: Optional[str] = None,
    ):
        self.record_id = str(uuid.uuid4())
        self.source_type = source_type
        self.query = query
        self.retrieved_at = datetime.now(timezone.utc)
        self.raw_result = raw_result
        self.extracted_entities = extracted_entities
        self.error = error
        self.classification_tag = "public_osint"

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "source_type": self.source_type,
            "query": self.query,
            "retrieved_at": self.retrieved_at.isoformat(),
            "raw_result": self.raw_result,
            "extracted_entities": self.extracted_entities,
            "classification_tag": self.classification_tag,
            "error": self.error,
        }


class BaseOSINTAdapter(ABC):
    """
    Base class for config-driven OSINT source adapters.

    Subclasses must implement:
        - source_type (str): unique identifier for this source
        - is_available() -> bool: check if credentials/deps are configured
        - execute(query: str) -> OSINTResult: perform the lookup
    """

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Unique identifier for this OSINT source."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this adapter has required credentials configured."""
        ...

    @abstractmethod
    def execute(self, query: str) -> OSINTResult:
        """Execute the OSINT query and return a canonical result."""
        ...

    def unavailable_result(self, query: str) -> OSINTResult:
        """Return a result indicating this adapter is not available."""
        return OSINTResult(
            source_type=self.source_type,
            query=query,
            raw_result={},
            extracted_entities=[],
            error=f"unavailable — credentials not configured for {self.source_type}",
        )
