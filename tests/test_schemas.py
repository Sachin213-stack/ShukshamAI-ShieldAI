# tests/test_schemas.py
# Tests for models/schemas.py — Pydantic request/response validation.

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from models.schemas import (
    FraudCheckRequest,
    FraudCheckResponse,
    AgentStep,
    ScanHistoryItem,
    StatsResponse,
)


# ── FraudCheckRequest ─────────────────────────────────────────────────────────

class TestFraudCheckRequest:
    def test_valid_request_with_all_fields(self):
        req = FraudCheckRequest(message_text="Hello, click here!", sender_id="9876543210")
        assert req.message_text == "Hello, click here!"
        assert req.sender_id == "9876543210"

    def test_valid_request_without_sender_id(self):
        req = FraudCheckRequest(message_text="Congratulations, you have won!")
        assert req.sender_id is None

    def test_empty_message_text_raises(self):
        with pytest.raises(ValidationError):
            FraudCheckRequest(message_text="")

    def test_message_text_too_long_raises(self):
        with pytest.raises(ValidationError):
            FraudCheckRequest(message_text="x" * 2001)

    def test_message_at_max_length_is_valid(self):
        req = FraudCheckRequest(message_text="x" * 2000)
        assert len(req.message_text) == 2000

    def test_sender_id_too_long_raises(self):
        with pytest.raises(ValidationError):
            FraudCheckRequest(message_text="test", sender_id="x" * 101)

    def test_sender_id_at_max_length_is_valid(self):
        req = FraudCheckRequest(message_text="test", sender_id="x" * 100)
        assert len(req.sender_id) == 100


# ── AgentStep ─────────────────────────────────────────────────────────────────

class TestAgentStep:
    def test_valid_agent_step(self):
        step = AgentStep(
            agent_name="Scanner",
            action="Called extract_urls",
            observation="[]",
            timestamp="2024-01-01T00:00:00+00:00",
        )
        assert step.agent_name == "Scanner"
        assert step.action == "Called extract_urls"

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            AgentStep(agent_name="Scanner", action="test", observation="obs")
        # timestamp is missing


# ── FraudCheckResponse ────────────────────────────────────────────────────────

class TestFraudCheckResponse:
    def _valid_step(self):
        return AgentStep(
            agent_name="Scanner",
            action="Called extract_urls",
            observation="[]",
            timestamp="2024-01-01T00:00:00+00:00",
        )

    def test_valid_fraud_response(self):
        resp = FraudCheckResponse(
            scan_id="abc-123",
            is_fraud=True,
            confidence_score=0.95,
            analysis_reason="Multiple fraud signals detected.",
            evidence_summary="• OTP harvesting detected",
            urls_found=["http://evil.tk"],
            url_risk_level="malicious",
            tools_used=["extract_urls", "pattern_match"],
            agent_trace=[self._valid_step()],
        )
        assert resp.is_fraud is True
        assert resp.confidence_score == 0.95
        assert resp.url_risk_level == "malicious"

    def test_default_optional_fields(self):
        resp = FraudCheckResponse(
            scan_id="xyz",
            is_fraud=False,
            confidence_score=0.1,
            analysis_reason="Looks safe.",
        )
        assert resp.evidence_summary == ""
        assert resp.urls_found == []
        assert resp.url_risk_level is None
        assert resp.tools_used == []
        assert resp.agent_trace == []

    def test_confidence_score_below_zero_raises(self):
        with pytest.raises(ValidationError):
            FraudCheckResponse(
                scan_id="x",
                is_fraud=False,
                confidence_score=-0.1,
                analysis_reason="test",
            )

    def test_confidence_score_above_one_raises(self):
        with pytest.raises(ValidationError):
            FraudCheckResponse(
                scan_id="x",
                is_fraud=False,
                confidence_score=1.1,
                analysis_reason="test",
            )

    def test_confidence_boundary_values(self):
        for val in (0.0, 1.0):
            resp = FraudCheckResponse(
                scan_id="x",
                is_fraud=False,
                confidence_score=val,
                analysis_reason="test",
            )
            assert resp.confidence_score == val


# ── ScanHistoryItem ───────────────────────────────────────────────────────────

class TestScanHistoryItem:
    def test_valid_scan_history_item(self):
        item = ScanHistoryItem(
            scan_id="id-1",
            message_text="win a prize now",
            sender_id=None,
            is_fraud=True,
            confidence_score=0.88,
            analysis_reason="Prize scam detected.",
            evidence_summary="• PRIZE_SCAM flag",
            urls_found=[],
            url_risk_level=None,
            tools_used=["pattern_match"],
            agent_trace=[],
            created_at=datetime.now(timezone.utc),
        )
        assert item.scan_id == "id-1"
        assert item.is_fraud is True


# ── StatsResponse ─────────────────────────────────────────────────────────────

class TestStatsResponse:
    def test_valid_stats(self):
        stats = StatsResponse(
            total_scans=100,
            total_fraud_detected=40,
            fraud_percentage=40.0,
            total_urls_flagged=10,
        )
        assert stats.total_scans == 100
        assert stats.fraud_percentage == 40.0

    def test_zero_stats(self):
        stats = StatsResponse(
            total_scans=0,
            total_fraud_detected=0,
            fraud_percentage=0.0,
            total_urls_flagged=0,
        )
        assert stats.total_scans == 0
        assert stats.fraud_percentage == 0.0
