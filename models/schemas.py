# models/schemas.py
# What it contains: Pydantic schemas for request/response validation.
# Why it is important: Prevents bad data from entering the system and ensures consistent API responses.
# Connectivity: Used by api/routes.py to validate incoming requests and format outgoing responses.

from pydantic import BaseModel, Field
from datetime import datetime


# --- Request Schemas ---

class FraudCheckRequest(BaseModel):
    message_text: str = Field(..., min_length=1, max_length=2000, description="The suspicious text message or email content")
    sender_id: str | None = Field(None, max_length=100, description="Optional phone number or email of the sender")


# --- Agent Trace Schema ---

class AgentStep(BaseModel):
    """A single step in the agent pipeline for audit/explainability."""
    agent_name: str = Field(..., description="Name of the agent that performed this step")
    action: str = Field(..., description="What the agent did (e.g., 'Called extract_urls')")
    observation: str = Field(..., description="Result of the action")
    timestamp: str = Field(..., description="ISO timestamp of when this step occurred")


# --- Response Schemas ---

class FraudCheckResponse(BaseModel):
    scan_id: str = Field(..., description="Unique ID for this scan record")
    is_fraud: bool = Field(..., description="True if the message is deemed fraudulent or a scam")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="AI confidence score between 0.0 and 1.0")
    analysis_reason: str = Field(..., description="Explanation of why this determination was made")
    evidence_summary: str = Field(default="", description="Bullet-point summary of key evidence collected by agents")
    urls_found: list[str] = Field(default_factory=list, description="URLs extracted from the message")
    url_risk_level: str | None = Field(None, description="Risk level of found URLs: safe, suspicious, or malicious")
    tools_used: list[str] = Field(default_factory=list, description="Tools invoked during the agentic analysis")
    agent_trace: list[AgentStep] = Field(default_factory=list, description="Step-by-step reasoning log from the agent pipeline")


class ScanHistoryItem(BaseModel):
    scan_id: str
    message_text: str
    sender_id: str | None
    is_fraud: bool
    confidence_score: float
    analysis_reason: str
    evidence_summary: str
    urls_found: list[str]
    url_risk_level: str | None
    tools_used: list[str]
    agent_trace: list[AgentStep]
    created_at: datetime

    model_config = {"from_attributes": True}


class StatsResponse(BaseModel):
    total_scans: int = Field(..., description="Total number of scans performed")
    total_fraud_detected: int = Field(..., description="Number of messages flagged as fraud")
    fraud_percentage: float = Field(..., description="Percentage of scans that were fraud")
    total_urls_flagged: int = Field(..., description="Number of scans with malicious URLs")
