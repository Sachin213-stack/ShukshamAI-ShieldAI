# tests/test_llm_service.py
# Unit tests for core/llm_service.py — the agentic pipeline entry point.
# The LangGraph graph is mocked so no real LLM calls are made.

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestAnalyzeTextForFraud:
    """Tests for core.llm_service.analyze_text_for_fraud."""

    def _final_state(self, **overrides):
        """Return a realistic mock final graph state."""
        base = {
            "message_text": "test message",
            "sender_id": None,
            "is_fraud": False,
            "confidence": 0.1,
            "reasoning": "No fraud indicators.",
            "evidence_summary": "",
            "urls_found": [],
            "url_safety_results": [],
            "web_search_results": [],
            "sender_reputation": None,
            "audit_log": [],
            "tools_used": ["extract_urls"],
            "pattern_flags": [],
            "known_scam_matches": [],
            "scanner_risk_score": 0.1,
            "next_agent": "reasoner",
            "messages": [],
        }
        base.update(overrides)
        return base

    @pytest.mark.asyncio
    async def test_raises_when_api_key_missing(self):
        """Should raise ValueError immediately if GEMINI_API_KEY is not set."""
        with patch("core.llm_service.Config") as mock_cfg:
            mock_cfg.GEMINI_API_KEY = None
            from core.llm_service import analyze_text_for_fraud
            with pytest.raises(ValueError, match="AI configuration is missing"):
                await analyze_text_for_fraud("test message")

    @pytest.mark.asyncio
    async def test_returns_dict_on_success(self):
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value=self._final_state())

        with patch("core.llm_service.Config") as mock_cfg, \
             patch("core.llm_service.fraud_detection_graph", mock_graph):
            mock_cfg.GEMINI_API_KEY = "fake-key"
            from core.llm_service import analyze_text_for_fraud
            result = await analyze_text_for_fraud("Hello world")

        assert isinstance(result, dict)
        assert "is_fraud" in result
        assert "confidence" in result
        assert "reasoning" in result
        assert "evidence_summary" in result
        assert "urls_found" in result
        assert "url_risk_level" in result
        assert "agent_trace" in result
        assert "tools_used" in result

    @pytest.mark.asyncio
    async def test_fraud_result_propagated_correctly(self):
        state = self._final_state(
            is_fraud=True,
            confidence=0.95,
            reasoning="Multiple scam signals detected.",
        )
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value=state)

        with patch("core.llm_service.Config") as mock_cfg, \
             patch("core.llm_service.fraud_detection_graph", mock_graph):
            mock_cfg.GEMINI_API_KEY = "fake-key"
            from core.llm_service import analyze_text_for_fraud
            result = await analyze_text_for_fraud("You have won a prize!")

        assert result["is_fraud"] is True
        assert result["confidence"] == 0.95
        assert result["reasoning"] == "Multiple scam signals detected."

    @pytest.mark.asyncio
    async def test_url_risk_level_malicious_when_any_malicious(self):
        state = self._final_state(
            url_safety_results=[
                {"url": "http://evil.tk", "risk_level": "malicious", "reasons": []},
                {"url": "https://safe.com", "risk_level": "safe", "reasons": []},
            ]
        )
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value=state)

        with patch("core.llm_service.Config") as mock_cfg, \
             patch("core.llm_service.fraud_detection_graph", mock_graph):
            mock_cfg.GEMINI_API_KEY = "fake-key"
            from core.llm_service import analyze_text_for_fraud
            result = await analyze_text_for_fraud("Click http://evil.tk")

        assert result["url_risk_level"] == "malicious"

    @pytest.mark.asyncio
    async def test_url_risk_level_suspicious_when_none_malicious(self):
        state = self._final_state(
            url_safety_results=[
                {"url": "https://bit.ly/abc", "risk_level": "suspicious", "reasons": []},
            ]
        )
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value=state)

        with patch("core.llm_service.Config") as mock_cfg, \
             patch("core.llm_service.fraud_detection_graph", mock_graph):
            mock_cfg.GEMINI_API_KEY = "fake-key"
            from core.llm_service import analyze_text_for_fraud
            result = await analyze_text_for_fraud("test")

        assert result["url_risk_level"] == "suspicious"

    @pytest.mark.asyncio
    async def test_url_risk_level_safe_when_all_safe(self):
        state = self._final_state(
            url_safety_results=[
                {"url": "https://google.com", "risk_level": "safe", "reasons": []},
            ]
        )
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value=state)

        with patch("core.llm_service.Config") as mock_cfg, \
             patch("core.llm_service.fraud_detection_graph", mock_graph):
            mock_cfg.GEMINI_API_KEY = "fake-key"
            from core.llm_service import analyze_text_for_fraud
            result = await analyze_text_for_fraud("test")

        assert result["url_risk_level"] == "safe"

    @pytest.mark.asyncio
    async def test_url_risk_level_none_when_no_urls(self):
        state = self._final_state(url_safety_results=[])
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value=state)

        with patch("core.llm_service.Config") as mock_cfg, \
             patch("core.llm_service.fraud_detection_graph", mock_graph):
            mock_cfg.GEMINI_API_KEY = "fake-key"
            from core.llm_service import analyze_text_for_fraud
            result = await analyze_text_for_fraud("no links here")

        assert result["url_risk_level"] is None

    @pytest.mark.asyncio
    async def test_tools_used_deduplicated(self):
        state = self._final_state(
            tools_used=["extract_urls", "pattern_match", "extract_urls"]
        )
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value=state)

        with patch("core.llm_service.Config") as mock_cfg, \
             patch("core.llm_service.fraud_detection_graph", mock_graph):
            mock_cfg.GEMINI_API_KEY = "fake-key"
            from core.llm_service import analyze_text_for_fraud
            result = await analyze_text_for_fraud("test")

        # tools_used should not have duplicates
        assert len(result["tools_used"]) == len(set(result["tools_used"]))

    @pytest.mark.asyncio
    async def test_re_raises_graph_exceptions(self):
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("graph crashed"))

        with patch("core.llm_service.Config") as mock_cfg, \
             patch("core.llm_service.fraud_detection_graph", mock_graph):
            mock_cfg.GEMINI_API_KEY = "fake-key"
            from core.llm_service import analyze_text_for_fraud
            with pytest.raises(RuntimeError, match="graph crashed"):
                await analyze_text_for_fraud("test")

    @pytest.mark.asyncio
    async def test_sender_id_passed_to_initial_state(self):
        captured = {}

        async def capture_invoke(state):
            captured["state"] = state
            return self._final_state()

        mock_graph = MagicMock()
        mock_graph.ainvoke = capture_invoke

        with patch("core.llm_service.Config") as mock_cfg, \
             patch("core.llm_service.fraud_detection_graph", mock_graph):
            mock_cfg.GEMINI_API_KEY = "fake-key"
            from core.llm_service import analyze_text_for_fraud
            await analyze_text_for_fraud("test message", sender_id="9876543210")

        assert captured["state"]["sender_id"] == "9876543210"
        assert captured["state"]["message_text"] == "test message"
