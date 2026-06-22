"""Neo4j client for OSINT service — writes OSINT-derived nodes to shared graph."""

import logging
from neo4j import GraphDatabase
from app.config import settings

logger = logging.getLogger(__name__)


class Neo4jClient:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        self.database = settings.NEO4J_DATABASE

    def get_session(self):
        return self.driver.session(database=self.database)

    def execute_read(self, query: str, params: dict = None):
        with self.get_session() as session:
            result = session.run(query, params or {})
            return [dict(record) for record in result]

    def execute_write(self, query: str, params: dict = None):
        with self.get_session() as session:
            result = session.run(query, params or {})
            return [dict(record) for record in result]

    def health_check(self) -> bool:
        try:
            self.driver.verify_connectivity()
            return True
        except Exception:
            return False

    def close(self):
        self.driver.close()


_client = None


def get_neo4j_client() -> Neo4jClient:
    global _client
    if _client is None:
        _client = Neo4jClient()
    return _client
