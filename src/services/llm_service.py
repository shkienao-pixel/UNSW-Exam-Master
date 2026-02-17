"""
LLM orchestration: summaries, chains, and prompts.
"""

import base64
import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

SYSTEM_PROMPT = (
    "你是一个 UNSW 的助教。请将以下课程内容总结为结构化的复习笔记。"
    "包含：核心概念、关键公式（使用 LaTeX）、考试重点。请使用 Markdown 格式。"
)

SYLLABUS_SYSTEM_PROMPT = """你是一个 UNSW 课程规划师。请分析上传的课程内容，提取出一份复习大纲。对于每个知识点，评估其考试重要性（High/Medium/Low）。

你必须只输出一个合法的 JSON 对象，不要用 markdown 代码块包裹，不要输出任何 JSON 以外的文字。

JSON 结构必须严格如下：
{
  "module_title": "章节或模块标题，如 Image Formation",
  "topics": [
    {"topic": "知识点名称", "priority": "High", "status": "Pending"},
    {"topic": "另一知识点", "priority": "Medium", "status": "Pending"}
  ]
}

要求：priority 只能是 High、Medium 或 Low；每个 topic 的 status 初始均为 Pending；至少 3 个 topics。"""

FLASHCARDS_SYSTEM_PROMPT = """你是一个 UNSW 复习助手。请从课程内容中提取 8-10 个核心术语、概念或公式，制成 Active Recall 闪卡。

你必须只输出一个合法的 JSON 数组，不要用 markdown 代码块包裹，不要输出任何 JSON 以外的文字。

格式严格如下（数组，每项为一张卡）：
[
  {"front": "术语或问题（正面）", "back": "定义/答案/公式解析（背面；公式请用 LaTeX，用 $ 包裹，如 $E = mc^2$）"},
  {"front": "下一张正面", "back": "下一张背面"}
]

要求：至少 8 张、至多 10 张卡；背面若有数学公式必须用 $...$ 或 $$...$$ 的 LaTeX 格式；正面为简短术语或提问，背面为完整解释。"""

IMAGE_ANALYSIS_PROMPT = (
    "你是一个 UNSW 教授。请解释这张课件截图中的视觉模型、流程或公式，"
    "并预测它在考试中可能以什么形式出现。使用 Markdown 和 LaTeX（$...$）作答。"
)

CHAT_CONTEXT_PROMPT = (
    "你是 UNSW 助教。以下是从用户上传的资料中提取的摘要、大纲和原文片段。"
    "请仅基于这些内容回答用户问题；若无法从资料中得出答案，请说明。使用 Markdown 和 LaTeX 作答。"
)


def _call_llm(system_prompt: str, user_message: str, api_key: str, temperature: float = 0.3) -> str:
    """
    Invoke OpenAI Chat with the given messages.

    Args:
        system_prompt: System message content.
        user_message: User message content.
        api_key: OpenAI API key.
        temperature: Model temperature.

    Returns:
        Assistant response content.

    Raises:
        ValueError: If API key is missing, invalid, or quota insufficient.
    """
    if not (api_key and api_key.strip()):
        raise ValueError("请提供有效的 API Key。")
    try:
        llm = ChatOpenAI(
            model="gpt-4o",
            api_key=api_key.strip(),
            temperature=temperature,
        )
        messages = [("system", system_prompt), ("human", user_message)]
        response = llm.invoke(messages)
        return response.content if response.content else ""
    except Exception as e:
        err_msg = str(e).lower()
        if "invalid" in err_msg or "authentication" in err_msg or "incorrect api key" in err_msg:
            raise ValueError("API Key 无效，请检查后重试。") from e
        if "insufficient_quota" in err_msg or "quota" in err_msg or "rate limit" in err_msg:
            raise ValueError("API 余额不足或请求过于频繁，请稍后再试。") from e
        raise ValueError(f"调用 API 时出错：{e!s}") from e


def _call_llm_vision(image_bytes: bytes, text_prompt: str, api_key: str) -> str:
    """
    Invoke OpenAI vision model with an image and text prompt.

    Args:
        image_bytes: Raw image bytes (PNG or JPEG).
        text_prompt: Text prompt for the image.
        api_key: OpenAI API key.

    Returns:
        Assistant response content.

    Raises:
        ValueError: If API key is missing or API call fails.
    """
    if not (api_key and api_key.strip()):
        raise ValueError("请提供有效的 API Key。")
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    mime = "image/png" if image_bytes[:8].startswith(b"\x89PNG") else "image/jpeg"
    data_url = f"data:{mime};base64,{b64}"
    content: list[Any] = [
        {"type": "text", "text": text_prompt or IMAGE_ANALYSIS_PROMPT},
        {"type": "image_url", "image_url": {"url": data_url, "detail": "auto"}},
    ]
    try:
        llm = ChatOpenAI(
            model="gpt-4o",
            api_key=api_key.strip(),
            temperature=0.3,
        )
        messages = [
            SystemMessage(content=IMAGE_ANALYSIS_PROMPT),
            HumanMessage(content=content),
        ]
        response = llm.invoke(messages)
        return response.content if response.content else ""
    except Exception as e:
        err_msg = str(e).lower()
        if "invalid" in err_msg or "authentication" in err_msg or "incorrect api key" in err_msg:
            raise ValueError("API Key 无效，请检查后重试。") from e
        if "insufficient_quota" in err_msg or "quota" in err_msg or "rate limit" in err_msg:
            raise ValueError("API 余额不足或请求过于频繁，请稍后再试。") from e
        raise ValueError(f"分析图片时出错：{e!s}") from e


