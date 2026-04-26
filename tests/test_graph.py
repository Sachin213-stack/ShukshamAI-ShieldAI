# tests/test_graph.py
# Unit tests for routing logic in core/graph.py.

from core.graph import _route_after_scanner


class TestRouteAfterScanner:
    def _state(self, next_agent="researcher"):
        """Return a minimal state dict for routing tests."""
        return {"next_agent": next_agent}

    def test_routes_to_researcher_when_state_says_researcher(self):
        result = _route_after_scanner(self._state("researcher"))
        assert result == "researcher"

    def test_routes_to_reasoner_when_state_says_reasoner(self):
        result = _route_after_scanner(self._state("reasoner"))
        assert result == "reasoner"

    def test_defaults_to_researcher_when_key_missing(self):
        # next_agent key not present → default is "researcher"
        result = _route_after_scanner({})
        assert result == "researcher"

    def test_state_with_extra_keys_still_routes_correctly(self):
        state = {
            "next_agent": "reasoner",
            "scanner_risk_score": 0.95,
            "urls_found": ["http://evil.tk"],
        }
        assert _route_after_scanner(state) == "reasoner"
