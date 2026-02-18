"""UNSW Exam Master main entry point."""

from __future__ import annotations

import json
import random
from io import BytesIO
from pathlib import Path
from datetime import datetime
from typing import Any
from uuid import uuid4

import streamlit as st
from streamlit_echarts import st_echarts

from config import (
    MOTIVATIONAL_QUOTES,
    PAGE_ICON,
    PAGE_TITLE,
    SIDEBAR_HEADER,
    UNSW_BG_PAGE,
    UNSW_CARD_BG,
    UNSW_CARD_SHADOW,
    UNSW_FONT_HEADING,
    UNSW_PRIMARY,
    UNSW_PRIMARY_HOVER,
    UNSW_SIDEBAR_BG,
    UNSW_SIDEBAR_BORDER,
    UNSW_SIDEBAR_TEXT,
    UNSW_TEXT,
)
from i18n import tr
from migrations.migrate import (
    BACKUPS_DIR,
    DB_PATH,
    MigrationError,
    MigrationInProgressError,
    migrate_to_latest,
)
from services.document_processor import PDFProcessor
from services.graph_service import GraphGenerator
from services.llm_service import LLMProcessor
from services.quiz_generator import QuizGenerator
from services.course_workspace_service import (
    WorkspaceValidationError,
    create_course,
    create_output,
    create_scope_set,
    delete_scope_set,
    ensure_default_scope_set,
    get_course,
    get_output,
    get_scope_set,
    list_artifacts,
    list_artifacts_by_ids,
    list_courses,
    list_outputs,
    list_scope_sets,
    rename_scope_set,
    replace_scope_set_items,
    resolve_scope_artifact_ids,
    save_artifact,
)
from services.vector_store_service import DocumentVectorStore
from services.flashcards_mistakes_service import (
    archive_mistake,
    list_flashcards_by_deck,
    list_mistakes,
    list_mistakes_review,
    mark_mistake_master,
    review_flashcard,
    save_generated_flashcards,
    submit_flashcard_answer,
)

_MIGRATIONS_DONE = False
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_TO_PAGE: dict[str, str] = {
    "/dashboard": "dashboard",
    "/study": "study",
    "/outline": "outline",
    "/graph": "graph",
    "/quiz": "quiz",
    "/flashcards": "flashcards",
    "/mistakes": "mistakes",
}
PAGE_TO_ROUTE: dict[str, str] = {v: k for k, v in ROUTE_TO_PAGE.items()}


def _read_app_version() -> str:
    version_file = Path(__file__).resolve().parents[1] / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip() or "0.0.0"
    except Exception:
        return "0.0.0"


APP_VERSION = _read_app_version()


def _lang() -> str:
    return st.session_state.get("lang", "zh")


def _t(key: str, **kwargs: object) -> str:
    return tr(_lang(), key, **kwargs)


def _now_label() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _request_nav(page: str) -> None:
    if page not in PAGE_TO_ROUTE:
        return
    st.query_params["route"] = PAGE_TO_ROUTE[page]
    st.session_state["nav_page_request"] = page
    st.rerun()


def _sync_nav_with_route_query() -> None:
    allowed_pages = set(PAGE_TO_ROUTE.keys())
    current = str(st.session_state.get("nav_page_selector") or "dashboard")
    if current not in allowed_pages:
        current = "dashboard"
        st.session_state["nav_page_selector"] = current

    raw_route = st.query_params.get("route", "")
    if isinstance(raw_route, list):
        raw_route = raw_route[0] if raw_route else ""
    route = str(raw_route or "").strip().lower()
    query_page = ROUTE_TO_PAGE.get(route)
    if query_page and query_page in allowed_pages and query_page != current:
        st.session_state["nav_page_selector"] = query_page
        current = query_page

    expected_route = PAGE_TO_ROUTE.get(current, "/dashboard")
    if route != expected_route:
        st.query_params["route"] = expected_route


def _active_course_id() -> str:
    return str(st.session_state.get("active_course_id") or "").strip()


def _active_course() -> dict[str, Any] | None:
    course_id = _active_course_id()
    if not course_id:
        return None
    return get_course(course_id)


def _active_course_label() -> str:
    course = _active_course()
    if not course:
        return _t("course_not_selected")
    return f"{course.get('code', '')} - {course.get('name', '')}"


def _current_collection() -> str:
    """Backward-compatible alias for active course id."""
    return _active_course_id()


def _render_language_switcher() -> None:
    """Render a simple sidebar-top language toggle with connected click buttons."""
    if "lang" not in st.session_state:
        st.session_state["lang"] = "zh"

    c1, c2 = st.sidebar.columns(2, gap="small")
    if c1.button(
        _t("lang_zh"),
        key="btn_lang_zh",
        type="primary" if _lang() == "zh" else "secondary",
        use_container_width=True,
    ):
        st.session_state["lang"] = "zh"
        st.rerun()
    if c2.button(
        _t("lang_en"),
        key="btn_lang_en",
        type="primary" if _lang() == "en" else "secondary",
        use_container_width=True,
    ):
        st.session_state["lang"] = "en"
        st.rerun()
    st.sidebar.caption(f"{_t('lang_label')}: {_t('lang_zh') if _lang() == 'zh' else _t('lang_en')}")


def _ensure_migrations_once() -> int:
    global _MIGRATIONS_DONE
    if not _MIGRATIONS_DONE:
        try:
            version = migrate_to_latest()
        except MigrationInProgressError:
            if not st.session_state.get("migration_in_progress_notice_shown"):
                st.info("Migration in progress. Please refresh shortly.")
                st.session_state["migration_in_progress_notice_shown"] = True
            return int(st.session_state.get("schema_version", 0))
        except MigrationError as e:
            st.error(f"{e}")
            st.error(f"Recovery: restore from backups in {BACKUPS_DIR}")
            st.stop()
        _MIGRATIONS_DONE = True
        st.session_state["migration_in_progress_notice_shown"] = False
        st.session_state["schema_version"] = version
        return version
    if "schema_version" in st.session_state:
        return int(st.session_state["schema_version"])
    # Best effort if session state got reset while process is alive.
    try:
        version = migrate_to_latest()
    except MigrationInProgressError:
        if not st.session_state.get("migration_in_progress_notice_shown"):
            st.info("Migration in progress. Please refresh shortly.")
            st.session_state["migration_in_progress_notice_shown"] = True
        return int(st.session_state.get("schema_version", 0))
    except MigrationError as e:
        st.error(f"{e}")
        st.error(f"Recovery: restore from backups in {BACKUPS_DIR}")
        st.stop()
    st.session_state["migration_in_progress_notice_shown"] = False
    st.session_state["schema_version"] = version
    return version


