"""Neo4j driver wrapper with transaction-safe execution and automatic retry.

Uses session.execute_read() / session.execute_write() for automatic retry
on transient errors (leader switches, network blips, connection resets).
This is critical for production stability under load.
"""

import logging
from typing import Optional

from neo4j import GraphDatabase, Driver

from app.config import settings

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Thread-safe Neo4j client with transactional retry."""

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
        max_connection_pool_size: int = 50,
        connection_acquisition_timeout: float = 60.0,
    ) -> None:
        self._uri = uri or settings.NEO4J_URI
        self._user = user or settings.NEO4J_USER
        self._password = password or settings.NEO4J_PASSWORD
        self.database = database or settings.NEO4J_DATABASE
        self._driver: Driver = GraphDatabase.driver(
            self._uri,
            auth=(self._user, self._password),
            max_connection_pool_size=max_connection_pool_size,
            connection_acquisition_timeout=connection_acquisition_timeout,
        )

    def get_session(self, **kwargs):
        """Get a Neo4j session for the configured database."""
        return self._driver.session(database=self.database, **kwargs)

    def execute_read(self, query: str, parameters: dict = None) -> list[dict]:
        """Execute a read transaction with automatic retry on transient errors.

        Uses session.execute_read() which retries on:
        - TransientError (leader switches, temporary unavailability)
        - ServiceUnavailable (connection drops)
        - SessionExpired (cluster topology changes)
        """
        def _tx_work(tx):
            result = tx.run(query, parameters or {})
            return [record.data() for record in result]

        with self.get_session() as session:
            return session.execute_read(_tx_work)

    def execute_write(self, query: str, parameters: dict = None) -> list[dict]:
        """Execute a write transaction with automatic retry on transient errors.

        Uses session.execute_write() which retries on:
        - TransientError (leader switches, temporary unavailability)
        - ServiceUnavailable (connection drops)
        - SessionExpired (cluster topology changes)

        Write transactions are retried with the same query and parameters.
        The query MUST be idempotent (use MERGE over CREATE where possible).
        """
        def _tx_work(tx):
            result = tx.run(query, parameters or {})
            return [record.data() for record in result]

        with self.get_session() as session:
            return session.execute_write(_tx_work)

    def execute_read_batch(self, queries: list[tuple[str, dict]]) -> list[list[dict]]:
        """Execute multiple read queries in a single transaction.

        Reduces round-trips for bulk operations. All queries share
        the same transaction — if any fails, none are committed.
        """
        def _tx_work(tx):
            results = []
            for query, params in queries:
                result = tx.run(query, params or {})
                results.append([record.data() for record in result])
            return results

        with self.get_session() as session:
            return session.execute_read(_tx_work)

    def execute_write_batch(self, queries: list[tuple[str, dict]]) -> list[list[dict]]:
        """Execute multiple write queries in a single transaction.

        Atomic — all succeed or all fail. Critical for operations
        like person merging where multiple relationship transfers
        must complete together.
        """
        def _tx_work(tx):
            results = []
            for query, params in queries:
                result = tx.run(query, params or {})
                results.append([record.data() for record in result])
            return results

        with self.get_session() as session:
            return session.execute_write(_tx_work)

    def health_check(self) -> bool:
        """Verify connectivity to Neo4j."""
        try:
            self._driver.verify_connectivity()
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Close the driver connection."""
        self._driver.close()
        global _client
        _client = None


# Module-level singleton
_client: Neo4jClient | None = None


def get_neo4j_client() -> Neo4jClient:
    """Return the Neo4j client singleton."""
    global _client
    if _client is None:
        _client = Neo4jClient()
    return _client
