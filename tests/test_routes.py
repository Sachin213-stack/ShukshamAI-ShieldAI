# tests/test_routes.py
# Integration tests for api/routes.py using FastAPI TestClient.
# The LLM pipeline (analyze_text_for_fraud) is mocked to avoid calling external APIs.

import json
import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from models.db_models import ScanRecord, KnownScam


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_analysis_result(**overrides):
    """Return a realistic mock pipeline result."""
    base = {
        "is_fraud": False,
        "confidence": 0.2,
        "reasoning": "No fraud indicators found.",
        "evidence_summary": "",
        "urls_found": [],
        "url_risk_level": None,
        "tools_used": ["extract_urls", "pattern_match"],
        "agent_trace": [
            {
                "agent_name": "Scanner",
                "action": "Called extract_urls",
                "observation": "[]",
                "timestamp": "2024-01-01T00:00:00+00:00",
            }
        ],
    }
    base.update(overrides)
    return base


def _make_scan_record(**kwargs):
    """Build a ScanRecord with sensible defaults."""
    defaults = dict(
        id=str(uuid.uuid4()),
        message_text="test message",
        sender_id=None,
        is_fraud=False,
        confidence_score=0.1,
        analysis_reason="Safe.",
        evidence_summary="",
        urls_found=json.dumps([]),
        url_risk_level=None,
        tools_used=json.dumps([]),
        agent_trace=json.dumps([]),
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return ScanRecord(**defaults)


# ── GET /api/ ─────────────────────────────────────────────────────────────────

class TestApiRoot:
    def test_api_root_returns_200(self, client):
        resp = client.get("/api/")
        assert resp.status_code == 200

    def test_api_root_response_body(self, client):
        resp = client.get("/api/")
        data = resp.json()
        assert "message" in data
        assert "version" in data
        assert data["version"] == "2.0.0"


# ── GET / (application root) ──────────────────────────────────────────────────

class TestAppRoot:
    def test_root_returns_welcome(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert "documentation" in data


# ── POST /api/check ───────────────────────────────────────────────────────────

class TestCheckForFraud:
    def test_successful_check_returns_200(self, client):
        with patch(
            "api.routes.analyze_text_for_fraud",
            new=AsyncMock(return_value=_fake_analysis_result()),
        ):
            resp = client.post(
                "/api/check",
                json={"message_text": "Hello, how are you?"},
            )
        assert resp.status_code == 200

    def test_successful_check_response_schema(self, client):
        with patch(
            "api.routes.analyze_text_for_fraud",
            new=AsyncMock(return_value=_fake_analysis_result()),
        ):
            resp = client.post(
                "/api/check",
                json={"message_text": "Hello, how are you?"},
            )
        data = resp.json()
        assert "scan_id" in data
        assert "is_fraud" in data
        assert "confidence_score" in data
        assert "analysis_reason" in data
        assert isinstance(data["urls_found"], list)
        assert isinstance(data["tools_used"], list)
        assert isinstance(data["agent_trace"], list)

    def test_fraud_result_persisted_to_db(self, client, db_session):
        with patch(
            "api.routes.analyze_text_for_fraud",
            new=AsyncMock(
                return_value=_fake_analysis_result(
                    is_fraud=True,
                    confidence=0.92,
                    reasoning="Scam detected.",
                )
            ),
        ):
            client.post("/api/check", json={"message_text": "Click here now!"})

        records = db_session.query(ScanRecord).all()
        assert len(records) == 1
        assert records[0].is_fraud is True
        assert records[0].message_text == "Click here now!"

    def test_sender_id_saved_when_provided(self, client, db_session):
        with patch(
            "api.routes.analyze_text_for_fraud",
            new=AsyncMock(return_value=_fake_analysis_result()),
        ):
            client.post(
                "/api/check",
                json={"message_text": "test", "sender_id": "9876543210"},
            )
        record = db_session.query(ScanRecord).first()
        assert record.sender_id == "9876543210"

    def test_value_error_returns_503(self, client):
        with patch(
            "api.routes.analyze_text_for_fraud",
            new=AsyncMock(side_effect=ValueError("API key missing")),
        ):
            resp = client.post(
                "/api/check",
                json={"message_text": "test message"},
            )
        assert resp.status_code == 503
        assert "API key missing" in resp.json()["detail"]

    def test_generic_exception_returns_500(self, client):
        with patch(
            "api.routes.analyze_text_for_fraud",
            new=AsyncMock(side_effect=RuntimeError("unexpected crash")),
        ):
            resp = client.post(
                "/api/check",
                json={"message_text": "test message"},
            )
        assert resp.status_code == 500

    def test_empty_message_returns_422(self, client):
        resp = client.post("/api/check", json={"message_text": ""})
        assert resp.status_code == 422

    def test_missing_message_returns_422(self, client):
        resp = client.post("/api/check", json={})
        assert resp.status_code == 422

    def test_message_too_long_returns_422(self, client):
        resp = client.post("/api/check", json={"message_text": "x" * 2001})
        assert resp.status_code == 422

    def test_agent_trace_returned_in_response(self, client):
        trace = [
            {
                "agent_name": "Scanner",
                "action": "Called pattern_match",
                "observation": "2 flags found",
                "timestamp": "2024-01-01T00:00:00+00:00",
            }
        ]
        with patch(
            "api.routes.analyze_text_for_fraud",
            new=AsyncMock(return_value=_fake_analysis_result(agent_trace=trace)),
        ):
            resp = client.post("/api/check", json={"message_text": "Urgent! Send money now."})
        data = resp.json()
        assert len(data["agent_trace"]) == 1
        assert data["agent_trace"][0]["agent_name"] == "Scanner"

    def test_urls_and_risk_level_returned(self, client):
        with patch(
            "api.routes.analyze_text_for_fraud",
            new=AsyncMock(
                return_value=_fake_analysis_result(
                    urls_found=["http://evil.tk/win"],
                    url_risk_level="malicious",
                )
            ),
        ):
            resp = client.post(
                "/api/check",
                json={"message_text": "Click http://evil.tk/win"},
            )
        data = resp.json()
        assert "http://evil.tk/win" in data["urls_found"]
        assert data["url_risk_level"] == "malicious"


# ── GET /api/history ──────────────────────────────────────────────────────────

class TestGetScanHistory:
    def test_empty_history_returns_empty_list(self, client):
        resp = client.get("/api/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_history_returns_persisted_records(self, client, db_session):
        record = _make_scan_record(message_text="prize scam message", is_fraud=True)
        db_session.add(record)
        db_session.commit()

        resp = client.get("/api/history")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["message_text"] == "prize scam message"
        assert data[0]["is_fraud"] is True

    def test_history_limit_parameter(self, client, db_session):
        for i in range(5):
            db_session.add(_make_scan_record(message_text=f"message {i}"))
        db_session.commit()

        resp = client.get("/api/history?limit=3")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_history_ordered_by_most_recent(self, client, db_session):
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        older = _make_scan_record(
            message_text="older message",
            created_at=now - timedelta(hours=1),
        )
        newer = _make_scan_record(
            message_text="newer message",
            created_at=now,
        )
        db_session.add(older)
        db_session.add(newer)
        db_session.commit()

        resp = client.get("/api/history")
        data = resp.json()
        assert data[0]["message_text"] == "newer message"

    def test_history_item_has_expected_fields(self, client, db_session):
        db_session.add(_make_scan_record())
        db_session.commit()

        resp = client.get("/api/history")
        item = resp.json()[0]
        for field in (
            "scan_id", "message_text", "is_fraud", "confidence_score",
            "analysis_reason", "urls_found", "tools_used", "agent_trace",
        ):
            assert field in item, f"Field '{field}' missing from history item"

    def test_history_parses_json_fields(self, client, db_session):
        record = _make_scan_record(
            urls_found=json.dumps(["https://evil.tk"]),
            tools_used=json.dumps(["extract_urls"]),
        )
        db_session.add(record)
        db_session.commit()

        resp = client.get("/api/history")
        item = resp.json()[0]
        assert item["urls_found"] == ["https://evil.tk"]
        assert item["tools_used"] == ["extract_urls"]


# ── GET /api/check/{scan_id}/trace ────────────────────────────────────────────

class TestGetScanTrace:
    def test_returns_trace_for_existing_scan(self, client, db_session):
        trace = [
            {
                "agent_name": "Reasoner",
                "action": "Delivered final verdict",
                "observation": "is_fraud=True, confidence=0.9",
                "timestamp": "2024-01-01T00:00:00+00:00",
            }
        ]
        record = _make_scan_record(agent_trace=json.dumps(trace))
        db_session.add(record)
        db_session.commit()

        resp = client.get(f"/api/check/{record.id}/trace")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["agent_name"] == "Reasoner"

    def test_returns_404_for_missing_scan(self, client):
        resp = client.get("/api/check/nonexistent-id/trace")
        assert resp.status_code == 404

    def test_returns_empty_list_when_no_trace(self, client, db_session):
        record = _make_scan_record(agent_trace=None)
        db_session.add(record)
        db_session.commit()

        resp = client.get(f"/api/check/{record.id}/trace")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_trace_step_has_required_fields(self, client, db_session):
        trace = [
            {
                "agent_name": "Scanner",
                "action": "Called lookup_known_scams",
                "observation": "0 matches",
                "timestamp": "2024-01-02T00:00:00+00:00",
            }
        ]
        record = _make_scan_record(agent_trace=json.dumps(trace))
        db_session.add(record)
        db_session.commit()

        resp = client.get(f"/api/check/{record.id}/trace")
        step = resp.json()[0]
        assert set(step.keys()) >= {"agent_name", "action", "observation", "timestamp"}


# ── GET /api/stats ────────────────────────────────────────────────────────────

class TestGetStats:
    def test_stats_with_no_records(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_scans"] == 0
        assert data["total_fraud_detected"] == 0
        assert data["fraud_percentage"] == 0.0
        assert data["total_urls_flagged"] == 0

    def test_stats_counts_total_scans(self, client, db_session):
        for _ in range(3):
            db_session.add(_make_scan_record())
        db_session.commit()

        resp = client.get("/api/stats")
        assert resp.json()["total_scans"] == 3

    def test_stats_counts_fraud_records(self, client, db_session):
        db_session.add(_make_scan_record(is_fraud=True))
        db_session.add(_make_scan_record(is_fraud=True))
        db_session.add(_make_scan_record(is_fraud=False))
        db_session.commit()

        resp = client.get("/api/stats")
        data = resp.json()
        assert data["total_fraud_detected"] == 2

    def test_stats_calculates_fraud_percentage(self, client, db_session):
        for _ in range(2):
            db_session.add(_make_scan_record(is_fraud=True))
        for _ in range(8):
            db_session.add(_make_scan_record(is_fraud=False))
        db_session.commit()

        resp = client.get("/api/stats")
        assert resp.json()["fraud_percentage"] == 20.0

    def test_stats_counts_flagged_urls(self, client, db_session):
        db_session.add(_make_scan_record(url_risk_level="malicious"))
        db_session.add(_make_scan_record(url_risk_level="suspicious"))
        db_session.add(_make_scan_record(url_risk_level="safe"))
        db_session.add(_make_scan_record(url_risk_level=None))
        db_session.commit()

        resp = client.get("/api/stats")
        assert resp.json()["total_urls_flagged"] == 2

    def test_stats_has_expected_fields(self, client):
        resp = client.get("/api/stats")
        data = resp.json()
        for field in ("total_scans", "total_fraud_detected", "fraud_percentage", "total_urls_flagged"):
            assert field in data