def _inject_unsw_css() -> None:
    """Inject UNSW style CSS."""
    st.markdown(
        f"""
        <style>
        .unsw-header {{
            background: {UNSW_PRIMARY};
            clip-path: polygon(0 0, 100% 0, 100% 84%, 0 100%);
            height: 80px;
            margin: 0 -2rem 1rem -2rem;
            padding: 0 0 0 2rem;
            display: flex;
            align-items: center;
            width: calc(100% + 4rem);
            box-sizing: border-box;
        }}
        .unsw-logo {{
            font-family: {UNSW_FONT_HEADING};
            font-weight: 900;
            font-size: 1.6rem;
            line-height: 1;
            letter-spacing: 0.2em;
            color: #000;
        }}
        .stApp {{ background: {UNSW_BG_PAGE}; }}
        .main .block-container {{
            padding: 1.5rem 2rem;
            max-width: 100%;
            background: {UNSW_CARD_BG};
            box-shadow: {UNSW_CARD_SHADOW};
            border-radius: 6px;
        }}
        h1, h2, h3 {{
            font-family: {UNSW_FONT_HEADING} !important;
            letter-spacing: 0.03em !important;
            color: {UNSW_TEXT} !important;
        }}
        p, .stMarkdown {{ color: {UNSW_TEXT} !important; }}
        [data-testid="stSidebar"] {{
            background: {UNSW_SIDEBAR_BG};
            border-right: 1px solid {UNSW_SIDEBAR_BORDER};
        }}
        [data-testid="stSidebar"] .stMarkdown,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] .stCaptionContainer,
        [data-testid="stSidebar"] small {{ color: {UNSW_SIDEBAR_TEXT} !important; }}
        [data-testid="stSidebar"] .stButton > button {{
            border-radius: 4px !important;
            min-height: 2.1rem !important;
        }}
        [data-testid="stSidebar"] .stButton > button[kind="primary"] {{
            background: #FFFFFF !important;
            color: #111111 !important;
            border: 1px solid #D0D0D0 !important;
        }}
        [data-testid="stSidebar"] .stButton > button[kind="primary"] *,
        [data-testid="stSidebar"] .stButton > button[kind="secondary"] * {{
            color: #111111 !important;
            -webkit-text-fill-color: #111111 !important;
        }}
        [data-testid="stSidebar"] .stButton > button[kind="secondary"] {{
            background: #FFFFFF !important;
            color: #111111 !important;
            border: 1px solid #D0D0D0 !important;
        }}
        [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {{
            background: #F3F4F6 !important;
            color: #111111 !important;
            border: 1px solid #BDBDBD !important;
        }}
        [data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {{
            background: #F3F4F6 !important;
            color: #111111 !important;
            border: 1px solid #BDBDBD !important;
        }}
        [data-testid="stSidebar"] .stButton > button:disabled {{
            background: #FFFFFF !important;
            color: #111111 !important;
            border: 1px solid #D0D0D0 !important;
            opacity: 1 !important;
            -webkit-text-fill-color: #111111 !important;
        }}
        [data-testid="stSidebar"] .stButton > button:disabled * {{
            color: #111111 !important;
            -webkit-text-fill-color: #111111 !important;
            opacity: 1 !important;
        }}
        [data-testid="stSidebar"] .stDownloadButton > button {{
            background: #FFFFFF !important;
            color: #111111 !important;
            border: 1px solid #D0D0D0 !important;
            border-radius: 4px !important;
            min-height: 2.1rem !important;
            font-weight: 600 !important;
        }}
        [data-testid="stSidebar"] .stDownloadButton > button:hover {{
            background: #F3F4F6 !important;
            color: #111111 !important;
            border: 1px solid #BDBDBD !important;
        }}
        .stButton > button {{
            background: {UNSW_PRIMARY} !important;
            color: {UNSW_TEXT} !important;
            border: none !important;
            border-radius: 4px;
            font-weight: 600;
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }}
        .stButton > button[kind="secondary"] {{
            background: #FFFFFF !important;
            color: {UNSW_TEXT} !important;
            border: 1px solid #D0D0D0 !important;
        }}
        .stButton > button:hover {{
            background: {UNSW_PRIMARY_HOVER} !important;
            color: {UNSW_TEXT} !important;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.12);
        }}
        .stButton > button[kind="secondary"]:hover {{
            background: #F7F7F7 !important;
            color: {UNSW_TEXT} !important;
            border: 1px solid #BDBDBD !important;
            transform: translateY(-1px);
        }}
        .stProgress > div > div > div {{ background: {UNSW_PRIMARY}; }}
        .sidebar-header {{
            font-family: {UNSW_FONT_HEADING};
            font-size: 0.9rem;
            font-weight: 700;
            color: {UNSW_PRIMARY};
            letter-spacing: 0.08em;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid {UNSW_SIDEBAR_BORDER};
        }}
        .quote-box {{
            background: rgba(255,255,255,0.06);
            border-left: 4px solid {UNSW_PRIMARY};
            padding: 0.75rem 1rem;
            border-radius: 0 4px 4px 0;
            color: rgba(255,255,255,0.9);
            font-size: 0.85rem;
            margin-top: 1rem;
        }}
        .unsw-section-title {{
            font-family: {UNSW_FONT_HEADING};
            font-size: 1rem;
            letter-spacing: 0.05em;
            color: #333;
            margin-bottom: 0.5rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _clear_study_derived_state() -> None:
    keys = [
        "study_extracted_text",
        "study_upload_signature",
        "study_uploaded_files_cache",
        "study_recent_file_names",
        "last_uploaded_study_name",
        "study_summary",
        "study_graph_data",
        "study_syllabus",
        "study_image_analysis",
        "study_chat_history",
        "exam_quiz",
        "exam_submitted",
        "exam_user_answers",
        "study_index_stats",
        "selected_output_id",
        "selected_deck_id",
        "flashcard_review_index",
        "study_scope_quiz",
        "study_scope_quiz_scope_ids",
        "study_scope_quiz_output_id",
        "selected_option",
        "submitted",
        "is_correct",
        "translation_on",
        "translation_cache",
        "translation_model_calls_by_qid",
        "quiz_translation_cache",
        "quiz_translation_model_calls",
        "flashcards_active_deck_id",
        "flashcards_generate_attempts",
        "flashcards_main_index",
        "flashcards_main_mcq_selected_option",
        "flashcards_main_mcq_submitted",
        "flashcards_main_mcq_is_correct",
        "flashcards_main_mcq_correct_answer",
        "flashcards_main_known_count",
        "flashcards_main_unknown_count",
        "flashcards_main_finished",
        "flashcards_main_translation_on",
        "flashcards_main_translation_cache",
        "mistakes_review_cards",
        "mistakes_review_index",
        "mistakes_review_mcq_selected_option",
        "mistakes_review_mcq_submitted",
        "mistakes_review_mcq_is_correct",
        "mistakes_review_mcq_correct_answer",
        "mistakes_review_known_count",
        "mistakes_review_unknown_count",
        "mistakes_review_finished",
        "mistakes_review_translation_on",
        "mistakes_review_translation_cache",
    ]
    for k in keys:
        st.session_state.pop(k, None)


def _clear_generated_content_state() -> None:
    keys = [
        "study_summary",
        "study_graph_data",
        "study_syllabus",
        "study_image_analysis",
        "study_chat_history",
        "exam_quiz",
        "exam_submitted",
        "exam_user_answers",
        "selected_output_id",
        "study_scope_quiz",
        "study_scope_quiz_scope_ids",
        "study_scope_quiz_output_id",
        "selected_option",
        "submitted",
        "is_correct",
        "translation_on",
        "translation_cache",
        "translation_model_calls_by_qid",
        "quiz_translation_cache",
        "quiz_translation_model_calls",
        "flashcards_main_index",
        "flashcards_main_mcq_selected_option",
        "flashcards_main_mcq_submitted",
        "flashcards_main_mcq_is_correct",
        "flashcards_main_mcq_correct_answer",
        "flashcards_main_known_count",
        "flashcards_main_unknown_count",
        "flashcards_main_finished",
        "flashcards_main_translation_on",
        "flashcards_main_translation_cache",
        "mistakes_review_cards",
        "mistakes_review_index",
        "mistakes_review_mcq_selected_option",
        "mistakes_review_mcq_submitted",
        "mistakes_review_mcq_is_correct",
        "mistakes_review_mcq_correct_answer",
        "mistakes_review_known_count",
        "mistakes_review_unknown_count",
        "mistakes_review_finished",
        "mistakes_review_translation_on",
        "mistakes_review_translation_cache",
    ]
    for k in keys:
        st.session_state.pop(k, None)


def _uploaded_files_signature(files: list[Any]) -> tuple[str, ...]:
    return tuple(sorted(f"{getattr(f, 'name', 'unknown')}:{getattr(f, 'size', 0)}" for f in files))


def _get_vector_store() -> DocumentVectorStore:
    course_id = _current_collection()
    if not course_id:
        raise ValueError("No active course selected.")
    return DocumentVectorStore(course_id=course_id)


def _get_index_status() -> dict[str, Any]:
    if not _current_collection():
        return {"compatible": True, "reasons": [], "metadata": {}, "expected": {}}
    try:
        return _get_vector_store().get_index_status()
    except Exception:
        return {"compatible": True, "reasons": [], "metadata": {}, "expected": {}}


def _is_rebuild_locked() -> bool:
    return bool(st.session_state.get("index_rebuild_in_progress", False))


def _build_session_md() -> str:
    parts: list[str] = []
    summary = str(st.session_state.get("study_summary") or "").strip()
    if summary:
        parts.append("## Chapter Summary\n\n")
        parts.append(summary)
        parts.append("\n\n---\n\n")
    syllabus_raw = st.session_state.get("study_syllabus") or {}
    if isinstance(syllabus_raw, dict):
        s = syllabus_raw
    else:
        s = {}
    topics = s.get("topics") or []
    module_title = str(s.get("module_title") or "").strip()
    if module_title or topics:
        parts.append("## Syllabus Checklist\n\n")
        parts.append(f"**{module_title or 'Revision List'}**\n\n")
        for t in topics:
            parts.append(f"- [{t.get('status', 'Pending')}] **{t.get('topic', '')}** - {t.get('priority', '')}\n")
        parts.append("\n---\n\n")
    if st.session_state.get("study_flashcards"):
        parts.append("## Flashcards\n\n")
        for i, c in enumerate(st.session_state["study_flashcards"], 1):
            parts.append(f"### Card {i}\n\n**Front** {c.get('front', '')}\n\n**Back** {c.get('back', '')}\n\n")
    return "".join(parts)


def _build_chat_context_base() -> str:
    parts: list[str] = []
    if st.session_state.get("study_summary"):
        parts.append("[Summary]\n")
        parts.append(st.session_state["study_summary"][:8000])
        parts.append("\n\n")
    if st.session_state.get("study_syllabus"):
        s = st.session_state["study_syllabus"]
        parts.append("[Syllabus]\n")
        parts.append(f"{s.get('module_title') or ''}\n")
        for t in s.get("topics") or []:
            parts.append(f"- {t.get('topic', '')} ({t.get('priority', '')})\n")
        parts.append("\n")
    return "".join(parts)


def _rag_context(query: str, api_key: str, top_k: int = 10) -> str:
    if not api_key.strip() or not _current_collection():
        return ""
    try:
        status = _get_index_status()
        if not status.get("compatible", True):
            st.session_state["index_outdated"] = True
            return ""
        chunks = _get_vector_store().search(query=query, api_key=api_key, top_k=top_k)
    except Exception:
        return ""
    if not chunks:
        return ""
    lines: list[str] = []
    for i, item in enumerate(chunks, 1):
        meta = item.get("metadata") or {}
        name = meta.get("file_name", "Unknown")
        page = meta.get("page", "-")
        lines.append(f"[Chunk {i}] ({name}, p.{page})\n{item.get('text', '')}\n")
    return "\n".join(lines)


def _task_context(task_hint: str, api_key: str, fallback_chars: int = 12000) -> str:
    retrieved = _rag_context(task_hint, api_key, top_k=12)
    if retrieved:
        return retrieved
    return (st.session_state.get("study_extracted_text") or "")[:fallback_chars]


def _build_revision_report_md() -> str:
    sections: list[str] = []
    summary = str(st.session_state.get("study_summary") or "").strip()
    if summary:
        sections.append("## Chapter Summary\n\n")
        sections.append(summary)
        sections.append("\n\n---\n\n")
    syllabus_raw = st.session_state.get("study_syllabus") or {}
    if isinstance(syllabus_raw, dict):
        s = syllabus_raw
    else:
        s = {}
    topics = s.get("topics") or []
    module_title = str(s.get("module_title") or "").strip()
    if module_title or topics:
        sections.append("## Syllabus\n\n")
        sections.append(f"### {module_title or 'Revision List'}\n\n")
        for t in topics:
            sections.append(f"- **{t.get('topic', '')}** - *{t.get('priority', '')}*\n")
        sections.append("\n---\n\n")
    if st.session_state.get("study_flashcards"):
        sections.append("## Flashcards\n\n")
        for i, c in enumerate(st.session_state["study_flashcards"], 1):
            sections.append(f"### Card {i}\n\n**Q** {c.get('front', '')}\n\n**A** {c.get('back', '')}\n\n")
    if not sections:
        return ""
    parts = ["# UNSW Revision Notes\n\n", "---\n\n"]
    parts.extend(sections)
    return "".join(parts)


def _build_report_pdf_bytes(report_md: str) -> bytes | None:
    """Create a simple PDF from Markdown text if reportlab is installed."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import simpleSplit
        from reportlab.pdfgen import canvas
    except Exception:
        return None

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin_x = 40
    y = height - 50
    for raw_line in report_md.splitlines():
        line = raw_line.strip() or " "
        wrapped = simpleSplit(line, "Helvetica", 10, width - (margin_x * 2))
        for w in wrapped:
            c.setFont("Helvetica", 10)
            c.drawString(margin_x, y, w)
            y -= 14
            if y < 40:
                c.showPage()
                y = height - 50
    c.save()
    buffer.seek(0)
    return buffer.read()


def _persist_output_record(
    course_id: str,
    output_type: str,
    content: Any,
    scope_artifact_ids: list[int],
    scope_set_id: int | None = None,
    model_used: str = "gpt-4o",
) -> int:
    payload = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=2)
    return create_output(
        course_id=course_id,
        output_type=output_type,
        content=payload,
        scope_artifact_ids=scope_artifact_ids,
        scope_set_id=scope_set_id,
        scope="course",
        model_used=model_used,
        status="success",
        path="",
    )


def _render_outputs_tab(course_id: str, fixed_output_type: str | None = None, key_prefix: str = "outputs") -> None:
    st.markdown(f'<p class="unsw-section-title">{_t("outputs_history")}</p>', unsafe_allow_html=True)
    artifacts = list_artifacts(course_id)
    artifact_map = {int(a.get("id", 0)): a for a in artifacts if a.get("id") is not None}
    scope_sets = list_scope_sets(course_id)
    scope_set_map = {int(s.get("id", 0)): s for s in scope_sets if s.get("id") is not None}
    if fixed_output_type:
        out_type = fixed_output_type
        st.caption(f"{_t('output_filter')}: {out_type}")
    else:
        out_type = st.selectbox(
            _t("output_filter"),
            options=["all", "summary", "graph", "outline", "quiz", "syllabus"],
            key=f"{key_prefix}_output_filter_type",
            format_func=lambda x: _t("output_filter_all") if x == "all" else x,
        )
    rows = list_outputs(course_id, "" if out_type == "all" else out_type)
    if not rows:
        st.info(_t("outputs_empty"))
        return

    labels: list[str] = []
    for r in rows:
        raw_sid = r.get("scope_set_id")
        try:
            sid = int(raw_sid) if raw_sid is not None else None
        except (TypeError, ValueError):
            sid = None
        scope_name = (scope_set_map.get(sid) or {}).get("name", _t("not_available"))
        labels.append(
            f"#{r.get('id')} | {r.get('output_type')} | {r.get('created_at')} | "
            f"{_t('output_scope_set_name')}: {scope_name} | "
            f"{_t('output_scope_count', n=r.get('scope_file_count', 0))}"
        )
    idx = st.selectbox(
        _t("output_select"),
        options=list(range(len(rows))),
        format_func=lambda i: labels[i],
        key=f"{key_prefix}_output_select",
    )
    selected = rows[int(idx)]
    output_id = int(selected.get("id", 0))
    details = get_output(output_id) or selected
    scope_ids = [int(x) for x in (details.get("scope_artifact_ids") or [])]
    raw_scope_set_id = details.get("scope_set_id")
    scope_set_id = int(raw_scope_set_id) if raw_scope_set_id is not None else None
    scope_set_name = (scope_set_map.get(scope_set_id) or {}).get("name", _t("not_available"))
    st.caption(
        f"{_t('output_scope')}: {details.get('scope', '')} | "
        f"{_t('output_scope_set_name')}: {scope_set_name} | "
        f"{_t('output_model')}: {details.get('model_used', '')} | "
        f"{_t('output_status')}: {details.get('status', '')}"
    )
    st.caption(_t("output_scope_count", n=len(scope_ids)))
    with st.expander(_t("output_scope_files")):
        if scope_ids:
            for aid in scope_ids:
                a = artifact_map.get(aid)
                if a:
                    st.markdown(f"- `{a.get('file_name', f'Artifact #{aid}')}`")
                else:
                    st.markdown(f"- `Artifact #{aid}`")
        else:
            st.caption(_t("output_scope_empty"))
    content = str(details.get("content") or "")
    output_type = str(details.get("output_type") or details.get("type") or "")
    if output_type == "summary":
        st.markdown(content)
    elif output_type == "quiz":
        try:
            quiz_obj = json.loads(content)
        except json.JSONDecodeError:
            quiz_obj = {}
        questions = quiz_obj.get("questions") if isinstance(quiz_obj, dict) else []
        st.markdown(f"**{quiz_obj.get('quiz_title') or _t('practice_test')}**")
        st.caption(_t("quiz_history_count", n=len(questions) if isinstance(questions, list) else 0))
        st.code(content or "-", language="json")
    else:
        st.code(content or "-", language="json" if output_type == "graph" else "markdown")

    file_name = f"course_output_{output_id}_{output_type or 'text'}.md"
    mime = "text/markdown"
    if output_type in {"graph", "quiz"}:
        file_name = f"course_output_{output_id}_{output_type}.json"
        mime = "application/json"
    if st.download_button(
        _t("output_download"),
        data=content.encode("utf-8"),
        file_name=file_name,
        mime=mime,
        key=f"{key_prefix}_output_download_{output_id}",
    ):
        st.session_state["last_export_time"] = _now_label()


