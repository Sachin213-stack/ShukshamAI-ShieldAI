# tests/test_agent_state.py
# Tests for core/agent_state.py — shared state helpers.

from core.agent_state import merge_lists, AgentStepLog


class TestMergeLists:
    def test_merge_two_non_empty_lists(self):
        assert merge_lists([1, 2], [3, 4]) == [1, 2, 3, 4]

    def test_merge_left_empty(self):
        assert merge_lists([], [1, 2, 3]) == [1, 2, 3]

    def test_merge_right_empty(self):
        assert merge_lists([1, 2, 3], []) == [1, 2, 3]

    def test_merge_both_empty(self):
        assert merge_lists([], []) == []

    def test_merge_preserves_order(self):
        result = merge_lists(["a", "b"], ["c", "d"])
        assert result == ["a", "b", "c", "d"]

    def test_merge_with_duplicate_values(self):
        # merge_lists does not deduplicate — all items are kept
        result = merge_lists(["x"], ["x"])
        assert result == ["x", "x"]

    def test_merge_mixed_types(self):
        result = merge_lists([1, "a"], [True, None])
        assert result == [1, "a", True, None]


class TestAgentStepLog:
    def test_valid_step_log_creation(self):
        step: AgentStepLog = {
            "agent_name": "Scanner",
            "action": "Called extract_urls",
            "observation": "[]",
            "timestamp": "2024-01-01T00:00:00+00:00",
        }
        assert step["agent_name"] == "Scanner"
        assert step["action"] == "Called extract_urls"
        assert step["observation"] == "[]"
        assert step["timestamp"] == "2024-01-01T00:00:00+00:00"

    def test_step_log_is_dict_compatible(self):
        step: AgentStepLog = {
            "agent_name": "Reasoner",
            "action": "Delivered final verdict",
            "observation": "is_fraud=True, confidence=0.95",
            "timestamp": "2024-01-01T01:00:00+00:00",
        }
        assert isinstance(step, dict)
        assert set(step.keys()) == {"agent_name", "action", "observation", "timestamp"}
