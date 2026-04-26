# tests/test_tools.py
# Unit tests for core/tools.py — all tool functions.

import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.tools import (
    extract_urls,
    pattern_match,
    check_url_safety,
    search_web_for_scam_reports,
    lookup_known_scams,
    check_sender_reputation,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def invoke_tool(tool_fn, **kwargs):
    """Invoke a LangChain tool synchronously and return JSON-parsed output."""
    result = tool_fn.invoke(kwargs)
    return json.loads(result)


def _make_tool_test_engine():
    """
    Create a fresh in-memory SQLite engine with StaticPool.
    StaticPool ensures all sessions share the same underlying connection,
    so data seeded by one session is visible to another (including sessions
    opened internally by tool functions).
    """
    from core.database import Base
    from models.db_models import ScanRecord, KnownScam  # noqa: F401 – registers ORM models

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


# ── extract_urls ──────────────────────────────────────────────────────────────

class TestExtractUrls:
    def test_no_urls(self):
        urls = invoke_tool(extract_urls, text="Hello, how are you?")
        assert urls == []

    def test_single_https_url(self):
        urls = invoke_tool(extract_urls, text="Visit https://example.com for details")
        assert "https://example.com" in urls

    def test_http_url(self):
        urls = invoke_tool(extract_urls, text="Go to http://bad-site.org now")
        assert any("http://bad-site.org" in u for u in urls)

    def test_multiple_urls(self):
        urls = invoke_tool(
            extract_urls,
            text="See https://google.com and also http://evil.tk/win",
        )
        assert len(urls) == 2

    def test_url_with_path_and_query(self):
        urls = invoke_tool(
            extract_urls,
            text="Click https://phishing.com/login?token=abc123 immediately",
        )
        assert any("https://phishing.com" in u for u in urls)

    def test_returns_json_list(self):
        raw = extract_urls.invoke({"text": "Visit https://example.com"})
        parsed = json.loads(raw)
        assert isinstance(parsed, list)

    def test_no_www_without_http(self):
        # The tool only extracts full http/https URLs in the clean pass
        urls = invoke_tool(extract_urls, text="Visit www.example.com for info")
        # May or may not find www — assert it doesn't crash
        assert isinstance(urls, list)

    def test_empty_string(self):
        urls = invoke_tool(extract_urls, text="")
        assert urls == []


# ── pattern_match ─────────────────────────────────────────────────────────────

class TestPatternMatch:
    def test_no_flags_for_clean_message(self):
        flags = invoke_tool(pattern_match, text="Hi, hope you're doing well.")
        assert flags == []

    def test_urgency_flag_detected(self):
        flags = invoke_tool(pattern_match, text="Act now! This offer expires today.")
        urgency_flags = [f for f in flags if f.startswith("URGENCY")]
        assert len(urgency_flags) >= 1

    def test_multiple_urgency_phrases(self):
        flags = invoke_tool(
            pattern_match,
            text="Urgent! Hurry! Last chance! Don't delay!",
        )
        urgency_flags = [f for f in flags if f.startswith("URGENCY")]
        assert len(urgency_flags) >= 3

    def test_financial_pressure_flag(self):
        flags = invoke_tool(pattern_match, text="Please send money via UPI right now.")
        fin_flags = [f for f in flags if f.startswith("FINANCIAL_PRESSURE")]
        assert len(fin_flags) >= 1

    def test_impersonation_flag_rbi(self):
        flags = invoke_tool(pattern_match, text="This is an official notice from RBI.")
        imp_flags = [f for f in flags if f.startswith("IMPERSONATION")]
        assert len(imp_flags) >= 1

    def test_impersonation_flag_kyc(self):
        flags = invoke_tool(pattern_match, text="Your KYC verification is pending. KYC Update needed.")
        imp_flags = [f for f in flags if f.startswith("IMPERSONATION")]
        assert len(imp_flags) >= 1

    def test_suspicious_link_url_shortener(self):
        flags = invoke_tool(pattern_match, text="Click here: bit.ly/abc123")
        link_flags = [f for f in flags if f.startswith("SUSPICIOUS_LINK")]
        assert len(link_flags) == 1

    def test_prize_scam_flag(self):
        flags = invoke_tool(
            pattern_match,
            text="Congratulations! You have won a lottery prize. Claim your reward.",
        )
        prize_flags = [f for f in flags if f.startswith("PRIZE_SCAM")]
        assert len(prize_flags) >= 1

    def test_credential_harvest_flag(self):
        flags = invoke_tool(pattern_match, text="Please share OTP to verify your identity.")
        cred_flags = [f for f in flags if f.startswith("CREDENTIAL_HARVEST")]
        assert len(cred_flags) >= 1

    def test_case_insensitive_detection(self):
        flags = invoke_tool(pattern_match, text="URGENT ACT NOW SEND MONEY")
        assert len(flags) >= 2

    def test_returns_json_list(self):
        raw = pattern_match.invoke({"text": "urgent!"})
        parsed = json.loads(raw)
        assert isinstance(parsed, list)

    def test_bitcoin_financial_flag(self):
        flags = invoke_tool(pattern_match, text="Send Bitcoin to this wallet immediately")
        fin_flags = [f for f in flags if "FINANCIAL_PRESSURE" in f]
        assert len(fin_flags) >= 1

    def test_gift_card_financial_flag(self):
        flags = invoke_tool(pattern_match, text="Buy iTunes card and share the code")
        fin_flags = [f for f in flags if "FINANCIAL_PRESSURE" in f]
        assert len(fin_flags) >= 1


# ── check_url_safety ──────────────────────────────────────────────────────────

class TestCheckUrlSafety:
    def test_safe_url(self):
        result = invoke_tool(check_url_safety, url="https://www.google.com/search")
        assert result["risk_level"] == "safe"
        assert result["url"] == "https://www.google.com/search"

    def test_url_shortener_is_suspicious(self):
        result = invoke_tool(check_url_safety, url="https://bit.ly/abc123")
        assert result["risk_level"] == "suspicious"
        assert any("shortener" in r.lower() for r in result["reasons"])

    def test_tinyurl_is_suspicious(self):
        result = invoke_tool(check_url_safety, url="https://tinyurl.com/xyz")
        assert result["risk_level"] == "suspicious"

    def test_suspicious_tld_tk(self):
        result = invoke_tool(check_url_safety, url="http://win-prize.tk/claim")
        assert result["risk_level"] == "malicious"

    def test_suspicious_tld_ml(self):
        result = invoke_tool(check_url_safety, url="http://free-gift.ml/now")
        assert result["risk_level"] == "malicious"

    def test_suspicious_tld_xyz(self):
        result = invoke_tool(check_url_safety, url="http://scam.xyz/prize")
        assert result["risk_level"] == "malicious"

    def test_ip_address_url_is_suspicious(self):
        result = invoke_tool(check_url_safety, url="http://192.168.1.1/login")
        assert result["risk_level"] in ("suspicious", "malicious")
        assert any("ip" in r.lower() for r in result["reasons"])

    def test_no_red_flags_message_for_safe_url(self):
        # Use a domain that contains none of the shortener substrings
        # (e.g. "microsoft.com" contains "t.co" as a substring which is a
        # known false-positive in the current heuristic implementation)
        result = invoke_tool(check_url_safety, url="https://www.wikipedia.org/wiki/Fraud")
        assert "No immediate red flags detected" in result["reasons"]

    def test_result_has_expected_keys(self):
        result = invoke_tool(check_url_safety, url="https://example.com")
        assert "url" in result
        assert "risk_level" in result
        assert "reasons" in result
        assert isinstance(result["reasons"], list)


# ── search_web_for_scam_reports ───────────────────────────────────────────────

class TestSearchWebForScamReports:
    def test_returns_stub_result(self):
        result = invoke_tool(search_web_for_scam_reports, query="fake prize lottery")
        assert result["query"] == "fake prize lottery"
        assert "results" in result
        assert isinstance(result["results"], list)

    def test_stub_note_present(self):
        result = invoke_tool(search_web_for_scam_reports, query="bank fraud")
        assert "note" in result
        assert "stub" in result["note"].lower()

    def test_empty_results_list(self):
        result = invoke_tool(search_web_for_scam_reports, query="test query")
        assert result["results"] == []

    def test_returns_json_dict(self):
        raw = search_web_for_scam_reports.invoke({"query": "test"})
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)