def _get_changelog_preview(limit: int = 3) -> list[str]:
    changelog_path = Path(__file__).resolve().parents[1] / "CHANGELOG.md"
    if not changelog_path.exists():
        return []
    try:
        lines = changelog_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []

    in_latest_section = False
    bullets: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if in_latest_section:
                break
            in_latest_section = True
            continue
        if not in_latest_section:
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
    if bullets:
        return bullets[:limit]

    # fallback: first bullet lines in file
    all_bullets = [ln.strip()[2:].strip() for ln in lines if ln.strip().startswith("- ")]
    return all_bullets[:limit]


def _run_index_build(uploaded_files: list[Any], api_key: str) -> None:
    if not _current_collection():
        st.warning(_t("select_course_first"))
        return
    if not uploaded_files:
        st.warning(_t("rebuild_need_upload"))
        return
    if not api_key:
        st.warning(_t("enter_api_first"))
        return
    if _is_rebuild_locked():
        st.info("Index rebuild already in progress.")
        return

    st.session_state["index_rebuild_in_progress"] = True
    try:
        with st.spinner(_t("indexing")):
            for f in uploaded_files:
                f.seek(0)
            store = _get_vector_store()
            store.clear_course()
            stats = store.index_uploaded_files(uploaded_files, api_key=api_key)
            st.session_state["study_index_stats"] = stats
            st.session_state["last_index_build_time"] = _now_label()
            st.session_state["last_studied_collection"] = _active_course_label()
            st.session_state["index_outdated"] = False
            st.success(
                _t(
                    "index_ready",
                    i=stats["indexed_files"],
                    s=stats["skipped_files"],
                    c=stats["chunks_added"],
                )
            )
    except Exception as e:
        st.error(f"Index build failed: {e!s}. Please rebuild.")
    finally:
        st.session_state["index_rebuild_in_progress"] = False


def _cached_uploaded_file_objects(course_id: str = "") -> list[Any]:
    active_course_id = course_id or _current_collection()
    cache_by_course = st.session_state.get("study_uploaded_files_cache_by_course") or {}
    cache = cache_by_course.get(active_course_id) or []
    out: list[Any] = []
    for item in cache:
        name = str(item.get("name") or "uploaded.pdf")
        data = item.get("data") or b""
        bio = BytesIO(data)
        bio.name = name  # type: ignore[attr-defined]
        out.append(bio)
    return out


def _artifact_label(artifact: dict[str, Any]) -> str:
    return f"{artifact.get('file_name', 'uploaded.pdf')} ({artifact.get('created_at', '')})"


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return int(value)
    text = str(value or "").strip()
    if not text:
        return None
    token = ""
    started = False
    for ch in text:
        if ch.isdigit() or (ch == "-" and not started):
            token += ch
            started = True
            continue
        if started:
            break
    if token in {"", "-"}:
        return None
    try:
        return int(token)
    except (TypeError, ValueError):
        return None


def _render_generation_page_switcher(current_page: str) -> None:
    pages = [
        ("summary", _t("summary_page")),
        ("graph", _t("graph_page")),
        ("outline", _t("outline_page")),
        ("quiz", _t("quiz_page")),
    ]
    cols = st.columns(len(pages))
    for i, (page_key, label) in enumerate(pages):
        if cols[i].button(label, key=f"switch_{current_page}_{page_key}", use_container_width=True, disabled=page_key == current_page):
            _request_nav(page_key)


def _render_scope_set_header(course_id: str, page_key: str) -> tuple[dict[str, Any] | None, list[int], bool]:
    ensure_default_scope_set(course_id)
    scope_sets = list_scope_sets(course_id)
    if not scope_sets:
        st.warning(_t("scope_set_missing"))
        return None, [], False

    option_ids = [int(s["id"]) for s in scope_sets if s.get("id") is not None]
    if not option_ids:
        st.warning(_t("scope_set_missing"))
        return None, [], False
    labels = {int(s["id"]): f"{s.get('name', 'Scope')} ({s.get('file_count', 0)})" for s in scope_sets if s.get("id") is not None}
    scope_map = {int(s["id"]): s for s in scope_sets if s.get("id") is not None}

    legacy_single_key = f"active_scope_set_id_{course_id}"
    legacy_single_raw = st.session_state.pop(legacy_single_key, None)
    legacy_single_id = _coerce_int(legacy_single_raw)

    selected_key = f"active_scope_set_ids_{course_id}"
    raw_selected = st.session_state.get(selected_key, [])
    selected_scope_ids: list[int] = []
    if isinstance(raw_selected, list):
        for v in raw_selected:
            parsed = _coerce_int(v)
            if parsed is not None and parsed in option_ids and parsed not in selected_scope_ids:
                selected_scope_ids.append(parsed)
    else:
        parsed = _coerce_int(raw_selected)
        if parsed is not None and parsed in option_ids:
            selected_scope_ids.append(parsed)
    if legacy_single_id is not None and legacy_single_id in option_ids and legacy_single_id not in selected_scope_ids:
        selected_scope_ids.append(legacy_single_id)
    if not selected_scope_ids:
        selected_scope_ids = [option_ids[0]]
    st.session_state[selected_key] = selected_scope_ids

    with st.container(border=True):
        st.markdown(f"**{_t('scope_set_selector')}**")
        col_count = min(4, max(1, len(option_ids)))
        checkbox_cols = st.columns(col_count, gap="small")
        new_selected_scope_ids: list[int] = []
        for idx, sid in enumerate(option_ids):
            check_key = f"scope_set_checkbox_{course_id}_{sid}"
            if check_key not in st.session_state:
                st.session_state[check_key] = sid in selected_scope_ids
            checked = checkbox_cols[idx % col_count].checkbox(labels.get(sid, str(sid)), key=check_key)
            if checked:
                new_selected_scope_ids.append(sid)
        selected_scope_ids = [sid for sid in option_ids if sid in new_selected_scope_ids]
        st.session_state[selected_key] = selected_scope_ids

    if not selected_scope_ids:
        st.warning(_t("scope_set_pick_at_least_one"))
        return None, [], False

    selected_scope_names = [str(scope_map.get(sid, {}).get("name", sid)) for sid in selected_scope_ids]
    st.caption(
        f"{_t('scope_set_selected_sets_count', n=len(selected_scope_ids))} | "
        f"{_t('scope_set_current')}: {', '.join(selected_scope_names)}"
    )

    artifacts = list_artifacts(course_id)
    artifact_options = [int(a["id"]) for a in artifacts if a.get("id") is not None]
    artifact_map = {int(a["id"]): a for a in artifacts if a.get("id") is not None}
    primary_scope_set = get_scope_set(int(selected_scope_ids[0])) if selected_scope_ids else None
    selected_ids_set = set()
    for sid in selected_scope_ids:
        selected_ids_set.update(int(x) for x in resolve_scope_artifact_ids(course_id, sid) if int(x) in artifact_options)
    selected_ids = sorted(selected_ids_set)
    scope_ready = len(selected_ids) > 0

    with st.container(border=True):
        title_col, meta_col, create_col = st.columns([4, 2, 2])
        title_col.markdown(f"**{_t('scope_set_edit_files')}**")
        meta_col.caption(_t("scope_selected_count", n=len(selected_ids)))

        create_open_key = f"scope_set_create_open_{page_key}"
        if create_open_key not in st.session_state:
            st.session_state[create_open_key] = False
        if create_col.button(
            _t("scope_set_create"),
            key=f"scope_set_create_open_btn_{page_key}",
            use_container_width=True,
            type="secondary",
        ):
            st.session_state[create_open_key] = True
            st.rerun()

        if st.session_state.get(create_open_key):
            with st.container(border=True):
                st.text_input(_t("scope_set_name"), key=f"scope_set_new_name_{page_key}")
                create_confirm_col, create_cancel_col = st.columns(2)
                if create_confirm_col.button(
                    _t("scope_set_create"),
                    key=f"scope_set_create_confirm_btn_{page_key}",
                    use_container_width=True,
                    type="secondary",
                ):
                    try:
                        new_id = create_scope_set(course_id, str(st.session_state.get(f"scope_set_new_name_{page_key}") or ""))
                        next_selected = [sid for sid in selected_scope_ids if sid in option_ids]
                        next_selected.append(int(new_id))
                        st.session_state[selected_key] = sorted(set(next_selected))
                        st.session_state[f"scope_set_checkbox_{course_id}_{int(new_id)}"] = True
                        st.session_state[create_open_key] = False
                        st.session_state.pop(f"scope_set_new_name_{page_key}", None)
                        st.success(_t("scope_set_create_success"))
                        st.rerun()
                    except WorkspaceValidationError as e:
                        st.error(str(e))
                if create_cancel_col.button(
                    _t("scope_set_delete_cancel_btn"),
                    key=f"scope_set_create_cancel_btn_{page_key}",
                    use_container_width=True,
                    type="secondary",
                ):
                    st.session_state[create_open_key] = False
                    st.session_state.pop(f"scope_set_new_name_{page_key}", None)
                    st.rerun()

        selected_entries = [(sid, scope_map.get(sid) or {}) for sid in selected_scope_ids]

        def _render_one_scope_editor(sid: int, scope_set: dict[str, Any]) -> None:
            is_default = int(scope_set.get("is_default", 0)) == 1
            scope_name = str(scope_set.get("name") or sid)
            current_ids = [int(x) for x in resolve_scope_artifact_ids(course_id, sid) if int(x) in artifact_options]
            if is_default:
                st.caption(f"{_t('scope_set_rename_disabled_default')} {_t('scope_set_all_materials_hint')}")
                return

            rename_key = f"scope_set_rename_name_{course_id}_{sid}"
            if rename_key not in st.session_state:
                st.session_state[rename_key] = scope_name
            rename_col, rename_btn_col, delete_btn_col = st.columns([6, 2, 2])
            rename_col.text_input(_t("scope_set_rename_label"), key=rename_key)
            if rename_btn_col.button(
                _t("scope_set_rename_action"),
                key=f"scope_set_rename_btn_{course_id}_{sid}",
                use_container_width=True,
                type="secondary",
            ):
                try:
                    rename_scope_set(int(sid), str(st.session_state.get(rename_key) or ""))
                    st.success(_t("scope_set_rename_success"))
                    st.rerun()
                except WorkspaceValidationError as e:
                    st.error(str(e))

            delete_pending_key = f"scope_set_delete_pending_{course_id}_{sid}"
            if delete_btn_col.button(
                _t("scope_set_delete_action"),
                key=f"scope_set_delete_start_btn_{course_id}_{sid}",
                use_container_width=True,
                type="secondary",
            ):
                st.session_state[delete_pending_key] = True

            if st.session_state.get(delete_pending_key):
                st.warning(_t("scope_set_delete_confirm", name=scope_name))
                confirm_col, cancel_col = st.columns(2)
                if confirm_col.button(_t("scope_set_delete_confirm_btn"), key=f"scope_set_delete_confirm_btn_{course_id}_{sid}", use_container_width=True):
                    try:
                        delete_scope_set(int(sid))
                        selected_now = [int(x) for x in (st.session_state.get(selected_key) or []) if _coerce_int(x) is not None]
                        st.session_state[selected_key] = [x for x in selected_now if int(x) != int(sid)]
                        st.session_state.pop(f"scope_set_checkbox_{course_id}_{sid}", None)
                        st.session_state.pop(rename_key, None)
                        st.session_state.pop(f"scope_set_editor_items_{course_id}_{sid}", None)
                        st.session_state.pop(delete_pending_key, None)
                        st.success(_t("scope_set_delete_success"))
                        st.rerun()
                    except WorkspaceValidationError as e:
                        st.error(str(e))
                if cancel_col.button(_t("scope_set_delete_cancel_btn"), key=f"scope_set_delete_cancel_btn_{course_id}_{sid}", use_container_width=True):
                    st.session_state.pop(delete_pending_key, None)
                    st.rerun()

            editor_key = f"scope_set_editor_items_{course_id}_{sid}"
            if editor_key not in st.session_state:
                st.session_state[editor_key] = current_ids.copy()
            edited_ids = st.multiselect(
                _t("scope_set_edit_files"),
                options=artifact_options,
                key=editor_key,
                format_func=lambda aid: _artifact_label(artifact_map.get(int(aid), {"file_name": f"#{aid}"})),
            )
            normalized_edited = [int(x) for x in edited_ids if int(x) in artifact_options]
            if sorted(normalized_edited) != sorted(current_ids):
                try:
                    replace_scope_set_items(int(sid), normalized_edited)
                    st.caption(_t("scope_set_saved"))
                    st.rerun()
                except WorkspaceValidationError as e:
                    st.error(str(e))

        if len(selected_entries) == 1:
            sid, scope_set = selected_entries[0]
            scope_name = str(scope_set.get("name") or sid)
            current_ids = [int(x) for x in resolve_scope_artifact_ids(course_id, sid) if int(x) in artifact_options]
            st.caption(f"{scope_name} ({len(current_ids)})")
            _render_one_scope_editor(int(sid), scope_set)
        else:
            tabs = st.tabs([f"{str(s.get('name') or sid)} ({int(s.get('file_count') or 0)})" for sid, s in selected_entries])
            for idx, (sid, scope_set) in enumerate(selected_entries):
                with tabs[idx]:
                    _render_one_scope_editor(int(sid), scope_set)

    if not scope_ready:
        st.warning(_t("select_at_least_one_file"))
    return primary_scope_set, selected_ids, scope_ready


