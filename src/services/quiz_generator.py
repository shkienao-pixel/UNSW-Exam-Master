"""
Exam logic: generate and validate quiz JSON from course content.
"""

from __future__ import annotations

import json
import re
from typing import Any

from services.llm_service import LLMProcessor

QUIZ_SYSTEM_PROMPT = (
    "You are a UNSW exam question writer. "
    "Return ONLY valid JSON (no markdown, no extra text). "
    "Generate MCQ questions from the provided course content with exactly 4 options each. "
    "JSON schema:\n"
    "{\n"
    '  "quiz_title": "string",\n'
    '  "questions": [\n'
    "    {\n"
    '      "id": 1,\n'
    '      "type": "MCQ",\n'
    '      "question": "string",\n'
    '      "options": ["A", "B", "C", "D"],\n'
    '      "correct_answer": "string",\n'
    '      "explanation": "string",\n'
    '      "answer_en": "string",\n'
    '      "answer_zh": "string",\n'
    '      "explanation_en": "string",\n'
    '      "explanation_zh": "string"\n'
    "    }\n"
    "  ]\n"
    "}"
)

EMPTY_QUIZ: dict[str, Any] = {"quiz_title": "", "questions": []}


def _strip_json_raw(raw: str) -> str:
    """Remove markdown code fences and surrounding whitespace from LLM output."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def _try_parse_json(raw: str) -> dict[str, Any]:
    """
    Parse JSON from LLM output. Tries raw parse, then stripped, then first { to last }.
    Returns EMPTY_QUIZ on failure.
    """
    for candidate in [raw, _strip_json_raw(raw)]:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return EMPTY_QUIZ.copy()


def _validate_quiz(obj: Any) -> dict[str, Any]:
    """Ensure structure has quiz_title and questions list; normalize to expected shape."""
    if not isinstance(obj, dict):
        return EMPTY_QUIZ.copy()
    title = obj.get("quiz_title")
    questions = obj.get("questions")
    if not isinstance(questions, list):
        questions = []
    out_questions: list[dict[str, Any]] = []
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            continue
        normalized = {
            "id": q.get("id", i + 1),
            "type": q.get("type", "MCQ"),
            "question": str(q.get("question", "")),
            "options": list(q.get("options", [])) if isinstance(q.get("options"), list) else [],
            "correct_answer": str(q.get("correct_answer", "")),
            "explanation": str(q.get("explanation", "")),
            "answer_en": str(q.get("answer_en", q.get("correct_answer", ""))),
            "answer_zh": str(q.get("answer_zh", "")),
            "explanation_en": str(q.get("explanation_en", q.get("explanation", ""))),
            "explanation_zh": str(q.get("explanation_zh", "")),
        }
        out_questions.append(normalized)
    return {"quiz_title": str(title) if title else "", "questions": out_questions}


class QuizGenerator:
    """Generates MCQ quizzes from course text via LLM."""

    def __init__(self) -> None:
        self._llm = LLMProcessor()

    def generate_quiz(self, text: str, num_questions: int = 5, api_key: str = "") -> dict[str, Any]:
        """
        Generate a quiz as a JSON-schema dict from course text.

        Args:
            text: Raw course material text (e.g. from PDF).
            num_questions: Number of MCQ questions to generate.
            api_key: OpenAI API key.

        Returns:
            Dict with keys "quiz_title" and "questions" (list of question dicts).
            On parse or API failure, returns structure with empty questions.
        """
        if not (api_key and api_key.strip()):
            return EMPTY_QUIZ.copy()
        safe_num = max(1, min(int(num_questions), 50))
        user_message = (
            f"Generate exactly {safe_num} MCQ questions from the following scope-limited course text.\n"
            "Requirements:\n"
            "- Exactly 4 options per question.\n"
            "- Include correct_answer and explanation.\n"
            "- Also include bilingual fields: answer_en, answer_zh, explanation_en, explanation_zh.\n"
            "- Keep explanations concise and exam-focused.\n\n"
            f"{text[:30000]}"
        )
        try:
            raw = self._llm.invoke(
                QUIZ_SYSTEM_PROMPT,
                user_message,
                api_key=api_key.strip(),
                temperature=0.4,
            )
        except ValueError:
            return EMPTY_QUIZ.copy()
        if not raw:
            return EMPTY_QUIZ.copy()
        parsed = _try_parse_json(raw)
        return _validate_quiz(parsed)