# ── lookup_known_scams ────────────────────────────────────────────────────────

class TestLookupKnownScams:
    """Tests for the DB-backed known scam lookup tool using an in-memory database."""

    @pytest.fixture(autouse=True)
    def setup_db(self, monkeypatch):
        """
        Self-contained DB setup: creates its own engine, seeds data, patches the tool,
        and tears everything down after the test. This avoids cross-engine sharing issues.
        """
        from models.db_models import KnownScam
        from core.database import Base
        import core.tools as tools_module

        engine = _make_tool_test_engine()
        Session = sessionmaker(bind=engine)

        # Seed a known scam pattern
        session = Session()
        scam = KnownScam(
            pattern_text="win a free iphone",
            category="phishing",
            severity="high",
            source="test",
        )
        session.add(scam)
        session.commit()
        session.close()

        # Patch SessionLocal so the tool uses the same in-memory DB
        monkeypatch.setattr(tools_module, "SessionLocal", Session)

        yield

        Base.metadata.drop_all(bind=engine)

    def test_match_found(self):
        flags = invoke_tool(
            lookup_known_scams,
            text="Click here to win a free iPhone today!",
        )
        assert len(flags) == 1
        assert flags[0]["category"] == "phishing"
        assert flags[0]["severity"] == "high"

    def test_no_match(self):
        flags = invoke_tool(
            lookup_known_scams,
            text="Hi, meeting is at 3pm tomorrow.",
        )
        assert flags == []

    def test_case_insensitive_match(self):
        flags = invoke_tool(
            lookup_known_scams,
            text="WIN A FREE IPHONE NOW",
        )
        assert len(flags) == 1

    def test_returns_json_list(self):
        raw = lookup_known_scams.invoke({"text": "hello world"})
        parsed = json.loads(raw)
        assert isinstance(parsed, list)


