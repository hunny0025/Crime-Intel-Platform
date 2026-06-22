from app.graph.driver import get_neo4j_client

client = get_neo4j_client()
nodes = client.execute_read("MATCH (r:ProceduralComplianceRecord {case_id: '9f09262e-ad29-475f-897e-78ca15c55494'}) RETURN r.requirement_id as rid, r.status as status")
for n in nodes:
    print(n)
