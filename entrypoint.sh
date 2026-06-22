#!/bin/bash
set -e

if [ "$SKIP_WAIT_DEPENDENCIES" = "true" ]; then
    echo "Skipping dependency wait checks as SKIP_WAIT_DEPENDENCIES is true"
else
    echo "Waiting for PostgreSQL..."
    until python -c "
import psycopg2, os
try:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.close()
    print('PostgreSQL is ready')
except Exception as e:
    print(f'Waiting... {e}')
    exit(1)
" 2>/dev/null; do
        sleep 2
    done

    echo "Waiting for MinIO..."
    until curl -sf http://$MINIO_ENDPOINT/minio/health/live > /dev/null 2>&1; do
        echo "Waiting for MinIO..."
        sleep 2
    done
    echo "MinIO is ready"

    echo "Waiting for Kafka..."
    until python -c "
from confluent_kafka.admin import AdminClient
import os
try:
    admin = AdminClient({'bootstrap.servers': os.environ['KAFKA_BOOTSTRAP_SERVERS']})
    admin.list_topics(timeout=5)
    print('Kafka is ready')
except Exception as e:
    print(f'Waiting... {e}')
    exit(1)
" 2>/dev/null; do
        sleep 2
    done

    echo "Waiting for Neo4j..."
    until python -c "
from neo4j import GraphDatabase
import os
try:
    driver = GraphDatabase.driver(
        os.environ['NEO4J_URI'],
        auth=(os.environ.get('NEO4J_USER', 'neo4j'), os.environ.get('NEO4J_PASSWORD', 'password'))
    )
    driver.verify_connectivity()
    driver.close()
    print('Neo4j is ready')
except Exception as e:
    print(f'Waiting... {e}')
    exit(1)
" 2>/dev/null; do
        sleep 2
    done
fi

echo "All services ready. Running Alembic migrations..."
alembic upgrade head 2>/dev/null || echo "Alembic migrations skipped (will create tables directly)"

echo "Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info

