"""Tests for pure functions in quiz_generator (no API calls)."""

from __future__ import annotations

import pytest

import services.quiz_generator as qg_mod

_strip_json_raw = qg_mod._strip_json_raw
_try_parse_json = qg_mod._try_parse_json
_validate_quiz = qg_mod._validate_quiz
EMPTY_QUIZ = qg_mod.EMPTY_QUIZ


# ──────────────────────────────────────────────────────────────
# _strip_json_raw
# ──────────────────────────────────────────────────────────────

class TestStripJsonRaw:
    def test_no_fences_unchanged(self):
        raw = '{"a": 1}'
        assert _strip_json_raw(raw) == '{"a": 1}'

    def test_strips_json_fences(self):
        raw = "```json\n{\"a\": 1}\n```"
        assert _strip_json_raw(raw) == '{"a": 1}'

    def test_strips_bare_fences(self):
        raw = "```\n{\"b\": 2}\n```"
        assert _strip_json_raw(raw) == '{"b": 2}'

    def test_strips_whitespace(self):
        raw = "   {\"c\": 3}   "
        assert _strip_json_raw(raw) == '{"c": 3}'

    def test_empty_string(self):
        assert _strip_json_raw("") == ""


# ──────────────────────────────────────────────────────────────
# _try_parse_json
# ──────────────────────────────────────────────────────────────

class TestTryParseJson:
    def test_valid_json_parsed(self):
        raw = '{"quiz_title": "Test", "questions": []}'
        result = _try_parse_json(raw)
        assert result["quiz_title"] == "Test"

    def test_fenced_json_parsed(self):
        raw = "```json\n{\"quiz_title\": \"X\", \"questions\": []}\n```"
        result = _try_parse_json(raw)
        assert result["quiz_title"] == "X"

    def test_embedded_json_extracted(self):
        raw = 'Here is the quiz: {"quiz_title": "Y", "questions": []} done.'
        result = _try_parse_json(raw)
        assert result["quiz_title"] == "Y"

    def test_invalid_json_returns_empty_quiz(self):
        result = _try_parse_json("total garbage")
        assert result == EMPTY_QUIZ

    def test_empty_string_returns_empty_quiz(self):
        result = _try_parse_json("")
        assert result == EMPTY_QUIZ


# ──────────────────────────────────────────────────────────────
# _validate_quiz
# ──────────────────────────────────────────────────────────────

class TestValidateQuiz:
    def _make_question(self, **kwargs) -> dict:
        base = {
            "id": 1,
            "type": "MCQ",
            "question": "What is 2+2?",
            "options": ["1", "2", "4", "8"],
            "correct_answer": "4",
            "explanation": "Basic arithmetic.",
            "answer_en": "4",
            "answer_zh": "4",
            "explanation_en": "Basic arithmetic.",
            "explanation_zh": "基本算术。",
        }
        base.update(kwargs)
        return base

    def test_valid_quiz_passes_through(self):
        obj = {
            "quiz_title": "Math Quiz",
            "questions": [self._make_question()],
        }
        result = _validate_quiz(obj)
        assert result["quiz_title"] == "Math Quiz"
        assert len(result["questions"]) == 1

    def test_non_dict_returns_empty(self):
        assert _validate_quiz([1, 2, 3]) == EMPTY_QUIZ
        assert _validate_quiz(None) == EMPTY_QUIZ  # type: ignore[arg-type]
        assert _validate_quiz("string") == EMPTY_QUIZ  # type: ignore[arg-type]

    def test_missing_questions_returns_empty_list(self):
        result = _validate_quiz({"quiz_title": "T"})
        assert result["questions"] == []

    def test_invalid_questions_value_treated_as_empty(self):
        result = _validate_quiz({"quiz_title": "T", "questions": "not a list"})
        assert result["questions"] == []

    def test_question_fields_normalized(self):
        q = self._make_question()
        del q["answer_zh"]  # missing field should default to ""
        result = _validate_quiz({"quiz_title": "T", "questions": [q]})
        assert result["questions"][0]["answer_zh"] == ""

    def test_answer_en_falls_back_to_correct_answer(self):
        q = {
            "id": 1,
            "type": "MCQ",
            "question": "Q?",
            "options": ["A", "B", "C", "D"],
            "correct_answer": "B",
            "explanation": "Exp",
        }
        result = _validate_quiz({"quiz_title": "T", "questions": [q]})
        assert result["questions"][0]["answer_en"] == "B"

    def test_non_dict_question_skipped(self):
        result = _validate_quiz({"quiz_title": "T", "questions": ["not a dict", None]})
        assert result["questions"] == []

    def test_multiple_questions(self):
        questions = [self._make_question(id=i, question=f"Q{i}?") for i in range(1, 6)]
        result = _validate_quiz({"quiz_title": "Big Quiz", "questions": questions})
        assert len(result["questions"]) == 5

    def test_options_preserved_as_list(self):
        q = self._make_question(options=["W", "X", "Y", "Z"])
        result = _validate_quiz({"quiz_title": "T", "questions": [q]})
        assert result["questions"][0]["options"] == ["W", "X", "Y", "Z"]

    def test_options_invalid_becomes_empty_list(self):
        q = self._make_question(options="not a list")
        result = _validate_quiz({"quiz_title": "T", "questions": [q]})
        assert result["questions"][0]["options"] == []

    def test_quiz_title_stringified(self):
        result = _validate_quiz({"quiz_title": 42, "questions": []})
        assert result["quiz_title"] == "42"
