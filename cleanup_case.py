import uuid
from app.db.session import SessionLocal
from app.db.models import EvidenceArtifact
from app.graph.driver import get_neo4j_client

CASE_ID = "9f09262e-ad29-475f-897e-78ca15c55494"

def main():
    db = SessionLocal()
    client = get_neo4j_client()
    
    # 1. Delete evidence artifacts from PostgreSQL
    deleted_postgres = db.query(EvidenceArtifact).filter(
        EvidenceArtifact.case_id == uuid.UUID(CASE_ID)
    ).delete()
    db.commit()
    print(f"Deleted {deleted_postgres} artifacts from PostgreSQL")
    
    # 2. Delete all Neo4j nodes and relationships for the case
    res = client.execute_write(
        """
        MATCH (n)
        WHERE n.case_id = $cid
        DETACH DELETE n
        RETURN count(n) AS cnt
        """,
        {"cid": CASE_ID}
    )
    cnt = res[0]["cnt"] if res else 0
    print(f"Deleted {cnt} nodes from Neo4j")
    
    db.close()

if __name__ == "__main__":
    main()
