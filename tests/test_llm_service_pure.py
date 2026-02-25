"""Tests for pure JSON parsing helpers in llm_service (no API calls)."""

from __future__ import annotations

import pytest

# Import the module-level helpers directly
import services.llm_service as llm_mod

_extract_json_object = llm_mod._extract_json_object
_extract_json_array = llm_mod._extract_json_array


# ──────────────────────────────────────────────────────────────
# _extract_json_object
# ──────────────────────────────────────────────────────────────

class TestExtractJsonObject:
    def test_plain_json(self):
        raw = '{"key": "value", "num": 42}'
        result = _extract_json_object(raw)
        assert result == {"key": "value", "num": 42}

    def test_strips_markdown_fences(self):
        raw = '```json\n{"a": 1}\n```'
        result = _extract_json_object(raw)
        assert result == {"a": 1}

    def test_strips_bare_fences(self):
        raw = "```\n{\"x\": true}\n```"
        result = _extract_json_object(raw)
        assert result == {"x": True}

    def test_extracts_embedded_object(self):
        raw = 'Some text before {"found": "yes"} and after'
        result = _extract_json_object(raw)
        assert result == {"found": "yes"}

    def test_nested_object(self):
        raw = '{"outer": {"inner": [1, 2, 3]}}'
        result = _extract_json_object(raw)
        assert result["outer"]["inner"] == [1, 2, 3]

    def test_empty_string_returns_empty_dict(self):
        assert _extract_json_object("") == {}

    def test_invalid_json_returns_empty_dict(self):
        assert _extract_json_object("not json at all") == {}

    def test_array_not_returned_as_object(self):
        # An array at top level should return empty dict (must be dict)
        result = _extract_json_object('[1, 2, 3]')
        assert result == {}

    def test_whitespace_around_fences(self):
        raw = "  ```json\n  {\"k\": \"v\"}\n  ```  "
        result = _extract_json_object(raw)
        assert result == {"k": "v"}


# ──────────────────────────────────────────────────────────────
# _extract_json_array
# ──────────────────────────────────────────────────────────────

class TestExtractJsonArray:
    def test_plain_array(self):
        raw = '[{"front": "Q1", "back": "A1"}, {"front": "Q2", "back": "A2"}]'
        result = _extract_json_array(raw)
        assert len(result) == 2
        assert result[0]["front"] == "Q1"

    def test_strips_markdown_fences(self):
        raw = '```json\n[1, 2, 3]\n```'
        result = _extract_json_array(raw)
        assert result == [1, 2, 3]

    def test_extracts_embedded_array(self):
        raw = 'Prefix text [{"a": 1}] suffix'
        result = _extract_json_array(raw)
        assert result == [{"a": 1}]

    def test_empty_string_returns_empty_list(self):
        assert _extract_json_array("") == []

    def test_invalid_json_returns_empty_list(self):
        assert _extract_json_array("garbage") == []

    def test_object_not_returned_as_array(self):
        # Top-level object should return empty list (must be list)
        result = _extract_json_array('{"key": "val"}')
        assert result == []

    def test_empty_array(self):
        assert _extract_json_array("[]") == []

    def test_nested_arrays(self):
        raw = '[[1, 2], [3, 4]]'
        result = _extract_json_array(raw)
        assert result == [[1, 2], [3, 4]]
