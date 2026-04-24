# models/db_models.py
# What it contains: SQLAlchemy ORM models that define the database tables.
# Why it is important: These models map directly to database tables, storing scan history and known scam patterns.
# Connectivity: Used by core/database.py to create tables, and by api/routes.py to read/write records.

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, Float, Text, DateTime
from core.database import Base


class ScanRecord(Base):
    """Stores every fraud check performed by the system."""
    __tablename__ = "scan_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    message_text = Column(Text, nullable=False)
    sender_id = Column(String(100), nullable=True)
    is_fraud = Column(Boolean, nullable=False)
    confidence_score = Column(Float, nullable=False)
    analysis_reason = Column(Text, nullable=False)
    evidence_summary = Column(Text, nullable=True)           # Summary of evidence collected by agents
    urls_found = Column(Text, nullable=True)                  # JSON string of extracted URLs
    url_risk_level = Column(String(20), nullable=True)        # safe, suspicious, malicious
    tools_used = Column(Text, nullable=True)                  # JSON string of tools invoked
    agent_trace = Column(Text, nullable=True)                 # JSON string of full agent reasoning chain
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class KnownScam(Base):
    """Stores known scam patterns for fast local matching without needing the LLM."""
    __tablename__ = "known_scams"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pattern_text = Column(Text, nullable=False)
    category = Column(String(50), nullable=False)   # phishing, sms_scam, email_scam, financial
    severity = Column(String(20), nullable=False)    # low, medium, high, critical
    source = Column(String(200), nullable=True)      # Where this pattern was reported
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