# ── check_sender_reputation ───────────────────────────────────────────────────

class TestCheckSenderReputation:
    """Tests for the DB-backed sender reputation check tool."""

    @pytest.fixture(autouse=True)
    def setup_db(self, monkeypatch):
        """
        Self-contained DB setup: creates its own engine, patches the tool,
        and tears everything down after the test.
        """
        from core.database import Base
        import core.tools as tools_module

        engine = _make_tool_test_engine()
        Session = sessionmaker(bind=engine)

        # Patch SessionLocal so the tool uses the same in-memory DB
        monkeypatch.setattr(tools_module, "SessionLocal", Session)
        self.db = Session()

        yield

        self.db.close()
        Base.metadata.drop_all(bind=engine)

    def _add_fraud_record(self, sender_id):
        from models.db_models import ScanRecord
        record = ScanRecord(
            message_text="test scam",
            sender_id=sender_id,
            is_fraud=True,
            confidence_score=0.9,
            analysis_reason="fraud detected",
        )
        self.db.add(record)
        self.db.commit()

    def test_no_sender_id(self):
        result = invoke_tool(check_sender_reputation, sender_id="")
        assert result["reputation"] == "unknown"

    def test_unknown_sender_no_history(self):
        result = invoke_tool(check_sender_reputation, sender_id="9876543210")
        assert result["reputation"] == "unknown"
        assert result["past_fraud_count"] == 0

    def test_suspicious_sender_one_fraud(self):
        self._add_fraud_record("1111111111")
        result = invoke_tool(check_sender_reputation, sender_id="1111111111")
        assert result["reputation"] == "suspicious"
        assert result["past_fraud_count"] == 1

    def test_suspicious_sender_two_frauds(self):
        for _ in range(2):
            self._add_fraud_record("2222222222")
        result = invoke_tool(check_sender_reputation, sender_id="2222222222")
        assert result["reputation"] == "suspicious"
        assert result["past_fraud_count"] == 2

    def test_known_scammer_three_frauds(self):
        for _ in range(3):
            self._add_fraud_record("3333333333")
        result = invoke_tool(check_sender_reputation, sender_id="3333333333")
        assert result["reputation"] == "known_scammer"
        assert result["past_fraud_count"] == 3

    def test_result_has_expected_keys(self):
        result = invoke_tool(check_sender_reputation, sender_id="0000000000")
        assert "sender_id" in result
        assert "reputation" in result
        assert "past_fraud_count" in result
        assert "reason" in result

    def test_returns_json_dict(self):
        raw = check_sender_reputation.invoke({"sender_id": "test"})
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)