def _apply_output_to_session(details: dict[str, Any]) -> None:
    output_type = str(details.get("output_type") or details.get("type") or "").strip().lower()
    content = str(details.get("content") or "")
    if output_type == "summary":
        st.session_state["study_summary"] = content
        return
    if output_type == "graph":
        try:
            graph_data = json.loads(content)
        except json.JSONDecodeError:
            graph_data = {}
        st.session_state["study_graph_data"] = graph_data if isinstance(graph_data, dict) else {}
        return
    if output_type in {"outline", "syllabus"}:
        try:
            outline = json.loads(content)
        except json.JSONDecodeError:
            outline = {}
        st.session_state["study_syllabus"] = outline if isinstance(outline, dict) else {}
        return
    if output_type == "quiz":
        try:
            quiz = json.loads(content)
        except json.JSONDecodeError:
            quiz = {}
        st.session_state["study_scope_quiz"] = quiz if isinstance(quiz, dict) else {}
        st.session_state["study_scope_quiz_scope_ids"] = [int(x) for x in (details.get("scope_artifact_ids") or [])]
        st.session_state["study_scope_quiz_output_id"] = int(details.get("id", 0) or 0)


def _render_generation_recent_jump(course_id: str, current_page: str) -> None:
    st.caption(_t("generate_recent_jump"))
    page_defs = [
        ("summary", "summary", _t("summary_page")),
        ("graph", "graph", _t("graph_page")),
        ("outline", "outline", _t("outline_page")),
        ("quiz", "quiz", _t("quiz_page")),
    ]
    cols = st.columns(4)
    for i, (target_page, out_type, label) in enumerate(page_defs):
        latest_rows = list_outputs(course_id, out_type)
        latest = latest_rows[0] if latest_rows else None
        button_text = _t("open_latest", name=label)
        button_key = f"latest_jump_{current_page}_{target_page}"
        if latest:
            out_id = int(latest.get("id", 0) or 0)
            created_at = str(latest.get("created_at") or "")
            if cols[i].button(button_text, key=button_key, use_container_width=True):
                details = get_output(out_id) or latest
                _apply_output_to_session(details)
                _request_nav(target_page)
            cols[i].caption(f"#{out_id} | {created_at}")
        else:
            cols[i].button(button_text, key=button_key, disabled=True, use_container_width=True)
            cols[i].caption(_t("no_recent_output"))


def _scope_text_from_artifacts(course_id: str, artifact_ids: list[int], max_chars: int = 60000) -> str:
    if not artifact_ids:
        return ""
    cache_key = f"scope_text_cache_{course_id}"
    cache = st.session_state.get(cache_key) or {}
    scope_key = ",".join(str(x) for x in sorted({int(v) for v in artifact_ids}))
    if scope_key in cache:
        return str(cache[scope_key])

    selected = list_artifacts_by_ids(course_id, artifact_ids)
    if not selected:
        return ""
    processor = PDFProcessor()
    parts: list[str] = []
    total = 0
    for artifact in selected:
        rel = str(artifact.get("file_path") or "").strip()
        if not rel:
            continue
        abs_path = PROJECT_ROOT / rel
        if not abs_path.exists():
            continue
        try:
            data = abs_path.read_bytes()
            pages = processor.extract_pages_from_bytes(data)
            text = "\n".join(str(p.get("text") or "") for p in pages).strip()
        except Exception:
            text = ""
        if not text:
            continue
        block = f"[File: {artifact.get('file_name', 'uploaded.pdf')}]\n{text}\n"
        remaining = max_chars - total
        if remaining <= 0:
            break
        parts.append(block[:remaining])
        total += min(len(block), remaining)
    joined = "\n\n".join(parts).strip()
    cache[scope_key] = joined
    st.session_state[cache_key] = cache
    return joined


def _render_scope_quiz_cards(quiz: dict[str, Any], api_key: str, quiz_key: str = "default") -> None:
    questions = quiz.get("questions") if isinstance(quiz, dict) else []
    if not isinstance(questions, list) or not questions:
        return
    st.markdown(f"### {quiz.get('quiz_title') or _t('practice_test')}")

    if "selected_option" not in st.session_state:
        st.session_state["selected_option"] = {}
    if "submitted" not in st.session_state:
        st.session_state["submitted"] = {}
    if "is_correct" not in st.session_state:
        st.session_state["is_correct"] = {}
    if "translation_on" not in st.session_state:
        st.session_state["translation_on"] = {}
    if "translation_cache" not in st.session_state:
        legacy_cache = st.session_state.get("quiz_translation_cache")
        st.session_state["translation_cache"] = legacy_cache if isinstance(legacy_cache, dict) else {}
    if "translation_model_calls_by_qid" not in st.session_state:
        st.session_state["translation_model_calls_by_qid"] = {}
    if "quiz_translation_model_calls" not in st.session_state:
        st.session_state["quiz_translation_model_calls"] = 0

    selected_option: dict[str, Any] = st.session_state["selected_option"]
    submitted: dict[str, Any] = st.session_state["submitted"]
    is_correct: dict[str, Any] = st.session_state["is_correct"]
    translation_on: dict[str, Any] = st.session_state["translation_on"]
    translation_cache: dict[str, Any] = st.session_state["translation_cache"]
    translation_calls_by_qid: dict[str, Any] = st.session_state["translation_model_calls_by_qid"]

    for idx, q in enumerate(questions, 1):
        if not isinstance(q, dict):
            continue
        qid = f"{quiz_key}:{q.get('id', idx)}"
        question = str(q.get("question") or "")
        options = q.get("options") if isinstance(q.get("options"), list) else []
        selected_option.setdefault(qid, None)
        submitted.setdefault(qid, False)
        is_correct.setdefault(qid, False)
        translation_on.setdefault(qid, False)

        border_color = "#111111"
        if bool(submitted.get(qid)):
            border_color = "#1f9d55" if bool(is_correct.get(qid)) else "#dc2626"
        st.markdown(
            (
                f"<div style='border:2px solid {border_color}; border-radius:8px; "
                f"padding:10px; margin:8px 0;'><strong>{idx}. {question}</strong></div>"
            ),
            unsafe_allow_html=True,
        )

        toggle_key = f"quiz_translation_toggle_{qid}"
        if toggle_key not in st.session_state:
            st.session_state[toggle_key] = bool(translation_on.get(qid, False))
        translate_on_value = st.toggle(_t("translate_question"), key=toggle_key)
        translation_on[qid] = bool(translate_on_value)
        if translation_on[qid]:
            if not api_key:
                st.warning(_t("enter_api"))
            elif qid not in translation_cache:
                translated = LLMProcessor().translate_question(question, [str(x) for x in options], api_key)
                translation_cache[qid] = translated
                st.session_state["quiz_translation_model_calls"] = int(
                    st.session_state.get("quiz_translation_model_calls", 0)
                ) + 1
                translation_calls_by_qid[qid] = int(translation_calls_by_qid.get(qid, 0)) + 1
            translated = translation_cache.get(qid)
            if isinstance(translated, dict) and translated.get("question_zh"):
                st.markdown(f"**{_t('translated_question')}** {translated.get('question_zh')}")
                translated_opts = translated.get("options_zh") if isinstance(translated.get("options_zh"), list) else []
                for op_idx, option in enumerate(translated_opts, 1):
                    st.markdown(f"{op_idx}. {option}")
        st.caption(f"qid={qid} translation_model_calls={int(translation_calls_by_qid.get(qid, 0))}")

        answer_key = f"quiz_answer_{qid}"
        option_values = [str(x) for x in options]
        current_selected = selected_option.get(qid)
        default_index = option_values.index(current_selected) if current_selected in option_values else None
        selected = st.radio(
            _t("choose"),
            options=option_values,
            key=answer_key,
            index=default_index,
            disabled=bool(submitted.get(qid)),
            label_visibility="collapsed",
        )
        if selected is not None and not bool(submitted.get(qid)):
            selected_option[qid] = selected

        submit_key = f"quiz_submit_{qid}"
        if st.button(_t("submit_question"), key=submit_key, disabled=bool(submitted.get(qid))):
            chosen = selected_option.get(qid) or st.session_state.get(answer_key)
            if not chosen:
                st.warning(_t("select_option_before_submit"))
            else:
                correct_answer = str(q.get("correct_answer") or "")
                selected_option[qid] = chosen
                submitted[qid] = True
                is_correct[qid] = str(chosen) == correct_answer
                st.rerun()

        if bool(submitted.get(qid)):
            chosen = str(selected_option.get(qid) or "-")
            correct_answer = str(q.get("correct_answer") or "-")
            if bool(is_correct.get(qid)):
                st.success(_t("quiz_correct"))
            else:
                st.error(_t("quiz_wrong"))
            st.caption(_t("quiz_result_line", chosen=chosen, correct=correct_answer))

            with st.expander(_t("view_answer_analysis"), expanded=False):
                answer_en = str(q.get("answer_en") or q.get("correct_answer") or "").strip()
                answer_zh = str(q.get("answer_zh") or answer_en).strip()
                explanation_en = str(q.get("explanation_en") or q.get("explanation") or "").strip()
                explanation_zh = str(q.get("explanation_zh") or explanation_en).strip()
                st.markdown(f"**{_t('answer_en')}** {answer_en or '-'}")
                st.markdown(f"**{_t('answer_zh')}** {answer_zh or '-'}")
                st.markdown(f"**{_t('explanation_en')}** {explanation_en or '-'}")
                st.markdown(f"**{_t('explanation_zh')}** {explanation_zh or '-'}")

    quiz_qids = [f"{quiz_key}:{q.get('id', idx)}" for idx, q in enumerate(questions, 1) if isinstance(q, dict)]
    total_count = len(quiz_qids)
    submitted_count = sum(1 for qid in quiz_qids if bool(submitted.get(qid)))
    correct_count = sum(1 for qid in quiz_qids if bool(submitted.get(qid)) and bool(is_correct.get(qid)))
    accuracy = (correct_count / submitted_count) if submitted_count > 0 else 0.0
    st.divider()
    st.markdown(f"### {_t('quiz_accuracy')}")
    st.caption(
        _t(
            "quiz_accuracy_line",
            correct=correct_count,
            submitted=submitted_count,
            total=total_count,
            pct=int(accuracy * 100),
        )
    )
    st.progress(accuracy)

    st.session_state["selected_option"] = selected_option
    st.session_state["submitted"] = submitted
    st.session_state["is_correct"] = is_correct
    st.session_state["translation_on"] = translation_on
    st.session_state["translation_cache"] = translation_cache
    st.session_state["translation_model_calls_by_qid"] = translation_calls_by_qid
    st.caption(_t("translation_call_count", n=int(st.session_state.get("quiz_translation_model_calls", 0))))


