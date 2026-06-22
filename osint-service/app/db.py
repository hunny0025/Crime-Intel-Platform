"""Database session for OSINT service — connects to shared PostgreSQL."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=5)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
