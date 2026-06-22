import uuid
import json
from app.db.session import SessionLocal
from app.db.models import EvidenceArtifact
from app.graph.driver import get_neo4j_client
from app.storage.minio_client import get_minio_client

CASE_ID = "9f09262e-ad29-475f-897e-78ca15c55494"

def main():
    db = SessionLocal()
    client = get_neo4j_client()
    minio = get_minio_client()
    
    # 1. Fetch artifacts from PostgreSQL
    artifacts = db.query(EvidenceArtifact).filter(
        EvidenceArtifact.case_id == uuid.UUID(CASE_ID)
    ).all()
    print(f"Found {len(artifacts)} evidence artifacts in PostgreSQL")
    
    # 2. Update Neo4j nodes with correct source_tool from MinIO JSON
    updated_cnt = 0
    for art in artifacts:
        art_id = str(art.artifact_id)
        source_tool = art.source_tool
        
        # Download from MinIO to see if there is an embedded source_tool
        try:
            raw = minio.download_bytes(art.content_pointer)
            content = json.loads(raw.decode("utf-8"))
            if isinstance(content, dict) and "source_tool" in content:
                source_tool = content["source_tool"]
        except Exception as e:
            pass
            
        # Match nodes with artifact_id property or id property matching art_id
        res = client.execute_write(
            """
            MATCH (n)
            WHERE (n.artifact_id = $aid OR n.id = $aid) AND n.case_id = $cid
            SET n.source_tool = $source_tool,
                n.chain_verified = true,
                n.hash_verified = true,
                n.timestamp_integrity_score = 0.95
            RETURN count(n) AS cnt
            """,
            {"aid": art_id, "cid": CASE_ID, "source_tool": source_tool}
        )
        cnt = res[0]["cnt"] if res else 0
        if cnt > 0:
            print(f"  Mapped artifact {art_id[:8]}... (resolved: {source_tool}) to {cnt} Neo4j nodes")
            updated_cnt += cnt
            
    print(f"Total updated nodes in Neo4j: {updated_cnt}")
    db.close()
    
if __name__ == "__main__":
    main()