def _render_sidebar() -> None:
    _render_language_switcher()
    st.sidebar.markdown(f'<p class="sidebar-header">{SIDEBAR_HEADER}</p>', unsafe_allow_html=True)
    st.sidebar.caption(_t("sidebar_settings"))

    with st.sidebar.expander(_t("course_manage"), expanded=True):
        with st.form("create_course_form", clear_on_submit=True):
            st.text_input(_t("course_code"), key="course_code_input")
            st.text_input(_t("course_name"), key="course_name_input")
            create_submitted = st.form_submit_button(_t("course_create"))
        if create_submitted:
            try:
                created = create_course(
                    code=str(st.session_state.get("course_code_input") or ""),
                    name=str(st.session_state.get("course_name_input") or ""),
                )
                st.session_state["active_course_id"] = str(created.get("id") or "")
                _clear_study_derived_state()
                st.success(_t("course_create_success", code=created.get("code", "")))
                st.rerun()
            except WorkspaceValidationError as e:
                st.error(str(e))

    courses = list_courses()
    course_options = [str(c.get("id") or "") for c in courses if c.get("id")]
    if "active_course_id" not in st.session_state:
        st.session_state["active_course_id"] = course_options[0] if course_options else ""
    if st.session_state["active_course_id"] and st.session_state["active_course_id"] not in course_options:
        st.session_state["active_course_id"] = course_options[0] if course_options else ""
    if course_options:
        current_id = str(st.session_state.get("active_course_id") or course_options[0])
        current_idx = course_options.index(current_id) if current_id in course_options else 0
        labels = {
            str(c.get("id")): f"{c.get('code', '')} - {c.get('name', '')}"
            for c in courses
            if c.get("id")
        }
        selected_id = st.sidebar.selectbox(
            _t("course_selector"),
            options=course_options,
            index=current_idx,
            format_func=lambda cid: labels.get(cid, cid),
        )
        if selected_id != st.session_state.get("active_course_id"):
            st.session_state["active_course_id"] = selected_id
            _clear_study_derived_state()
            st.rerun()
    else:
        st.sidebar.info(_t("course_create_first"))
        st.session_state["active_course_id"] = ""

    nav_options = ["dashboard", "study", "outline", "graph", "quiz", "flashcards", "mistakes"]
    requested_page = str(st.session_state.pop("nav_page_request", "") or "")
    if requested_page in nav_options:
        st.session_state["nav_page_selector"] = requested_page
    if "nav_page_selector" not in st.session_state:
        st.session_state["nav_page_selector"] = "dashboard"
    elif st.session_state["nav_page_selector"] not in nav_options:
        st.session_state["nav_page_selector"] = "dashboard"
    current_page = str(st.session_state.get("nav_page_selector") or "dashboard")

    st.sidebar.markdown(f"**{_t('nav')}**")
    nav_entries = [
        ("dashboard", _t("dashboard")),
        ("study", _t("study_mode")),
        ("flashcards", _t("flashcards_nav")),
        ("mistakes", _t("mistakes_nav")),
    ]
    for target_page, label in nav_entries:
        is_active = current_page == target_page or (
            target_page == "study" and current_page in {"outline", "graph", "quiz"}
        )
        if st.sidebar.button(
            label,
            key=f"nav_btn_{target_page}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            if current_page != target_page:
                _request_nav(target_page)
    st.sidebar.text_input(
        _t("api_key"),
        type="password",
        key="api_key",
        placeholder=_t("api_placeholder"),
        help=_t("api_help"),
    )

    stats = st.session_state.get("study_index_stats") or {}
    if stats:
        st.sidebar.caption(f"**{_t('index_status')}**")
        st.sidebar.markdown(
            f"{_t('indexed_files')}: **{stats.get('indexed_files', 0)}**  \n"
            f"{_t('skipped_files')}: **{stats.get('skipped_files', 0)}**  \n"
            f"{_t('chunks')}: **{stats.get('chunks_added', 0)}**"
        )

    st.sidebar.divider()
    report_md = _build_revision_report_md()
    if report_md:
        if st.sidebar.download_button(
            _t("download_md"),
            data=report_md,
            file_name="UNSW_Revision_Notes.md",
            mime="text/markdown",
            key="download_report_md",
        ):
            st.session_state["last_export_time"] = _now_label()
        report_pdf = _build_report_pdf_bytes(report_md)
        if report_pdf is not None:
            if st.sidebar.download_button(
                _t("download_pdf"),
                data=report_pdf,
                file_name="UNSW_Revision_Notes.pdf",
                mime="application/pdf",
                key="download_report_pdf",
            ):
                st.session_state["last_export_time"] = _now_label()
        else:
            st.sidebar.caption(_t("reportlab_hint"))

    session_md = _build_session_md()
    if session_md:
        if st.sidebar.download_button(
            _t("save_session"),
            data=session_md,
            file_name="unsw_session.md",
            mime="text/markdown",
            key="export_session",
        ):
            st.session_state["last_export_time"] = _now_label()

    st.sidebar.divider()
    with st.sidebar.expander(_t("about"), expanded=False):
        st.caption(f"{_t('app_version')}: {APP_VERSION}")
        st.caption(f"{_t('schema_version')}: {st.session_state.get('schema_version', 0)}")
        st.caption(f"{_t('active_course')}: {_active_course_label()}")
        st.caption(f"DB: {DB_PATH}")

    st.sidebar.divider()
    st.sidebar.markdown(f'<div class="quote-box">{random.choice(MOTIVATIONAL_QUOTES)}</div>', unsafe_allow_html=True)


def _render_dashboard() -> None:
    st.subheader(_t("dashboard"))
    st.caption(_t("hero_tagline"))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(_t("app_version"), APP_VERSION)
    c2.metric(_t("schema_version"), str(st.session_state.get("schema_version", 0)))
    c3.metric(_t("selected_lang"), _lang())
    c4.metric(_t("active_course"), _active_course_label())

    action1, action2, action3 = st.columns(3)
    if action1.button(_t("go_study"), use_container_width=True):
        _request_nav("study")
    if action2.button(_t("build_index"), use_container_width=True):
        api_key = (st.session_state.get("api_key") or "").strip()
        _run_index_build(_cached_uploaded_file_objects(), api_key)
    if action3.button(_t("start_exam"), use_container_width=True):
        _request_nav("quiz")

    st.divider()
    qa1, qa2 = st.columns(2)
    with qa1.container(border=True):
        st.markdown(f"#### {_t('continue_study')}")
        st.caption(_t("continue_study_desc"))
        recent = st.session_state.get("study_recent_file_names") or []
        if recent:
            st.caption(", ".join(recent[:5]))
        if st.button(_t("continue_study"), key="btn_continue_study", use_container_width=True):
            _request_nav("study")
    with qa2.container(border=True):
        st.markdown(f"#### {_t('start_mock_exam')}")
        st.caption(_t("start_mock_exam_desc"))
        st.caption(f"{_t('active_course')}: {_active_course_label()}")
        if st.button(_t("start_mock_exam"), key="btn_start_mock", use_container_width=True):
            _request_nav("quiz")

    st.divider()
    st.markdown(f"#### {_t('updates')}")
    updates = _get_changelog_preview(limit=3)
    if updates:
        for item in updates:
            st.markdown(f"- {item}")
    else:
        st.caption(_t("not_available"))
    toggle_key = "show_full_changelog"
    if st.button(_t("hide_full_changelog") if st.session_state.get(toggle_key) else _t("open_full_changelog")):
        st.session_state[toggle_key] = not st.session_state.get(toggle_key, False)
    if st.session_state.get(toggle_key):
        changelog_path = Path(__file__).resolve().parents[1] / "CHANGELOG.md"
        if changelog_path.exists():
            st.code(changelog_path.read_text(encoding="utf-8"), language="markdown")

    st.divider()
    st.markdown(f"#### {_t('activity')}")
    idx_time = st.session_state.get("last_index_build_time") or _t("not_available")
    exp_time = st.session_state.get("last_export_time") or _t("not_available")
    last_collection = st.session_state.get("last_studied_collection") or _t("not_available")
    st.markdown(f"- {_t('last_index_time')}: **{idx_time}**")
    st.markdown(f"- {_t('last_export_time')}: **{exp_time}**")
    st.markdown(f"- {_t('last_studied_collection')}: **{last_collection}**")
    if idx_time == _t("not_available") and exp_time == _t("not_available"):
        st.caption(_t("empty_activity_tip_1"))
        st.caption(_t("empty_activity_tip_2"))

    st.divider()
    st.markdown(f"#### {_t('need_help')}")
    if st.button(_t("help_index"), key="btn_help_index"):
        _request_nav("study")
    st.markdown(f"- {_t('help_migration')}: `backups/`")
    st.markdown(f"- {_t('help_self_check')}")
    st.caption(_t("help_self_check_cmd"))


def _render_study_mode() -> None:
    st.subheader(_t("study_mode"))
    course_id = _current_collection()
    if not course_id:
        st.warning(_t("select_course_first"))
        return

    st.caption(f"{_t('active_course')}: {_active_course_label()}")
    tab_upload, tab_generate, tab_outputs, tab_qa = st.tabs(
        [_t("study_tab_upload"), _t("study_tab_generate"), _t("study_tab_outputs"), _t("qa")]
    )

    with tab_upload:
        st.markdown(f'<p class="unsw-section-title">{_t("upload_materials")}</p>', unsafe_allow_html=True)
        uploaded_files = st.file_uploader(
            _t("upload_pdf"),
            type=["pdf"],
            accept_multiple_files=True,
            key="study_upload",
            help=_t("upload_help"),
        )
        if uploaded_files:
            signature = (course_id,) + _uploaded_files_signature(uploaded_files)
            if signature != st.session_state.get("study_upload_signature"):
                _clear_generated_content_state()
                st.session_state["study_upload_signature"] = signature
                processor = PDFProcessor()
                extracted_parts: list[str] = []
                cache_for_course: list[dict[str, Any]] = []
                for file in uploaded_files:
                    file.seek(0)
                    data = file.read()
                    if not data:
                        continue
                    cache_for_course.append({"name": getattr(file, "name", "uploaded.pdf"), "data": data})
                    try:
                        save_artifact(course_id, getattr(file, "name", "uploaded.pdf"), data)
                    except WorkspaceValidationError as e:
                        st.warning(str(e))
                    file.seek(0)
                    try:
                        extracted_parts.append(processor.extract_text(file))
                    except ValueError as e:
                        st.warning(f"{getattr(file, 'name', 'file')}: {e!s}")

                cache_by_course = st.session_state.get("study_uploaded_files_cache_by_course") or {}
                cache_by_course[course_id] = cache_for_course
                st.session_state["study_uploaded_files_cache_by_course"] = cache_by_course
                st.session_state["study_recent_file_names"] = [getattr(f, "name", "uploaded.pdf") for f in uploaded_files]
                st.session_state["study_extracted_text"] = "\n\n".join(extracted_parts)
                st.session_state["last_uploaded_study_name"] = ", ".join(getattr(f, "name", "") for f in uploaded_files)
                st.session_state["last_studied_collection"] = _active_course_label()

        text = st.session_state.get("study_extracted_text", "")
        cached_files = _cached_uploaded_file_objects(course_id)
        if text:
            st.success(_t("loaded_files", n=len(cached_files), c=len(text)))
            with st.expander(_t("preview")):
                st.text(text[:700])
        artifacts = list_artifacts(course_id)
        if artifacts:
            st.caption(_t("artifacts_saved", n=len(artifacts)))
            for item in artifacts[:8]:
                st.markdown(f"- `{item.get('file_name', 'uploaded.pdf')}` ({item.get('created_at', '')})")

        api_key = (st.session_state.get("api_key") or "").strip()
        if st.button(_t("build_index"), key="btn_index_build"):
            _run_index_build(cached_files, api_key)

        status = _get_index_status()
        if not status.get("compatible", True):
            details = "; ".join(status.get("reasons") or [])
            st.warning(_t("index_outdated"))
            if details:
                st.caption(_t("index_details", details=details))
            if st.button(_t("rebuild_now"), key="btn_rebuild_outdated"):
                _run_index_build(cached_files, api_key)

    with tab_generate:
        st.markdown(f'<p class="unsw-section-title">{_t("generate")}</p>', unsafe_allow_html=True)
        st.caption(_t("generate_jump_hint"))
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button(_t("outline_page"), key="go_outline_page", use_container_width=True):
                _request_nav("outline")
        with col2:
            if st.button(_t("graph_page"), key="go_graph_page", use_container_width=True):
                _request_nav("graph")
        with col3:
            if st.button(_t("quiz_page"), key="go_quiz_page", use_container_width=True):
                _request_nav("quiz")

    with tab_outputs:
        _render_outputs_tab(course_id)

    with tab_qa:
        st.subheader(_t("qa"))
        if "study_chat_history" not in st.session_state:
            st.session_state["study_chat_history"] = []

        for msg in st.session_state["study_chat_history"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        api_key = (st.session_state.get("api_key") or "").strip()
        if prompt := st.chat_input(_t("chat_placeholder")):
            if not api_key:
                st.warning(_t("enter_api"))
            else:
                st.session_state["study_chat_history"].append({"role": "user", "content": prompt})
                with st.spinner(_t("answering")):
                    base = _build_chat_context_base()
                    retrieved = _rag_context(prompt, api_key, top_k=10)
                    if not retrieved:
                        retrieved = (st.session_state.get("study_extracted_text") or "")[:10000]
                    context = f"{base}\n\n[Retrieved Chunks]\n{retrieved}"
                    reply = LLMProcessor().chat_with_context(context, prompt, api_key)
                st.session_state["study_chat_history"].append({"role": "assistant", "content": reply})
                st.rerun()


def _render_summary_page() -> None:
    course_id = _current_collection()
    if not course_id:
        st.warning(_t("select_course_first"))
        return
    scope_set, scope_artifact_ids, scope_ready = _render_scope_set_header(course_id, "summary")
    header_col, action_col = st.columns([4, 1])
    header_col.subheader(_t("summary_page"))
    api_key = (st.session_state.get("api_key") or "").strip()
    if action_col.button(_t("gen_summary"), key="summary_generate_btn", disabled=not scope_ready, use_container_width=True):
        if not api_key:
            st.warning(_t("enter_api"))
        else:
            with st.spinner(_t("gen_summary_spinner")):
                context = _scope_text_from_artifacts(course_id, scope_artifact_ids)
                if not context.strip():
                    st.warning(_t("upload_or_index_first"))
                else:
                    summary = LLMProcessor().generate_summary(context, api_key)
                    st.session_state["study_summary"] = summary
                    _persist_output_record(
                        course_id,
                        "summary",
                        summary,
                        scope_artifact_ids,
                        scope_set_id=int(scope_set.get("id")) if scope_set else None,
                    )
    if st.session_state.get("study_summary"):
        st.markdown(st.session_state["study_summary"])


def _render_graph_page() -> None:
    st.subheader(_t("graph_page"))
    course_id = _current_collection()
    if not course_id:
        st.warning(_t("select_course_first"))
        return
    scope_set, scope_artifact_ids, scope_ready = _render_scope_set_header(course_id, "graph")
    api_key = (st.session_state.get("api_key") or "").strip()
    if st.button(_t("gen_graph"), key="graph_generate_btn", disabled=not scope_ready):
        if not api_key:
            st.warning(_t("enter_api"))
        else:
            with st.spinner(_t("gen_graph_spinner")):
                context = _scope_text_from_artifacts(course_id, scope_artifact_ids)
                if not context.strip():
                    st.warning(_t("upload_or_index_first"))
                else:
                    graph_data = GraphGenerator().generate_graph_data(context, api_key)
                    st.session_state["study_graph_data"] = graph_data
                    _persist_output_record(
                        course_id,
                        "graph",
                        graph_data,
                        scope_artifact_ids,
                        scope_set_id=int(scope_set.get("id")) if scope_set else None,
                    )
    graph_data = st.session_state.get("study_graph_data") or {}
    nodes_data = graph_data.get("nodes") if isinstance(graph_data, dict) else []
    links_data = graph_data.get("links") if isinstance(graph_data, dict) else []
    categories_data = graph_data.get("categories") if isinstance(graph_data, dict) else []
    if nodes_data or links_data:
        category_colors = ["#FFCC00", "#F5F5F5", "#9E9E9E"]
        categories_echarts = []
        for i, cat in enumerate((categories_data or [])[:3]):
            name = cat.get("name", ["Core Topic", "Key Concept", "Detail"][i])
            color = category_colors[i] if i < len(category_colors) else "#BDBDBD"
            categories_echarts.append({"name": name, "itemStyle": {"color": color}, "label": {"color": "#1a1a1a"}})
        option = {
            "backgroundColor": "#FFFFFF",
            "tooltip": {"show": True},
            "legend": {
                "show": True,
                "data": [c["name"] for c in categories_echarts],
                "textStyle": {"color": "#333"},
                "top": "top",
            },
            "series": [
                {
                    "type": "graph",
                    "layout": "force",
                    "symbolSize": 30,
                    "roam": True,
                    "label": {"show": True, "position": "right", "color": "#333"},
                    "edgeSymbol": ["circle", "arrow"],
                    "edgeSymbolSize": [4, 8],
                    "lineStyle": {"curveness": 0.3, "color": "source", "opacity": 0.6},
                    "emphasis": {"focus": "adjacency", "lineStyle": {"width": 3}},
                    "force": {"repulsion": 1000, "edgeLength": [50, 200], "gravity": 0.08},
                    "data": nodes_data,
                    "links": links_data,
                    "categories": categories_echarts,
                }
            ],
        }
        st_echarts(options=option, height="550px")
    st.divider()
    _render_outputs_tab(course_id, fixed_output_type="graph", key_prefix=f"graph_outputs_{course_id}")


def _render_outline_page() -> None:
    st.subheader(_t("outline_page"))
    course_id = _current_collection()
    if not course_id:
        st.warning(_t("select_course_first"))
        return
    scope_set, scope_artifact_ids, scope_ready = _render_scope_set_header(course_id, "outline")
    api_key = (st.session_state.get("api_key") or "").strip()
    if st.button(_t("gen_syllabus"), key="outline_generate_btn", disabled=not scope_ready):
        if not api_key:
            st.warning(_t("enter_api"))
        else:
            with st.spinner(_t("gen_syllabus_spinner")):
                context = _scope_text_from_artifacts(course_id, scope_artifact_ids)
                if not context.strip():
                    st.warning(_t("upload_or_index_first"))
                else:
                    syllabus = LLMProcessor().generate_syllabus_checklist(context, api_key)
                    st.session_state["study_syllabus"] = syllabus
                    _persist_output_record(
                        course_id,
                        "outline",
                        syllabus,
                        scope_artifact_ids,
                        scope_set_id=int(scope_set.get("id")) if scope_set else None,
                    )
    syllabus = st.session_state.get("study_syllabus")
    if isinstance(syllabus, dict):
        st.markdown(f"**{syllabus.get('module_title') or _t('syllabus_default')}**")
        frameworks = syllabus.get("frameworks") if isinstance(syllabus.get("frameworks"), list) else []
        total_points = 0
        checked_points = 0
        module_key = str(syllabus.get("module_title") or _t("syllabus_default"))

        if frameworks:
            for fw_idx, fw in enumerate(frameworks):
                if not isinstance(fw, dict):
                    continue
                fw_name = str(fw.get("framework") or f"{_t('syllabus_framework')} {fw_idx + 1}").strip()
                objective = str(fw.get("objective") or "").strip()
                sections = fw.get("sections") if isinstance(fw.get("sections"), list) else []
                with st.expander(f"📚 {fw_name}", expanded=(fw_idx == 0)):
                    if objective:
                        st.caption(f"{_t('syllabus_objective')}: {objective}")
                    for sec_idx, sec in enumerate(sections):
                        if not isinstance(sec, dict):
                            continue
                        sec_name = str(sec.get("section") or f"{_t('syllabus_section')} {sec_idx + 1}").strip()
                        st.markdown(f"**{sec_name}**")
                        kps = sec.get("knowledge_points") if isinstance(sec.get("knowledge_points"), list) else []
                        for kp_idx, kp in enumerate(kps):
                            if isinstance(kp, dict):
                                point = str(kp.get("point") or "").strip()
                                detail = str(kp.get("detail") or "").strip()
                                priority = str(kp.get("priority") or "Medium")
                            else:
                                point = str(kp).strip()
                                detail = ""
                                priority = "Medium"
                            if not point:
                                continue
                            kp_token = f"{module_key}:{fw_name}:{sec_name}:{point}:{priority}:{kp_idx}"
                            kp_hash = abs(hash(kp_token))
                            cb_key = f"syllabus_kp_cb_{kp_hash}"
                            label = f"• {point} ({priority})"
                            is_checked = st.checkbox(label, key=cb_key)
                            total_points += 1
                            if is_checked:
                                checked_points += 1
                            if detail:
                                st.caption(f"{_t('syllabus_detail')}: {detail}")
                        st.divider()

        if total_points == 0:
            topics = syllabus.get("topics") if isinstance(syllabus.get("topics"), list) else []
            for i, t in enumerate(topics):
                if not isinstance(t, dict):
                    continue
                topic_name = str(t.get("topic", ""))
                if not topic_name:
                    continue
                priority = str(t.get("priority", "Medium"))
                topic_token = f"{module_key}:{topic_name}:{priority}:{i}"
                topic_hash = abs(hash(topic_token))
                cb_key = f"syllabus_cb_{topic_hash}"
                is_checked = st.checkbox(f"• {topic_name} ({priority})", key=cb_key)
                total_points += 1
                if is_checked:
                    checked_points += 1

        if total_points > 0:
            progress = checked_points / total_points
            st.progress(progress)
            st.caption(_t("progress", done=checked_points, all=total_points, pct=int(progress * 100)))


def _render_quiz_page() -> None:
    st.subheader(_t("quiz_page"))
    course_id = _current_collection()
    if not course_id:
        st.warning(_t("select_course_first"))
        return
    scope_set, scope_artifact_ids, scope_ready = _render_scope_set_header(course_id, "quiz")
    api_key = (st.session_state.get("api_key") or "").strip()
    count_map = {"10": 10, "20": 20, "All (max 50)": 50}
    quiz_count_label = st.selectbox(
        _t("quiz_count"),
        options=list(count_map.keys()),
        index=0,
        key=f"quiz_count_selector_{course_id}",
    )
    quiz_count = count_map.get(quiz_count_label, 10)
    if st.button(_t("generate_quiz_scope"), key="quiz_generate_btn", disabled=not scope_ready):
        if not api_key:
            st.warning(_t("enter_api"))
        else:
            with st.spinner(_t("generating_quiz")):
                context = _scope_text_from_artifacts(course_id, scope_artifact_ids)
                if not context.strip():
                    st.warning(_t("upload_or_index_first"))
                else:
                    quiz = QuizGenerator().generate_quiz(context, num_questions=quiz_count, api_key=api_key)
                    st.session_state["study_scope_quiz"] = quiz
                    st.session_state["study_scope_quiz_scope_ids"] = scope_artifact_ids
                    output_id = _persist_output_record(
                        course_id,
                        "quiz",
                        quiz,
                        scope_artifact_ids,
                        scope_set_id=int(scope_set.get("id")) if scope_set else None,
                    )
                    st.session_state["study_scope_quiz_output_id"] = output_id

    scope_quiz = st.session_state.get("study_scope_quiz")
    if isinstance(scope_quiz, dict) and scope_quiz.get("questions"):
        quiz_key = str(st.session_state.get("study_scope_quiz_output_id") or "latest_quiz")
        _render_scope_quiz_cards(scope_quiz, api_key, quiz_key=quiz_key)


def _current_user_id() -> str:
    return str(st.session_state.get("active_user_id") or "default")


def _reset_flashcard_reviewer_state(prefix: str) -> None:
    for key in [
        f"{prefix}_index",
        f"{prefix}_mcq_selected_option",
        f"{prefix}_mcq_submitted",
        f"{prefix}_mcq_is_correct",
        f"{prefix}_mcq_correct_answer",
        f"{prefix}_known_count",
        f"{prefix}_unknown_count",
        f"{prefix}_finished",
        f"{prefix}_translation_on",
        f"{prefix}_translation_cache",
    ]:
        st.session_state.pop(key, None)


def _fallback_scope_lines(context: str, count: int) -> list[str]:
    lines = [ln.strip() for ln in context.splitlines() if len(ln.strip()) > 20]
    if not lines:
        lines = [context.strip() or "Scope material"]
    out: list[str] = []
    for i in range(max(1, int(count))):
        seed = lines[i % len(lines)]
        out.append(seed[:180])
    return out


def _normalize_correct_answer(options: list[str], raw_answer: Any) -> str:
    if not options:
        return str(raw_answer or "")
    answer_text = str(raw_answer or "").strip()
    if answer_text in options:
        return answer_text
    parsed = _coerce_int(answer_text)
    if parsed is not None:
        if 0 <= parsed < len(options):
            return options[parsed]
        if 1 <= parsed <= len(options):
            return options[parsed - 1]
    letter = answer_text.upper()[:1]
    if letter in {"A", "B", "C", "D"}:
        idx = ord(letter) - ord("A")
        if 0 <= idx < len(options):
            return options[idx]
    return options[0]


def _build_source_refs(course_id: str, scope_artifact_ids: list[int]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for item in list_artifacts_by_ids(course_id, scope_artifact_ids)[:6]:
        refs.append(
            {
                "fileId": str(item.get("id") or ""),
                "chunkId": "",
                "quote": str(item.get("file_name") or ""),
                "page": None,
            }
        )
    return refs


def _generate_mixed_flashcards_payload(
    course_id: str,
    scope_artifact_ids: list[int],
    context: str,
    api_key: str,
    count: int,
) -> tuple[list[dict[str, Any]], int]:
    safe_count = max(1, min(int(count), 50))
    mcq_count = max(1, int(round(safe_count * 0.6))) if safe_count > 1 else 1
    mcq_count = min(mcq_count, safe_count)
    knowledge_count = max(0, safe_count - mcq_count)
    source_refs = _build_source_refs(course_id, scope_artifact_ids)
    fallback_lines = _fallback_scope_lines(context, safe_count)

    attempts = 0
    while attempts < 2:
        attempts += 1
        cards: list[dict[str, Any]] = []

        quiz = QuizGenerator().generate_quiz(context, num_questions=mcq_count, api_key=api_key)
        questions = quiz.get("questions") if isinstance(quiz, dict) else []
        if isinstance(questions, list):
            for idx, q in enumerate(questions[:mcq_count], 1):
                if not isinstance(q, dict):
                    continue
                options = [str(x) for x in (q.get("options") or []) if str(x).strip()]
                if not options:
                    options = ["A", "B", "C", "D"]
                cards.append(
                    {
                        "type": "mcq",
                        "front": {"stem": str(q.get("question") or fallback_lines[idx - 1]), "options": options},
                        "back": {
                            "answer": _normalize_correct_answer(options, q.get("correct_answer")),
                            "explanation": str(q.get("explanation") or q.get("explanation_en") or ""),
                        },
                        "sourceRefs": source_refs,
                    }
                )

        if len(cards) < mcq_count:
            missing = mcq_count - len(cards)
            offset = len(cards)
            for i in range(missing):
                stem = fallback_lines[(offset + i) % len(fallback_lines)]
                cards.append(
                    {
                        "type": "mcq",
                        "front": {"stem": f"{stem} (MCQ)", "options": ["A", "B", "C", "D"]},
                        "back": {"answer": "B", "explanation": "Based on selected scope material."},
                        "sourceRefs": source_refs,
                    }
                )

        try:
            knowledge_cards = LLMProcessor().generate_flashcards(context, api_key)[:knowledge_count]
        except ValueError:
            knowledge_cards = []
        for i, item in enumerate(knowledge_cards):
            if not isinstance(item, dict):
                continue
            cards.append(
                {
                    "type": "knowledge",
                    "front": {"stem": str(item.get("front") or fallback_lines[(mcq_count + i) % len(fallback_lines)])},
                    "back": {"explanation": str(item.get("back") or "")},
                    "sourceRefs": source_refs,
                }
            )

        if len(cards) < safe_count:
            missing = safe_count - len(cards)
            base_idx = len(cards)
            for i in range(missing):
                cards.append(
                    {
                        "type": "knowledge",
                        "front": {"stem": fallback_lines[(base_idx + i) % len(fallback_lines)]},
                        "back": {"explanation": "Key point synthesized from selected scope files."},
                        "sourceRefs": source_refs,
                    }
                )

        parsed = json.loads(json.dumps({"cards": cards[:safe_count]}, ensure_ascii=False))
        parsed_cards = parsed.get("cards") if isinstance(parsed, dict) else None
        if isinstance(parsed_cards, list):
            return [c for c in parsed_cards if isinstance(c, dict)], attempts
    return [], attempts


def _load_flashcard_translation(
    state_prefix: str,
    translation_id: str,
    stem: str,
    options: list[str],
    answer: str,
    explanation: str,
    translation_on_map: dict[str, Any],
    translation_cache_map: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    toggle_key = f"{state_prefix}_translate_toggle_{translation_id}"
    if toggle_key not in st.session_state:
        st.session_state[toggle_key] = bool(translation_on_map.get(translation_id, False))
    translate_on = bool(st.toggle(_t("flashcards_translate"), key=toggle_key))
    translation_on_map[translation_id] = translate_on
    if not translate_on:
        return False, {}
    api_key = (st.session_state.get("api_key") or "").strip()
    if not api_key:
        st.warning(_t("enter_api"))
        return True, {}
    if translation_id not in translation_cache_map:
        translated = LLMProcessor().translate_flashcard(
            stem=stem,
            options=options,
            answer=answer,
            explanation=explanation,
            api_key=api_key,
        )
        translation_cache_map[translation_id] = translated
    obj = translation_cache_map.get(translation_id)
    return True, obj if isinstance(obj, dict) else {}


def _render_mcq_flashcard(
    card: dict[str, Any],
    state_prefix: str,
    card_key: str,
    known_key: str,
    unknown_key: str,
    selected_map: dict[str, Any],
    submitted_map: dict[str, Any],
    is_correct_map: dict[str, Any],
    correct_answer_map: dict[str, Any],
    translation_on_map: dict[str, Any],
    translation_cache_map: dict[str, Any],
) -> bool:
    card_id = str(card.get("id") or "")
    front = card.get("front") if isinstance(card.get("front"), dict) else {}
    back = card.get("back") if isinstance(card.get("back"), dict) else {}
    stem = str(front.get("stem") or "-")
    options = [str(x) for x in (front.get("options") or []) if str(x).strip()]
    answer_text = str(back.get("answer") or "")
    explanation = str(back.get("explanation") or "")

    selected_map.setdefault(card_key, None)
    submitted_map.setdefault(card_key, False)
    is_correct_map.setdefault(card_key, False)
    correct_answer_map.setdefault(card_key, answer_text)

    submitted = bool(submitted_map.get(card_key))
    selected = str(selected_map.get(card_key) or "")
    if selected and selected not in options:
        selected = ""

    border_color = "#111111"
    if submitted:
        border_color = "#16a34a" if bool(is_correct_map.get(card_key)) else "#dc2626"
    st.markdown(
        f"<div style='border:2px solid {border_color}; border-radius:8px; padding:10px; margin:8px 0;'><strong>{stem}</strong></div>",
        unsafe_allow_html=True,
    )

    translate_on, translated_obj = _load_flashcard_translation(
        state_prefix=state_prefix,
        translation_id=card_key,
        stem=stem,
        options=options,
        answer=answer_text,
        explanation=explanation,
        translation_on_map=translation_on_map,
        translation_cache_map=translation_cache_map,
    )
    if translate_on:
        stem_zh = str(translated_obj.get("stem_zh") or "").strip()
        if stem_zh:
            st.markdown(f"**{_t('flashcards_translated_front')}** {stem_zh}")
        options_zh = translated_obj.get("options_zh") if isinstance(translated_obj.get("options_zh"), list) else []
        for oi, option_zh in enumerate(options_zh, 1):
            st.markdown(f"{oi}. {option_zh}")

    radio_key = f"{state_prefix}_mcq_choice_{card_key}"
    if radio_key not in st.session_state and selected:
        st.session_state[radio_key] = selected
    chosen = st.radio(
        _t("choose"),
        options=options,
        key=radio_key,
        disabled=submitted,
        label_visibility="collapsed",
    )
    if not submitted:
        selected_map[card_key] = chosen

    if not submitted:
        if st.button(_t("submit_question"), key=f"{state_prefix}_mcq_submit_{card_key}", use_container_width=True):
            selected_option = selected_map.get(card_key) or st.session_state.get(radio_key)
            if not selected_option:
                st.warning(_t("select_option_before_submit"))
            elif not card_id:
                st.warning(_t("not_available"))
            else:
                result = submit_flashcard_answer(_current_user_id(), card_id, selected_option)
                selected_map[card_key] = str(result.get("selectedOption") or selected_option)
                submitted_map[card_key] = True
                is_correct_map[card_key] = bool(result.get("isCorrect"))
                correct_answer_map[card_key] = str(result.get("correctAnswer") or answer_text)
                if bool(result.get("isCorrect")):
                    st.session_state[known_key] = int(st.session_state.get(known_key) or 0) + 1
                else:
                    st.session_state[unknown_key] = int(st.session_state.get(unknown_key) or 0) + 1
                st.rerun()
        st.caption(_t("flashcards_submit_required"))
        return False

    selected_value = str(selected_map.get(card_key) or "")
    correct_value = str(correct_answer_map.get(card_key) or answer_text)
    if bool(is_correct_map.get(card_key)):
        st.success(_t("quiz_correct"))
    else:
        st.error(_t("quiz_wrong"))
    st.caption(_t("quiz_result_line", chosen=selected_value or "-", correct=correct_value or "-"))

    for oi, option in enumerate(options, 1):
        opt_color = "#111111"
        bg = "#f8f8f8"
        if option == correct_value:
            opt_color = "#166534"
            bg = "#dcfce7"
        elif option == selected_value and selected_value != correct_value:
            opt_color = "#991b1b"
            bg = "#fee2e2"
        st.markdown(
            f"<div style='border:1px solid {opt_color}; border-radius:6px; padding:6px 8px; margin:4px 0; background:{bg};'>{oi}. {option}</div>",
            unsafe_allow_html=True,
        )

    st.markdown(f"**{_t('answer_label')}**: {correct_value or '-'}")
    if explanation:
        st.markdown(f"**{_t('explanation')}**: {explanation}")
    if translate_on:
        answer_zh = str(translated_obj.get("answer_zh") or "").strip()
        explanation_zh = str(translated_obj.get("explanation_zh") or "").strip()
        if answer_zh:
            st.markdown(f"**{_t('flashcards_translated_answer')}**: {answer_zh}")
        if explanation_zh:
            st.markdown(f"**{_t('flashcards_translated_explanation')}**: {explanation_zh}")
    return True


def _render_knowledge_flashcard(
    card: dict[str, Any],
    state_prefix: str,
    card_key: str,
    translation_on_map: dict[str, Any],
    translation_cache_map: dict[str, Any],
) -> str:
    front = card.get("front") if isinstance(card.get("front"), dict) else {}
    back = card.get("back") if isinstance(card.get("back"), dict) else {}
    stem = str(front.get("stem") or "-")
    answer_text = str(back.get("answer") or "")
    explanation = str(back.get("explanation") or "")

    st.markdown(f"### {stem}")
    if answer_text:
        st.markdown(f"**{_t('answer_label')}**: {answer_text}")
    if explanation:
        st.markdown(f"**{_t('explanation')}**: {explanation}")

    translate_on, translated_obj = _load_flashcard_translation(
        state_prefix=state_prefix,
        translation_id=card_key,
        stem=stem,
        options=[],
        answer=answer_text,
        explanation=explanation,
        translation_on_map=translation_on_map,
        translation_cache_map=translation_cache_map,
    )
    if translate_on:
        stem_zh = str(translated_obj.get("stem_zh") or "").strip()
        answer_zh = str(translated_obj.get("answer_zh") or "").strip()
        explanation_zh = str(translated_obj.get("explanation_zh") or "").strip()
        if stem_zh:
            st.markdown(f"**{_t('flashcards_translated_front')}** {stem_zh}")
        if answer_zh:
            st.markdown(f"**{_t('flashcards_translated_answer')}**: {answer_zh}")
        if explanation_zh:
            st.markdown(f"**{_t('flashcards_translated_explanation')}**: {explanation_zh}")

    known_col, unknown_col = st.columns(2)
    if known_col.button(_t("flashcards_known"), key=f"{state_prefix}_knowledge_known_{card_key}", use_container_width=True):
        return "known"
    if unknown_col.button(
        _t("flashcards_unknown"),
        key=f"{state_prefix}_knowledge_unknown_{card_key}",
        use_container_width=True,
    ):
        return "unknown"
    return ""


def _render_flashcard_reviewer(cards: list[dict[str, Any]], state_prefix: str) -> None:
    if not cards:
        st.info(_t("cards_empty"))
        return
    index_key = f"{state_prefix}_index"
    known_key = f"{state_prefix}_known_count"
    unknown_key = f"{state_prefix}_unknown_count"
    finished_key = f"{state_prefix}_finished"
    selected_key = f"{state_prefix}_mcq_selected_option"
    submitted_key = f"{state_prefix}_mcq_submitted"
    is_correct_key = f"{state_prefix}_mcq_is_correct"
    correct_answer_key = f"{state_prefix}_mcq_correct_answer"
    translation_on_key = f"{state_prefix}_translation_on"
    translation_cache_key = f"{state_prefix}_translation_cache"

    if index_key not in st.session_state:
        st.session_state[index_key] = 0
    if known_key not in st.session_state:
        st.session_state[known_key] = 0
    if unknown_key not in st.session_state:
        st.session_state[unknown_key] = 0
    if finished_key not in st.session_state:
        st.session_state[finished_key] = False
    if selected_key not in st.session_state:
        st.session_state[selected_key] = {}
    if submitted_key not in st.session_state:
        st.session_state[submitted_key] = {}
    if is_correct_key not in st.session_state:
        st.session_state[is_correct_key] = {}
    if correct_answer_key not in st.session_state:
        st.session_state[correct_answer_key] = {}
    if translation_on_key not in st.session_state:
        st.session_state[translation_on_key] = {}
    if translation_cache_key not in st.session_state:
        st.session_state[translation_cache_key] = {}

    idx = int(st.session_state.get(index_key) or 0)
    total = len(cards)
    if idx >= total:
        st.session_state[finished_key] = True

    if st.session_state.get(finished_key):
        known_count = int(st.session_state.get(known_key) or 0)
        unknown_count = int(st.session_state.get(unknown_key) or 0)
        answered = known_count + unknown_count
        acc = (known_count / answered) if answered > 0 else 0.0
        st.success(_t("flashcards_done"))
        st.caption(_t("flashcards_done_line", known=known_count, unknown=unknown_count, pct=int(acc * 100)))
        return

    idx = max(0, min(idx, total - 1))
    card = cards[idx]
    card_id = str(card.get("id") or "")
    card_type = str(card.get("type") or "knowledge").strip().lower()
    card_key = str(card_id or f"{state_prefix}_{idx}")

    selected_map = st.session_state[selected_key] if isinstance(st.session_state[selected_key], dict) else {}
    submitted_map = st.session_state[submitted_key] if isinstance(st.session_state[submitted_key], dict) else {}
    is_correct_map = st.session_state[is_correct_key] if isinstance(st.session_state[is_correct_key], dict) else {}
    correct_answer_map = st.session_state[correct_answer_key] if isinstance(st.session_state[correct_answer_key], dict) else {}
    translation_on_map = (
        st.session_state[translation_on_key] if isinstance(st.session_state[translation_on_key], dict) else {}
    )
    translation_cache_map = (
        st.session_state[translation_cache_key] if isinstance(st.session_state[translation_cache_key], dict) else {}
    )

    st.caption(_t("review_progress", current=idx + 1, total=total))
    st.progress((idx + 1) / total)

    can_next = True
    knowledge_action = ""
    if card_type == "mcq":
        can_next = _render_mcq_flashcard(
            card=card,
            state_prefix=state_prefix,
            card_key=card_key,
            known_key=known_key,
            unknown_key=unknown_key,
            selected_map=selected_map,
            submitted_map=submitted_map,
            is_correct_map=is_correct_map,
            correct_answer_map=correct_answer_map,
            translation_on_map=translation_on_map,
            translation_cache_map=translation_cache_map,
        )
    else:
        knowledge_action = _render_knowledge_flashcard(
            card=card,
            state_prefix=state_prefix,
            card_key=card_key,
            translation_on_map=translation_on_map,
            translation_cache_map=translation_cache_map,
        )

    if knowledge_action in {"known", "unknown"}:
        if knowledge_action == "known":
            st.session_state[known_key] = int(st.session_state.get(known_key) or 0) + 1
        else:
            if card_id:
                review_flashcard(_current_user_id(), card_id, "unknown")
            st.session_state[unknown_key] = int(st.session_state.get(unknown_key) or 0) + 1
        if idx + 1 >= total:
            st.session_state[finished_key] = True
        else:
            st.session_state[index_key] = idx + 1
        st.rerun()

    if st.button(_t("review_next"), key=f"{state_prefix}_next_{card_key}", disabled=not can_next, use_container_width=True):
        if idx + 1 >= total:
            st.session_state[finished_key] = True
        else:
            st.session_state[index_key] = idx + 1
        st.rerun()

    st.session_state[selected_key] = selected_map
    st.session_state[submitted_key] = submitted_map
    st.session_state[is_correct_key] = is_correct_map
    st.session_state[correct_answer_key] = correct_answer_map
    st.session_state[translation_on_key] = translation_on_map
    st.session_state[translation_cache_key] = translation_cache_map


def _mistake_rows_to_cards(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        card_type = str(row.get("cardType") or "knowledge").strip().lower()
        front = row.get("front") if isinstance(row.get("front"), dict) else {}
        back = row.get("back") if isinstance(row.get("back"), dict) else {}
        source_refs = row.get("sourceRefs") if isinstance(row.get("sourceRefs"), list) else []
        cards.append(
            {
                "id": str(row.get("flashcardId") or ""),
                "type": card_type if card_type in {"mcq", "knowledge"} else "knowledge",
                "front": {
                    "stem": str(front.get("stem") or front.get("question") or "-"),
                    "options": [str(x) for x in (front.get("options") or [])] if isinstance(front.get("options"), list) else [],
                },
                "back": {
                    "answer": back.get("answer"),
                    "explanation": str(back.get("explanation") or ""),
                },
                "sourceRefs": source_refs,
            }
        )
    return cards


def _render_flashcards_page() -> None:
    st.subheader(_t("flashcards_nav"))
    course_id = _current_collection()
    if not course_id:
        st.warning(_t("select_course_first"))
        return
    st.caption(f"{_t('active_course')}: {_active_course_label()}")

    artifacts = list_artifacts(course_id)
    scope_artifact_ids = [int(a["id"]) for a in artifacts if a.get("id") is not None]
    scope_ready = len(scope_artifact_ids) > 0
    st.caption(_t("flashcards_scope_default", n=len(scope_artifact_ids)))
    api_key = (st.session_state.get("api_key") or "").strip()
    deck_count = 10
    if st.button(_t("flashcards_generate"), disabled=not scope_ready, use_container_width=True):
        if not api_key:
            st.warning(_t("enter_api"))
        else:
            context = _scope_text_from_artifacts(course_id, scope_artifact_ids)
            if not context.strip():
                st.warning(_t("upload_or_index_first"))
            else:
                with st.spinner(_t("extracting_flashcards")):
                    cards_payload, _attempts = _generate_mixed_flashcards_payload(
                        course_id=course_id,
                        scope_artifact_ids=scope_artifact_ids,
                        context=context,
                        api_key=api_key,
                        count=int(deck_count),
                    )
                    deck_id = str(uuid4())
                    saved_cards = save_generated_flashcards(
                        user_id=_current_user_id(),
                        course_id=course_id,
                        deck_id=deck_id,
                        cards=cards_payload,
                        scope={"chapterIds": [], "fileIds": scope_artifact_ids},
                    )
                if not saved_cards:
                    st.error(_t("quiz_fail"))
                else:
                    st.session_state["flashcards_active_deck_id"] = deck_id
                    _reset_flashcard_reviewer_state("flashcards_main")
                    st.success(_t("deck_generate_done", n=len(saved_cards)))
                    st.rerun()

    active_deck_id = str(st.session_state.get("flashcards_active_deck_id") or "")
    if not active_deck_id:
        st.info(_t("cards_empty"))
        return
    cards = list_flashcards_by_deck(_current_user_id(), active_deck_id)
    if not cards:
        st.info(_t("cards_empty"))
        return
    _render_flashcard_reviewer(cards, "flashcards_main")


def _render_mistakes_page() -> None:
    st.subheader(_t("mistakes_nav"))
    course_id = _current_collection()
    if not course_id:
        st.warning(_t("select_course_first"))
        return
    st.caption(f"{_t('active_course')}: {_active_course_label()}")

    filter_col1, filter_col2 = st.columns(2)
    status_filter = filter_col1.selectbox(
        _t("mistakes_filter_status"),
        options=["all", "active", "mastered", "archived"],
        key=f"mistakes_status_filter_{course_id}",
    )
    type_filter = filter_col2.selectbox(
        _t("mistakes_filter_type"),
        options=["all", "mcq", "knowledge"],
        key=f"mistakes_type_filter_{course_id}",
    )
    query_status = "" if status_filter == "all" else status_filter
    query_type = "" if type_filter == "all" else type_filter

    rows = list_mistakes(_current_user_id(), status=query_status, card_type=query_type)
    st.caption(_t("mistakes_count", n=len(rows)))
    review_rows = list_mistakes_review(_current_user_id(), card_type=query_type)
    if st.button(_t("mistakes_review_start"), use_container_width=True, disabled=len(review_rows) == 0):
        st.session_state["mistakes_review_cards"] = _mistake_rows_to_cards(review_rows)
        _reset_flashcard_reviewer_state("mistakes_review")
        st.rerun()

    if not rows:
        st.info(_t("mistakes_empty"))
    for row in rows:
        row_id = int(row.get("id") or 0)
        front = row.get("front") if isinstance(row.get("front"), dict) else {}
        stem = str(front.get("stem") or front.get("question") or "-")
        with st.container(border=True):
            st.markdown(f"**#{row_id} | {row.get('cardType', '-')} | {row.get('status', '-')}**")
            st.markdown(stem)
            st.caption(
                f"{_t('mistakes_wrong_count')}: {int(row.get('wrongCount') or 0)} | "
                f"{_t('mistakes_last_wrong')}: {row.get('lastWrongAt') or '-'}"
            )
            c1, c2 = st.columns(2)
            if c1.button(_t("mistakes_mark_mastered"), key=f"mistake_master_{row_id}", use_container_width=True):
                mark_mistake_master(_current_user_id(), row_id)
                st.rerun()
            if c2.button(_t("mistakes_delete"), key=f"mistake_delete_{row_id}", use_container_width=True):
                archive_mistake(_current_user_id(), row_id)
                st.rerun()

    review_cards = st.session_state.get("mistakes_review_cards")
    if isinstance(review_cards, list) and review_cards:
        st.divider()
        st.markdown(f"### {_t('mistakes_review_title')}")
        _render_flashcard_reviewer([c for c in review_cards if isinstance(c, dict)], "mistakes_review")


def _render_exam_simulator() -> None:
    st.subheader(_t("exam_simulator"))
    if not _current_collection():
        st.warning(_t("select_course_first"))
        return
    st.caption(f"{_t('active_course')}: {_active_course_label()}")

    status = _get_index_status()
    if not status.get("compatible", True):
        details = "; ".join(status.get("reasons") or [])
        st.warning(_t("index_outdated"))
        if details:
            st.caption(_t("index_details", details=details))
    if "exam_quiz" not in st.session_state:
        st.session_state["exam_quiz"] = None
    if "exam_submitted" not in st.session_state:
        st.session_state["exam_submitted"] = False
    if "exam_user_answers" not in st.session_state:
        st.session_state["exam_user_answers"] = {}

    text = str(st.session_state.get("study_extracted_text") or "")
    has_index = False
    try:
        has_index = _get_vector_store().has_indexed_content()
    except Exception:
        has_index = False
    if not text.strip() and not has_index:
        st.warning(_t("upload_first"))
        return

    num_questions = st.number_input(_t("num_questions"), min_value=1, max_value=15, value=5, key="exam_num_questions")
    if st.button(_t("generate_quiz"), key="exam_generate"):
        api_key = (st.session_state.get("api_key") or "").strip()
        if not api_key:
            st.warning(_t("enter_api"))
        else:
            with st.spinner(_t("generating_quiz")):
                quiz_context = _task_context(
                    f"Create {num_questions} single-choice exam questions covering broad key topics", api_key
                )
                quiz = QuizGenerator().generate_quiz(quiz_context, num_questions=num_questions, api_key=api_key)
                st.session_state["exam_quiz"] = quiz
                st.session_state["exam_submitted"] = False
                st.session_state["exam_user_answers"] = {}
            if not quiz.get("questions"):
                st.error(_t("quiz_fail"))
            else:
                st.success(_t("quiz_success", n=len(quiz["questions"])))

    quiz = st.session_state.get("exam_quiz")
    if not quiz or not quiz.get("questions"):
        return

    st.markdown(f"**{quiz.get('quiz_title') or _t('practice_test')}**")
    questions = quiz["questions"]
    with st.form("exam_form"):
        for q in questions:
            qid = q.get("id", 0)
            st.write(f"**{qid}. {q.get('question', '')}**")
            st.radio(_t("choose"), options=q.get("options") or [], key=f"exam_q_{qid}", label_visibility="collapsed")
        submitted = st.form_submit_button(_t("submit"))

    if submitted:
        st.session_state["exam_user_answers"] = {q.get("id", 0): st.session_state.get(f"exam_q_{q.get('id', 0)}") for q in questions}
        st.session_state["exam_submitted"] = True

    if st.session_state.get("exam_submitted"):
        st.divider()
        st.subheader(_t("results"))
        user_answers = st.session_state["exam_user_answers"]
        for q in questions:
            qid = q.get("id", 0)
            correct = q.get("correct_answer", "")
            chosen = user_answers.get(qid)
            if chosen == correct:
                st.success(_t("correct", qid=qid))
            else:
                st.error(_t("wrong", qid=qid, chosen=chosen or "N/A", correct=correct))
            expl = q.get("explanation", "").strip()
            if expl:
                with st.expander(_t("explanation")):
                    st.write(expl)


def main() -> None:
    st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout="wide")
    _ensure_migrations_once()
    _inject_unsw_css()
    _sync_nav_with_route_query()
    _render_sidebar()
    page = st.session_state.get("nav_page_selector", "dashboard")
    if page == "dashboard":
        st.markdown('<div class="unsw-header"><span class="unsw-logo">UNSW</span></div>', unsafe_allow_html=True)
        st.title(PAGE_TITLE)
        _render_dashboard()
    elif page == "study":
        _render_study_mode()
    elif page == "outline":
        _render_outline_page()
    elif page == "graph":
        _render_graph_page()
    elif page == "quiz":
        _render_quiz_page()
    elif page == "flashcards":
        _render_flashcards_page()
    elif page == "mistakes":
        _render_mistakes_page()
    else:
        _render_dashboard()


if __name__ == "__main__":
    main()
