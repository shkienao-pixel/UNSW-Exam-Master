"""LLM orchestration: summaries, graph helpers, flashcards, translation, and chat."""

from __future__ import annotations

import base64
import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

SYSTEM_PROMPT = (
    "You are a UNSW teaching assistant. Summarize the provided course text into structured revision notes "
    "using Markdown. Include key concepts, formulas (LaTeX), and exam priorities."
)

SYLLABUS_SYSTEM_PROMPT = (
    "You are a UNSW course planner. Return only valid JSON with this schema: "
    '{"module_title":"...",'
    '"frameworks":[{"framework":"...","objective":"...",'
    '"sections":[{"section":"...","knowledge_points":['
    '{"point":"...","detail":"...","priority":"High|Medium|Low","status":"Pending"}]}]}],'
    '"topics":[{"topic":"...","priority":"High|Medium|Low","status":"Pending"}]}. '
    "Use hierarchical depth: framework -> section -> knowledge_points. "
    "Include at least 2 frameworks and at least 6 knowledge points in total."
)

FLASHCARDS_SYSTEM_PROMPT = (
    "You are a UNSW revision assistant. Return only valid JSON array of 8-10 flashcards, "
    "each as {\"front\":\"...\",\"back\":\"...\"}. Use LaTeX for formulas when needed."
)

IMAGE_ANALYSIS_PROMPT = (
    "You are a UNSW professor. Explain the uploaded slide/screenshot, key mechanisms/formulas, "
    "and likely exam question style. Use Markdown and LaTeX where helpful."
)

CHAT_CONTEXT_PROMPT = (
    "You are a UNSW teaching assistant. Answer using ONLY the provided context. "
    "If the answer cannot be derived from context, say so explicitly."
)

CHAT_GENERAL_PROMPT = (
    "You are a knowledgeable UNSW teaching assistant. "
    "The user's question is not covered by the uploaded course materials. "
    "Draw on your broad academic knowledge to give a thorough, accurate answer. "
    "If you reference anything beyond the course docs, note it comes from general knowledge. "
    "Answer in the same language as the user's question (Chinese if they wrote in Chinese)."
)

TRANSLATE_QUESTION_PROMPT = (
    "You are a precise technical translator. Return only valid JSON with this schema: "
    '{"question_zh":"...","options_zh":["...","...","...","..."]}. '
    "Do not output markdown."
)

TRANSLATE_FLASHCARD_PROMPT = (
    "You are a precise technical translator. Return only valid JSON with this schema: "
    '{"stem_zh":"...","options_zh":["..."],"answer_zh":"...","explanation_zh":"..."}. '
    "Keep terms accurate and concise. Do not output markdown."
)


def _call_llm(system_prompt: str, user_message: str, api_key: str, temperature: float = 0.3) -> str:
    """Invoke OpenAI Chat with the given system and user message."""
    if not (api_key and api_key.strip()):
        raise ValueError("Please provide a valid API key.")
    try:
        llm = ChatOpenAI(model="gpt-4o", api_key=api_key.strip(), temperature=temperature)
        response = llm.invoke([("system", system_prompt), ("human", user_message)])
        return response.content if response.content else ""
    except Exception as e:  # pragma: no cover - network/API specific
        err_msg = str(e).lower()
        if "invalid" in err_msg or "authentication" in err_msg or "incorrect api key" in err_msg:
            raise ValueError("Invalid API key.") from e
        if "insufficient_quota" in err_msg or "quota" in err_msg or "rate limit" in err_msg:
            raise ValueError("API quota/rate limit reached. Please retry later.") from e
        raise ValueError(f"API call failed: {e!s}") from e


def _call_llm_vision(image_bytes: bytes, text_prompt: str, api_key: str) -> str:
    """Invoke OpenAI vision model with image + text prompt."""
    if not (api_key and api_key.strip()):
        raise ValueError("Please provide a valid API key.")
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    mime = "image/png" if image_bytes[:8].startswith(b"\x89PNG") else "image/jpeg"
    data_url = f"data:{mime};base64,{b64}"
    content: list[Any] = [
        {"type": "text", "text": text_prompt or IMAGE_ANALYSIS_PROMPT},
        {"type": "image_url", "image_url": {"url": data_url, "detail": "auto"}},
    ]
    try:
        llm = ChatOpenAI(model="gpt-4o", api_key=api_key.strip(), temperature=0.3)
        messages = [SystemMessage(content=IMAGE_ANALYSIS_PROMPT), HumanMessage(content=content)]
        response = llm.invoke(messages)
        return response.content if response.content else ""
    except Exception as e:  # pragma: no cover - network/API specific
        err_msg = str(e).lower()
        if "invalid" in err_msg or "authentication" in err_msg or "incorrect api key" in err_msg:
            raise ValueError("Invalid API key.") from e
        if "insufficient_quota" in err_msg or "quota" in err_msg or "rate limit" in err_msg:
            raise ValueError("API quota/rate limit reached. Please retry later.") from e
        raise ValueError(f"Image analysis failed: {e!s}") from e


