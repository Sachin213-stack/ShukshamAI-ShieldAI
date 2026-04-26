# tests/test_agents.py
# Unit tests for pure helper functions in core/agents.py.

from core.agents import _extract_text


class TestExtractText:
    def test_string_input_returned_as_is(self):
        assert _extract_text("hello world") == "hello world"

    def test_empty_string(self):
        assert _extract_text("") == ""

    def test_list_of_strings(self):
        result = _extract_text(["hello", " ", "world"])
        assert result == "hello   world"

    def test_list_of_dicts_with_text_key(self):
        parts = [{"text": "part one"}, {"text": "part two"}]
        result = _extract_text(parts)
        assert result == "part one part two"

    def test_mixed_list_with_string_and_dict(self):
        parts = ["intro ", {"text": "body"}, {"other_key": "ignored"}]
        result = _extract_text(parts)
        assert "intro " in result
        assert "body" in result

    def test_list_with_non_text_parts_ignored(self):
        # Parts without 'text' key (e.g. image blobs) should be silently skipped
        parts = [{"type": "image", "data": b"\x00"}, {"text": "caption"}]
        result = _extract_text(parts)
        assert "caption" in result

    def test_integer_input_returns_str(self):
        result = _extract_text(42)
        assert result == "42"

    def test_none_input_returns_str(self):
        result = _extract_text(None)
        assert result == "None"

    def test_empty_list_returns_empty_string(self):
        result = _extract_text([])
        assert result == ""

    def test_list_with_all_non_text_dicts(self):
        parts = [{"type": "blob"}, {"kind": "media"}]
        result = _extract_text(parts)
        # No text parts → joined empty strings
        assert result == ""
