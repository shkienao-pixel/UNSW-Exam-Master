"""
Exam logic: generate and validate quiz JSON from course content.
"""

import json
import re
from typing import Any

from services.llm_service import LLMProcessor

QUIZ_SYSTEM_PROMPT = (
    "你是一个 UNSW 考试出题助手。根据用户提供的课程文本，生成指定数量的单选题。"
    "你必须只输出一个合法的 JSON 对象，不要用 markdown 代码块包裹，不要输出任何 JSON 以外的文字。"
    "JSON 结构必须严格如下（注意字段名和类型）：\n"
    '{"quiz_title": "字符串", "questions": [{"id": 1, "type": "MCQ", "question": "题目文本", '
    '"options": ["A", "B", "C", "D"], "correct_answer": "正确选项的完整文本", "explanation": "解析说明"}]}'
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
        out_questions.append({
            "id": q.get("id", i + 1),
            "type": q.get("type", "MCQ"),
            "question": str(q.get("question", "")),
            "options": list(q.get("options", [])) if isinstance(q.get("options"), list) else [],
            "correct_answer": str(q.get("correct_answer", "")),
            "explanation": str(q.get("explanation", "")),
        })
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
        user_message = (
            f"请根据以下课程内容，生成恰好 {num_questions} 道单选题。"
            "每道题必须有 4 个选项，correct_answer 为正确选项的完整文本，explanation 为解析。\n\n"
            f"{text[:12000]}"
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