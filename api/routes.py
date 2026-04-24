# api/routes.py
# What it contains: The HTTP endpoints for your application.
# Why it is important: This is how the frontend (or users) communicate with your fraud app.
# Connectivity: Receives web requests, validates them using models/schemas.py,
#   invokes the agentic pipeline via core/llm_service.py, and persists results via core/database.py.

import json
import logging
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session

from models.schemas import (
    FraudCheckRequest,
    FraudCheckResponse,
    ScanHistoryItem,
    StatsResponse,
    AgentStep,
)
from models.db_models import ScanRecord
from core.llm_service import analyze_text_for_fraud
from core.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def read_root():
    return {
        "message": "Fraud Detection Agentic API is running",
        "version": "2.0.0",
        "architecture": "Multi-Agent (Scanner → Researcher → Reasoner)",
    }


@router.post("/check", response_model=FraudCheckResponse, status_code=status.HTTP_200_OK)
async def check_for_fraud(request: FraudCheckRequest, db: Session = Depends(get_db)):
    """
    Receives a message and runs the full agentic fraud analysis pipeline.

    The pipeline consists of:
    1. Scanner Agent — fast first-pass with deterministic tools
    2. Researcher Agent — deep investigation (conditional, skipped if Scanner is confident)
    3. Reasoner Agent — synthesizes all evidence into a final verdict
    """
    try:
        # Run the agentic pipeline
        result = await analyze_text_for_fraud(
            text=request.message_text,
            sender_id=request.sender_id,
        )

        # Persist the scan result to the database
        scan_record = ScanRecord(
            message_text=request.message_text,
            sender_id=request.sender_id,
            is_fraud=result["is_fraud"],
            confidence_score=result["confidence"],
            analysis_reason=result["reasoning"],
            evidence_summary=result.get("evidence_summary", ""),
            urls_found=json.dumps(result.get("urls_found", [])),
            url_risk_level=result.get("url_risk_level"),
            tools_used=json.dumps(result.get("tools_used", [])),
            agent_trace=json.dumps(result.get("agent_trace", [])),
        )
        db.add(scan_record)
        db.commit()
        db.refresh(scan_record)

        # Build the response
        return FraudCheckResponse(
            scan_id=scan_record.id,
            is_fraud=result["is_fraud"],
            confidence_score=result["confidence"],
            analysis_reason=result["reasoning"],
            evidence_summary=result.get("evidence_summary", ""),
            urls_found=result.get("urls_found", []),
            url_risk_level=result.get("url_risk_level"),
            tools_used=result.get("tools_used", []),
            agent_trace=[
                AgentStep(**step) for step in result.get("agent_trace", [])
            ],
        )

    except ValueError as ve:
        logger.error(f"Configuration Error: {ve}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to process fraud check: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the fraud check.",
        )


@router.get("/history", response_model=list[ScanHistoryItem])
async def get_scan_history(limit: int = 20, db: Session = Depends(get_db)):
    """Retrieve recent scan history with full agent traces."""
    records = (
        db.query(ScanRecord)
        .order_by(ScanRecord.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        ScanHistoryItem(
            scan_id=r.id,
            message_text=r.message_text,
            sender_id=r.sender_id,
            is_fraud=r.is_fraud,
            confidence_score=r.confidence_score,
            analysis_reason=r.analysis_reason,
            evidence_summary=r.evidence_summary or "",
            urls_found=json.loads(r.urls_found) if r.urls_found else [],
            url_risk_level=r.url_risk_level,
            tools_used=json.loads(r.tools_used) if r.tools_used else [],
            agent_trace=[
                AgentStep(**step)
                for step in (json.loads(r.agent_trace) if r.agent_trace else [])
            ],
            created_at=r.created_at,
        )
        for r in records
    ]


@router.get("/check/{scan_id}/trace", response_model=list[AgentStep])
async def get_scan_trace(scan_id: str, db: Session = Depends(get_db)):
    """Retrieve the full agent reasoning trace for a specific scan."""
    record = db.query(ScanRecord).filter(ScanRecord.id == scan_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")

    trace_data = json.loads(record.agent_trace) if record.agent_trace else []
    return [AgentStep(**step) for step in trace_data]


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: Session = Depends(get_db)):
    """Get aggregate statistics across all scans."""
    total = db.query(ScanRecord).count()
    frauds = db.query(ScanRecord).filter(ScanRecord.is_fraud == True).count()
    urls_flagged = db.query(ScanRecord).filter(
        ScanRecord.url_risk_level.in_(["suspicious", "malicious"])
    ).count()

    return StatsResponse(
        total_scans=total,
        total_fraud_detected=frauds,
        fraud_percentage=round((frauds / total * 100) if total > 0 else 0.0, 2),
        total_urls_flagged=urls_flagged,
    )