def _extract_json_object(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned).strip()
    for candidate in [raw, cleaned]:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    return {}


def _extract_json_array(raw: str) -> list[Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned).strip()
    for candidate in [raw, cleaned]:
        try:
            arr = json.loads(candidate)
            if isinstance(arr, list):
                return arr
        except json.JSONDecodeError:
            continue
    match = re.search(r"\[[\s\S]*\]", raw)
    if match:
        try:
            arr = json.loads(match.group(0))
            if isinstance(arr, list):
                return arr
        except json.JSONDecodeError:
            pass
    return []


class LLMProcessor:
    """Generates structured summaries and utility outputs via OpenAI."""

    def invoke(self, system_prompt: str, user_message: str, api_key: str, temperature: float = 0.3) -> str:
        return _call_llm(system_prompt, user_message, api_key, temperature)

    def generate_summary(self, text: str, api_key: str) -> str:
        return _call_llm(SYSTEM_PROMPT, text, api_key, temperature=0.3)

    def generate_syllabus_checklist(self, text: str, api_key: str) -> dict[str, Any]:
        raw = _call_llm(SYLLABUS_SYSTEM_PROMPT, text[:24000], api_key, temperature=0.3)
        obj = _extract_json_object(raw)
        title = str(obj.get("module_title") or "").strip()
        topics_raw = obj.get("topics") if isinstance(obj, dict) else []
        if not isinstance(topics_raw, list):
            topics_raw = []
        valid_priority = {"High", "Medium", "Low"}
        frameworks_raw = obj.get("frameworks") if isinstance(obj, dict) else []
        if not isinstance(frameworks_raw, list):
            frameworks_raw = []

        frameworks_out: list[dict[str, Any]] = []
        flat_topics_from_tree: list[dict[str, str]] = []
        for fw_idx, fw in enumerate(frameworks_raw):
            if not isinstance(fw, dict):
                continue
            framework_name = str(
                fw.get("framework") or fw.get("name") or fw.get("title") or f"Framework {fw_idx + 1}"
            ).strip()
            if not framework_name:
                framework_name = f"Framework {fw_idx + 1}"
            objective = str(fw.get("objective") or "").strip()
            sections_raw = fw.get("sections") if isinstance(fw.get("sections"), list) else []
            sections_out: list[dict[str, Any]] = []

            for sec_idx, sec in enumerate(sections_raw):
                if not isinstance(sec, dict):
                    continue
                section_name = str(sec.get("section") or sec.get("name") or f"Section {sec_idx + 1}").strip()
                if not section_name:
                    section_name = f"Section {sec_idx + 1}"
                kps_raw = sec.get("knowledge_points") if isinstance(sec.get("knowledge_points"), list) else []
                kps_out: list[dict[str, str]] = []
                for kp_idx, kp in enumerate(kps_raw):
                    if isinstance(kp, dict):
                        point = str(kp.get("point") or kp.get("name") or kp.get("topic") or "").strip()
                        detail = str(kp.get("detail") or kp.get("description") or "").strip()
                        prio = str(kp.get("priority") or "Medium").strip()
                        status = str(kp.get("status") or "Pending").strip() or "Pending"
                    else:
                        point = str(kp).strip()
                        detail = ""
                        prio = "Medium"
                        status = "Pending"
                    if not point:
                        point = f"Knowledge Point {kp_idx + 1}"
                    if prio not in valid_priority:
                        prio = "Medium"
                    kp_item = {"point": point, "detail": detail, "priority": prio, "status": status}
                    kps_out.append(kp_item)
                    flat_topics_from_tree.append(
                        {
                            "topic": f"{framework_name} / {section_name} / {point}",
                            "priority": prio,
                            "status": status,
                        }
                    )
                sections_out.append({"section": section_name, "knowledge_points": kps_out})
            frameworks_out.append({"framework": framework_name, "objective": objective, "sections": sections_out})

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
            status = str(t.get("status") or "Pending").strip() or "Pending"
            topics_out.append({"topic": topic_name, "priority": prio, "status": status})

        # Backward-compatible topics list; prefer tree-derived flatten when available.
        if flat_topics_from_tree:
            merged_topics = flat_topics_from_tree
        else:
            merged_topics = topics_out

        # If model did not provide frameworks, synthesize a simple hierarchy from topics.
        if not frameworks_out and topics_out:
            frameworks_out = [
                {
                    "framework": "Core Framework",
                    "objective": "",
                    "sections": [
                        {
                            "section": "Key Topics",
                            "knowledge_points": [
                                {
                                    "point": str(t.get("topic") or ""),
                                    "detail": "",
                                    "priority": str(t.get("priority") or "Medium"),
                                    "status": str(t.get("status") or "Pending"),
                                }
                                for t in topics_out
                            ],
                        }
                    ],
                }
            ]

        return {"module_title": title, "frameworks": frameworks_out, "topics": merged_topics}

    def generate_flashcards(self, text: str, api_key: str) -> list[dict[str, str]]:
        raw = _call_llm(FLASHCARDS_SYSTEM_PROMPT, text[:24000], api_key, temperature=0.3)
        arr = _extract_json_array(raw)
        out: list[dict[str, str]] = []
        for item in arr[:10]:
            if not isinstance(item, dict):
                continue
            front = str(item.get("front") or "").strip()
            back = str(item.get("back") or "").strip()
            if front:
                out.append({"front": front, "back": back or "-"})
        return out

    def analyze_image(self, image_bytes: bytes, prompt: str, api_key: str) -> str:
        return _call_llm_vision(image_bytes, prompt.strip() or IMAGE_ANALYSIS_PROMPT, api_key)

    def chat_with_context(self, context: str, user_message: str, api_key: str) -> str:
        system = f"{CHAT_CONTEXT_PROMPT}\n\n[Context]\n{context[:20000]}"
        return _call_llm(system, f"User question: {user_message}", api_key, temperature=0.4)

    def chat_general_knowledge(self, user_message: str, api_key: str, extra_context: str = "") -> str:
        """Answer from general knowledge when vector search returns no relevant chunks."""
        system = CHAT_GENERAL_PROMPT
        if extra_context:
            system = f"{CHAT_GENERAL_PROMPT}\n\n[Course Background (partial)]\n{extra_context[:8000]}"
        return _call_llm(system, f"User question: {user_message}", api_key, temperature=0.5)

    def translate_question(self, question: str, options: list[str], api_key: str) -> dict[str, Any]:
        """Translate one MCQ question and options into Chinese."""
        if not (api_key and api_key.strip()):
            return {"question_zh": "", "options_zh": []}
        safe_options = [str(x) for x in options[:4]]
        user_message = (
            "Translate the following multiple-choice question into Simplified Chinese.\n"
            "Keep technical terms accurate.\n"
            f"Question: {question}\n"
            f"Options: {json.dumps(safe_options, ensure_ascii=False)}"
        )
        try:
            raw = _call_llm(TRANSLATE_QUESTION_PROMPT, user_message, api_key.strip(), temperature=0.0)
        except ValueError:
            return {"question_zh": "", "options_zh": []}
        obj = _extract_json_object(raw)
        question_zh = str(obj.get("question_zh") or "").strip()
        options_zh_raw = obj.get("options_zh") if isinstance(obj, dict) else []
        options_zh = options_zh_raw if isinstance(options_zh_raw, list) else []
        out_options = [str(x) for x in options_zh[: len(safe_options)]]
        return {"question_zh": question_zh, "options_zh": out_options}

    def translate_flashcard(
        self,
        stem: str,
        options: list[str],
        answer: str,
        explanation: str,
        api_key: str,
    ) -> dict[str, Any]:
        """Translate flashcard content into Chinese, preserving structure."""
        if not (api_key and api_key.strip()):
            return {"stem_zh": "", "options_zh": [], "answer_zh": "", "explanation_zh": ""}
        payload = {
            "stem": str(stem or ""),
            "options": [str(x) for x in options],
            "answer": str(answer or ""),
            "explanation": str(explanation or ""),
        }
        try:
            raw = _call_llm(
                TRANSLATE_FLASHCARD_PROMPT,
                json.dumps(payload, ensure_ascii=False),
                api_key.strip(),
                temperature=0.0,
            )
        except ValueError:
            return {"stem_zh": "", "options_zh": [], "answer_zh": "", "explanation_zh": ""}
        obj = _extract_json_object(raw)
        stem_zh = str(obj.get("stem_zh") or "").strip()
        options_zh_raw = obj.get("options_zh") if isinstance(obj.get("options_zh"), list) else []
        options_zh = [str(x) for x in options_zh_raw[: len(options)]]
        answer_zh = str(obj.get("answer_zh") or "").strip()
        explanation_zh = str(obj.get("explanation_zh") or "").strip()
        return {
            "stem_zh": stem_zh,
            "options_zh": options_zh,
            "answer_zh": answer_zh,
            "explanation_zh": explanation_zh,
        }
