# core/database.py
# What it contains: SQLAlchemy database engine, session factory, and base model.
# Why it is important: This is the foundation for all data persistence — scan history, known scams, etc.
# Connectivity: Used by api/routes.py to save/retrieve scan records. Uses SQLite in dev, PostgreSQL in production.

import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

logger = logging.getLogger(__name__)

# Use SQLite for development. For production, swap this to:
# DATABASE_URL = "postgresql://user:password@localhost:5432/fraud_detection"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/fraud_detection.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


def get_db():
    """
    Dependency that provides a database session per request.
    Used in FastAPI routes via Depends(get_db).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Creates all tables defined by ORM models. Called once on startup."""
    from models.db_models import ScanRecord, KnownScam  # noqa: F401
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully.")