class LLMProcessor:
    """Generates structured summaries from course text via OpenAI."""

    def invoke(self, system_prompt: str, user_message: str, api_key: str, temperature: float = 0.3) -> str:
        """
        Invoke the LLM with custom system and user messages.

        Args:
            system_prompt: System message.
            user_message: User message.
            api_key: OpenAI API key.
            temperature: Optional temperature.

        Returns:
            Assistant response text.
        """
        return _call_llm(system_prompt, user_message, api_key, temperature)

    def generate_summary(self, text: str, api_key: str) -> str:
        """
        Summarize course content into structured revision notes.

        Args:
            text: Raw course material text.
            api_key: OpenAI API key.

        Returns:
            Markdown-formatted summary string.

        Raises:
            ValueError: If API key is missing, invalid, or quota insufficient.
        """
        return _call_llm(SYSTEM_PROMPT, text, api_key, temperature=0.3)

    def generate_syllabus_checklist(self, text: str, api_key: str) -> dict[str, Any]:
        """
        Extract a revision syllabus with topics and exam priority (High/Medium/Low).

        Args:
            text: Raw course material text.
            api_key: OpenAI API key.

        Returns:
            Dict with "module_title" and "topics" (list of {topic, priority, status}).
            On parse failure returns {"module_title": "", "topics": []}.
        """
        raw = _call_llm(SYLLABUS_SYSTEM_PROMPT, text[:12000], api_key, temperature=0.3)
        if not raw:
            return {"module_title": "", "topics": []}
        text_stripped = raw.strip()
        if text_stripped.startswith("```"):
            text_stripped = re.sub(r"^```(?:json)?\s*", "", text_stripped)
            text_stripped = re.sub(r"\s*```\s*$", "", text_stripped).strip()
        for candidate in [raw, text_stripped]:
            try:
                obj = json.loads(candidate)
                break
            except json.JSONDecodeError:
                continue
        else:
            match = re.search(r"\{[\s\S]*\}", raw)
            if match:
                try:
                    obj = json.loads(match.group(0))
                except json.JSONDecodeError:
                    obj = {}
            else:
                obj = {}
        if not isinstance(obj, dict):
            return {"module_title": "", "topics": []}
        title = str(obj.get("module_title") or "").strip()
        topics_raw = obj.get("topics")
        if not isinstance(topics_raw, list):
            return {"module_title": title, "topics": []}
        valid_priority = {"High", "Medium", "Low"}
        topics_out: list[dict[str, str]] = []
        for t in topics_raw:
            if not isinstance(t, dict):
                continue
            topic_name = str(t.get("topic") or "").strip()
            if not topic_name:
                continue
            prio = str(t.get("priority") or "Medium").strip()
            if prio not in valid_priority:
                prio = "Medium"
            topics_out.append({
                "topic": topic_name,
                "priority": prio,
                "status": str(t.get("status") or "Pending").strip() or "Pending",
            })
        return {"module_title": title, "topics": topics_out}

    def generate_flashcards(self, text: str, api_key: str) -> list[dict[str, str]]:
        """
        Extract 8-10 core terms/concepts/formulas as flashcard pairs (front, back).

        Args:
            text: Raw course material text.
            api_key: OpenAI API key.

        Returns:
            List of {"front": "...", "back": "..."}. Back may contain LaTeX in $...$.
            On parse failure returns [].
        """
        raw = _call_llm(FLASHCARDS_SYSTEM_PROMPT, text[:12000], api_key, temperature=0.3)
        if not raw:
            return []
        text_stripped = raw.strip()
        if text_stripped.startswith("```"):
            text_stripped = re.sub(r"^```(?:json)?\s*", "", text_stripped)
            text_stripped = re.sub(r"\s*```\s*$", "", text_stripped).strip()
        for candidate in [raw, text_stripped]:
            try:
                arr = json.loads(candidate)
                break
            except json.JSONDecodeError:
                continue
        else:
            match = re.search(r"\[[\s\S]*\]", raw)
            if match:
                try:
                    arr = json.loads(match.group(0))
                except json.JSONDecodeError:
                    arr = []
            else:
                arr = []
        if not isinstance(arr, list):
            return []
        out: list[dict[str, str]] = []
        for item in arr[:10]:
            if not isinstance(item, dict):
                continue
            front = str(item.get("front") or "").strip()
            back = str(item.get("back") or "").strip()
            if front:
                out.append({"front": front, "back": back or "—"})
        return out

    def analyze_image(self, image_bytes: bytes, prompt: str, api_key: str) -> str:
        """
        Analyze a slide/screenshot with a vision model; explain content and exam relevance.

        Args:
            image_bytes: Raw image bytes (PNG or JPEG).
            prompt: User prompt; if empty, uses default UNSW professor prompt.
            api_key: OpenAI API key.

        Returns:
            Model response text (Markdown/LaTeX).

        Raises:
            ValueError: If API key is missing or API call fails.
        """
        return _call_llm_vision(image_bytes, prompt.strip() or IMAGE_ANALYSIS_PROMPT, api_key)

    def chat_with_context(self, context: str, user_message: str, api_key: str) -> str:
        """
        Answer user question based on provided context (summary, syllabus, extracted text).

        Args:
            context: Concatenated course materials text.
            user_message: User's question.
            api_key: OpenAI API key.

        Returns:
            Assistant response text.

        Raises:
            ValueError: If API key is missing or API call fails.
        """
        system = f"{CHAT_CONTEXT_PROMPT}\n\n【资料】\n{context[:20000]}"
        return _call_llm(system, f"用户问：{user_message}", api_key, temperature=0.4)
