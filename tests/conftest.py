# tests/conftest.py
# Shared fixtures for all test modules.

import pytest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from core.database import Base, get_db
from main import app


# ── In-memory SQLite engine shared across all connections via StaticPool ──────
#
# StaticPool ensures every session/connection in a test reuses the same
# underlying SQLite in-memory connection. This means tool functions that open
# their own SessionLocal inside the test still see the data seeded by the
# test session.

TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db_session():
    """
    Provides a clean in-memory SQLite session for every test function.
    All tables are created fresh and dropped after each test.
    """
    # Import models so SQLAlchemy registers them before create_all
    from models.db_models import ScanRecord, KnownScam  # noqa: F401

    Base.metadata.create_all(bind=test_engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session):
    """
    Provides a FastAPI TestClient with the database dependency overridden
    to use the in-memory test database.

    `init_db` is mocked so the lifespan does not attempt to create
    `./data/fraud_detection.db` (which would fail in CI without the directory).
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # session lifecycle managed by db_session fixture

    app.dependency_overrides[get_db] = override_get_db
    with patch("main.init_db"):
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.clear()
